#!/usr/bin/env python3
"""Execute the retained rear-voltage controller and protected-offset learner.

Bank feedback and electrical samples are explicit boundaries. Both complete
slow-task workers execute native instructions; this does not model sensor
hardware, scheduler timing, or recover retained values from the drive log.
"""
import _test_paths
from itertools import product
import unittest

from test_wideband_feedback_process_flow import WidebandFeedbackMachine
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT, RAM = _test_paths.ROOT, 0xFFFF0000
FLOATS = {*range(0xBD04, 0xBD18, 4), *range(0xBD20, 0xBDC8, 4),
          0xBDD4, 0xBDD8, 0xBDE8, 0xBDEC}
BYTES = {0xBD1C, 0xBD1D, 0xBD1E, *range(0xBDCE, 0xBDD3),
         0xBDDC, 0xBDDD, 0xBDF4, 0xBDF5}
WORDS = {0xBD18, 0xBD1A, 0xBDC8, 0xBDCA, 0xBDCC, 0xBDDE, 0xBDE0,
         0xBDE2, 0xBDE4, 0xBDF0, 0xBDF2}
RECORD_WRITES = {(RAM+base+off, size) for base in (0x8200, 0x8208)
                 for off, size in ((0, 4), (4, 2), (6, 2))}
WRITES = {(RAM+a, 4) for a in FLOATS} | {(RAM+a, 1) for a in BYTES} | {
    (RAM+a, 2) for a in WORDS} | RECORD_WRITES


class LegacyO2Machine(WidebandFeedbackMachine):
    LOOKUPS = WidebandFeedbackMachine.LOOKUPS | {
        0x65100, 0x65114, 0x17210, 0x1722C, 0x46FF8, 0x46FFC,
        0x218F0, 0x219C6, 0x21AC0, 0x21B1C, 0x21A54, 0x21BF2,
        0x21C50, 0x21C7A, 0x21D5C, 0x21F0C, 0x22170, 0x22286,
    }

    def __init__(self, image, offset0=.125, offset1=-.125):
        super().__init__(image)
        for a in range(0xBD04, 0xBDF6):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xD26E, 0, 1)
        self.write(RAM | self.read(0x1724E, 2), 0, 1)
        for a, value in ((0xABCC, .45), (0xABD0, .55), (0xB424, 100)):
            self.put_float(RAM+a, value)
        self.put_retained(RAM+0x8200, offset0)
        self.put_retained(RAM+0x8208, offset1)
        self.execute(0x21774, WRITES)

    def slow_pair(self):
        self.execute(0x217B8, WRITES)
        self.execute(0x2212C, WRITES)
        return self.get_float(RAM+0xBD04), self.get_float(RAM+0xBD08)


