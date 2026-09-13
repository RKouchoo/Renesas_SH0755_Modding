#!/usr/bin/env python3
"""Execute changed knock axes through native hysteresis and cell consumption.

No knock waveform or learned vehicle state is reconstructed. Stored grid
values, prior row/column and caller inputs are explicit fixtures. Instructions
in 3DAA6/3DB90 and both learning-range publishers execute from each image.
"""
import _test_paths
from itertools import product
import unittest

from test_cam_iam_timing_process_flow import CamIAMMachine
from test_primary_fueling_execution import bits
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT = _test_paths.ROOT
GRID = 0xFFFF831C
IAM = 0xFFFF851C
CELL_WRITES = {(0xFFFFCD0C+i, 1) for i in range(3)}


class KnockCellMachine(CamIAMMachine):
    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n = (op >> 8) & 15
        if op & 0xF0FF == 0x4008:  # SHLL2; does not change T.
            self.r[n] = (self.r[n] << 2) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x4000:  # SHLL; outgoing high bit becomes T.
            self.t = bool(self.r[n] & 0x80000000)
            self.r[n] = (self.r[n] << 1) & 0xFFFFFFFF
        elif op & 0xF00F == 0x000E:  # MOV.L @(R0,Rm),Rn.
            m = (op >> 4) & 15
            self.r[n] = self.load((self.r[0]+self.r[m]) & 0xFFFFFFFF, 4)
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def __init__(self, image, previous=0):
        super().__init__(image)
        for i in range(64):
            self.put_float(GRID+8*i, -i/16)
            self.write(GRID+8*i+4, 0xA55A5AA5)
        self.put_float(IAM, 1)
        self.put_float(0xFFFFCD30, 5)
        self.put_float(0xFFFFCCFC, 0)
        for address in (0xFFFFCD0C, 0xFFFFCD0D):
            self.write(address, previous, 1)
        self.write(0xFFFFCD0E, previous*9, 1)
        self.write(0xFFFFCD11, 0xA0, 1)
        self.write(0xFFFFCD40, 0xA0, 1)

    def call_lookup(self, target):
        if target in (0x2484, 0x650BA):
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def select(self, rpm, load):
        self.put_float(0xFFFFB544, rpm)
        self.put_float(0xFFFFB438, load)
        self.invoke(0x3DAA6, CELL_WRITES)
        return tuple(self.read(0xFFFFCD0C+i, 1) for i in range(3))

    def consume(self):
        self.invoke(0x3DB90, {(0xFFFFCCF8, 4)})
        return self.get_float(0xFFFFCCF8)

    def range_flags(self, entry, address, rpm, load):
        self.original_fr[4] = bits(rpm)
        self.original_fr[5] = bits(load)
        self.invoke(entry, {(address, 1)})
        return self.read(address, 1)


class KnockCellFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        cls.images = {
            'main': (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes(),
            'v2': (ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes(),
        }
        cls.images['captured'] = before_pump_scaling(cls.images['v2'])
        for image in cls.images.values():
            for a, b in ((0x3DAA6, 0x3DBC6), (0x3DC54, 0x3DC88),
                         (0x3E0B0, 0x3E1B0), (0x3F256, 0x3F368),
                         (0x4C740, 0x4C778)):
                assert image[a:b] == cls.stock[a:b], hex(a)

    def test_both_axis_directions_stay_in_the_64_cell_grid_and_consume_the_selected_cell(self):
        for name, image in self.images.items():
            for previous in (0, 7):
                cpu = KnockCellMachine(image, previous)
                for rpm, load in product((0, 2500, 2800, 3000, 3500, 4400, 8000),
                        (-.1, 0, .62, .7, 1.1, 1.5, 1.8, 1.98, 2, 2.17, 2.5, 3.5, 4, 10)):
                    row, column, index = cpu.select(rpm, load)
                    self.assertTrue(0 <= row <= 7 and 0 <= column <= 7, (name, rpm, load))
                    self.assertEqual(index, row*8+column)
                    self.assertLess(index, 64)
                    self.assertEqual(cpu.consume(), -index/16)
                    self.assertEqual(cpu.get_float(IAM), 1)
                    self.assertIn(GRID+8*index, cpu.reads)

    def test_last_grid_cell_ends_immediately_before_iam_without_overwriting_it(self):
        self.assertEqual(GRID+64*8, IAM)
        for image in self.images.values():
            cpu = KnockCellMachine(image)
            self.assertEqual(cpu.select(10000, 10), (7, 7, 63))
            self.assertEqual(cpu.consume(), -63/16)
            self.assertEqual(cpu.get_float(IAM), 1)
            self.assertEqual(cpu.read(GRID+63*8+4, 4), 0xA55A5AA5)

    def test_load_gate_transitions_preserve_unrelated_flags_and_iam(self):
        for name, image in self.images.items():
            for entry, address in ((0x3E0B0, 0xFFFFCD11), (0x3F256, 0xFFFFCD40)):
                cpu = KnockCellMachine(image)
                # Move through lower/upper boundaries in both directions.
                for rpm in (2800, 3000, 3500):
                    for load in (0, .6, .65, .95, 1, 2, 2.1, 2.2, 3.9, 4, 4.1, 3.9, 2, 0):
                        flags = cpu.range_flags(entry, address, rpm, load)
                        self.assertEqual(flags & 0xF0, 0xA0)
                        self.assertEqual(cpu.get_float(IAM), 1, (name, rpm, load))
                        self.assertFalse(any(a == IAM for a, _ in cpu.writes))

    def test_selected_learned_correction_reaches_all_six_final_angles(self):
        for image in self.images.values():
            cpu = KnockCellMachine(image)
            _, _, index = cpu.select(2800, 2.17)
            correction = cpu.consume()
            self.assertEqual(correction, -index/16)
            cpu.put_float(0xFFFFCD14, 0)
            cpu.put_float(0xFFFFCD34, 0)
            cpu.invoke(0x3F386, {(0xFFFFCD44, 4)})
            self.assertEqual(cpu.get_float(0xFFFFCD44), correction)
            cpu.put_float(0xFFFFC130, 20)
            self.assertEqual(cpu.final(), (20+correction,)*6)


if __name__ == '__main__':
    unittest.main(verbosity=2)
