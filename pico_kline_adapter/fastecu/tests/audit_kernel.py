#!/usr/bin/env python3
"""Offline ELF/layout and protected flash-gate regression checks.

This never opens a device. The small SH-2 interpreter below executes only the
compiled flash erase/write *protected and argument-rejection* paths. Any call
to a microcode routine, MMIO access or unsupported instruction fails the test.
It is not a full CPU emulator or a qualification of real erase/programming.
"""
import argparse
import hashlib
import struct
from pathlib import Path


MASK = 0xFFFFFFFF


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


class Elf:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        h = struct.unpack_from(">16sHHIIIIIHHHHHH", self.data)
        require(h[0][:7] == b"\x7fELF\x01\x02\x01", "not ELF32 big-endian")
        require(h[2] == 42 and h[7] == 2, "not a SH-2 ELF")
        require(h[4] == 0xFFFF6004, "wrong sti04 entry point")
        self.sections = [struct.unpack_from(">IIIIIIIIII", self.data, h[6] + i * h[11])
                         for i in range(h[12])]
        self.symbols = {}
        for s in self.sections:
            if s[1] != 2:  # SHT_SYMTAB
                continue
            strings = self.sections[s[6]]
            table = self.data[strings[4]:strings[4] + strings[5]]
            for at in range(s[4], s[4] + s[5], s[9]):
                name, value, size, _, _, _ = struct.unpack_from(">IIIBBH", self.data, at)
                name = table[name:].split(b"\0", 1)[0].decode()
                if name:
                    self.symbols[name] = (value, size)

    def symbol(self, name):
        return self.symbols[name][0]


