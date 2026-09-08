#!/usr/bin/env python3
"""Execute retained load-change compensation B874 and final fuel composition.

The 1E7E8 family, scalar helpers and flag getters execute ROM instructions.
Table interpolation is a mathematical boundary. Inputs/timing are fixtures;
this does not simulate an engine or recover unlogged ECU state.
"""
from io import StringIO
from itertools import product
from pathlib import Path
import unittest

from test_primary_fueling_execution import PrimaryFuelMachine, number, signed

ROOT = Path(__file__).resolve().parent.parent
ENTRY = 0x1E7E8
IMAGE = None
TRANSIENT_WRITES = {(a, 4) for a in range(0xFFFFB874, 0xFFFFB8CC, 4)} | {
    (0xFFFFB8B4, 2), *((a, 1) for a in range(0xFFFFB8CC, 0xFFFFB8D1))}
DESCRIPTORS = {
    0x5F6F8, 0x5F70C, 0x5F5E0, 0x5F680, 0x5F608, 0x5F694,
    0x5F5F4, 0x5F6A8, 0x5F61C, 0x5F6BC, 0x5F2A0, 0x5F630,
    0x5F644, 0x5F658, 0x5F66C, 0x5F6D0, 0x5F6E4,
}
NATIVE = {0x1ADD8, 0x15192, 0x19C40, 0x19C68, 0x1E9E4, 0x1EAD4,
          0x1EC62, 0x2424, 0x2450, 0x24FC, 0x2534}


class TransientFuelMachine(PrimaryFuelMachine):
    def __init__(self, image, load=.75, rpm=1250, coolant=35):
        super().__init__(image)
        for address in range(0xFFFFB874, 0xFFFFB8D1):
            self.write(address, 0, 1)
        for address in (0xFFFFB6B8, 0xFFFFB2BC, 0xFFFFB51E, 0xFFFFB51C,
                        0xFFFFBF20):
            self.write(address, 0, 1)
        for address in (0xFFFFB878, 0xFFFFB8B8, 0xFFFFB8BC, 0xFFFFB8C0, 0xFFFFB8C4):
            self.put_float(address, load)
        for address in (0xFFFFB890, 0xFFFFB894):
            self.put_float(address, 1)
        self.put_float(0xFFFFB438, load)
        self.put_float(0xFFFFB544, rpm)
        self.put_float(0xFFFFB3AC, coolant)
        self.put_float(0xFFFFB3B0, 29)
        self.write(0xFFFFB688, 15000, 2)

    def table(self, target, descriptor, x, y):
        if descriptor not in DESCRIPTORS:
            return super().table(target, descriptor, x, y)
        assert target == 0x209C
        n, kind = self.read(descriptor, 2), self.read(descriptor + 2, 2)
        axis = self.array(self.read(descriptor + 4, 4), n)
        data = self.read(descriptor + 8, 4)
        assert kind in (0x400, 0x800)
        size = kind >> 10
        scale, bias = self.get_float(descriptor + 12), self.get_float(descriptor + 16)
        values = [self.read(data + i * size, size) * scale + bias for i in range(n)]
        return self.interpolate(axis, values, x)

    def call_lookup(self, target):
        if target in NATIVE:
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        elif target == 0x20E0:
            # Byte-valued 1-axis lookup. Its descriptor has no float scale/bias.
            descriptor, x = self.r[4], number(self.fr[4])
            assert descriptor == 0x5F2B4
            n = self.read(descriptor, 2)
            axis = self.array(self.read(descriptor + 4, 4), n)
            data = self.read(descriptor + 8, 4)
            value = int(self.interpolate(axis, [self.read(data + i, 1) for i in range(n)], x))
            self.table_calls.append((target, descriptor, x, None))
            self.poison_scratch()
            self.r[0] = value
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        self.pc += 2
        if op & 0xF000 == 0xB000:
            assert not in_delay
            self.pr = pc + 4
            self.step(in_delay=True)
            self.call_lookup(pc + 4 + signed(op & 0xFFF, 12) * 2)
            self.pc = self.pr
        elif op & 0xFF00 == 0x8100:
            self.write(self.r[m] + (op & 15) * 2, self.r[0], 2, record=True)
        elif op & 0xFF00 == 0x8500:
            self.r[0] = signed(self.load(self.r[m] + (op & 15) * 2, 2), 16) & 0xFFFFFFFF
        elif op & 0xF0FF == 0xF01D:
            self.fpul = self.fr[n]
        elif op & 0xF0FF == 0x005A:
            self.r[n] = self.fpul
        elif op & 0xF0FF == 0xF05D:
            self.fr[n] &= 0x7FFFFFFF
        elif op & 0xF00F == 0x3000:
            self.t = self.r[n] == self.r[m]
        else:
            self.pc = pc
            return super().step(in_delay)
        self.instructions += 1
        assert self.instructions < 2000

    def transient(self, load=None, rpm=None, coolant=None):
        for address, value in ((0xFFFFB438, load), (0xFFFFB544, rpm), (0xFFFFB3AC, coolant)):
            if value is not None:
                self.put_float(address, value)
        self.table_calls.clear()
        self.invoke(ENTRY, TRANSIENT_WRITES)
        return self.get_float(0xFFFFB874)


class TransientFuelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x1E7E8, 0x1EE0C), (0x2424, 0x2458), (0x24FC, 0x2560),
                           (0x15192, 0x151A6), (0x1ADD8, 0x1ADEC),
                           (0x19C40, 0x19C54), (0x19C68, 0x19C7C),
                           (0x82B6, 0x82E0), (0x87F2, 0x8990),
                           (0xCF7E, 0xCFA4), (0x696C, 0x6980)):
            assert cls.image[start:end] == stock[start:end], f'Retained code changed at {start:#x}'

    def test_crank_phase_routes_six_updates_per_cycle(self):
        # 24 native 30-degree slots per 720-degree cycle; only these six
        # dispatch task 6 via 82B6 -> FBC4/CF7E -> 696C -> 11AD0.
        self.assertEqual(self.image[0xFA7C:0xFA94], bytes.fromhex(
            '00ffffff01ffffff02ffffff03ffffff04ffffff05ffffff'))
        for address, pointer in ((0x8974, 0xFA7C), (0x82DC, 0xFBC4),
                                 (0xFBC4, 0xCF7E), (0x6ABC, 0x11AD0), (0x11D70, ENTRY)):
            self.assertEqual(int.from_bytes(self.image[address:address+4], 'big'), pointer)

    def test_steady_load_neutral_across_temperature_and_rpm(self):
        for load, rpm, coolant in product((.5, .75, 1.5), (750, 1250, 2500), (20, 35, 80)):
            cpu = TransientFuelMachine(self.image, load, rpm, coolant)
            self.assertEqual(cpu.transient(), 0)
            self.assertEqual(cpu.get_float(0xFFFFB87C), 0)
            self.assertEqual(cpu.get_float(0xFFFFB880), 0)

    def test_load_change_remains_active_long_after_start(self):
        for count in (625, 15000, 60000):
            up, down = TransientFuelMachine(self.image), TransientFuelMachine(self.image)
            for cpu in (up, down):
                cpu.write(0xFFFFB688, count, 2)
            self.assertGreater(up.transient(.85), 0)
            self.assertLess(down.transient(.65), 0)
            # No counter decay causes this response: the counter is held fixed.
            self.assertEqual(down.read(0xFFFFB688, 2), count)

    def test_slow_load_memory_and_recovery(self):
        cpu = TransientFuelMachine(self.image)
        for count in range(1, 101):
            correction = cpu.transient(.53)
            expected = .53 + (.75 - .53) * .99**count
            self.assertAlmostEqual(cpu.get_float(0xFFFFB878), expected, delta=6e-6)
            if count == 4:
                first = correction
                self.assertEqual(cpu.get_float(0xFFFFB880), 0)
        self.assertLess(first, correction)
        self.assertLess(correction, 0)

    def test_startup_negative_gate_and_flag_variants(self):
        for count in (0, 14, 15, 624, 625):
            cpu = TransientFuelMachine(self.image)
            cpu.write(0xFFFFB688, count, 2)
            correction = cpu.transient(.53)
            if count < 625:
                self.assertEqual(correction, 0)
            else:
                self.assertLess(correction, 0)
        for flags in product((False, True), repeat=4):
            cpu = TransientFuelMachine(self.image)
            for (address, mask), active in zip(((0xFFFFB6B8, 128), (0xFFFFB2BC, 2),
                                              (0xFFFFB51E, 32), (0xFFFFB51C, 128)), flags):
                cpu.write(address, mask * active, 1)
            self.assertGreater(cpu.transient(.85), 0)

    def test_negative_correction_reaches_all_cylinder_durations(self):
        cpu = TransientFuelMachine(self.image)
        for _ in range(4):
            correction = cpu.transient(.53)
        cpu.seed_composer()
        cpu.put_float(0xFFFFB874, correction)
        cpu.put_float(0xFFFFB82C, 1731.3334)
        cpu.compose()
        expected = 1731.3334 * (1 + correction)
        for address in range(0xFFFFB7F4, 0xFFFFB80C, 4):
            self.assertAlmostEqual(cpu.get_float(address), expected, delta=.002)
        self.assertLess(expected, 1731.3334)

    def test_running_selector_preserves_composed_duration(self):
        cpu = TransientFuelMachine(self.image)
        cpu.write(0xFFFFB74A, 0, 1)
        for channel in range(6):
            cpu.put_float(0xFFFFB7F4 + 4 * channel, 750 + channel * 125)
        cpu.invoke(0x1CA38, {(a, 4) for a in range(0xFFFFB768, 0xFFFFB780, 4)})
        for channel in range(6):
            self.assertEqual(cpu.get_float(0xFFFFB768 + 4 * channel), 750 + channel * 125)

    def test_negative_controls_detect_removed_history_or_contribution(self):
        import struct
        changed = bytearray(self.image)
        changed[0x76050:0x76054] = struct.pack('>f', 1)
        normal, instant = TransientFuelMachine(self.image), TransientFuelMachine(changed)
        for _ in range(4):
            a, b = normal.transient(.53), instant.transient(.53)
        self.assertLess(a, 0)
        self.assertEqual(b, 0)
        changed = bytearray(self.image)
        self.assertEqual(changed[0x1DD2E:0x1DD30], bytes.fromhex('f118'))
        changed[0x1DD2E:0x1DD30] = bytes.fromhex('f18d')
        cpu = TransientFuelMachine(changed)
        cpu.seed_composer()
        cpu.put_float(0xFFFFB874, -.5)
        cpu.compose()
        self.assertEqual(cpu.get_float(0xFFFFB7F4), 2000)
        self.assertNotEqual(cpu.get_float(0xFFFFB7F4), 1000)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TransientFuelTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Transient fuel: {result.testsRun} execution test groups passed')
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
