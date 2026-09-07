#!/usr/bin/env python3
"""Execute retained O2-adder/feedback-target opcodes; audit lambda identity.

49B20 is instruction-executed using the existing independent SH decoder plus
the extra stock opcodes below. Its two external helper results are enumerated,
not instruction-emulated: this covers gate outcomes, not their physical timing.
20564 and 202B8, including their clamp helper 24C0, are also executed. The
20564 voltage lookup is decoded/interpolated from the ROM descriptor, not
instruction-emulated. Tests enumerate bank-offset gates and independently
vary the legacy voltage trim and every other feedback-target input.
The atmospheric lookup is a Q15 interpolation model pinned to the stock
descriptor/consumer. No whole-ECU, closed-loop stability or engine claim.
"""
from itertools import product
from io import StringIO
from pathlib import Path
import struct
import sys
import unittest

import wideband_component as patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "speed_density"))
from test_hook_execution import Machine, bits, number, signed

STOCK = Path(__file__).resolve().parent.parent / "2005 BLE MT.bin"
IMAGE = None


class AuxiliaryMachine(Machine):
    def __init__(self, image, inhibit, counter, gates, mode, volts, lambdas):
        super().__init__()
        self.image = image
        self.memory.clear()
        self.pc = 0x49B20
        self.mode = mode
        self.gates = iter(gates)
        self.write(0xFFFFD110, inhibit, 1)
        self.write(0xFFFFB90C, counter, 1)
        for a, v in zip((0xFFFFABCC, 0xFFFFABD0), volts):
            self.put_float(a, v)
        for a, v in zip((0xFFFFB4E8, 0xFFFFB4EC), lambdas):
            self.put_float(a, v)
        for a in (0xFFFFBDF8, 0xFFFFBE48):
            self.put_float(a, 0)
        for a in (0xFFFFD114, 0xFFFFD118):
            self.put_float(a, float("nan"))

    def read(self, address, size):
        if 0 <= address <= len(self.image) - size:
            return int.from_bytes(self.image[address:address + size], "big")
        return super().read(address, size)

    def call_lookup(self, target):
        if target == 0x18CF4:
            self.r[0] = self.mode
        elif target == 0x24FC:
            self.r[0] = next(self.gates)
        else:
            raise AssertionError(f"Unexpected stock helper {target:#x}")

    def step(self, in_delay=False):
        pc = self.pc
        op = self.read(pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        handled = True
        self.pc += 2
        if op & 0xF000 == 0x9000:
            self.r[n] = signed(self.read(pc + 4 + (op & 255) * 2, 2), 16) & 0xFFFFFFFF
        elif op & 0xF000 == 0xE000:
            self.r[n] = signed(op & 255, 8) & 0xFFFFFFFF
        elif op & 0xF000 == 0x7000:
            self.r[n] = (self.r[n] + signed(op & 255, 8)) & 0xFFFFFFFF
        elif op & 0xFF00 == 0xC700:
            self.r[0] = ((pc + 4) & ~3) + (op & 255) * 4
        elif op & 0xF00F == 0x6006:
            self.r[n] = self.load(self.r[m], 4)
            self.r[m] += 4
        elif op & 0xF00F == 0x600C:
            self.r[n] = self.r[m] & 255
        elif op & 0xF0FF == 0x4015:
            self.t = signed(self.r[n], 32) > 0
        elif op & 0xF00F == 0x2008:
            self.t = (self.r[n] & self.r[m]) == 0
        elif op & 0xFF00 == 0x8000:
            self.write(self.r[m] + (op & 15), self.r[0] & 255, 1, record=True)
        elif op & 0xFF00 == 0x8400:
            self.r[0] = signed(self.load(self.r[m] + (op & 15), 1), 8) & 0xFFFFFFFF
        elif op & 0xF00F == 0x2000:
            self.write(self.r[n], self.r[m] & 255, 1, record=True)
        elif op & 0xF00F == 0xF006:
            self.fr[n] = self.load(self.r[0] + self.r[m], 4)
        elif op & 0xF00F == 0xF007:
            self.write(self.r[0] + self.r[n], self.fr[m], record=True)
        elif op & 0xFF00 in (0x8D00, 0x8F00):
            assert not in_delay
            taken = self.t == ((op & 0xFF00) == 0x8D00)
            self.step(in_delay=True)
            if taken:
                self.pc = pc + 4 + signed(op & 255, 8) * 2
        else:
            handled = False
        if handled:
            self.instructions += 1
            assert self.instructions < 1000
        else:
            self.pc = pc
            super().step(in_delay)

    def run(self):
        while self.pc != self.STOP:
            self.step()
        assert self.r[15] == self.STACK and self.pr == self.STOP
        assert self.r[8:15] == self.original_r[8:15]
        assert self.fr[12:] == self.original_fr[12:]
        outputs = (0xFFFFD114, 0xFFFFD118)
        for a, _ in self.writes:
            assert a in outputs or self.STACK - 64 <= a < self.STACK
        assert all(self.writes.count((a, 4)) == 1 for a in outputs)
        return tuple(self.get_float(a) for a in outputs)


class TargetMachine(AuxiliaryMachine):
    """Execute the two retained target consumers with actual bank descriptors."""

    def __init__(self, image, entry, bank):
        Machine.__init__(self)
        self.image = image
        self.memory.clear()
        self.pc = entry
        self.bank = bank
        self.r[4] = 0x4B27C + bank * 16
        self.r[5] = bank
        self.outputs = ()

    def call_lookup(self, target):
        if target == 0x24C0:
            # Execute the real clamp, including its delay slots and FR7 use.
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        elif target == 0x209C:
            descriptor = self.r[4]
            assert descriptor == 0x5F2E8
            count = self.read(descriptor, 2)
            assert self.read(descriptor + 2, 2) == 0x0400
            axis = self.array(self.read(descriptor + 4, 4), count)
            data = self.read(descriptor + 8, 4)
            scale = self.get_float(descriptor + 12)
            bias = self.get_float(descriptor + 16)
            values = [self.read(data + i, 1) * scale + bias for i in range(count)]
            self.fr[0] = bits(self.interpolate(axis, values, number(self.fr[4])))
        else:
            raise AssertionError(f"Unexpected target helper {target:#x}")

    def step(self, in_delay=False):
        pc = self.pc
        op = self.read(pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        handled = True
        self.pc += 2
        if op & 0xF000 == 0x5000:
            self.r[n] = self.load(self.r[m] + (op & 15) * 4, 4)
        elif op & 0xF00F == 0x6002:
            self.r[n] = self.load(self.r[m], 4)
        elif op & 0xF00F == 0x6001:
            self.r[n] = signed(self.load(self.r[m], 2), 16) & 0xFFFFFFFF
        elif op & 0xF00F == 0x600D:
            self.r[n] = self.r[m] & 65535
        else:
            handled = False
        if handled:
            self.instructions += 1
            assert self.instructions < 1000
        else:
            self.pc = pc
            super().step(in_delay)

    def run(self):
        while self.pc != self.STOP:
            self.step()
        assert self.r[15] == self.STACK and self.pr == self.STOP
        assert self.r[8:15] == self.original_r[8:15]
        assert self.fr[12:] == self.original_fr[12:]
        for a, size in self.writes:
            assert (a, size) in self.outputs or self.STACK - 64 <= a < self.STACK
        assert all(self.writes.count(output) == 1 for output in self.outputs)


def bank_offset(image, bank, stopped, hold, counter, volts):
    cpu = TargetMachine(image, 0x20564, bank)
    cpu.r[5] = cpu.r[4]
    cpu.r[4] = 0x4B2CC + bank * 16
    flag, output = 0xFFFFB918 + bank, 0xFFFFB900 + bank * 4
    cpu.outputs = ((flag, 1), (output, 4))
    cpu.write(0xFFFFBCAB, stopped, 1)
    cpu.write(0xFFFFB90C, hold, 1)
    cpu.write(0xFFFFBB64 + bank * 2, counter, 2)
    cpu.put_float(0xFFFFBC64 + bank * 4, volts)
    cpu.write(flag, 255, 1)
    cpu.put_float(output, float("nan"))
    cpu.run()
    return cpu.read(flag, 1), cpu.get_float(output)


def feedback_target(image, bank, voltage_trim, other_terms):
    cpu = TargetMachine(image, 0x202B8, bank)
    output = 0xFFFFB8F4 + bank * 4
    cpu.outputs = ((output, 4),)
    # Both legacy trim channels are initialized, but neither may be read in
    # the patched target. The other bank deliberately has a different value.
    for a in (0xFFFFBD04, 0xFFFFBD08):
        cpu.put_float(a, -99)
    trim_address = 0xFFFFBD04 + bank * 4
    cpu.put_float(trim_address, voltage_trim)
    # BB50/54 - BB60 + B900/04 + B8FC - B910/14 + B908.
    addresses = (0xFFFFBB50 + bank * 4, 0xFFFFBB60,
                 0xFFFFB900 + bank * 4, 0xFFFFB8FC,
                 0xFFFFB910 + bank * 4, 0xFFFFB908)
    for a, value in zip(addresses, other_terms):
        cpu.put_float(a, value)
    cpu.put_float(output, float("nan"))
    cpu.run()
    return cpu.get_float(output), cpu.reads[trim_address]


class StockSensorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = STOCK.read_bytes()
        image = bytearray(cls.stock)
        patch.apply_stock_sensor_corrections(image)
        cls.patched = bytes(image)
        cls.execution_image = IMAGE if IMAGE is not None else cls.patched
        patch.check_stock_sensor_consumers(cls.execution_image)
        for _, a, _, data in patch.STOCK_SENSOR_PATCHES:
            assert cls.execution_image[a:a + len(data)] == data

    def test_auxiliary_adder_zero_across_all_gate_outcomes_and_banks(self):
        signals = [((0, 0), (1.2, 1.2)), ((0, .5), (1.2, 1.2)),
                   ((.5, 0), (1.2, 1.2)), ((0, 0), (1, 1.2)),
                   ((0, 0), (1.2, 1)), ((float("nan"), 5), (float("nan"), 1.3))]
        for inhibit, counter, g1, g2, mode in product((0, 1), repeat=5):
            for volts, lambdas in signals:
                cpu = AuxiliaryMachine(self.execution_image, inhibit, counter, (g1, g2), mode, volts, lambdas)
                self.assertEqual(cpu.run(), (0, 0))

    def test_stock_and_each_restored_adder_are_positive_negative_controls(self):
        for mode, a in ((0, 0x76384), (1, 0x76388)):
            mutated = bytearray(self.patched)
            mutated[a:a + 4] = self.stock[a:a + 4]
            for image in (self.stock, bytes(mutated)):
                cpu = AuxiliaryMachine(image, 0, 1, (0, 0), mode, (0, 0), (1.2, 1.2))
                self.assertEqual(cpu.run(), (.25, .25))

    def test_external_lambda_identity_across_barometric_axis(self):
        # Descriptor: 4 knots, uint16 Q15, axis/data pointers and scale/bias.
        self.assertEqual(self.stock[0x5EA2C:0x5EA40],
                         bytes.fromhex("0004080000073df800073e083800000000000000"))
        axis = struct.unpack_from(">4f", self.stock, 0x73DF8)
        coefficients = [v / 32768 for v in struct.unpack_from(">4H", self.execution_image, 0x73E08)]
        for baro in (300, *axis, 570, 720, 760, 850):
            k = Machine.interpolate(axis, coefficients, baro)
            for lam in (.76, .9, 1, 1.1, 1.29):
                self.assertAlmostEqual(1 + (lam - 1) * k, lam)
        old = [v / 32768 for v in struct.unpack_from(">4H", self.stock, 0x73E08)]
        self.assertGreater(1 + .2 * Machine.interpolate(axis, old, 720), 1.2)

    def test_bank_voltage_offset_zero_across_gates_banks_and_voltage_range(self):
        # This ROM's five uint8 values are all 61 * 0.0048828125.
        threshold = 61 * .0048828125
        volts = (0, .1, threshold - 1e-5, threshold, .3, .45, .7, 1, 5)
        for bank, stopped, hold, counter, voltage in product(
            (0, 1), (0, 1, 2), (0, 1, 120), (0, 1, 654), volts
        ):
            active = int(stopped != 1 and hold == 0 and counter > 0)
            self.assertEqual(bank_offset(self.execution_image, bank, stopped, hold, counter, voltage),
                             (active, 0))

    def test_bank_offset_stock_and_restored_constant_negative_controls(self):
        restored = bytearray(self.patched)
        restored[0x760F0:0x760F4] = self.stock[0x760F0:0x760F4]
        for image, bank in product((self.stock, bytes(restored)), (0, 1)):
            flag, correction = bank_offset(image, bank, 0, 0, 1, 0)
            self.assertEqual(flag, 1)
            self.assertAlmostEqual(correction, -.04)
            self.assertEqual(bank_offset(image, bank, 0, 0, 1, .5), (1, 0))
            self.assertEqual(bank_offset(image, bank, 0, 1, 1, 0), (0, 0))
            # 452B8's reciprocal with common B8FC=0 and unit gains:
            self.assertAlmostEqual(1 / (1 + correction) - 1, 1 / .96 - 1)

    def test_target_ignores_voltage_trim_preserves_each_other_input_and_clamps(self):
        restored = bytearray(self.execution_image)
        for _, a, original, _ in patch.STOCK_SENSOR_CODE_PATCHES:
            restored[a:a + len(original)] = original
        scenarios = [(0,) * 6, (.02, .01, -.02, .01, .03, .02)]
        for i, value in product(range(6), (-.2, -.02, .02, .2)):
            terms = [0] * 6
            terms[i] = value
            scenarios.append(tuple(terms))
        lower, upper = struct.unpack_from(">2f", self.stock, 0x760D0)
        for bank, trim, terms in product((0, 1), (-.5, -.04, 0, .04, .5, float("nan")), scenarios):
            actual, trim_reads = feedback_target(self.execution_image, bank, trim, terms)
            control, control_reads = feedback_target(bytes(restored), bank, 0, terms)
            self.assertEqual(actual, control)
            self.assertEqual(trim_reads, 0)
            self.assertEqual(control_reads, 1)
            target = 1 + terms[0] - terms[1] + terms[2] + terms[3] - terms[4] + terms[5]
            self.assertAlmostEqual(actual, min(upper, max(lower, target)), places=6)

    def test_target_stock_and_each_restored_instruction_negative_controls(self):
        for bank, (_, a, original, _) in enumerate(patch.STOCK_SENSOR_CODE_PATCHES):
            restored = bytearray(self.patched)
            restored[a:a + len(original)] = original
            for image in (self.stock, bytes(restored)):
                target, reads = feedback_target(image, bank, -.04, (0,) * 6)
                self.assertAlmostEqual(target, .96)
                self.assertEqual(reads, 1)
            self.assertEqual(feedback_target(self.execution_image, bank, -.04, (0,) * 6), (1, 0))

    def test_exact_data_ownership_and_atomic_guard_refusals(self):
        allowed = {a + i for _, a, _, data in patch.STOCK_SENSOR_PATCHES for i in range(len(data))}
        changed = {i for i, (a, b) in enumerate(zip(self.stock, self.patched)) if a != b}
        self.assertEqual(len(changed), 16)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(len(allowed), 24)
        for a in (0x18DAC, 0x49B20, 0x5EA2C, 0x73E08, 0x76384,
                  0x20564, 0x20678, 0x760F0, 0x760F4, 0x4B27C, 0x4B2CC,
                  0x5F2E8, 0x202CC, 0x202D0, 0x202D2, 0x203C2, 0x24C0):
            mutated = bytearray(self.stock)
            mutated[a] ^= 1
            before = bytes(mutated)
            with self.assertRaises(SystemExit):
                patch.apply_stock_sensor_corrections(mutated)
            self.assertEqual(bytes(mutated), before)


def verify_execution(image):
    global IMAGE
    previous = IMAGE
    IMAGE = image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(StockSensorTests)
        )
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
    finally:
        IMAGE = previous


if __name__ == "__main__":
    if len(sys.argv) == 2 and not sys.argv[1].startswith("-"):
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
