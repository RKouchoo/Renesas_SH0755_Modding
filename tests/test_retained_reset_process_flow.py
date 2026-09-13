#!/usr/bin/env python3
"""Native serial-input rearm/invalidation and its retained-bank consumers.

Every CPU helper executes ROM instructions. SCI0 completion bytes and GPIO
levels are explicit hardware inputs; shutdown states are explicit except
where the native ignition-on parent executes. No peripheral wiring identity,
power retention or vehicle input state is inferred.
"""
import _test_paths
from itertools import product
import unittest

from test_startup_retained_process_flow import (
    StartupRetainedMachine, ROOT, RAM, HEADER, LEARNED, PATCH_CANARIES,
)
from test_runtime_switch_process_flow import SAMPLE_WRITES, PUBLISH_WRITES
from test_knock_event_process_flow import SERIAL_WRITES
from test_shutdown_process_flow import MODE_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling

REARM_WRITES = {(RAM+a, 1) for a in (0x8E0C, 0xD04C, 0xD04D, 0xD04E,
                                     0xC779, 0xC77A)}
REQUEST_WRITES = {(HEADER, 2), (RAM+0x8262, 2), (RAM+0x8E0C, 1)}


class RetainedResetMachine(StartupRetainedMachine):
    def __init__(self, image, port_e=0, serial=4):
        self.serial_inputs = (0, 0, serial)
        self.serial_channel = 0
        self.serial_transactions = []
        super().__init__(image)
        for a in range(0xF000, 0xF007):
            self.write(RAM+a, 0, 1)
        for a, value in ((0xF726, 0), (0xF72C, 0), (0xF754, port_e),
                         (0xF74E, 1), (0xF764, 0)):
            self.write(RAM+a, value, 2)
        # Include 147C0, the first entry: starting at 10148 would omit B289
        # and falsely disable CC4D/02 in this installed configuration.
        for p in range(0x10140, 0x10188, 4):
            self.bank_entry(self.read(p, 4))
        self.cold_bank()
        self.sample(initial=True)
        self.visited.clear()

    def step(self, in_delay=False):
        if self.pc == 0x766C:
            self.serial_channel = self.r[4]
            assert 0 <= self.serial_channel < 3
            self.serial_transactions.append(self.serial_channel)
        if self.pc == 0x77DE:
            # Supplied SCI0 transaction completion at the native poll.
            self.write(RAM+0xF004, self.read(RAM+0xF004, 1) | 0xC0, 1)
            self.write(RAM+0xF005, self.serial_inputs[self.serial_channel], 1)
        return super().step(in_delay)

    def sample(self, initial=False):
        self.execute(0x6B08 if initial else 0x6BB4, SAMPLE_WRITES | SERIAL_WRITES)
        self.execute(0x193D0, PUBLISH_WRITES)

    def serial_level(self, value):
        self.serial_inputs = (0, 0, value)
        self.sample()
        self.sample()

    def request(self):
        self.execute(0x4892C, REQUEST_WRITES)


class RetainedResetProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x6B08, 0x6CE4), (0x766C, 0x7748), (0x77AA, 0x7840),
                         (0x10140, 0x10188), (0x147C0, 0x148E4),
                         (0x193D0, 0x19EEA), (0x3BAB8, 0x3BB3C),
                         (0x3BC1E, 0x3BC56), (0x48830, 0x489DC),
                         (0x313F2, 0x313FA), (0x31476, 0x31482),
                         (0x11EE8, 0x11EF4), (0x11F8C, 0x11F94),
                         (0xFD14, 0xFD24), (0x3107C, 0x310AE)):
                assert image[a:b] == stock[a:b], hex(a)
            assert image[0x737C8] == 0x81
            assert int.from_bytes(image[0x117D0:0x117D4], 'big') == 0x48830
            assert int.from_bytes(image[0x117D4:0x117D8], 'big') == 0x4892C

    def test_installed_feature_is_enabled_but_cold_latch_blocks_either_serial_level(self):
        for image, port, serial in product(self.images.values(),
                (0, 0x4000, 0x8000, 0xC000), (0, 4)):
            cpu = RetainedResetMachine(image, port, serial)
            self.assertEqual(cpu.read(RAM+0xB289, 1), 0xC4)
            self.assertEqual(cpu.read(RAM+0xCC4D, 1), 7)
            self.assertEqual(cpu.serial_transactions, [0, 1, 2])
            self.assertEqual(cpu.read(RAM+0x8E0C, 1) & 0xC0, 0x40)
            before = cpu.protected_bytes()
            for _ in range(4):
                cpu.request()
            self.assertEqual(cpu.protected_bytes(), before)
            self.assertNotIn(0xF5F6, cpu.visited)

    def test_rearm_needs_shutdown_and_serial_bit_high_and_preserves_other_packed_fields(self):
        for image, enabled, shutdown, serial in product(self.images.values(),
                (False, True), (0, 1, 2), (0, 4)):
            cpu = RetainedResetMachine(image, serial=serial)
            if not enabled:
                cpu.write(RAM+0xCC4D, cpu.read(RAM+0xCC4D, 1) & ~2, 1)
            cpu.write(RAM+0x8E0C, 0x7B, 1)
            cpu.write(RAM+0xC778, shutdown, 1)
            cpu.execute(0x48830, REARM_WRITES)
            self.assertEqual(cpu.read(RAM+0x8E0C, 1),
                             0xBB if enabled and shutdown and serial else 0x7B)
            self.assertEqual(cpu.read(HEADER, 2), 0xAA55)
            self.assertEqual(cpu.read(RAM+0xC779, 1), int(enabled and bool(shutdown)))
            self.assertNotIn(0xF5F6, cpu.visited)

    def test_request_checks_feature_shutdown_serial_and_all_four_packed_states(self):
        for image, enabled, shutdown, serial, packed in product(self.images.values(),
                (False, True), (0, 1, 2), (0, 4), range(4)):
            cpu = RetainedResetMachine(image, serial=serial)
            if not enabled:
                cpu.write(RAM+0xCC4D, cpu.read(RAM+0xCC4D, 1) & ~2, 1)
            cpu.write(RAM+0xC778, shutdown, 1)
            cpu.write(RAM+0x8E0C, packed << 6 | 0x3B, 1)
            cpu.request()
            active = enabled and shutdown == 0 and serial == 0 and not (packed & 1)
            self.assertEqual(0xF5F6 in cpu.visited, active)
            self.assertEqual(cpu.read(HEADER, 2), 0x55AA if active else 0xAA55)
            self.assertEqual(cpu.read(RAM+0x8262, 2), 0x4055 if active else 0)
            self.assertEqual(cpu.read(RAM+0x8E0C, 1),
                             0x7B if active else packed << 6 | 0x3B)

    def test_native_rearm_then_request_latches_once_and_defers_learning_reset_to_startup(self):
        for name, image in self.images.items():
            cpu = RetainedResetMachine(image)
            for a, value in LEARNED:
                cpu.put_record(RAM+a, value)
            for i, a in enumerate(PATCH_CANARIES):
                cpu.write(RAM+a, 0x3F000000+i, 4)
            cpu.execute(0x48830, REARM_WRITES)
            cpu.write(RAM+0xC778, 1, 1)
            cpu.execute(0x48830, REARM_WRITES)
            self.assertTrue({0xC700, 0x11EE8, 0x11EEE, 0x3107C, 0x31094} <= cpu.visited)
            self.assertEqual(cpu.read(RAM+0xC779, 1), 1)
            self.assertEqual(cpu.read(RAM+0xC77A, 1), 1)
            cpu.write(RAM+0xC778, 0, 1)
            cpu.serial_level(0)
            cpu.execute(0x48830, REARM_WRITES)
            cpu.request()
            self.assertEqual(cpu.read(HEADER, 2), 0x55AA)
            for a, value in LEARNED:
                self.assertEqual(cpu.get_float(RAM+a), value)
            for i, a in enumerate(PATCH_CANARIES):
                self.assertEqual(cpu.read(RAM+a, 4), 0x3F000000+i)
            cpu.request()
            self.assertFalse(set(cpu.writes) & REQUEST_WRITES)
            cpu.cold_bank()
            for a, value in ((0x81D0, 0), (0x8264, 40), (0x831C, 0),
                             (0x851C, .5 if name == 'main' else 1), (0x8E04, 760)):
                self.assertEqual(cpu.get_float(RAM+a), value)
            self.assertEqual(cpu.read(HEADER, 2), 0xAA55)

    def test_invalid_link_status_does_not_start_shutdown_while_native_ignition_input_is_on(self):
        for image in self.images.values():
            cpu = RetainedResetMachine(image)
            self.assertEqual(cpu.read(RAM+0xB51E, 1) & 0x10, 0x10)
            cpu.execute(0xF5F6, {(HEADER, 2)})
            cpu.execute(0x30A84, {(RAM+0xC6F6, 1)})
            self.assertEqual(cpu.read(RAM+0xC6F6, 1) & 1, 1)
            for _ in range(100):
                cpu.execute(0x310D8, MODE_WRITES)
                self.assertEqual(cpu.read(RAM+0xC778, 1), 0)
            self.assertEqual(cpu.read(HEADER, 2), 0x55AA)
            self.assertNotIn(0xCCBA, cpu.visited)


if __name__ == '__main__':
    unittest.main(verbosity=2)
