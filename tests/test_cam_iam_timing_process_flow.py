#!/usr/bin/env python3
"""Trace the shared low-lift AVCS table into native final spark correction.

498B0, 496C8/49960 and 279CC execute image instructions. Table interpolation
is an explicit mathematical boundary; actual cam angles, IAM, eligibility
flags and scheduling calls are fixtures, not recovered vehicle observations.
"""

import _test_paths
from itertools import product
import struct
import unittest

from test_opening_timing_execution import OpeningTimingMachine
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT = _test_paths.ROOT
CORRECTION_WRITES = {(a, 4) for a in range(0xFFFFD0F8, 0xFFFFD108, 4)} | {
    (0xFFFFD108, 1)}
ONE_AXIS = {0x5FF24, 0x5FF38, 0x5FF4C, 0x5FF60}


class CamIAMMachine(OpeningTimingMachine):
    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        if op & 0xF00F == 0x6002:  # mov.l @Rm,Rn
            n, m = (op >> 8) & 15, (op >> 4) & 15
            self.r[n] = self.load(self.r[m], 4)
            self.pc += 2
            self.instructions += 1
        else:
            super().step(in_delay)

    def __init__(self, image, rpm=2800, load=2, cam=0, iam=1, mode=1):
        super().__init__(image, rpm=rpm, load=load, coolant=80,
                         actual_cams=(cam, cam))
        for address in (0xFFFFD0FC, 0xFFFFD100, 0xFFFFD104):
            self.put_float(address, 0)
        for address in (0xFFFFD108, 0xFFFFD26F, 0xFFFF8274, 0xFFFFB51A):
            self.write(address, 0, 1)
        self.write(0xFFFFCD86, mode, 1)
        self.write(0xFFFFB28C, image[0x737C9], 1)  # Native configuration initialization.
        self.put_float(0xFFFFB2F4, 10)  # Explicit native >6 eligibility input.
        self.put_float(0xFFFF851C, iam)

    def call_lookup(self, target):
        if target in (0x349DC, 0x19EC4, 0x651A6, 0x49960, 0x148EE):
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def table(self, target, descriptor, x, y):
        if descriptor in ONE_AXIS:
            assert target == 0x209C
            n, kind, axis, data, scale, bias = struct.unpack_from(
                '>HHIIff', self.image, descriptor)
            assert kind == 0x400
            return self.interpolate(self.array(axis, n),
                                    [self.read(data+i, 1)*scale+bias for i in range(n)], x)
        if descriptor == 0x60C34:
            assert target == 0x2150
            nx, ny, axis_x, axis_y, data, kind, scale, bias = struct.unpack_from(
                '>HHIIIIff', self.image, descriptor)
            assert kind == 0x08000000
            rows = [self.interpolate(self.array(axis_x, nx),
                    [self.read(data+2*(j*nx+i), 2)*scale+bias for i in range(nx)], x)
                    for j in range(ny)]
            return self.interpolate(self.array(axis_y, ny), rows, y)
        return super().table(target, descriptor, x, y)

    def correction(self):
        self.invoke(0x498B0, CORRECTION_WRITES)
        self.invoke(0x496C8, CORRECTION_WRITES)
        return self.get_float(0xFFFFD0F8)


class CamIAMFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        cls.images = {
            'main': (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes(),
            'v2': (ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes(),
        }
        cls.images['captured'] = before_pump_scaling(cls.images['v2'])
        for image in cls.images.values():
            for start, end in ((0x496C8, 0x49A04), (0x5FF24, 0x5FF74),
                               (0x60C34, 0x60C50), (0x78644, 0x786DC)):
                assert image[start:end] == stock[start:end], hex(start)

    def test_iam_one_zeroes_correction_through_cam_lift_and_rpm_states(self):
        for name, image in self.images.items():
            for rpm, cam, mode in product((2500, 2800, 3000, 3500), (-5, 0, 9, 18, 30), (1, 3)):
                cpu = CamIAMMachine(image, rpm=rpm, cam=cam, mode=mode)
                for _ in range(65):  # Includes both native 25/60-call counter periods.
                    self.assertEqual(cpu.correction(), 0, (name, rpm, cam, mode))

    def test_low_iam_positive_control_reaches_final_spark_and_recovers(self):
        for name, image in self.images.items():
            cpu = CamIAMMachine(image, iam=0)
            correction = cpu.correction()
            self.assertGreater(cpu.get_float(0xFFFFD0FC), 0, name)
            self.assertLess(correction, -1, name)
            cpu.put_float(0xFFFFC130, 20)
            for value in cpu.final():
                self.assertAlmostEqual(value, 20+correction, places=5)
            cpu.put_float(0xFFFF851C, 1)
            self.assertEqual(cpu.correction(), 0)
            self.assertEqual(cpu.final(), (20,)*6)

    def test_committed_high_lift_clears_cam_deficit_in_low_iam_fixture(self):
        for image in self.images.values():
            cpu = CamIAMMachine(image, iam=0)
            self.assertLess(cpu.correction(), 0)
            cpu.write(0xFFFFCD86, 3, 1)
            self.assertEqual(cpu.correction(), 0)
            self.assertEqual([cpu.get_float(a) for a in
                              (0xFFFFD0FC, 0xFFFFD100, 0xFFFFD104)], [0, 0, 0])

    def test_above_six_thousand_holds_old_state_until_producers_run_again(self):
        for image in self.images.values():
            cpu = CamIAMMachine(image, iam=0)
            previous = cpu.correction()
            self.assertLess(previous, 0)
            cpu.put_float(0xFFFF851C, 1)
            cpu.put_float(0xFFFFB544, 6000)
            self.assertEqual(cpu.correction(), previous)
            cpu.put_float(0xFFFFB544, 2800)
            self.assertEqual(cpu.correction(), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
