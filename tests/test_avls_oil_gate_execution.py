#!/usr/bin/env python3
"""Execute the native AVLS selector to separate oil, pedal and RPM gates.

40168 and its diagnostic/stationary getters execute actual ROM instructions;
405B2 executes the requested-to-committed copy. Lookup interpolation and three
unlogged qualifier returns are explicit fixtures. CD9C is supplied as selector
state 2. This does not emulate the selector's upstream initialization, bank
phase scheduling, hydraulic lift or the engine.
"""

import _test_paths
from io import StringIO
from pathlib import Path
import struct
import sys
import unittest

from test_idle_air_execution import IdleAirOutputMachine

ROOT = _test_paths.ROOT
IMAGE = None
OIL_LIMITS = (0x7D4B0, 0x7D4B4)
NATIVE_GETTERS = {0x650D4, 0x6521C, 0x65208, 0x148EE, 0x19C68, 0x19D88}
WRITES = {(0xFFFFCD84, 2), (0xFFFFCD87, 1), (0xFFFFCD8F, 1),
          (0xFFFFCD9E, 1), (0xFFFFCD94, 4), (0xFFFFCD98, 4)}


class AVLSMachine(IdleAirOutputMachine):
    def __init__(self, image, *, rpm=3400, speed=0, oil=50, pedal=12,
                 switch_b51c=0x80):
        super().__init__(image, rpm=rpm)
        for address in (0xFFFFCD8F, 0xFFFFCD9E, 0xFFFFB28C,
                        0xFFFFD26D, 0xFFFFD26E, 0xFFFFD270):
            self.write(address, 0, 1)
        self.write(0xFFFFCD84, 0, 2)
        self.write(0xFFFFCD86, 1, 1)
        self.write(0xFFFFCD87, 1, 1)
        self.write(0xFFFFCD9C, 2, 1)
        self.write(0xFFFFB51C, switch_b51c, 1)
        self.write(0xFFFFB51E, 0, 1)
        self.put_float(0xFFFFB538, speed)
        self.put_float(0xFFFFB46C, pedal)
        self.put_float(0xFFFFCF94, oil)
        self.qualifiers = {0x18D08: 0, 0x18CF4: 0, 0x3B430: 0}
        self.visited = set()

    def step(self, in_delay=False):
        self.visited.add(self.pc)
        super().step(in_delay)

    def call_lookup(self, target):
        if target in NATIVE_GETTERS:
            return_pc, self.pc = self.pr, target
            while self.pc != return_pc:
                self.step()
        elif target in self.qualifiers:
            result = self.qualifiers[target]
            self.poison_scratch()
            self.r[0] = result
        else:
            super().call_lookup(target)

    def table(self, target, descriptor, x, y):
        if descriptor not in (0x60F58, 0x60F64):
            return super().table(target, descriptor, x, y)
        assert target == 0x209C and self.read(descriptor + 2, 2) == 0
        count = self.read(descriptor, 2)
        return self.interpolate(self.array(self.read(descriptor + 4, 4), count),
                                self.array(self.read(descriptor + 8, 4), count), x)

    def select(self, rpm=None):
        if rpm is not None:
            self.put_float(0xFFFFB544, rpm)
        self.visited.clear()
        self.invoke(0x40168, WRITES)
        self.invoke(0x405B2, {(0xFFFFCD86, 1)})
        return self.read(0xFFFFCD86, 1)


def with_limits(image, a, b):
    changed = bytearray(image)
    for address, value in zip(OIL_LIMITS, (a, b)):
        struct.pack_into('>f', changed, address, value)
    return bytes(changed)


class AVLSOilGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        assert cls.image[0x40168:0x405CC] == stock[0x40168:0x405CC]

    def test_installed_oil_thresholds_are_stock(self):
        self.assertEqual(tuple(struct.unpack_from('>f', self.image, a)[0]
                               for a in OIL_LIMITS), (15.0, 15.0))

    def test_stationary_warm_engagement_and_release(self):
        cpu = AVLSMachine(self.image)
        self.assertEqual([cpu.select(rpm) for rpm in (2999, 3200, 3100, 2999)],
                         [1, 3, 3, 1])

    def test_old_110_degree_error_blocks_stationary_but_not_moving_entry(self):
        broken = with_limits(self.image, 110, 110)
        for image, expected_stationary in ((broken, 1), (self.image, 3)):
            stationary = AVLSMachine(image, oil=50)
            self.assertEqual(stationary.select(), expected_stationary)
            self.assertIn(0x403C4, stationary.visited)
            moving = AVLSMachine(image, speed=30, oil=50)
            self.assertEqual(moving.select(), 3)
            self.assertNotIn(0x403C4, moving.visited)

    def test_both_scalars_compare_oil_and_ignore_pedal_in_stationary_branch(self):
        # Distinct A/B temperatures detect selecting the wrong scalar or input.
        image = with_limits(self.image, 40, 60)
        for switch, threshold in ((0x80, 40), (0, 60)):
            for oil, expected in ((threshold - .1, 1), (threshold, 3)):
                for pedal in (0, 12, 100):
                    cpu = AVLSMachine(image, oil=oil, pedal=pedal, switch_b51c=switch)
                    self.assertEqual(cpu.select(), expected, (switch, oil, pedal))

    def test_cold_oil_and_native_fault_override_remain_effective(self):
        for oil, expected in ((14.9, 1), (15, 3), (50, 3)):
            self.assertEqual(AVLSMachine(self.image, oil=oil).select(), expected)
        cpu = AVLSMachine(self.image)
        cpu.write(0xFFFFD26E, 4, 1)  # Native 65208 forces low lift.
        self.assertEqual(cpu.select(), 1)
        self.assertNotIn(0x403C4, cpu.visited)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(AVLSOilGateTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    if len(sys.argv) > 1:
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