class ProtectedSH2:
    """Fail-closed subset needed by GCC's protected eb/wb paths."""
    def __init__(self, elf, image):
        self.memory = dict.fromkeys(range(0xFFFF6000, 0xFFFFE000), 0)
        self.memory.update(enumerate(image, 0xFFFF6004))
        self.r = [0] * 16
        self.r[15] = elf.symbol("_stackinit")
        self.t = False
        self.pr = 0

    def read(self, address, width):
        require(all(address + i in self.memory for i in range(width)),
                f"unexpected read/MMIO at {address:08x}")
        return int.from_bytes(bytes(self.memory[address + i] for i in range(width)), "big")

    def write_stack(self, address, value):
        require(0xFFFFC000 <= address <= 0xFFFFCFFC,
                f"unexpected non-stack write at {address:08x}")
        self.memory.update(enumerate((value & MASK).to_bytes(4, "big"), address))

    def execute(self, pc, delay=False):
        op = self.read(pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        next_pc = pc + 2

        def branch(target, delayed):
            require(not delay, "branch inside delay slot")
            if delayed:
                require(self.execute(pc + 2, True) == pc + 4, "bad delay slot")
            return target

        if op == 0x0009:
            pass
        elif op == 0x000B:  # RTS + delay slot
            return branch(self.pr, True)
        elif op & 0xF000 == 0xE000:
            self.r[n] = signed(op & 255, 8) & MASK
        elif op & 0xF000 == 0xD000:
            self.r[n] = self.read(((pc + 4) & ~3) + (op & 255) * 4, 4)
        elif op & 0xF000 == 0x9000:
            self.r[n] = signed(self.read(pc + 4 + (op & 255) * 2, 2), 16) & MASK
        elif op & 0xF00F == 0x6003:
            self.r[n] = self.r[m]
        elif op & 0xF00F == 0x6000:
            self.r[n] = signed(self.read(self.r[m], 1), 8) & MASK
        elif op & 0xF00F == 0x6006:
            self.r[n] = self.read(self.r[m], 4)
            if n != m:
                self.r[m] = (self.r[m] + 4) & MASK
        elif op & 0xF00F == 0x2006:
            self.r[n] = (self.r[n] - 4) & MASK
            self.write_stack(self.r[n], self.r[m])
        elif op & 0xF0FF == 0x4022:
            self.r[n] = (self.r[n] - 4) & MASK
            self.write_stack(self.r[n], self.pr)
        elif op & 0xF0FF == 0x4026:
            self.pr = self.read(self.r[n], 4)
            self.r[n] = (self.r[n] + 4) & MASK
        elif op & 0xF000 == 0x7000:
            self.r[n] = (self.r[n] + signed(op & 255, 8)) & MASK
        elif op & 0xF00F == 0x3008:
            self.r[n] = (self.r[n] - self.r[m]) & MASK
        elif op & 0xF00F == 0x2009:
            self.r[n] &= self.r[m]
        elif op & 0xF00F == 0x2008:
            self.t = not (self.r[n] & self.r[m])
        elif op & 0xF00F == 0x3000:
            self.t = self.r[n] == self.r[m]
        elif op & 0xF00F == 0x3006:
            self.t = self.r[n] > self.r[m]
        elif op & 0xF00F == 0x3002:
            self.t = self.r[n] >= self.r[m]
        elif op & 0xFF00 == 0x8800:
            self.t = self.r[0] == (signed(op & 255, 8) & MASK)
        elif op & 0xFF00 == 0xC800:
            self.t = not (self.r[0] & (op & 255))
        elif op & 0xF0FF == 0x4010:
            self.r[n] = (self.r[n] - 1) & MASK
            self.t = self.r[n] == 0
        elif op & 0xFF00 in (0x8900, 0x8B00, 0x8D00, 0x8F00):
            delayed = bool(op & 0x0400)
            take = self.t if not (op & 0x0200) else not self.t
            target = pc + 4 + signed(op & 255, 8) * 2
            return branch(target if take else pc + (4 if delayed else 2), delayed)
        elif op & 0xF000 == 0xA000:
            return branch(pc + 4 + signed(op & 0xFFF, 12) * 2, True)
        else:
            raise AssertionError(f"unexpected instruction/call {op:04x} at {pc:08x}")
        return next_pc

    def run(self, address, arguments):
        self.r[4:4 + len(arguments)] = arguments
        initial_sp = self.r[15]
        pc = address
        for _ in range(1000):
            pc = self.execute(pc)
            if pc == 0:
                require(self.r[15] == initial_sp, "stack not restored")
                return self.r[0]
        raise AssertionError("protected path did not return")


def audit(elf_path, binary_path):
    elf = Elf(elf_path)
    image = Path(binary_path).read_bytes()
    require(0 < len(image) <= 0x1FFC, "payload overlaps flash microcode")
    rebuilt = bytearray(len(image))
    for s in elf.sections:
        if not s[2] & 2 or not s[5]:  # SHF_ALLOC, nonempty
            continue
        address, size = s[3], s[5]
        if s[1] == 8:  # SHT_NOBITS
            require(0xFFFF9000 <= address < address + size <= 0xFFFFC000,
                    "BSS outside reserved DATA region")
        else:
            require(0xFFFF6004 <= address < address + size <= 0xFFFF8000,
                    "loaded section outside CODE region")
            offset = address - 0xFFFF6004
            rebuilt[offset:offset + size] = elf.data[s[4]:s[4] + size]
    require(bytes(rebuilt) == image, "binary does not match ELF loaded sections")
    require(elf.symbol("_stackinit") == 0xFFFFCFFC, "wrong stack")
    require(elf.symbol("_sbss") == 0xFFFF9000, "wrong BSS start")
    require(elf.symbol("_ebss") <= 0xFFFFC000, "BSS overlaps 4 KiB stack")
    require(elf.symbols["_flashbuffer"][1] == 0x1000, "wrong flash buffer size")
    require(image[:4] == b"\0\x09\0\x09", "missing entry NOPs")
    require(b"FastECU SH7055 180nm D2WD610H K-Line v1.01\0" in image, "wrong ID")

    starts = [i * 0x1000 for i in range(8)] + [0x8000] + [i * 0x10000 for i in range(1, 8)]
    cases = [("_platf_flash_eb", [a], 0) for a in starts]
    cases += [("_platf_flash_eb", [a], 0x8C) for a in (1, 0x8001, 0x7FFFF, 0x80000, MASK)]
    source = elf.symbol("_flashbuffer")
    cases += [("_platf_flash_wb", [0, source, 0x1000], 0),
              ("_platf_flash_wb", [0x7F000, source, 0x1000], 0),
              ("_platf_flash_wb", [0x7FF80, source, 0x80], 0),
              ("_platf_flash_wb", [0x7FF80, source, 0x1000], 0x88),
              ("_platf_flash_wb", [0x80000, source, 0x80], 0x88),
              ("_platf_flash_wb", [0, source, MASK], 0x88),
              ("_platf_flash_wb", [1, source, 0x80], 0x89),
              ("_platf_flash_wb", [0, source, 1], 0x8A)]
    for function, args, expected in cases:
        machine = ProtectedSH2(elf, image)
        actual = machine.run(elf.symbol(function), args)
        require(actual == expected, f"{function}{args}: got {actual:x}, expected {expected:x}")
    rejected = [case for case in cases if case[2] != 0]
    for function, args, expected in rejected:
        machine = ProtectedSH2(elf, image)
        machine.memory[elf.symbol("_reflash_enabled")] = 1
        actual = machine.run(elf.symbol(function), args)
        require(actual == expected, f"enabled {function}{args}: unsafe argument rejection")
    print(f"PASS: SH-2 BE, payload {len(image)} bytes, reserved microcode/BSS/stack layout")
    print(f"PASS: {len(cases)} compiled protected/rejected flash paths, no calls or MMIO writes")
    print(f"PASS: {len(rejected)} invalid-address/length paths also reject with flash enabled")
    print(f"SHA256 {hashlib.sha256(image).hexdigest()}")
    print("Offline checks only; actual microcode initialization/erase/programming not exercised.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    audit(args.elf, args.binary)
