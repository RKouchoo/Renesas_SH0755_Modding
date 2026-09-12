#!/usr/bin/env python3
"""Execute the converter, native SD lookup and shared lean guard at the repair.

These are instruction-level regressions, not an engine simulation. All ROM
fixtures are built in memory; original BINs and captures remain untouched.
"""

import _test_paths  # Shared offline-test imports and repository root.
from itertools import product
from io import StringIO
import math
import struct
import unittest

import build_master_patch as master
import idle_recovery_candidate as historical_idle
from audit_map_intercept import MapConversionMachine
from audit_fpu_usage import NativeSDMachine
from test_wideband_fuel_guard_execution import GuardMachine, bits, number, safety, boost
import test_hook_execution as hook

sd = master.speed_density
IMAGE = None
MINIMUM_WORD = 0x429D3ADC
AIR_WRITES = {(address, 4) for address in hook.Machine.OUTPUTS}


def airflow(image, pressure, rpm=1500, iat=25, mode=1):
    cpu = NativeSDMachine(image, rpm, pressure, iat, mode)
    cpu.invoke(sd.WRAPPER_ADDR, AIR_WRITES)
    result = cpu.read(sd.FINAL_MASS_AIRFLOW_ADDR, 4)
    assert all(cpu.read(address, 4) == result for address, _ in AIR_WRITES)
    return number(result), bool(cpu.reads[sd.FAILSAFE_AIRFLOW_ADDR])


class MapBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.source, _ = historical_idle.build_candidate()
        cls.stock, cls.rebuilt, _, _ = master.build_image()
        cls.image = IMAGE if IMAGE is not None else master.DEFAULT_OUT.read_bytes()

    def test_canonical_rebuild_and_exact_change_scope(self):
        self.assertEqual(self.rebuilt, self.image)
        allowed = {i for address in (sd.MAP_MIN_ADDR, master.calibration.CHECKSUM_TABLE_ADDR + 8,
                                    master.calibration.BUILD_MARKER_ADDR)
                   for i in range(address, address + 4)}
        # The rolling image also includes the later lean-reset hysteresis
        # repair. Require its exact emitted wrapper before allowing that
        # independently tested change relative to this historical MAP fixture.
        guard = safety.build_lean_cut_wrapper()
        start = safety.LEAN_CUT_WRAPPER_ADDR
        self.assertEqual(self.image[start:start + len(guard)], guard)
        allowed.update(range(start, start + len(guard)))
        # Later AVLS repair restores the two misidentified oil scalars to stock.
        self.assertEqual(self.image[0x7D4B0:0x7D4B8], self.stock[0x7D4B0:0x7D4B8])
        allowed.update(range(0x7D4B0, 0x7D4B8))
        # The later injector/pump calibration repair has its own execution
        # suite. Pin its exact word before extending this historical scope.
        self.assertEqual(self.image[0x72D54:0x72D58], bytes.fromhex('4116109b'))
        allowed.update(range(0x72D54, 0x72D58))
        changed = {i for i, (a, b) in enumerate(zip(self.source, self.image)) if a != b}
        self.assertLessEqual(changed, allowed)
        self.assertEqual(len(self.image), 0x80000)
        stored, calculated, _ = master.calibration.checksum_value(self.image)
        self.assertEqual(stored, calculated)
        self.assertEqual(struct.unpack_from('>I', self.image, master.calibration.BUILD_MARKER_ADDR)[0],
                         0x26090804)
        # The user's separate dashpot experiment is explicitly excluded.
        for start, end in ((0x7A6AC, 0x7AD24), (0x79524, 0x797D8)):
            self.assertEqual(self.image[start:end], self.stock[start:end])

    def test_native_converter_exact_minimum_and_old_discontinuity(self):
        converter = MapConversionMachine(self.image)
        pressure = converter.convert(3932)
        self.assertEqual(converter.classify(), 0)
        self.assertEqual(bits(pressure), MINIMUM_WORD)
        self.assertEqual(converter.read(sd.MAP_MIN_ADDR, 4), MINIMUM_WORD)
        self.assertEqual(airflow(self.source, pressure), (500, True))
        value, fallback = airflow(self.image, pressure)
        self.assertFalse(fallback)
        self.assertAlmostEqual(value, 3.54985, places=5)
        values = [airflow(self.image, number(word)) for word in
                  (bits(100) - 1, bits(100), bits(100) + 1)]
        self.assertFalse(any(fallback for _, fallback in values))
        self.assertLess(max(v for v, _ in values) - min(v for v, _ in values), 2e-6)

    def test_all_accepted_adc_counts_below_first_ve_row_use_actual_pressure(self):
        converter = MapConversionMachine(self.image)
        edge_flow, _ = airflow(self.image, 150)
        previous, repaired, count = 0, 0, 0
        for raw in range(3932, 5851):
            pressure = converter.convert(raw)
            if pressure >= 150:
                break
            self.assertEqual(converter.classify(), 0)
            value, fallback = airflow(self.image, pressure)
            self.assertFalse(fallback, raw)
            self.assertGreater(value, previous, raw)
            # The native table helper already uses the first VE row below
            # its axis. The air-mass product must retain the actual pressure.
            self.assertAlmostEqual(value, edge_flow * pressure / 150, delta=3e-6)
            previous = value
            repaired += pressure < 100
            count += 1
        self.assertEqual((repaired, count), (575, 1918))

    def test_previous_valid_domain_is_bit_identical(self):
        for rpm, pressure, iat, mode in product(
                (1, 500, 800, 1500, 3200, 7500), (100, 150, 315, 760, 1600),
                (-50, 25, 150), (1, 3)):
            with self.subTest(rpm=rpm, pressure=pressure, iat=iat, mode=mode):
                self.assertEqual(airflow(self.image, pressure, rpm, iat, mode),
                                 airflow(self.source, pressure, rpm, iat, mode))

    def test_new_lower_boundary_rejects_bad_values_and_preserves_stopped_behavior(self):
        converter = MapConversionMachine(self.image)
        pressure = converter.convert(3931)
        self.assertEqual(converter.classify(), 2)
        for bad in (pressure, number(MINIMUM_WORD - 1), 0, -1,
                    math.nan, math.inf, -math.inf, 1601):
            self.assertEqual(airflow(self.image, bad), (500, True))
            self.assertEqual(airflow(self.image, bad, rpm=0), (0, False))

    def test_shared_lean_limit_releases_only_on_valid_pressure_and_keeps_other_cut(self):
        for pressure, valid in ((number(MINIMUM_WORD - 1), False),
                                (number(MINIMUM_WORD), True), (99, True),
                                (math.nan, False)):
            for rpm in (1300, 6800):
                cpu = GuardMachine(self.image)
                cpu.put_float(safety.MAP_PRESSURE, pressure)
                cpu.put_float(boost.RPM_ADDR, rpm)
                cpu.write(safety.LEAN_STATE_RAM, 3, 1)
                cpu.write(safety.LEAN_COUNTER_RAM, 7, 2)
                expected = (0, 0, rpm == 6800) if valid else (3, 7, True)
                self.assertEqual(cpu.cut_step(), expected)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(MapBoundaryTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  MAP lower boundary: {result.testsRun} execution/integrity groups passed')
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main(verbosity=2)
