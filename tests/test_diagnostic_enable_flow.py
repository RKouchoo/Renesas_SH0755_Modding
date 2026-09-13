#!/usr/bin/env python3
"""Trace changed DTC enables through native retained-status masking.

511F8 and 24DC run from image instructions. Preexisting status is deliberately
set, and the mask starts at the value provided by normal startup DMA. This
does not emulate every physical monitor, reset mode, or diagnostic transport.
"""

import _test_paths
import unittest

from test_runtime_rom_checksum_execution import ChecksumMachine, before_pump_scaling

ROOT = _test_paths.ROOT
ENABLE_BASE, DESCRIPTORS, COUNT = 0x5BD54, 0x5BDF0, 153
MASK_BASE, RAW_BASES = 0xFFFFDBC6, (0xFFFFDAB6, 0xFFFFDAEC)
PROTECTED_BASES = (0xFFFF8E58, 0xFFFF8EC4, 0xFFFF8F30)
WRITE_SET = {(MASK_BASE + i, 1) for i in range(54)}
WRITE_SET |= {(base + i, 1) for base in RAW_BASES for i in range(54)}
WRITE_SET |= {(base + 2*i, size) for base in PROTECTED_BASES
              for i in range(54) for size in (1, 2)}


class EnableMachine(ChecksumMachine):
    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        if op & 0xF0FF == 0x4018:  # shll8 Rn; T unchanged
            n = (op >> 8) & 15
            self.r[n] = (self.r[n] << 8) & 0xFFFFFFFF
            self.pc += 2
            self.instructions += 1
        elif op & 0xF00F == 0x6004:  # mov.b @Rm+,Rn; sign-extended load
            n, m = (op >> 8) & 15, (op >> 4) & 15
            address = self.r[m]
            value = self.load(address, 1)
            self.r[n] = value if value < 128 else value | 0xFFFFFF00
            if n != m:
                self.r[m] = (address + 1) & 0xFFFFFFFF
            self.pc += 2
            self.instructions += 1
        else:
            super().step(in_delay)

    def call_lookup(self, target):
        if target in (0x24DC, 0x3AF4, 0x3B08):
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)


class DiagnosticEnableFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        cls.images = {
            'main': (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes(),
            'v2': (ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes(),
        }
        cls.images['captured'] = before_pump_scaling(cls.images['v2'])
        for image in cls.images.values():
            for start, end in ((0x511F8, 0x51368), (0x50FF6, 0x511B8),
                               (0x24DC, 0x24EC), (DESCRIPTORS, DESCRIPTORS + COUNT*20)):
                assert image[start:end] == cls.stock[start:end], hex(start)

    def test_periodic_mask_clears_disabled_retained_states_and_preserves_enabled_states(self):
        for name, image in self.images.items():
            cpu = EnableMachine(image)
            masks = [0]*54
            for i in range(COUNT):
                byte, mask = image[DESCRIPTORS + 20*i + 1:DESCRIPTORS + 20*i + 3]
                if image[ENABLE_BASE + i] == 1:
                    masks[byte] |= mask
            for i in range(54):
                cpu.write(MASK_BASE + i, 0, 1)  # Normal startup DMA boundary.
                for base in RAW_BASES:
                    cpu.write(base + i, 255, 1)
                for base in PROTECTED_BASES:
                    cpu.write(base + 2*i, 0xFF00, 2)  # All statuses set, valid complement.
            cpu.invoke(0x511F8, WRITE_SET)
            for i, mask in enumerate(masks):
                self.assertEqual(cpu.read(MASK_BASE + i, 1), mask, (name, i))
                for base in RAW_BASES:
                    self.assertEqual(cpu.read(base + i, 1), mask)
                for base in PROTECTED_BASES:
                    self.assertEqual(cpu.read(base + 2*i, 2), (mask << 8) | (mask ^ 255))

    def test_all_22_changed_switches_gate_both_set_and_clear_reporters(self):
        for image in self.images.values():
            changed = [i for i in range(COUNT) if image[ENABLE_BASE+i] != self.stock[ENABLE_BASE+i]]
            self.assertEqual(len(changed), 22)
            for i in changed:
                self.assertEqual((self.stock[ENABLE_BASE+i], image[ENABLE_BASE+i]), (1, 0))
                descriptor = image[DESCRIPTORS + 20*i:DESCRIPTORS + 20*(i+1)]
                # No still-enabled descriptor shares this status bit.
                self.assertFalse([j for j in range(COUNT)
                                  if image[ENABLE_BASE+j] == 1 and
                                  image[DESCRIPTORS+20*j+1:DESCRIPTORS+20*j+3] == descriptor[1:3]])
                for entry in (0x50FF6, 0x5108C):
                    cpu = EnableMachine(image)
                    cpu.write(0xFFFFDE08, 0, 1)
                    cpu.original_r[4] = i
                    cpu.invoke(entry, set())
                    self.assertFalse([(a, n) for a, n in cpu.writes
                                      if not cpu.min_sp <= a < cpu.STACK])
                    # Returning before reading 8FA0 proves the disabled gate
                    # rather than an imposed reporting-mode early return.
                    self.assertNotIn(0xFFFF8FA0, cpu.reads)


if __name__ == '__main__':
    unittest.main(verbosity=2)
