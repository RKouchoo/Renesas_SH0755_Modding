#!/usr/bin/env python3
"""Execute native cut-word publication and a downstream channel inhibit gate.

1C5D4 and its six D94C getters execute in GuardMachine. This suite also
executes 26DFC, the 268E8 channel gate and its 26958 output-activity flag tail.
Hardware handoff 90BA is a recorded substitute, not a device action. The
separate scheduler suite covers queued-state transitions; neither suite
emulates interrupt timing or physical injection.
"""

import _test_paths  # Shared offline-test imports and repository root.
from io import StringIO
from pathlib import Path
import sys
import unittest

from test_wideband_fuel_guard_execution import (
    GuardMachine, INHIBIT_WORD, INHIBIT_BUILDER, safety, boost, bits, number, signed,
)

ROOT = _test_paths.ROOT
IMAGE = None


class ChannelGateMachine(GuardMachine):
    def __init__(self, image):
        super().__init__(image)
        self.handoffs = []

    def call_lookup(self, target):
        if target == 0x26DFC:
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        elif target == 0x90BA:
            self.handoffs.append(target)
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        handled = True
        self.pc += 2
        if op & 0xFF00 == 0xC700:
            self.r[0] = ((pc + 4) & ~3) + (op & 255) * 4
        elif op & 0xF00F == 0xF007:
            self.write((self.r[0] + self.r[n]) & 0xFFFFFFFF, self.fr[m], record=True)
        elif op & 0xF00F == 0xF006:
            self.fr[n] = self.load((self.r[0] + self.r[m]) & 0xFFFFFFFF, 4)
        elif op & 0xF0FF == 0xF03D:
            value = number(self.fr[n])
            assert -2**31 <= value < 2**31  # This suite supplies ordinary pulse values.
            self.fpul = int(value) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x005A:
            self.r[n] = self.fpul
        elif op & 0xF0FF == 0x4000:
            self.t = bool(self.r[n] & 0x80000000)
            self.r[n] = self.r[n] << 1 & 0xFFFFFFFF
        elif op & 0xF00F == 0x000D:
            self.r[n] = signed(self.load((self.r[0] + self.r[m]) & 0xFFFFFFFF, 2), 16) & 0xFFFFFFFF
        elif op & 0xF00F == 0x300C:
            self.r[n] = (self.r[n] + self.r[m]) & 0xFFFFFFFF
        else:
            handled = False
        if handled:
            self.instructions += 1
            assert self.instructions < self.INSTRUCTION_LIMIT
        else:
            self.pc = pc
            super().step(in_delay)

    def channel(self, channel):
        self.original_r[4] = channel
        self.original_fr[4] = bits(1000)
        self.handoffs.clear()
        self.write(0xFFFFC0B0, 0, 1)
        self.invoke(0x268E8, {(0xFFFFC0B0, 1)})
        assert self.read(0xFFFFC0B0, 1) == bool(self.handoffs)
        return bool(self.handoffs)


class InjectorCutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / "master_patch/D2WD610H_master_patch.bin").read_bytes()
        stock = (ROOT / "2005 BLE MT.bin").read_bytes()
        for start, end in ((0x1C5D4, 0x1C91E), (0x46EE0, 0x46F52), (0x46FD8, 0x46FDA),
                           (0x26DFC, 0x26E02), (0x26EEE, 0x26EF0), (0x268E8, 0x26944),
                           (0x26958, 0x26960), (0x269DA, 0x269DC),
                           (0x269E0, 0x269F8), (0x4B64C, 0x4B658), (0x4B6A8, 0x4B6B4)):
            assert cls.image[start:end] == stock[start:end], f"Stock cut path changed at {start:#x}"
        assert cls.image[0x4B64C:0x4B658] == bytes.fromhex("000100020004000800100020")

    def test_native_per_channel_fault_mapping(self):
        for address, masks in ((0xFFFFBF21, (128, 64, 32, 16, 8, 4)),
                               (0xFFFFBF8C, (64, 32, 16, 8, 4, 2)),
                               (0xFFFFBF90, (128, 64, 32, 16, 8, 4)),
                               (0xFFFFCCB9, (2, 4, 8, 16, 32, 64)),
                               (0xFFFFBF9D, (1, 2, 4, 8, 16, 32)),
                               (0xFFFFD94C, (1, 2, 4, 8, 16, 32))):
            cpu = GuardMachine(self.image)
            for byte in range(256):
                cpu.write(address, byte, 1)
                cpu.invoke(INHIBIT_BUILDER, {(INHIBIT_WORD, 2)})
                expected = sum(1 << i for i, mask in enumerate(masks) if byte & mask)
                self.assertEqual(cpu.read(INHIBIT_WORD, 2), expected)

    def test_native_global_cut_value(self):
        for address, mask in ((safety.FUEL_CUT_FLAG, 128), (0xFFFFBF70, 128),
                               (0xFFFFBF74, 128), (0xFFFFCE24, 1), (0xFFFFCF24, 128), (0xFFFFCFA0, 1)):
            cpu = GuardMachine(self.image)
            cpu.write(address, mask, 1)
            cpu.invoke(INHIBIT_BUILDER, {(INHIBIT_WORD, 2)})
            self.assertEqual(cpu.read(INHIBIT_WORD, 2), 0xFFFF)

    def test_every_word_mask_controls_only_its_channel(self):
        cpu = ChannelGateMachine(self.image)
        for word in range(64):
            cpu.write(INHIBIT_WORD, word, 2)
            for channel in range(6):
                self.assertEqual(cpu.channel(channel), not bool(word & (1 << channel)))

    def test_added_cuts_block_handoffs_and_release_to_native_fault_word(self):
        for pressure, state in ((1150, 0), (820, 3)):
            cpu = ChannelGateMachine(self.image)
            cpu.write(0xFFFFD94C, 0x12, 1)  # Retain two independent cylinder faults.
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.write(safety.LEAN_STATE_RAM, state, 1)
            self.assertTrue(cpu.cut_step()[-1])
            self.assertEqual(cpu.read(INHIBIT_WORD, 2), 0xFFFF)
            self.assertTrue(all(not cpu.channel(i) for i in range(6)))
            cpu.put_float(safety.MAP_PRESSURE, 700)
            self.assertFalse(cpu.cut_step()[-1])
            self.assertEqual(cpu.read(INHIBIT_WORD, 2), 0x12)
            for channel in range(6):
                self.assertEqual(cpu.channel(channel), not bool(0x12 & (1 << channel)))

    def test_each_missing_word_store_recovers_flag_only_defect(self):
        for start, blob, pressure, state in (
                (boost.REVWRAP_ADDR, boost.build_fuelcut_wrapper(), 1150, 0),
                (safety.LEAN_CUT_WRAPPER_ADDR, safety.build_lean_cut_wrapper(), 820, 3)):
            image = bytearray(self.image)
            marker = bytes.fromhex("e0ff2101")
            self.assertEqual(blob.count(marker), 1)
            address = start + blob.index(marker) + 2
            image[address:address + 2] = bytes.fromhex("0009")
            cpu = ChannelGateMachine(image)
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.write(safety.LEAN_STATE_RAM, state, 1)
            self.assertTrue(cpu.cut_step()[-1])
            self.assertEqual(cpu.read(INHIBIT_WORD, 2), 0)
            self.assertTrue(all(cpu.channel(i) for i in range(6)))

    def test_changed_native_cut_contract_refuses_before_mutation(self):
        stock = (ROOT / "2005 BLE MT.bin").read_bytes()
        for address in (0x1C662, 0x1C68C, 0x1C908, 0x1C91C, 0x26DFC, 0x26EEE):
            image = bytearray(stock)
            image[address] ^= 1
            before = bytes(image)
            with self.assertRaisesRegex(SystemExit, "native injector-inhibit contract"):
                boost.apply_to_rom(image)
            self.assertEqual(bytes(image), before)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(unittest.defaultTestLoader.loadTestsFromTestCase(InjectorCutTests))
        if not result.wasSuccessful():
            raise SystemExit(report.getvalue())
        print(f"  Injector cut: {result.testsRun} execution test groups passed")
    finally:
        IMAGE = previous


if __name__ == "__main__":
    if len(sys.argv) > 1:
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
