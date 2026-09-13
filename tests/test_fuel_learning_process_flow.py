#!/usr/bin/env python3
"""Follow changed airflow ranges into retained trim and open-loop fuel.

Protected trim values and other engine/feedback states are explicit inputs.
Native classification, initialization, trim publication, target/pressure
guard and final composition execute opcodes. No learned value is attributed
to the driving log, and no calibration or firmware image is written.
"""
import _test_paths
from itertools import product
import unittest

from test_dbw_arbitration_process_flow import DBWArbitrationMachine
from test_primary_fueling_execution import TARGET_WRITES, FUEL_WRITES, bits
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT = _test_paths.ROOT
CLASS_WRITES = {(0xFFFFBCD3, 1), (0xFFFFBCFE, 1)}
TRIM_WRITES = {(0xFFFF0000+a, 1) for a in (0xBCD9, 0xBCDA)} | {
    (0xFFFF0000+a, 4) for a in (0xBCB8, 0xBCBC)}
INIT_WRITES = TRIM_WRITES | {(0xFFFFBCC0, 4), (0xFFFFBCC4, 4)} | {
    (0xFFFF0000+a, 1) for a in (0xBCF2, 0xBCF3, 0xBCF4, 0xBCF5)}
PAIR_WRITES = INIT_WRITES | CLASS_WRITES | {
    (0xFFFF0000+a, 4) for a in (0xBCDC, 0xBCE0, 0xBCE4, 0xBCE8, 0xBCC8)
} | {(0xFFFF0000+a, 2) for a in (0xBCEC, 0xBCEE, 0xBCCC)} | {
    (0xFFFF0000+a, 1) for a in (0xBCF0, 0xBCF1, 0xBCFF, 0xBCFC, 0xBCFD,
                               0xBCD4, 0xBCD5, 0xBCD6, 0xBCD7, 0xBCFA, 0xBCFB,
                               0xBCCE, 0xBCCF, 0xBCD0, 0xBCD1, 0xBCD8, 0xBCD2,
                               0xBD00, 0xBD01)} | {
    (0xFFFF0000+base+8*region+offset, size)
    for base in (0x81C0, 0x81E0) for region in range(4)
    for offset, size in ((0, 4), (4, 2), (6, 2))}


class FuelLearningMachine(DBWArbitrationMachine):
    LOOKUPS = DBWArbitrationMachine.LOOKUPS | {
        0x15192, 0x2458, 0x22454, 0x2684, 0x1487E, 0x46FE8,
        0x64FE4, 0x65024, 0x6504C, 0x216EA, 0x20D80, 0x20D0E, 0x20F9C,
        0x20E5E, 0x21024, 0x213CE, 0x21350, 0x215FC, 0x214EC,
        0x1ADD8, 0x13330, 0x2118, 0x20E0,
    }

    def __init__(self, image, trim_c=.125, trim_d=0):
        super().__init__(image)
        self.seed_composer()
        # Explicit owned trim workspace initialization, followed by native
        # protected-record publication and runtime trim initialization.
        for a in range(0xFFFFBCC8, 0xFFFFBD02):
            self.write(a, 0, 1)
        self.write(0xFFFFBCF1, 0, 1)
        self.write(0xFFFFB2BC, 0, 1)
        for a in (0xB43C, 0xB6DC, 0xCF94):
            self.put_float(0xFFFF0000+a, 0)
        for a in (0xB4F0, 0xB4F4, 0xB8F4, 0xB8F8, 0xB8DC, 0xB8E0,
                  0xB730, 0xB734):
            self.put_float(0xFFFF0000+a, 1)
        self.put_float(0xFFFFAD84, 13.5)
        self.put_float(0xFFFFB3B0, 85)
        for a in (0xB702, 0xB68A):
            self.write(0xFFFF0000+a, 3000, 2)
        for a in (0xB90D, 0xB90E, 0xB91D, 0xB91E, 0xCCBB, 0x81B0, 0xD26D,
                  0xB289, 0xB6B8, 0xB19C):
            self.write(0xFFFF0000+a, 0, 1)
        for base in (0xFFFF81C0, 0xFFFF81E0):
            for region, value in enumerate((0, 0, trim_c, trim_d)):
                self.put_retained(base+8*region, value)
        self.classify(100)
        self.execute(0x20998, INIT_WRITES)

    def put_retained(self, address, value):
        argument, fargument = self.original_r[4], self.original_fr[4]
        self.original_r[4] = address
        self.original_fr[4] = bits(value)
        self.execute(0x49530, {(address, 4), (address+4, 2), (address+6, 2)})
        self.original_r[4], self.original_fr[4] = argument, fargument

    def classify(self, airflow, stopped=False):
        self.put_float(0xFFFFB420, airflow)
        self.write(0xFFFFBCF1, int(stopped), 1)
        self.execute(0x216EA, CLASS_WRITES)
        return self.read(0xFFFFBCD3, 1), self.read(0xFFFFBCFE, 1)

    def publish(self):
        argument = self.original_r[4]
        for descriptor in (0x4B2EC, 0x4B314):
            self.original_r[4] = descriptor
            self.execute(0x21350, TRIM_WRITES)
        self.original_r[4] = argument
        return self.get_float(0xFFFFBCB8), self.get_float(0xFFFFBCBC)

    def publish_pair(self):
        self.execute(0x20B28, PAIR_WRITES)
        return self.get_float(0xFFFFBCB8), self.get_float(0xFFFFBCBC)

    def open_loop_fuel(self):
        # Supplied running state with MAP above the wrapper's baro-margin gate.
        self.put_float(0xFFFFABC4, 820)
        self.put_float(0xFFFFCFBC, 712)
        self.put_float(0xFFFFB438, 2)
        self.execute(self.read(0x11D78, 4), TARGET_WRITES)
        self.execute(0x1DD04, FUEL_WRITES)
        return self.read(0xFFFFBE38, 1), self.get_float(0xFFFFB7EC), self.get_float(0xFFFFB7F0)


class FuelLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in
                      ('master_patch/D2WD610H_master_patch.bin',
                       'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x20998, 0x21774), (0x2142C, 0x21454),
                         (0x4B2EC, 0x4B33C), (0x1DD04, 0x1E0C8),
                         (0x76160, 0x7616C), (0x76178, 0x7617C)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_region_selection_is_separate_from_learning_airflow_eligibility(self):
        for image in self.images:
            cpu = FuelLearningMachine(image)
            last = cpu.get_float(0x76174)
            for airflow in (0, 1.999, 2, 4.999, 5, 9.999, 10, 21.999, 22,
                            51.999, 52, 100, 499.9, 500, 501):
                region = 0 if airflow < 5 else 1 if airflow < 10 else 2 if airflow < last else 3
                self.assertEqual(cpu.classify(airflow), (region, int(2 <= airflow < 52)))
                self.assertEqual(cpu.classify(airflow, stopped=True), (0, 0))

    def test_range_c_trim_can_reach_open_loop_despite_500_boundary(self):
        for image in self.images:
            cpu = FuelLearningMachine(image, trim_c=.125, trim_d=0)
            reference = FuelLearningMachine(image, trim_c=0, trim_d=0)
            expected = .125 if cpu.get_float(0x76174) == 500 else 0
            self.assertEqual(cpu.classify(100)[1], 0)  # New learning disabled here.
            self.assertEqual(cpu.publish(), (expected, expected))
            flags, first, second = cpu.open_loop_fuel()
            base_flags, base_first, base_second = reference.open_loop_fuel()
            self.assertEqual(flags & 0x80, 0)
            self.assertEqual(base_flags & 0x80, 0)
            self.assertAlmostEqual(first/base_first, 1+expected, delta=.000001)
            self.assertAlmostEqual(second/base_second, 1+expected, delta=.000001)

    def test_full_pair_publisher_keeps_stored_trim_when_new_learning_is_ineligible(self):
        for image in self.images:
            cpu = FuelLearningMachine(image)
            expected = .125 if cpu.get_float(0x76174) == 500 else 0
            cpu.open_loop_fuel()
            self.assertEqual(cpu.publish_pair(), (expected, expected))
            self.assertEqual(cpu.read(0xFFFFBCFE, 1), 0)
            self.assertEqual(cpu.read(0xFFFFBCFD, 1), 0)
            self.assertEqual(cpu.read(0xFFFFBCD6, 1), 0)
            self.assertEqual(cpu.read(0xFFFFBCD7, 1), 0)

    def test_crossing_500_selects_existing_d_and_filters_the_applied_change(self):
        for image in self.images[1:]:
            cpu = FuelLearningMachine(image, trim_c=.125, trim_d=0)
            cpu.classify(500)
            self.assertAlmostEqual(cpu.publish_pair()[0], .125*.994, delta=.0000001)
            for _ in range(420):
                cpu.publish_pair()
            self.assertEqual(cpu.get_float(0xFFFFBCB8), 0)
            # Changing a ROM boundary does not erase a retained D record.
            cpu = FuelLearningMachine(image, trim_c=.08, trim_d=.08)
            cpu.classify(500)
            self.assertAlmostEqual(cpu.publish_pair()[0], .08, delta=.0000001)
            self.assertAlmostEqual(cpu.get_float(0xFFFF81D8), .08, delta=.0000001)

    def test_native_learning_update_survives_transition_to_open_loop(self):
        for image, sign in product(self.images, (-1, 1)):
            cpu = FuelLearningMachine(image, trim_c=0, trim_d=0)
            cpu.classify(30)
            # Explicit prior feedback-qualification boundary: counters and
            # bank-active flags are supplied, not a model of sensor learning.
            for a in (0xB90D, 0xB90E, 0xB91D):
                cpu.write(0xFFFF0000+a, 1, 1)
            for a in (0xBCF6, 0xBCF7, 0xBCF8):
                cpu.write(0xFFFF0000+a, 90, 1)
            for a in (0xB8DC, 0xB8E0):
                cpu.put_float(0xFFFF0000+a, 1+sign*.2)
            region = cpu.read(0xFFFFBCD3, 1)
            record = 0xFFFF81C0+8*region
            for n in range(1, 97):
                cpu.publish_pair()
                if n in (78, 79, 95, 96):
                    expected = 0 if n == 78 else sign*(.002 if n == 96 else .001)
                    self.assertAlmostEqual(cpu.get_float(record), expected, delta=.00000001)
            cpu.classify(100)
            cpu.publish_pair()
            self.assertEqual(cpu.read(0xFFFFBCD6, 1), 0)
            self.assertAlmostEqual(cpu.get_float(record), sign*.002, delta=.00000001)
            self.assertAlmostEqual(cpu.get_float(0xFFFFBCB8), sign*.002, delta=.00000001)
            flags, first, second = cpu.open_loop_fuel()
            baseline = FuelLearningMachine(image, trim_c=0, trim_d=0).open_loop_fuel()
            self.assertEqual(flags & 128, 0)
            self.assertAlmostEqual(first/baseline[1], 1+sign*.002, delta=.000001)
            self.assertAlmostEqual(second/baseline[2], 1+sign*.002, delta=.000001)


if __name__ == '__main__':
    unittest.main(verbosity=2)
