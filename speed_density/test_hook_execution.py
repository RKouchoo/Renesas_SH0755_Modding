#!/usr/bin/env python3
"""Execute emitted SD-wrapper SH-2E opcodes against adversarial lookup models.

This is deliberately independent of sh2_asm/sh2_disasm and the patch's Python
airflow-policy model. It decodes generated machine words, branches/delay slots,
literal loads, stack operations, FP comparisons and SH-2E round-to-zero
arithmetic, including denormal flushing and finite-overflow saturation.
Stock lookup functions are NOT instruction-emulated: their descriptors and
tables are decoded from image bytes, then linearly/bilinearly interpolated.
The lookup models poison caller-saved registers to exercise the wrapper ABI.

This checks wrapper control flow, snapshot reuse and return/stack integrity;
it does not establish stock lookup instruction timing, ADC refresh rate, ISR
interleaving, FPSCR exception delivery/flags, whole-ECU scheduling or safety.
Run: python3 speed_density/test_hook_execution.py [optional-generated-ROM.bin]
"""

from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import struct
import sys
import unittest

import patch_speed_density as patch
import sh2e_test_fpu as fpu


IMAGE: bytes | None = None


def bits(value: float) -> int:
    try:
        return struct.unpack(">I", struct.pack(">f", value))[0]
    except OverflowError:
        return 0xFF800000 if value < 0 else 0x7F800000


def number(value: int) -> float:
    return struct.unpack(">f", struct.pack(">I", value & 0xFFFFFFFF))[0]


def f32(value: float) -> float:
    return number(bits(value))