class LegacyO2ProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x21774, 0x22454), (0x4B33C, 0x4B424),
                         (0x761AC, 0x76240), (0x75E70, 0x75E7E),
                         (0x17210, 0x17268), (0x65100, 0x65128),
                         (0x46FF8, 0x47000)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_installed_wb_clears_legacy_controller_and_holds_protected_offsets(self):
        for image, raw, speed in product(self.images, (0, 18000, 40000), (0, 25, 54)):
            cpu = LegacyO2Machine(image)
            cpu.put_float(RAM+0xB538, speed)
            cpu.sensor(raw)
            cpu.qualify()
            for a in (0xBD1C, 0xBD1D):
                cpu.write(RAM+a, 0x80, 1)
            cpu.write(RAM+0xBD18, 4000, 2)
            cpu.write(RAM+0xBD1A, 4000, 2)
            for _ in range(3):
                self.assertEqual(cpu.slow_pair(), (.125, -.125))
                for a in (0xBD1C, 0xBD1D):
                    self.assertEqual(cpu.read(RAM+a, 1) & 128, 0)
                for a in (0xBD18, 0xBD1A, 0xBDF0, 0xBDF2):
                    self.assertEqual(cpu.read(RAM+a, 2), 0)
                for a in (0xBDDC, 0xBDDD):
                    self.assertEqual(cpu.read(RAM+a, 1), 0)
                self.assertEqual(cpu.get_float(RAM+0x8200), .125)
                self.assertEqual(cpu.get_float(RAM+0x8208), -.125)

    def test_slow_airflow_accumulator_saturates_and_holds_while_cranking(self):
        for image in self.images:
            cpu = LegacyO2Machine(image)
            cpu.put_float(RAM+0xBD28, 76750)
            cpu.execute(0x21C50, {(RAM+0xBD28, 4)})
            self.assertEqual(cpu.get_float(RAM+0xBD28), 76800)
            cpu.put_float(RAM+0xBD28, 123)
            cpu.write(RAM+0xB748, 128, 1)
            cpu.execute(0x21C50, {(RAM+0xBD28, 4)})
            self.assertEqual(cpu.get_float(RAM+0xBD28), 123)
            cpu.write(RAM+0xB748, 0, 1)
            cpu.execute(0x21C50, {(RAM+0xBD28, 4)})
            self.assertEqual(cpu.get_float(RAM+0xBD28), 223)

    def test_retained_legacy_offsets_do_not_reenter_removed_fuel_adder(self):
        # The two complete slow workers still preserve/publish legacy offsets.
        # The patched primary feedback preparation deliberately ignores these
        # publications at 202CC/202D0; test their consumer as well as producer.
        for image in self.images:
            outputs = []
            for offsets in ((0, 0), (.5, -.5), (-.5, .5)):
                cpu = LegacyO2Machine(image, *offsets)
                cpu.sensor(18000)
                cpu.qualify()
                self.assertEqual(cpu.slow_pair(), offsets)
                for phase in range(24):
                    cpu.phase(phase)
                outputs.append(cpu.open_loop_fuel())
            self.assertEqual(outputs, [outputs[0]]*3)

    def test_speed_qualifiers_are_not_airflow_or_rpm_thresholds(self):
        for image in self.images:
            cpu = LegacyO2Machine(image)
            for speed, expected in ((10, 1), (20, 1), (30, 1), (31, 0), (20, 0), (10, 1)):
                cpu.put_float(RAM+0xB538, speed)
                cpu.execute(0x21AC0, {(RAM+0xBD14, 4), (RAM+0xBDD2, 1)})
                self.assertEqual(cpu.read(RAM+0xBDD2, 1), expected)
            cpu.put_float(RAM+0xB538, 255)
            for _ in range(32):
                cpu.execute(0x21B1C, WRITES)
            self.assertEqual(cpu.read(RAM+0xBD1E, 1) & 128, 0)
            cpu.execute(0x21B1C, WRITES)
            self.assertEqual(cpu.read(RAM+0xBD1E, 1) & 192, 192)
            cpu.put_float(RAM+0xB538, 253)
            cpu.execute(0x21B1C, WRITES)
            self.assertEqual(cpu.read(RAM+0xBD1E, 1) & 192, 0)
            self.assertEqual(cpu.get_float(RAM+0xBD10), 0)
            self.assertEqual(cpu.read(RAM+0xBDCC, 2), 0)

    def test_native_enabled_control_exercises_learning_then_disqualification_holds_records(self):
        # Deliberately supplied eligible banks/rear-ready status and hot/high
        # airflow states are a positive control, not the installed WB outcome.
        for image in self.images:
            cpu = LegacyO2Machine(image)
            for a in (0xB90D, 0xB90E, 0xB91D):
                cpu.write(RAM+a, 1, 1)
            cpu.write(RAM+0xB404, 0x30, 1)
            cpu.write(RAM+0xB688, 65535, 2)
            for a, value in ((0xB424, 350), (0xB3AC, 110),
                             (0xB910, -.1), (0xB914, -.1)):
                cpu.put_float(RAM+a, value)
            for a in (0xBD18, 0xBD1A):
                cpu.write(RAM+a, 3750, 2)
            for _ in range(150):
                cpu.slow_pair()
            saved = tuple(cpu.get_float(RAM+a) for a in (0x8200, 0x8208))
            self.assertGreater(saved[0], .125)
            self.assertLess(saved[1], -.125)
            self.assertTrue(all(-.5 <= v <= .5 for v in saved))
            for a in (0xBD1C, 0xBD1D):
                self.assertEqual(cpu.read(RAM+a, 1) & 128, 128)
            cpu.sensor(18000)
            cpu.qualify()
            self.assertEqual(cpu.slow_pair(), saved)
            self.assertEqual(tuple(cpu.get_float(RAM+a) for a in (0x8200, 0x8208)), saved)
            for a in (0xBD18, 0xBD1A, 0xBDF0, 0xBDF2):
                self.assertEqual(cpu.read(RAM+a, 2), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
