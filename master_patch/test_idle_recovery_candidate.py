#!/usr/bin/env python3
"""Check the isolated VE candidate and its retained transient interaction."""
import unittest

import idle_recovery_candidate as candidate
from analyze_20260908_idle import ve_from_bin, hook
from test_transient_fuel_execution import TransientFuelMachine


class IdleRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline, cls.image, cls.manifest = candidate.build_candidate()

    def test_reproducible_and_only_ten_cells_plus_checksum_change(self):
        image, manifest = candidate.revise_image(self.baseline)
        self.assertEqual((image, manifest), (self.image, self.manifest))
        self.assertEqual(len(manifest['cells']), 10)
        checksum_address = candidate.master.calibration.CHECKSUM_TABLE_ADDR + 8
        allowed = set(range(checksum_address, checksum_address + 4))
        for cell in manifest['cells']:
            address = int(cell['address'], 16)
            allowed.update(range(address, address + 4))
            self.assertGreater(cell['new_ve'], cell['old_ve'])
        changed = {i for i, (a,b) in enumerate(zip(self.baseline, self.image)) if a != b}
        self.assertLessEqual(changed, allowed)
        self.assertEqual(len(self.image), 0x80000)
        self.assertEqual(candidate.master.calibration.checksum_value(self.image)[0:2],
                         (int(manifest['subaru_checksum'], 16),) * 2)
        self.assertEqual(candidate.master_1030(), self.baseline)

    def test_pressure_and_rpm_edges_preserve_baseline(self):
        for rpm in (0, 500, 734, 800, 1069, 1200, 1252, 1600, 2500, 3200):
            for pressure in (150, 250, 315, 450, 550, 650, 760, 1050, 1500):
                if rpm == 0 or rpm >= 1200 or pressure <= 150 or pressure >= 760:
                    self.assertEqual(ve_from_bin(self.image, rpm, pressure * .1333224),
                                     ve_from_bin(self.baseline, rpm, pressure * .1333224))

    def test_rising_pressure_never_reduces_modeled_air_mass(self):
        # For linear VE between pressure knots, air mass is proportional to
        # P*VE(P), whose derivative is linear. Check both segment endpoints,
        # not just increasing values at the knots (which can miss a reversal).
        for rpm in (0, 250, 500, 650, 734, 800, 1000, 1069, 1200):
            for a,b in zip(candidate.master.speed_density.MAP_AXIS,
                           candidate.master.speed_density.MAP_AXIS[1:]):
                va = ve_from_bin(self.image, rpm, a*.1333224)
                vb = ve_from_bin(self.image, rpm, b*.1333224)
                slope = (vb-va)/(b-a)
                self.assertGreaterEqual(min(va+a*slope, vb+b*slope), 0,
                                        f'Air-mass reversal at {rpm} RPM, {a}..{b} mmHg')

    def test_recovery_plateau_and_measured_steady_point(self):
        for pressure in (250, 275, 310, 335, 350):
            kpa = pressure * .1333224
            reference = ve_from_bin(self.baseline, 1200, kpa)
            for rpm in (500, 650, 734, 800, 1000, 1069, 1199):
                self.assertAlmostEqual(ve_from_bin(self.image, rpm, kpa), reference, places=7)
        old = ve_from_bin(self.baseline, 1069, 41.32)
        new = ve_from_bin(self.image, 1069, 41.32)
        # Conditional steady-state estimate, not a promise of measured AFR.
        self.assertAlmostEqual(16.61 * old / new, 14.848, delta=.01)

    def test_actual_sd_wrapper_keeps_air_mass_per_rev_at_fixed_pressure(self):
        previous = hook.IMAGE
        try:
            hook.IMAGE = self.image
            loads = [hook.Machine(rpm=rpm, map_mmhg=315, iat=29, mode=1).run() * 60 / rpm
                     for rpm in (500, 734, 800, 1069, 1200)]
            self.assertLess(max(loads) - min(loads), 1e-6)
        finally:
            hook.IMAGE = previous

    def test_ve_slope_alone_triggers_retained_negative_correction(self):
        # Prescribed fixed-MAP RPM decline: feed each table's modeled load
        # into B438. This isolates the calibration interaction. It does not
        # reproduce the stock upstream filter or predict an engine trajectory.
        reference = ve_from_bin(self.baseline, 1252, 42)
        outputs = []
        for image in (self.baseline, self.image):
            cpu = TransientFuelMachine(image, load=.75, rpm=1252)
            for i in range(61):
                rpm = 1252 - (1252-734) * i / 60
                load = .75 * ve_from_bin(image, rpm, 42) / reference
                correction = cpu.transient(load, rpm)
            outputs.append((load, correction, load * 3.266667 * (1+correction)))
        self.assertLess(outputs[0][1], -.2)
        self.assertGreater(outputs[1][1], -.02)
        self.assertGreater(outputs[1][2], outputs[0][2] * 1.5)

    def test_refuses_other_baselines(self):
        wrong = bytearray(self.baseline)
        wrong[0x70000] ^= 1
        with self.assertRaises(ValueError):
            candidate.revise_image(wrong)


if __name__ == '__main__':
    unittest.main()
