#!/usr/bin/env python3
"""Execute stock primary OL target and final fuel composer under the master guard.

22454, 1DD04 and their scalar math/clamp helpers execute real ROM instructions.
Stock table helpers 209C/2150 are descriptor/interpolation models with poisoned
scratch registers. This is a fuel-value/ABI audit, not injector scheduling,
closed-loop convergence, hardware timing, or a calibration validation.
"""
from io import StringIO
from itertools import product
from pathlib import Path
import random
import sys
import unittest

from test_wideband_fuel_guard_execution import GuardMachine, safety, bits, number, signed
import sh2e_test_fpu as fpu

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
COMPOSER = 0x1DD04
TARGET_WRITES = {(a, 4) for a in (0xFFFFBE04, 0xFFFFBE20, 0xFFFFBE24,
                                0xFFFFBE00, 0xFFFFBDFC, 0xFFFFBDF8)} | {
    (0xFFFFBE1A, 2), (0xFFFFBE14, 2), (0xFFFFBE38, 1), (0xFFFFBE39, 1), (0xFFFFBE1C, 1)}
FUEL_WRITES = {(a, 4) for a in range(0xFFFFB7DC, 0xFFFFB82C, 4)}
DELAY_WRITES = {(0xFFFFBE2C, 4), (0xFFFFBE30, 4), (0xFFFFBE38, 1),
                (0xFFFFBE14, 2), (0xFFFFBE16, 2), (0xFFFFBE1A, 2), (0xFFFFBE28, 2)}


