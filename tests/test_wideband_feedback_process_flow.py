#!/usr/bin/env python3
"""Execute external WB -> native status -> bank feedback -> composed fuel.

These fixtures expose the installed readiness mismatch; passing records that
counterexample. Engine/diagnostic states and crank-phase delivery are supplied.
All lookup/control helpers execute native opcodes. No physical sensor timing,
interrupt deadlines, ECU observations or firmware modifications are implied.
"""
import _test_paths
from itertools import product
import math
import unittest

from test_fuel_learning_process_flow import FuelLearningMachine
from test_primary_fueling_execution import bits
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT = _test_paths.ROOT
RAM = 0xFFFF0000
# Typed ownership from native descriptors, loops and direct publications.
FLOAT_WORK = set(range(0xB8D4, 0xB908, 4)) | {0xB910, 0xB914, 0xBB70} | {
    *range(0xB920, 0xBB60, 4), *range(0xBB74, 0xBC5C, 4),
    *range(0xBC6C, 0xBC94, 4)}
BYTE_WORK = {0xB90C, 0xB90D, 0xB90E, *range(0xB91A, 0xB920),
             *range(0xBB68, 0xBB6E), *range(0xBC9A, 0xBCA7),
             *range(0xBCAC, 0xBCB5), 0xD954, 0xD955}
WORK_WRITES = {(RAM+a, 4) for a in FLOAT_WORK} | {
    (RAM+a, 1) for a in BYTE_WORK} | {(RAM+0xBC94, 2)}
LAMBDA_WRITES = {(RAM+a, 4) for a in range(0xB4E8, 0xB508, 4)} | {
    (RAM+0xB517, 1)}
STATUS_WRITES = {(RAM+a, 1) for a in (0xB512, 0xB513, 0xB515, 0xB516)}
COEFFICIENTS = ((0xB9D0, 22), (0xBA28, 22))
ERROR_HISTORIES = ((0xBA90, 21), (0xBAE4, 21))
PULSE_HISTORIES = ((0xBB74, 29), (0xBBE8, 29))


class WidebandFeedbackMachine(FuelLearningMachine):
    INSTRUCTION_LIMIT = 30000
    LOOKUPS = FuelLearningMachine.LOOKUPS | {
        0x1903A, 0x1932C, 0x19358, 0x13330, 0x64FD0, 0x6500C, 0x1493E,
        0x46FE0, 0x46FE4, 0x1F1DC, 0x1F3AC, 0x1F380, 0x1F354, 0x1F2AE,
        0x204AC, 0x2046C, 0x20326, 0x202B8, 0x1FF3C, 0x200F8,
        0x1F89C, 0x1F8CA, 0x1F990, 0x1FA9A, 0x1FB16, 0x1FCD4, 0x1FE4A,
        0x1F722, 0x20872, 0x208A6, 0x20088, 0x6A128,
    }

    def __init__(self, image):
        super().__init__(image, trim_c=0, trim_d=0)
        # Explicit DMA-zero workspace boundary, then real stopped-state init.
        for a in range(0xB8D4, 0xBCB8):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xB52C, 128, 1)
        self.execute(0x1F1DC, WORK_WRITES)
        self.write(RAM+0xB52C, 0, 1)
        for a in (0xB512, 0xB513, 0xB515, 0xB516, 0xB517, 0xC778,
                  0xB28C, 0xB2BC, 0xCF08, 0xD954, 0xD955):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xB19C, 128, 1)
        for a in range(0xB4E8, 0xB508, 4):
            self.put_float(RAM+a, 1)
        for a, value in ((0xB8F4, 1), (0xB8F8, 1), (0xB420, 100),
                         (0xB2A0, 820), (0xB2C8, 60), (0xCFBC, 712),
                         (0xB3AC, 67), (0xB3B0, 67), (0xB898, 0),
                         (0xB894, 0)):
            self.put_float(RAM+a, value)
        self.write(RAM+0xB688, 3000, 2)
        self.write(RAM+0xBC9A, 255, 1)
        self.write(RAM+0xBC9B, 255, 1)

    def sensor(self, raw):
        self.update_wideband(raw)
        self.execute(0x18DAC, LAMBDA_WRITES)
        self.execute(0x18FDC, STATUS_WRITES)

    def qualify(self):
        self.execute(0x1EE0C, WORK_WRITES)
        return tuple(self.read(RAM+a, 1) for a in (0xB90D, 0xB90E))

    def phase(self, phase):
        self.write(RAM+0xB528, phase, 1)
        self.execute(0x1EE74, WORK_WRITES)
        return tuple(self.get_float(RAM+a) for a in (0xB8D4, 0xB8D8))

    def native_ready_control(self, readiness=20, inhibit=0):
        """Positive control of 1903A inputs; never modify the image/publisher.

        Supply native readiness and an independent clear fault qualifier to
        the stock worker, so the test distinguishes its meaning from the
        incompatible 50/0 convention of the installed external publisher.
        """
        original_r, original_fr = self.original_r.copy(), self.original_fr.copy()
        for descriptor in (0x4B0C4, 0x4B0CC):
            self.original_r[4], self.original_r[5] = descriptor, inhibit
            self.original_fr[4] = bits(readiness)
            self.original_fr[5] = bits(1)
            self.original_fr[6] = bits(1)
            self.execute(0x1903A, STATUS_WRITES)
        self.original_r, self.original_fr = original_r, original_fr


class WidebandFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x18DAC, 0x193B8), (0x1EE0C, 0x202CC),
                         (0x202CE, 0x202D0), (0x202D2, 0x20998),
                         (0x4B0C4, 0x4B0D4), (0x4B10C, 0x4B2CC),
                         (0x73B60, 0x73B80), (0x75E10, 0x75E1D),
                         (0x75E69, 0x75E6A), (0x6A128, 0x6A156)):
                assert image[a:b] == stock[a:b], hex(a)
            assert image[0x202CC:0x202CE] == bytes.fromhex('f48d')
            assert image[0x202D0:0x202D2] == bytes.fromhex('f48d')
            assert image[0x73E08:0x73E10] == bytes.fromhex('8000800080008000')

    def test_external_lambda_reaches_both_conditioned_banks_without_baro_distortion(self):
        for image, raw, baro in product(self.images, (7000, 18000, 40000, 58000),
                                        (550, 712, 760)):
            cpu = WidebandFeedbackMachine(image)
            cpu.put_float(RAM+0xCFBC, baro)
            cpu.sensor(raw)
            expected = (10+2*raw*5/65536)/14.64
            for a in (0xAE60, 0xAE64, 0xB4E8, 0xB4EC):
                self.assertAlmostEqual(cpu.get_float(RAM+a), expected, delta=.000001)
            self.assertEqual(cpu.get_float(RAM+0xAE70), 50)
            self.assertEqual(cpu.get_float(RAM+0xAE74), 50)
            self.assertAlmostEqual(cpu.get_float(RAM+0xB4F0), (1+expected)/2, delta=.000001)
            cpu.sensor(0)
            self.assertEqual(cpu.get_float(RAM+0xAE70), 0)
            self.assertEqual(cpu.get_float(RAM+0xAE60), 1)

    def test_installed_ready_50_clears_native_feedback_flags_even_with_prior_history(self):
        for image, raw, prior in product(self.images, (0, 7000, 18000, 40000, 58000, 65535),
                                         (0, 255)):
            cpu = WidebandFeedbackMachine(image)
            for a in (0xB512, 0xB513, 0xB515, 0xB516):
                cpu.write(RAM+a, prior, 1)
            cpu.sensor(raw)
            for a in (0xB512, 0xB513):
                self.assertEqual(cpu.read(RAM+a, 1) & 0xC0, 0)
            self.assertEqual(cpu.qualify(), (0, 0))
            # Other prerequisites can be true: this is specifically readiness.
            self.assertEqual(cpu.read(RAM+0xB91A, 1), 1)

    def test_crank_phase_selection_resets_only_the_selected_bank_and_consumes_its_event(self):
        for image in self.images:
            bank0 = set(image[0x75E12:0x75E15])
            bank1 = set(image[0x75E15:0x75E18])
            self.assertEqual((bank0, bank1), ({0, 8, 16}, {4, 12, 20}))
            for phase in range(24):
                cpu = WidebandFeedbackMachine(image)
                cpu.sensor(18000)
                cpu.qualify()
                cpu.put_float(RAM+0xB8D4, .875)
                cpu.put_float(RAM+0xB8D8, 1.125)
                for base, n in ERROR_HISTORIES:
                    for i in range(n):
                        cpu.put_float(RAM+base+4*i, .125)
                cpu.write(RAM+0xD954, 1, 1)
                cpu.write(RAM+0xD955, 1, 1)
                first, second = cpu.phase(phase)
                self.assertEqual(first, 1 if phase in bank0 else .875)
                self.assertEqual(second, 1 if phase in bank1 else 1.125)
                for bank, phases in enumerate((bank0, bank1)):
                    base, n = ERROR_HISTORIES[bank]
                    self.assertEqual(cpu.array(RAM+base, n),
                                     [0 if phase in phases else .125]*n)
                    self.assertEqual(cpu.read(RAM+0xD954+bank, 1), int(phase not in phases))
                self.assertEqual(cpu.entered.count(0x1FCD4), int(phase in bank0 | bank1))

    def test_native_readiness_positive_control_activates_controller_and_invalid_wb_revokes_it(self):
        for image in self.images:
            cpu = WidebandFeedbackMachine(image)
            cpu.sensor(40000)
            cpu.native_ready_control()
            self.assertEqual(cpu.qualify(), (1, 1))
            for _ in range(8):
                cpu.phase(0)
                first, second = cpu.phase(4)
                self.assertTrue(.75 <= first <= 1.25)
                self.assertEqual(first, second)
            self.assertNotEqual(first, 1)
            cpu.sensor(0)
            self.assertEqual(cpu.qualify(), (0, 0))
            # Qualification alone does not rewrite the last bank multiplier.
            self.assertEqual(cpu.get_float(RAM+0xB8D4), first)
            self.assertEqual(cpu.phase(0), (1, second))
            self.assertEqual(cpu.phase(4), (1, 1))

    def test_enriched_target_disables_feedback_then_phase_updates_remove_old_short_term_trim(self):
        for image in self.images:
            cpu = WidebandFeedbackMachine(image)
            baseline = WidebandFeedbackMachine(image)
            cpu.sensor(40000)
            cpu.native_ready_control()
            self.assertEqual(cpu.qualify(), (1, 1))
            cpu.put_float(RAM+0xB8D4, .875)
            cpu.put_float(RAM+0xB8D8, .875)
            flags, before, _ = cpu.open_loop_fuel()
            self.assertEqual(flags & 128, 0)
            self.assertGreater(cpu.get_float(RAM+0xBDF8), .01)
            self.assertEqual(cpu.qualify(), (0, 0))
            self.assertEqual(cpu.get_float(RAM+0xB8D4), .875)
            cpu.phase(0)
            cpu.phase(4)
            _, after, after2 = cpu.open_loop_fuel()
            _, neutral, neutral2 = baseline.open_loop_fuel()
            self.assertAlmostEqual(before/neutral, .875, delta=.000001)
            self.assertEqual((after, after2), (neutral, neutral2))

    def test_computed_history_and_coefficient_bounds_across_rpm_and_airflow(self):
        for image, rpm, airflow in product(self.images, (500, 2800, 3500, 8000), (2, 100, 500)):
            cpu = WidebandFeedbackMachine(image)
            cpu.put_float(RAM+0xB544, rpm)
            cpu.put_float(RAM+0xB420, airflow)
            cpu.sensor(26000)
            cpu.qualify()
            # Neighboring trim and patch state must not be overwritten.
            sentinels = ((0xBCB8, 4), (0xC85C, 2), (0xC860, 1), (0xD953, 1), (0xD956, 1))
            for a, size in sentinels:
                cpu.write(RAM+a, 0xA5, size)
            for phase in (0, 4, 8, 12, 16, 20):
                self.assertEqual(cpu.phase(phase), (1, 1))
                for base, n in COEFFICIENTS + ERROR_HISTORIES + PULSE_HISTORIES:
                    self.assertTrue(all(math.isfinite(x) for x in cpu.array(RAM+base, n)))
            for a, size in sentinels:
                self.assertEqual(cpu.read(RAM+a, size), 0xA5)


if __name__ == '__main__':
    unittest.main()
