#!/usr/bin/env python3
"""Execute the two purge-delete leaves and check bounded/guarded ownership.

This independent small opcode decoder executes the actual emitted leaves,
including their delay slots.  It stops at the unchanged B182 driver handoff;
it does not emulate the complete ECU or establish physical valve polarity.
Run: python3 master_patch/test_purge_delete.py [optional-master-ROM.bin]
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

import purge_delete_component as patch


IMAGE: bytes | None = None
STOCK = Path(__file__).resolve().parent.parent / "2005 BLE MT.bin"


class LeafMachine:
    STOP = 0xDEAD1000

    def __init__(self, image: bytes, entry: int):
        self.image = image
        self.memory: dict[int, int] = {}
        self.r = [0x12340000 + i * 0x101 for i in range(16)]
        self.fr = [0x7FC00001 + i for i in range(16)]  # distinct quiet NaNs
        self.pr = self.STOP
        self.pc = entry
        self.steps = 0
        self.writes: list[tuple[int, int, int]] = []
        self.ram_reads: list[tuple[int, int]] = []
        self.original_r = self.r.copy()
        self.original_fr = self.fr.copy()

    def read(self, address: int, size: int) -> int:
        if address < len(self.image):
            return int.from_bytes(self.image[address:address + size], "big")
        self.ram_reads.append((address, size))
        return int.from_bytes(bytes(self.memory.get(address + i, 0xFF) for i in range(size)), "big")

    def write(self, address: int, value: int, size: int) -> None:
        self.writes.append((address, size, value & ((1 << (size * 8)) - 1)))
        for offset, byte in enumerate(value.to_bytes(size, "big")):
            self.memory[address + offset] = byte

    def step(self, delay: bool = False) -> None:
        pc = self.pc
        op = self.read(pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        self.pc += 2
        self.steps += 1
        assert self.steps <= 30, "Purge leaf failed to terminate"
        if op == 0x0009:
            return
        if op & 0xF0FF == 0xF08D:
            self.fr[n] = 0
        elif op & 0xF000 == 0xD000:
            self.r[n] = self.read(((pc + 4) & ~3) + (op & 255) * 4, 4)
        elif op & 0xF000 == 0xE000:
            imm = op & 255
            self.r[n] = (imm if imm < 128 else imm - 256) & 0xFFFFFFFF
        elif op & 0xF00F == 0xF00A:
            self.write(self.r[n], self.fr[m], 4)
        elif op & 0xF00F == 0x2000:
            self.write(self.r[n], self.r[m] & 255, 1)
        elif op == 0x000B or op & 0xF0FF == 0x402B:
            assert not delay, "Control transfer in delay slot"
            target = self.pr if op == 0x000B else self.r[n]
            self.step(delay=True)
            self.pc = target
        else:
            raise AssertionError(f"Unexpected opcode {op:04x} at {pc:#x}")

    def run(self, stop: int) -> None:
        while self.pc != stop:
            self.step()
        assert self.pr == self.STOP, "PR corrupted"
        assert self.r[15] == self.original_r[15], "Stack pointer changed"
        assert self.r[8:15] == self.original_r[8:15], "Callee-saved GPR changed"
        assert self.fr[12:] == self.original_fr[12:], "Callee-saved FP register changed"
        assert self.ram_reads == [], "Purge delete must not depend on stale RAM"


class PurgeDeleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stock = STOCK.read_bytes()

    def patched_image(self) -> bytes:
        if IMAGE is not None:
            patch.verify_rom(IMAGE)
            return IMAGE
        result = bytearray(self.stock)
        patch.apply_to_rom(result)
        return bytes(result)

    def test_purge_command_flow_mode_zero_and_stock_driver_handoff(self) -> None:
        cpu = LeafMachine(self.patched_image(), patch.PURGE_DISPATCH_ENTRY)
        cpu.run(patch.PURGE_OUTPUT_WRITER)
        self.assertEqual(cpu.fr[4], 0, "Driver must receive exact positive zero")
        self.assertEqual(cpu.writes, [
            (patch.PURGE_DUTY_ADDR, 4, 0),
            (patch.PURGE_MODELED_AIRFLOW_ADDR, 4, 0),
            (patch.PURGE_MODE_ADDR, 1, 0),
        ])
        self.assertEqual(cpu.r[2:], cpu.original_r[2:])
        self.assertEqual(cpu.fr[:4] + cpu.fr[5:], cpu.original_fr[:4] + cpu.original_fr[5:])

    def test_both_bank_subtractions_exact_zero_with_stale_and_nan_inputs(self) -> None:
        for destination in patch.PURGE_BANK_SUBTRACTION_ADDRS:
            for stale in (0x3F800000, 0x7FC12345, 0x7F800000, 0xFF800000, 0x80000000):
                with self.subTest(destination=hex(destination), stale=hex(stale)):
                    cpu = LeafMachine(self.patched_image(), patch.PURGE_SUBTRACTION_ENTRY)
                    cpu.r[4] = destination
                    cpu.original_r[4] = destination
                    cpu.fr = [stale] * 16
                    cpu.original_fr = cpu.fr.copy()
                    for address in (0xFFFFBE6C, 0xFFFFBE70, 0xFFFFBE84,
                                    patch.PURGE_MODELED_AIRFLOW_ADDR, 0xFFFFB730, 0xFFFFB734):
                        for i, value in enumerate(struct.pack(">I", stale)):
                            cpu.memory[address + i] = value
                    cpu.run(cpu.STOP)
                    self.assertEqual(cpu.writes, [(destination, 4, 0)])
                    self.assertEqual(cpu.r, cpu.original_r)
                    self.assertEqual(cpu.fr[:1] + cpu.fr[2:], cpu.original_fr[:1] + cpu.original_fr[2:])

    def test_owned_ranges_only_and_preserved_driver_initializers_fan(self) -> None:
        patched = self.patched_image()
        owned = {i for _, a, _, b in patch.STOCK_PATCHES for i in range(a, a + len(b))}
        # Optional integrated images legitimately include other components.
        if IMAGE is None:
            changed = {i for i, (x, y) in enumerate(zip(self.stock, patched)) if x != y}
            self.assertLessEqual(changed, owned)
        self.assertEqual(len(owned), 50)  # 40 + 8 code bytes; two DTC switch bytes
        for start, end in ((0xB0B4, 0xB0DA), (0xB182, 0xB1B2), (0x1BC00, 0x1BD82),
                           (0x22FE8, 0x23054), (0x2305C, 0x23300),
                           (0x3FC0A, 0x3FD38), (0xE8C4, 0xE8F0)):
            with self.subTest(range=(hex(start), hex(end))):
                self.assertEqual(patched[start:end], self.stock[start:end])

    def test_guard_failure_is_atomic_for_every_anchor(self) -> None:
        guards = [(n, a, old) for n, a, old, _ in patch.STOCK_PATCHES] + list(patch.STOCK_GUARDS)
        for name, address, _ in guards:
            with self.subTest(anchor=name):
                bad = bytearray(self.stock)
                bad[address] ^= 1
                before = bytes(bad)
                with self.assertRaises(SystemExit):
                    patch.apply_to_rom(bad)
                self.assertEqual(bytes(bad), before)

    def test_refuses_wrong_size_and_repeat_application(self) -> None:
        with self.assertRaises(SystemExit):
            patch.apply_to_rom(bytearray(8))
        patched = bytearray(self.stock)
        patch.apply_to_rom(patched)
        before = bytes(patched)
        with self.assertRaises(SystemExit):
            patch.apply_to_rom(patched)
        self.assertEqual(bytes(patched), before)

    def test_negative_control_missing_zero_instruction_is_detected(self) -> None:
        mutated = bytearray(self.patched_image())
        mutated[patch.PURGE_SUBTRACTION_ENTRY:patch.PURGE_SUBTRACTION_ENTRY + 2] = b"\x00\x09"
        cpu = LeafMachine(bytes(mutated), patch.PURGE_SUBTRACTION_ENTRY)
        cpu.r[4] = patch.PURGE_BANK_SUBTRACTION_ADDRS[0]
        cpu.run(cpu.STOP)
        self.assertNotEqual(cpu.writes, [(patch.PURGE_BANK_SUBTRACTION_ADDRS[0], 4, 0)])


def verify_execution(image: bytes) -> None:
    """Run focused checks against a supplied integrated ROM without writes."""
    global IMAGE
    previous = IMAGE
    IMAGE = image
    try:
        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(PurgeDeleteTests).run(result)
        if not result.wasSuccessful():
            details = "\n".join(f"{test}\n{trace}" for test, trace in result.failures + result.errors)
            raise AssertionError("Purge delete regression failed:\n" + details)
    finally:
        IMAGE = previous


if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        IMAGE = Path(sys.argv.pop(1)).read_bytes()
    unittest.main(verbosity=2)