def signed(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return (value ^ sign) - sign


class Machine:
    """Small fail-closed decoder: an unknown emitted opcode fails the test."""

    STOP = 0xDEADBEE0
    STACK = 0xFFFFE000
    INSTRUCTION_LIMIT = 2000
    OUTPUTS = (patch.FINAL_MASS_AIRFLOW_ADDR, patch.SYNTHETIC_RAW_AIRFLOW_ADDR,
               patch.SYNTHETIC_FILTER_A_ADDR, patch.SYNTHETIC_FILTER_B_ADDR)

    def __init__(self, rpm=1300.0, map_mmhg=315.0, iat=20.0, mode=0):
        self.memory = {}
        for _, address, blob in patch.build_blobs():
            if IMAGE is not None:
                blob = IMAGE[address:address + len(blob)]
            for offset, byte in enumerate(blob):
                self.memory[address + offset] = byte
        self.r = [0x11000000 + i * 0x101 for i in range(16)]
        self.r[15] = self.STACK
        self.fr = [bits(80.0 + i * 7.0) for i in range(16)]
        self.fr[15] = bits(rpm)  # Saved by retained stock caller, NOT reread RAM.
        self.pr = self.STOP
        self.t = False
        self.pc = patch.WRAPPER_ADDR
        self.instructions = 0
        self.min_sp = self.STACK
        self.writes = []
        self.reads = Counter()
        self.after_load = None
        self.lookup_override = {}
        self.calls = []
        self.put_float(patch.RPM_ADDR, 6001.0)  # Deliberately a different epoch.
        self.put_float(patch.MAP_ADDR, map_mmhg)
        self.put_float(patch.IAT_ADDR, iat)
        self.memory[patch.AVLS_COMMITTED_MODE_ADDR] = mode
        self.original_r = self.r.copy()
        self.original_fr = self.fr.copy()

    def read(self, address, size):
        try:
            return int.from_bytes(bytes(self.memory[address + i] for i in range(size)), "big")
        except KeyError as exc:
            raise AssertionError(f"Uninitialized memory read {address:#010x}/{size} at PC {self.pc:#x}") from exc

    def write(self, address, value, size=4, record=False):
        if record:
            self.writes.append((address, size))
        for i, byte in enumerate((value & ((1 << (8 * size)) - 1)).to_bytes(size, "big")):
            self.memory[address + i] = byte

    def put_float(self, address, value):
        self.write(address, bits(value))

    def get_float(self, address):
        return number(self.read(address, 4))

    def load(self, address, size):
        value = self.read(address, size)
        self.reads[address] += 1
        if self.after_load is not None:
            self.after_load(self, address, size)
        return value

    def push(self, value):
        self.r[15] -= 4
        self.min_sp = min(self.min_sp, self.r[15])
        self.write(self.r[15], value, record=True)

    def pop(self):
        value = self.load(self.r[15], 4)
        self.r[15] += 4
        return value

    def array(self, address, count):
        assert 1 <= count <= 256, "Corrupt lookup descriptor size"
        return [self.get_float(address + 4 * i) for i in range(count)]

    @staticmethod
    def interpolate(axis, values, point):
        assert all(axis[i] < axis[i + 1] for i in range(len(axis) - 1))
        if point <= axis[0]:
            return values[0]
        if point >= axis[-1]:
            return values[-1]
        for i in range(len(axis) - 1):
            if point <= axis[i + 1]:
                fraction = (point - axis[i]) / (axis[i + 1] - axis[i])
                return values[i] + fraction * (values[i + 1] - values[i])
        raise AssertionError("Lookup received invalid point")

    def lookup_value(self, target, descriptor, x, y=0.0):
        nx = self.read(descriptor, 2)
        ax = self.read(descriptor + 4, 4)
        if target == patch.TABLE_2D_LOOKUP:
            data = self.read(descriptor + 8, 4)
            return f32(self.interpolate(self.array(ax, nx), self.array(data, nx), x))
        assert target == patch.TABLE_3D_LOOKUP
        ny = self.read(descriptor + 2, 2)
        ay = self.read(descriptor + 8, 4)
        data = self.read(descriptor + 12, 4)
        rows = [self.interpolate(self.array(ax, nx), self.array(data + row * nx * 4, nx), x)
                for row in range(ny)]
        return f32(self.interpolate(self.array(ay, ny), rows, y))

    def call_lookup(self, target):
        assert target in (patch.TABLE_2D_LOOKUP, patch.TABLE_3D_LOOKUP), f"Unexpected call {target:#x}"
        descriptor = self.r[4]
        x, y = number(self.fr[4]), number(self.fr[5])
        self.calls.append((target, descriptor, x, y))
        result = self.lookup_override.get(target)
        if result is None:
            result = self.lookup_value(target, descriptor, x, y)
        # ABI-adversarial, not a claim about the exact stock helper scratch use.
        for i in range(8):
            self.r[i] = 0xA5000000 + i
        for i in range(12):
            self.fr[i] = bits(-400.0 - i)
        self.fr[0] = bits(result)
        self.t = not self.t

    def step(self, in_delay=False):
        pc = self.pc
        op = self.read(pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT, "Instruction budget exceeded"

        def delay_then(target, call=False):
            assert not in_delay, "Control transfer in delay slot"
            self.step(in_delay=True)
            if call:
                self.call_lookup(target)
                self.pc = self.pr
            else:
                self.pc = target

        if op == 0x0009:
            return
        if op == 0x4F22:
            self.push(self.pr)
        elif op == 0x4F26:
            self.pr = self.pop()
        elif op == 0x000B:
            delay_then(self.pr)
        elif op & 0xF0FF == 0x400B:
            target = self.r[n]
            self.pr = pc + 4
            delay_then(target, call=True)
        elif op & 0xF000 == 0xA000:
            delay_then(pc + 4 + signed(op & 0xFFF, 12) * 2)
        elif op & 0xFF00 in (0x8900, 0x8B00):
            assert not in_delay
            if self.t == ((op & 0xFF00) == 0x8900):
                self.pc = pc + 4 + signed(op & 0xFF, 8) * 2
        elif op & 0xF000 == 0xD000:
            self.r[n] = self.load(((pc + 4) & ~3) + (op & 0xFF) * 4, 4)
        elif op & 0xFF00 == 0x8800:
            self.t = self.r[0] == (signed(op & 0xFF, 8) & 0xFFFFFFFF)
        elif op & 0xF00F == 0x6000:
            self.r[n] = signed(self.load(self.r[m], 1), 8) & 0xFFFFFFFF
        elif op & 0xF00F == 0x6003:
            self.r[n] = self.r[m]
        elif op & 0xF00F == 0x2006:
            assert n == 15
            self.push(self.r[m])
        elif op & 0xF0FF == 0xF08D:
            self.fr[n] = bits(0.0)
        elif op & 0xF0FF == 0xF09D:
            self.fr[n] = bits(1.0)
        elif op & 0xF0FF == 0xF04D:
            self.fr[n] = fpu.negate(self.fr[n])
        elif op & 0xF00F == 0xF008:
            self.fr[n] = self.load(self.r[m], 4)
        elif op & 0xF00F == 0xF009:
            self.fr[n] = self.load(self.r[m], 4)
            self.r[m] += 4
        elif op & 0xF00F == 0xF00A:
            self.write(self.r[n], self.fr[m], record=True)
        elif op & 0xF00F == 0xF00B:
            assert n == 15
            self.push(self.fr[m])
        elif op & 0xF00F == 0xF00C:
            self.fr[n] = self.fr[m]
        elif op & 0xF00F in (0xF004, 0xF005):
            self.t = fpu.compare("eq" if (op & 15) == 4 else "gt", self.fr[n], self.fr[m])
        elif op & 0xF00F in (0xF000, 0xF001, 0xF002, 0xF003):
            self.fr[n] = fpu.binary(("add", "sub", "mul", "div")[op & 15], self.fr[n], self.fr[m])
        elif op & 0xF00F == 0xF00E:
            self.fr[n] = fpu.multiply_accumulate(self.fr[0], self.fr[m], self.fr[n])
        else:
            raise AssertionError(f"Unsupported opcode {op:04x} at {pc:#x}")

    def run(self):
        while self.pc != self.STOP:
            self.step()
        assert self.r[15] == self.STACK, "Unbalanced wrapper stack"
        assert self.pr == self.STOP, "Caller PR corrupted"
        assert self.r[8:15] == self.original_r[8:15], "Callee-saved GPR corrupted"
        assert self.fr[12:16] == self.original_fr[12:16], "Callee-saved FP register / caller RPM corrupted"
        output = self.fr[0]
        for address in self.OUTPUTS:
            assert self.read(address, 4) == output, f"Output {address:#x} inconsistent with FR0"
            assert self.writes.count((address, 4)) == 1, f"Output {address:#x} not written exactly once"
        for address, size in self.writes:
            assert address in self.OUTPUTS or self.min_sp <= address < self.STACK, f"Unexpected write {address:#x}/{size}"
        return number(output)

    def expected(self, rpm, map_mmhg, iat, mode):
        desc = patch.HIGH_VE_DESC_ADDR if mode == patch.AVLS_HIGH_MODE else patch.LOW_VE_DESC_ADDR
        value = self.lookup_value(patch.TABLE_3D_LOOKUP, desc, map_mmhg, rpm)
        for multiplier in (map_mmhg, rpm, self.get_float(patch.DISPLACEMENT_ADDR),
                           self.get_float(patch.AIRFLOW_CONSTANT_ADDR), self.get_float(patch.GLOBAL_MULTIPLIER_ADDR)):
            value = f32(value * f32(multiplier))
        correction = self.lookup_value(patch.TABLE_2D_LOOKUP, patch.IAT_DESC_ADDR, iat)
        return min(f32(correction * value), self.get_float(patch.MAX_AIRFLOW_ADDR))


class HookExecutionTests(unittest.TestCase):
    def assert_airflow(self, machine, expected):
        actual = machine.run()
        self.assertAlmostEqual(actual, expected, delta=max(abs(expected) * 2e-6, 1e-6))

    def test_valid_inputs_modes_table_edges_and_abi(self):
        for rpm, pressure, iat in ((1300, 315, 20), (3100, 760, 33), (6800, 1100, 80),
                                   (1, 100, -50), (7500, 1600, 150)):
            for mode in (0, 1, 2, 3, 4, 255):
                with self.subTest(rpm=rpm, pressure=pressure, iat=iat, mode=mode):
                    machine = Machine(rpm, pressure, iat, mode)
                    self.assert_airflow(machine, machine.expected(rpm, pressure, iat, mode))
                    self.assertEqual(machine.reads[patch.RPM_ADDR], 0)
                    self.assertEqual(machine.reads[patch.MAP_ADDR], 1)
                    self.assertEqual(machine.reads[patch.IAT_ADDR], 1)
                    self.assertEqual(len(machine.calls), 2)
                    self.assertEqual(machine.calls[0][2:], (float(pressure), float(rpm)))
                    self.assertEqual(machine.calls[1][2], float(iat))

    def test_changed_ram_after_each_snapshot_cannot_change_lookup_or_product(self):
        for mode in (0, 3):
            machine = Machine(mode=mode)
            expected = machine.expected(1300, 315, 20, mode)

            def corrupt_after_read(cpu, address, size):
                if size == 4 and address in (patch.MAP_ADDR, patch.IAT_ADDR):
                    cpu.put_float(address, math.nan)
                    cpu.put_float(patch.RPM_ADDR, -4000)

            machine.after_load = corrupt_after_read
            self.assert_airflow(machine, expected)
            self.assertEqual(machine.reads[patch.MAP_ADDR], 1)
            self.assertEqual(machine.reads[patch.IAT_ADDR], 1)
            self.assertEqual(machine.reads[patch.RPM_ADDR], 0)

    def test_zero_rpm_is_zero_even_if_other_inputs_invalid(self):
        for rpm in (0.0, -0.0):
            machine = Machine(rpm, math.nan, math.nan)
            self.assert_airflow(machine, 0.0)
            self.assertEqual(machine.calls, [])

    def test_invalid_sensor_inputs_fail_safe(self):
        cases = [("rpm", value) for value in (math.nan, math.inf, -math.inf, -1, 7501)]
        cases += [("map_mmhg", value) for value in (math.nan, math.inf, -math.inf, 99, 1601)]
        cases += [("iat", value) for value in (math.nan, math.inf, -math.inf, -51, 151)]
        for name, value in cases:
            with self.subTest(input=name, value=value):
                machine = Machine(**{name: value})
                self.assert_airflow(machine, 500.0)
                self.assertEqual(machine.calls, [])

    def test_invalid_calibrations_fail_safe(self):
        for address in (patch.GLOBAL_MULTIPLIER_ADDR, patch.DISPLACEMENT_ADDR, patch.MAX_AIRFLOW_ADDR):
            for value in (0, -1, math.nan, math.inf, -math.inf):
                with self.subTest(address=hex(address), value=value):
                    machine = Machine()
                    machine.put_float(address, value)
                    self.assert_airflow(machine, 500.0)
                    self.assertEqual(machine.calls, [])
        for address in (patch.MAP_MIN_ADDR, patch.MAP_MAX_ADDR, patch.RPM_MIN_ADDR,
                        patch.RPM_MAX_ADDR, patch.IAT_MIN_ADDR, patch.IAT_MAX_ADDR):
            for value in (math.nan, math.inf, -math.inf):
                with self.subTest(bound=hex(address), value=value):
                    machine = Machine()
                    machine.put_float(address, value)
                    self.assert_airflow(machine, 500.0)

    def test_invalid_lookup_results_unwind_every_stack_path(self):
        for target in (patch.TABLE_3D_LOOKUP, patch.TABLE_2D_LOOKUP):
            for value in (0, -1, math.nan, math.inf, -math.inf):
                with self.subTest(target=hex(target), value=value):
                    machine = Machine()
                    machine.lookup_override[target] = value
                    self.assert_airflow(machine, 500.0)
                    self.assertEqual(len(machine.calls), 1 if target == patch.TABLE_3D_LOOKUP else 2)

    def test_product_overflow_underflow_and_normal_cap(self):
        machine = Machine()
        machine.put_float(patch.GLOBAL_MULTIPLIER_ADDR, 3e38)
        self.assert_airflow(machine, 500.0)
        machine = Machine()
        machine.put_float(patch.AIRFLOW_CONSTANT_ADDR, 0.0)
        self.assert_airflow(machine, 500.0)
        machine = Machine(rpm=1, map_mmhg=100)
        machine.lookup_override[patch.TABLE_2D_LOOKUP] = number(1)
        self.assert_airflow(machine, 500.0)  # Positive f32 operands underflow to zero.
        machine = Machine()
        machine.put_float(patch.MAX_AIRFLOW_ADDR, 1.0)
        self.assert_airflow(machine, 1.0)

    def test_negative_control_detects_missing_fp_restore(self):
        machine = Machine()
        wrapper = patch.build_wrapper()
        # Redirect the first callee-saved FP pop into scratch FR1. It still
        # balances the stack but must fail the independent preserved-reg test.
        for offset in range(0, len(wrapper), 2):
            opcode = machine.read(patch.WRAPPER_ADDR + offset, 2)
            if opcode & 0xF0FF == 0xF0F9 and (opcode >> 8) & 15 >= 12:
                machine.write(patch.WRAPPER_ADDR + offset, 0xF1F9, size=2)
                break
        else:
            self.fail("No saved-FP restore found in wrapper")
        with self.assertRaisesRegex(AssertionError, "Callee-saved FP"):
            machine.run()


def verify_execution(image: bytes) -> None:
    """Run against a supplied artifact from the ordinary binary verifiers."""
    global IMAGE
    previous = IMAGE
    IMAGE = image
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(HookExecutionTests)
        result = unittest.TestResult()
        suite.run(result)
        if not result.wasSuccessful():
            details = "\n".join(str(test) + "\n" + trace
                                for test, trace in result.failures + result.errors)
            raise AssertionError("SD wrapper opcode execution failed:\n" + details)
    finally:
        IMAGE = previous


if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        IMAGE = Path(sys.argv.pop(1)).read_bytes()
    unittest.main(verbosity=2)