class PrimaryFuelMachine(GuardMachine):
    def __init__(self, image):
        super().__init__(image)
        self.tables = {}
        self.table_calls = []
        for address, value in {
            0xFFFFB438: .5, 0xFFFFB3AC: 80, 0xFFFFB314: 0,
            0xFFFF851C: 1, 0xFFFFCF04: 0, 0xFFFFBE08: 0,
            0xFFFFBE0C: 1, 0xFFFFBE10: 1, 0xFFFFBE20: 0, 0xFFFFBE24: 0,
            0xFFFFBE00: 0, 0xFFFFBE04: 0, 0xFFFFBDFC: 0, 0xFFFFBDF8: 0,
        }.items():
            self.put_float(address, value)
        for address, value in {0xFFFFBE1A: 2, 0xFFFFBE14: 1, 0xFFFFBE16: 1,
                               0xFFFFBE18: 1, 0xFFFFBE28: 3000, 0xFFFFB688: 3000}.items():
            self.write(address, value, 2)
        for address in (0xFFFFB748, 0xFFFFBE39, 0xFFFFBE1C):
            self.write(address, 0, 1)

    def table(self, target, descriptor, x, y):
        nx, kind = self.read(descriptor, 2), self.read(descriptor + 2, 2)
        ax = self.array(self.read(descriptor + 4, 4), nx)
        if target == 0x209C:
            assert descriptor in (0x5FA40, 0x5F40C, 0x5F908)
            data = self.read(descriptor + 8, 4)
            if kind == 0:
                values = self.array(data, nx)
            else:
                assert kind in (0x0400, 0x0800)
                size = kind >> 10
                scale, bias = self.get_float(descriptor + 12), self.get_float(descriptor + 16)
                values = [self.read(data + i * size, size) * scale + bias for i in range(nx)]
            return self.interpolate(ax, values, x)
        assert target == 0x2150 and descriptor in (0x5FA9C, 0x5FAB8)
        ny = kind
        ay = self.array(self.read(descriptor + 8, 4), ny)
        data = self.read(descriptor + 12, 4)
        assert self.read(descriptor + 16, 4) == 0x04000000
        scale, bias = self.get_float(descriptor + 20), self.get_float(descriptor + 24)
        rows = [self.interpolate(ax, [self.read(data + row * nx + i, 1) * scale + bias
                                     for i in range(nx)], x) for row in range(ny)]
        return self.interpolate(ay, rows, y)

    def call_lookup(self, target):
        self.entered.append(target)
        if target in (0x209C, 0x2150):
            descriptor, x, y = self.r[4], number(self.fr[4]), number(self.fr[5])
            self.table_calls.append((target, descriptor, x, y))
            result = self.tables.get(descriptor)
            if result is None:
                result = self.table(target, descriptor, x, y)
            self.poison_scratch()
            # Lookup is explicitly a mathematical boundary, not instruction-executed.
            self.fr[0] = bits(result)
        else:
            assert target in (safety.PRIMARY_OL_TARGET_UPDATE, 0x2458, 0x24A0, 0x24B0, 0x24C0, 0x251C), hex(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        self.pc += 2
        handled = True
        if op & 0xFF00 == 0xC700:
            self.r[0] = ((pc + 4) & ~3) + (op & 255) * 4
        elif op & 0xF00F == 0x3003:
            self.t = signed(self.r[n], 32) >= signed(self.r[m], 32)
        elif op & 0xF00F == 0x3006:
            self.t = self.r[n] > self.r[m]
        elif op & 0xF00F == 0x3008:
            self.r[n] = (self.r[n] - self.r[m]) & 0xFFFFFFFF
        elif op & 0xF00F == 0x300C:
            self.r[n] = (self.r[n] + self.r[m]) & 0xFFFFFFFF
        elif op & 0xF00F == 0x2008:
            self.t = (self.r[n] & self.r[m]) == 0
        elif op & 0xF0FF == 0x4015:
            self.t = signed(self.r[n], 32) > 0
        elif op & 0xF00F == 0xF006:
            self.fr[n] = self.load((self.r[0] + self.r[m]) & 0xFFFFFFFF, 4)
        elif op & 0xF00F == 0xF007:
            self.write((self.r[0] + self.r[n]) & 0xFFFFFFFF, self.fr[m], record=True)
        else:
            handled = False
        if handled:
            self.instructions += 1
            assert self.instructions < self.INSTRUCTION_LIMIT
        else:
            self.pc = pc
            super().step(in_delay)

    def target(self, wrapped=True):
        self.table_calls.clear()
        self.invoke(self.read(safety.PRIMARY_OL_TASK_PTR, 4) if wrapped else safety.PRIMARY_OL_TARGET_UPDATE,
                    TARGET_WRITES)
        return self.get_float(0xFFFFBDF8), self.read(safety.CL_OL_STATE_FLAGS, 1)

    def seed_composer(self):
        for address in (0xB868, 0xB854, 0xB834, 0xB874, 0xBE40, 0xBE48, 0xD1B4,
                        0xBE60, 0xCEFC, 0xD114, 0xBE64, 0xCF00, 0xD118,
                        0xBEB8, 0xBCB8, 0xBEBC, 0xBCBC, 0xBEC0):
            self.put_float(0xFFFF0000 | address, 0)
        for address in (0xBE88, 0xB8D4, 0xB8D8, 0xBECC, 0xBED0, 0xBED4,
                        0xBED8, 0xBEDC, 0xBEE0):
            self.put_float(0xFFFF0000 | address, 1)
        for offset in range(0, 24, 4):
            self.put_float(0xFFFFCC88 + offset, 0)
            self.put_float(0xFFFFD050 + offset, 1)
        self.put_float(0xFFFFB82C, 2000)

    def compose(self):
        self.invoke(COMPOSER, FUEL_WRITES)
        return tuple(self.get_float(a) for a in range(0xFFFFB7DC, 0xFFFFB82C, 4))


class PrimaryFuelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / "master_patch/D2WD610H_master_patch.bin").read_bytes()
        stock = (ROOT / "2005 BLE MT.bin").read_bytes()
        # Observed startup FPSCR load: 0x00040001, EV/EZ both clear. This pins
        # the value-model assumption, not every context restore/exception path.
        assert cls.image[0xF510:0xF514] == bytes.fromhex("d22e426a")
        assert cls.image[0xF5CC:0xF5D0] == bytes.fromhex("00040001")
        for start, end in ((0x22454, 0x22948), (0x2458, 0x2484), (0x24A0, 0x24E0),
                           (0x251C, 0x2534), (0x1DD04, 0x1E0C8)):
            assert cls.image[start:end] == stock[start:end], f"Retained code changed at {start:#x}"

    def test_actual_tables_pressure_override_and_composer(self):
        for rpm, load, pressure, mix in product((1300, 3200, 6800), (.5, 1, 1.5, 2, 3), (315, 760, 1000), (0, .5, 1)):
            stock, guarded = PrimaryFuelMachine(self.image), PrimaryFuelMachine(self.image)
            for cpu in (stock, guarded):
                cpu.put_float(0xFFFFB544, rpm)
                cpu.put_float(0xFFFFB438, load)
                cpu.put_float(0xFFFF851C, mix)
                cpu.put_float(safety.MAP_PRESSURE, pressure)
                cpu.write(safety.CL_OL_STATE_FLAGS, 0x55, 1)
            stock_result, flags = stock.target(False)
            result, guarded_flags = guarded.target()
            self.assertEqual(result, stock_result)
            self.assertEqual(guarded_flags, flags & (0x7F if pressure >= 760 else 0xFF))
            for address, size in TARGET_WRITES - {(safety.CL_OL_STATE_FLAGS, 1)}:
                self.assertEqual(guarded.read(address, size), stock.read(address, size))
            self.assertEqual(guarded.table_calls[0][2:], (load, rpm))
            guarded.seed_composer()
            guarded.compose()
            # Independent mathematical expectation at neutral bank corrections.
            expected = 2000 * (1 + result)
            for address in range(0xFFFFB7E4, 0xFFFFB814, 4):
                self.assertAlmostEqual(guarded.get_float(address), expected, delta=.003)

    def test_table_selection_delay_gates_and_enrichment_value(self):
        # Enumerate semantic gates separately from emitted control flow. Lookup
        # values are exact binary fractions; ROM's thresholds/counts remain live.
        for cached_b_higher, mix, gate, ramp, previous, aux in product(
                (False, True), (0, .5, 1), (False, True), (0, 1), (0, .375), (0, .125)):
            cpu = PrimaryFuelMachine(self.image)
            cpu.tables = {0x5FA9C: .25, 0x5FAB8: .125}
            cpu.put_float(0xFFFFBE20, 0)
            cpu.put_float(0xFFFFBE24, .5 if cached_b_higher else 0)
            cpu.put_float(0xFFFF851C, mix)
            cpu.put_float(0xFFFFCF04, previous)
            cpu.put_float(0xFFFFBE08, aux)
            cpu.put_float(0xFFFFBE0C, 1.25)
            cpu.put_float(0xFFFFBE10, .5)
            cpu.write(0xFFFFBE16, int(gate), 2)
            cpu.write(0xFFFFBE14, ramp, 2)
            selected = .125 if cached_b_higher else .25 * (1 - mix) + .125 * mix
            main = (min(previous + (selected - previous) * ramp, 2)
                    if previous <= selected else selected) if gate else 0
            auxiliary = aux if gate and previous <= aux else 0
            expected = max(main, auxiliary) * 1.25 * .5
            result, permission = cpu.target()
            self.assertEqual(cpu.get_float(0xFFFFBE00), selected)
            self.assertAlmostEqual(cpu.get_float(0xFFFFBDFC), main, delta=1e-7)
            self.assertAlmostEqual(cpu.get_float(0xFFFFBE04), auxiliary, delta=1e-7)
            self.assertAlmostEqual(result, expected, delta=1e-7)
            self.assertEqual(bool(permission & 128), not gate or previous > selected)
            self.assertEqual(len(cpu.table_calls), 1 if cached_b_higher else 2)

    def test_pressure_transition_advances_real_stock_ramp(self):
        cpu = PrimaryFuelMachine(self.image)
        cpu.put_float(safety.MAP_PRESSURE, 800)
        cpu.put_float(0xFFFFB438, 2)
        cpu.put_float(0xFFFFB82C, 2000)
        cpu.write(0xFFFFBE14, 0, 2)
        cpu.write(0xFFFFBE18, 0, 2)  # No extra BE16/BE18 eligibility delay.
        value, permission = cpu.target()
        self.assertEqual((value, permission & 128), (0, 0))
        self.assertGreater(cpu.get_float(0xFFFFBE00), .2)
        cpu.invoke(0x22756, DELAY_WRITES)
        self.assertEqual(cpu.read(0xFFFFBE14, 2), 1)
        self.assertEqual(cpu.read(safety.CL_OL_STATE_FLAGS, 1) & 128, 0)
        value, _ = cpu.target()
        self.assertEqual(value, cpu.get_float(0xFFFFBE00))
        self.assertGreater(value, .2)
        # High MAP with a low modeled load can still select zero enrichment.
        cpu.put_float(0xFFFFB438, .5)
        self.assertEqual(cpu.target()[0], 0)

    def test_alternate_target_branch_and_threshold_hysteresis(self):
        for throttle, latched, counter, temperature, eligible in product(
                (69, 72, 75), (False, True), (2500, 2501), (119, 120), (False, True)):
            cpu = PrimaryFuelMachine(self.image)
            cpu.tables = {0x5FA9C: .25, 0x5FAB8: .25, 0x5FA40: .125}
            cpu.put_float(0xFFFFB314, throttle)
            cpu.put_float(0xFFFFB3AC, temperature)
            cpu.write(0xFFFFBE39, 0x55 | (128 if latched else 0), 1)
            cpu.write(0xFFFFBE28, counter, 2)
            cpu.write(0xFFFFBE16, int(eligible), 2)
            result, _ = cpu.target()
            active = throttle >= 75 or (throttle >= 70 and latched)
            alternate = active and counter <= 2500 and temperature >= 120 and eligible
            self.assertEqual(result, .125 if alternate else .25 if eligible else 0)
            self.assertEqual(cpu.read(0xFFFFBE39, 1), 0x55 | (128 if active else 0))
            self.assertEqual(any(call[1] == 0x5FA40 for call in cpu.table_calls), alternate)

    def test_real_delay_flags_hysteresis_and_counter_saturation(self):
        for flags, throttle, duration in product((0, 0x20, 0x40, 0x60, 0x80, 0xFF),
                                                 (0, 18, 25), (1000, 1900, 2500)):
            cpu = PrimaryFuelMachine(self.image)
            cpu.tables = {0x5F40C: 20, 0x5F908: 2000}
            cpu.put_float(0xFFFFB314, throttle)
            cpu.put_float(0xFFFFB82C, duration)
            cpu.write(safety.CL_OL_STATE_FLAGS, flags, 1)
            cpu.write(0xFFFFBE16, 65535, 2)
            expected = flags
            for value, low, high, mask in ((throttle, 16, 20, 64), (duration, 1744, 2000, 32)):
                if value <= low:
                    expected |= mask
                elif value > high:
                    expected &= ~mask
            cpu.invoke(0x22756, DELAY_WRITES)
            self.assertEqual(cpu.read(safety.CL_OL_STATE_FLAGS, 1), expected)
            self.assertEqual(cpu.read(0xFFFFBE16, 2), 0 if expected & 0x60 == 0x60 else 65535)
            self.assertEqual(cpu.read(0xFFFFBE14, 2), 0 if flags & 128 else 1)

    def test_final_bank_and_cylinder_factors_independently(self):
        rng = random.Random(0x1DD04)
        for case in range(80):
            cpu = PrimaryFuelMachine(self.image)
            cpu.seed_composer()
            common = 0
            for address in (0xB854, 0xB834, 0xB874, 0xBDF8, 0xBE40, 0xBE48, 0xD1B4):
                v = rng.choice((-.125, 0, .125, .5))
                cpu.put_float(0xFFFF0000 | address, v)
                common += v
            special = rng.choice((-.25, 0, .25))
            hot = rng.choice((.75, 1, 1.25))
            base = rng.choice((100, 2000, 10000, 300000))
            cpu.put_float(0xFFFFB868, special)
            cpu.put_float(0xFFFFBE88, hot)
            cpu.put_float(0xFFFFB82C, base)
            bank_factors, corrections = [], []
            for bank in range(2):
                additive = 1 + common
                for address, sign in ((0xCEFC, 1), (0xBE60, -1), (0xD114, 1)):
                    v = rng.choice((-.125, 0, .25))
                    cpu.put_float(0xFFFF0000 | (address + 4 * bank), v)
                    additive += sign * v
                bank_factors.append(additive)
                trim = 0
                for address in (0xB8D4 + 4 * bank, 0xBCB8 + 4 * bank, 0xBEBC + 4 * bank):
                    v = rng.choice((0, .125, .5, 1))
                    cpu.put_float(0xFFFF0000 | address, v)
                    trim += v
                corrections.append(trim)
            shared_trim = .125
            cpu.put_float(0xFFFFBEB8, shared_trim)
            corrections = [c + shared_trim for c in corrections]
            pulse = lambda v: min(262136, max(600, v))
            factor = lambda v: min(32, max(0, v))
            expected = {0xB7DC: factor(special + bank_factors[0]),
                        0xB7E0: factor(special + bank_factors[1])}
            for bank, pre, post, untrimmed in ((0, 0xB7E8, 0xB7EC, 0xB80C), (1, 0xB7E4, 0xB7F0, 0xB810)):
                raw = base * factor(special + bank_factors[bank]) * corrections[bank]
                expected.update({pre: pulse(raw), post: pulse(raw * hot),
                                 untrimmed: pulse(base * hot * bank_factors[bank])})
            for channel in range(6):
                extra, scale, balance = rng.choice((-.125, 0, .25)), rng.choice((.75, 1, 1.25)), rng.choice((.5, 1))
                cpu.put_float(0xFFFFCC88 + channel * 4, extra)
                cpu.put_float(0xFFFFBECC + channel * 4, scale)
                cpu.put_float(0xFFFFD050 + channel * 4, balance)
                channel_factor = factor(special + bank_factors[channel % 2] + extra)
                expected[0xB814 + 4 * channel] = channel_factor
                expected[0xB7F4 + 4 * channel] = pulse(base * hot * channel_factor * scale * balance * corrections[channel % 2])
            cpu.compose()
            for address, value in expected.items():
                self.assertAlmostEqual(cpu.get_float(0xFFFF0000 | address), value,
                                       delta=max(.01, abs(value) * 1e-6), msg=f"case {case}, {address:#x}")

    def test_negative_controls_detect_lost_permission_and_fuel_path(self):
        image = bytearray(self.image)
        # Clearing permission with OR instead of AND must be detected with the
        # real low-load target publisher, which sets permission first.
        start = safety.PRESSURE_OL_WRAPPER_ADDR
        offset = image.index(bytes.fromhex("c97f"), start, start + 0x80)
        image[offset:offset + 2] = bytes.fromhex("cb7f")
        cpu = PrimaryFuelMachine(image)
        cpu.put_float(safety.MAP_PRESSURE, 800)
        self.assertEqual(cpu.target()[1] & 128, 128)
        image = bytearray(self.image)
        self.assertEqual(image[0x1DD36:0x1DD38], bytes.fromhex("f028"))
        image[0x1DD36:0x1DD38] = bytes.fromhex("f08d")  # Drop BDF8 from final fuel.
        cpu = PrimaryFuelMachine(image)
        cpu.seed_composer()
        cpu.put_float(0xFFFFBDF8, .25)
        cpu.compose()
        self.assertEqual(cpu.get_float(0xFFFFB7EC), 2000)
        self.assertNotEqual(cpu.get_float(0xFFFFB7EC), 2500)

    def test_native_factor_and_pulse_clamps(self):
        for enrichment, factor, pulse in ((-4, 0, 600), (0, 1, 2000), (40, 32, 64000)):
            cpu = PrimaryFuelMachine(self.image)
            cpu.seed_composer()
            cpu.put_float(0xFFFFBDF8, enrichment)
            cpu.compose()
            self.assertEqual(cpu.get_float(0xFFFFB7DC), factor)
            self.assertEqual(cpu.get_float(0xFFFFB7EC), pulse)
        cpu.put_float(0xFFFFB82C, 300000)
        cpu.compose()
        self.assertEqual(cpu.get_float(0xFFFFB7EC), 262136)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(unittest.defaultTestLoader.loadTestsFromTestCase(PrimaryFuelTests))
        if not result.wasSuccessful():
            raise SystemExit(report.getvalue())
        print(f"  Primary fueling: {result.testsRun} execution test groups passed")
    finally:
        IMAGE = previous


if __name__ == "__main__":
    if len(sys.argv) > 1:
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
