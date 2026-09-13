#!/usr/bin/env python3
"""Execute the ECU's additive checksum over the stock and captured images.

F5FE and its F97C range validator execute from ROM. D6F0 watchdog service
is an explicit hardware boundary. The separate 4FB8C rolling accumulator and
4FB46 protected-RAM check also execute. Corruption affects in-memory copies.
"""

import _test_paths
import hashlib
import sys
import unittest

from test_native_fault_cut_execution import FaultCutMachine
from test_wideband_fuel_guard_execution import signed

ROOT = _test_paths.ROOT
sys.path.insert(0, str(ROOT / 'tools' / 'analysis'))
from _captured_images import before_pump_scaling as _restore_before_pump_scaling


def before_pump_scaling(image):
    """Loaded-audit fixture: never silently relabel a later rolling ROM."""
    restored = _restore_before_pump_scaling(image)
    assert hashlib.sha256(restored).hexdigest() == (
        'fd795813febf817c845fc922e81e498539a539efeeb6e4d11822af47098094a2'), (
        'The loaded 2026-09-12 capture needs its pinned image; this rolling '
        'image cannot be reversed to it using the recorded pump edit.')
    return restored


class ChecksumMachine(FaultCutMachine):
    INSTRUCTION_LIMIT = 1_500_000

    def __init__(self, image):
        super().__init__(image)
        self.original_r[4] = 0
        self.watchdog_calls = 0

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF0FF in (0x4028, 0x4029):  # shll16/shlr16, T unchanged
            self.r[n] = ((self.r[n] << 16) & 0xFFFFFFFF
                         if op & 255 == 0x28 else self.r[n] >> 16)
            self.pc += 2
            self.instructions += 1
        elif op & 0xF0FF == 0x4021:  # shar Rn; arithmetic shift, low bit to T
            self.t = bool(self.r[n] & 1)
            self.r[n] = (signed(self.r[n], 32) >> 1) & 0xFFFFFFFF
            self.pc += 2
            self.instructions += 1
        elif op & 0xF00F == 0x000E:  # mov.l @(R0,Rm),Rn
            self.r[n] = self.load((self.r[0] + self.r[m]) & 0xFFFFFFFF, 4)
            self.pc += 2
            self.instructions += 1
            assert self.instructions < self.INSTRUCTION_LIMIT
        else:
            super().step(in_delay)

    def call_lookup(self, target):
        if target in (0xF97C, 0x2068, 0x24EC, 0x4824):
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        elif target == 0xD6F0:
            self.watchdog_calls += 1
            self.poison_scratch()
        else:
            super().call_lookup(target)


class RuntimeChecksumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        captured = before_pump_scaling(
            (ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes())
        assert hashlib.sha256(captured).hexdigest() == (
            'fd795813febf817c845fc922e81e498539a539efeeb6e4d11822af47098094a2')
        cls.images = {'stock': stock, 'captured_144204': captured}

    def test_exact_images_pass_native_checksum(self):
        for name, image in self.images.items():
            with self.subTest(image=name):
                cpu = ChecksumMachine(image)
                self.assertEqual(cpu.invoke(0xF5FE, {(0xFFFFB13E, 1)}), 0)
                self.assertEqual(cpu.watchdog_calls, 4)

    def test_corrupted_injector_scalar_fails_native_checksum(self):
        for name, image in self.images.items():
            with self.subTest(image=name):
                corrupt = bytearray(image)
                corrupt[0x76017] ^= 1
                cpu = ChecksumMachine(bytes(corrupt))
                self.assertEqual(cpu.invoke(0xF5FE, {(0xFFFFB13E, 1)}), 1)
                self.assertEqual(cpu.watchdog_calls, 4)


ROLLING_WRITES = {(a, n) for a, n in (
    (0xFFFFDA94, 4), (0xFFFFDA98, 4), (0xFFFFDA9C, 2),
    (0xFFFFDA9E, 2), (0xFFFFDAA0, 1), (0xFFFFDAA1, 1),
    (0xFFFF8E50, 4), (0xFFFF8E54, 4))}


class RollingAccumulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RuntimeChecksumTests.setUpClass()
        cls.images = RuntimeChecksumTests.images

    @staticmethod
    def expected(image, start, end):
        result = 0
        for address in range(start, end, 2):
            result = (result + int.from_bytes(image[address:address + 2], 'big')) & 65535
            result = ((result << 1) | (result >> 15)) & 65535
        return (result << 16) | (result ^ 65535)

    def test_complete_captured_accumulation_has_valid_protected_records(self):
        image = self.images['captured_144204']
        cpu = ChecksumMachine(image)
        cpu.write(0xFFFFDAA0, 0, 1)  # Explicit post-startup DMA-zero boundary.
        cpu.write(0xFFFFDAA1, 0, 1)
        cpu.invoke(0x4FB2C, ROLLING_WRITES)
        cpu.invoke(0x4FB74, ROLLING_WRITES)
        calls = 0
        while not cpu.read(0xFFFFDAA0, 1):
            cpu.invoke(0x4FB8C, ROLLING_WRITES)
            self.assertEqual(cpu.invoke(0x4FB46, set()), 0)
            calls += 1
            self.assertLess(calls, 2100)
        self.assertEqual(cpu.read(0xFFFFDA94, 4), 0x7D790)
        self.assertEqual(cpu.read(0xFFFFDA98, 4), 0x72668)
        self.assertEqual(cpu.read(0xFFFFDAA1, 1), 0)
        for destination, start, end in (
                (0xFFFF8E50, 0x727A0, 0x7D790),
                (0xFFFF8E54, 0x2034, 0x72668)):
            self.assertEqual(cpu.read(destination, 4), self.expected(image, start, end))
        cpu.invoke(0x4FB8C, ROLLING_WRITES)
        self.assertFalse([(a, n) for a, n in cpu.writes
                          if (a, n) in ROLLING_WRITES])

    def test_fault_getter_checks_record_complements_not_stock_calibration_sum(self):
        for name, image in self.images.items():
            cpu = ChecksumMachine(image)
            for destination, start, end in (
                    (0xFFFF8E50, 0x727A0, 0x7D790),
                    (0xFFFF8E54, 0x2034, 0x72668)):
                cpu.write(destination, self.expected(image, start, end), 4)
            self.assertEqual(cpu.invoke(0x4FB46, set()), 0, name)
            for destination in (0xFFFF8E50, 0xFFFF8E54):
                original = cpu.read(destination, 4)
                cpu.write(destination, original ^ 1, 4)
                self.assertEqual(cpu.invoke(0x4FB46, set()), 1)
                cpu.write(destination, original, 4)
                self.assertEqual(cpu.invoke(0x4FB46, set()), 0)

if __name__ == '__main__':
    unittest.main()
