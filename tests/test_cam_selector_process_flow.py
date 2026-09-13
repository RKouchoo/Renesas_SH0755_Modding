#!/usr/bin/env python3
"""Connect actual interface calibration refresh to cam-event classification.

Native 2FDDC publishes the installed selectors and expected edge counts.
Capture timing and phase delivery remain explicit; the 24-phase sequence is
executed without claiming physical cam motion or real interrupt deadlines.
"""
import _test_paths
from itertools import product
import unittest

from test_cam_sensor_process_flow import CamSensorMachine, ROOT, RAM
from test_avcs_event_process_flow import CAPTURE_WRITES, QUEUE_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling

INTERFACE_WRITES = {(RAM+a, 4) for a in (0xC67C, 0xC680, *range(0xC6B4, 0xC6CC, 4))} | {
    (RAM+a, 2) for a in (*range(0xC684, 0xC68C, 2), *range(0xC698, 0xC6A0, 2))} | {
    (RAM+a, 1) for a in (*range(0xC68C, 0xC698), *range(0xC6A0, 0xC6AA))}


class CamSelectorMachine(CamSensorMachine):
    LOOKUPS = CamSensorMachine.LOOKUPS | {0x2FDDC, 0x4408}

    def __init__(self, image):
        super().__init__(image)
        for a in range(0xC67C, 0xC6CC, 4):
            self.write(RAM+a, 0x5AA55AA5, 4)
        self.execute(0xFEE4, INTERFACE_WRITES)

    def phase(self, phase):
        self.original_r[4] = phase
        before = self.read(RAM+0x930C, 1)
        self.execute(0xE468, CAPTURE_WRITES | QUEUE_WRITES)
        return self.read(RAM+0x930C, 1)-before


class CamSelectorProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x2FDDC, 0x2FFA8), (0x7B248, 0x7B27C),
                         (0x7B2A4, 0x7B2AC), (0x60938, 0x60950),
                         (0xFEE4, 0xFEF4), (0x10A28, 0x10A30),
                         (0x10C74, 0x10C78), (0x4408, 0x44A0)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_native_refresh_copies_actual_cam_selectors_and_all_adjacent_interface_fields(self):
        for image in self.images.values():
            cpu = CamSelectorMachine(image)
            pairs = [(0xC67C, 0x7B2A4, 4), (0xC680, 0x7B2A8, 4)]
            pairs += [(0xC684+2*i, 0x7B270+2*i, 2) for i in range(4)]
            pairs += [(0xC68C+i, 0x7B250+i, 1) for i in range(12)]
            pairs += [(0xC698+2*i, 0x7B264+2*i, 2) for i in range(4)]
            pairs += [(0xC6A0+i, 0x7B248+2*i, 1) for i in range(3)]
            pairs += [(0xC6A3+i, 0x7B249+2*i, 1) for i in range(3)]
            pairs += [(0xC6A6+i, 0x7B260, 1) for i in range(2)]
            pairs += [(0xC6A8+i, 0x7B25F, 1) for i in range(2)]
            pairs += [(0xC6B4+i, 0x60938+i, 4) for i in range(0, 24, 4)]
            for target, source, size in pairs:
                self.assertEqual(cpu.read(RAM+target, size), cpu.read(source, size))
            self.assertEqual(cpu.read(RAM+0xC6A0, 10), int.from_bytes(bytes((0,8,16,4,12,20,0,0,3,3)), 'big'))
            self.assertEqual(cpu.read(RAM+0xC6AA, 2), 0x5AA5)
            self.assertEqual(cpu.read(RAM+0xC6AC, 8), 0x5AA55AA55AA55AA5)
            # The same copy is called at10A28 each periodic pass. Refresh
            # corrects a supplied stale selector rather than preserving it.
            cpu.write(RAM+0xC6A9, 1, 1)
            cpu.execute(cpu.read(0x10C74, 4), INTERFACE_WRITES)
            self.assertEqual(cpu.read(RAM+0xC6A9, 1), 3)

    def test_actual_twenty_four_phase_sequence_publishes_three_observations_per_bank(self):
        for image in self.images.values():
            cpu = CamSelectorMachine(image)
            cpu.slow()
            for cycle in range(3):
                banks = []
                for phase in range(24):
                    bank = phase//4 % 2 if phase % 4 == 0 else None
                    if bank is not None:
                        cpu.capture(bank)
                    head = cpu.read(RAM+0x930A, 1)
                    self.assertEqual(cpu.phase(phase), int(bank is not None))
                    if bank is not None:
                        record = RAM+0x94A0+20*head
                        self.assertEqual(cpu.read(record, 4), 0x11EC8)
                        self.assertEqual(cpu.read(record+4, 4), bank)
                        banks.append(bank)
                    if cycle and phase == 0:
                        self.assertEqual(cpu.read(RAM+0xB0B8, 2), 0)
                    cpu.fast()
                self.assertEqual(banks, [0,1,0,1,0,1])
                self.assertEqual(cpu.slow(), 0)
            self.assertEqual(cpu.read(RAM+0xD375, 2), 0)

    def test_actual_expected_count_reports_missing_or_extra_edges_and_clears_after_healthy_cycle(self):
        for image, bank, edges in product(self.images.values(), (0, 1), (2, 3, 4)):
            cpu = CamSelectorMachine(image)
            cpu.slow()
            # Actual anchor is phase modulo4==0 for BOTH banks. First anchor
            # opens a window, five more anchors hold it, seventh compares.
            for phase in range(24):
                cpu.phase(phase)
            for _ in range(edges):
                cpu.capture(bank)
            self.assertEqual(cpu.phase(0), 1)
            self.assertEqual(cpu.read(RAM+0xB0B8+bank, 1), {2:1,3:0,4:2}[edges])
            # This window deliberately supplies only the selected bank's
            # captures; inspect that bank's bit independently of the other.
            for _ in range(5):
                cpu.fast()
            bit = 0x10 if bank == 0 else 8
            self.assertEqual(cpu.slow() & bit, bit if edges != 3 else 0)
            for phase in range(1,24):
                cpu.phase(phase)
            for _ in range(3):
                cpu.capture(bank)
            cpu.phase(0)
            cpu.fast()
            self.assertEqual(cpu.slow() & bit, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
