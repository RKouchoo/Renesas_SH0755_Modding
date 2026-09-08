#!/usr/bin/env python3
"""Execute the retained 172A4 load-conditioning body, with explicit boundaries.

1753A..1770A executes ROM instructions and scalar helpers. The earlier airflow
producer and caller frame are fixtures; 2150 interpolation is mathematical.
This does not execute the upstream B444 flag builder or model an engine.
"""
from io import StringIO
from pathlib import Path
import struct
import unittest

from test_transient_fuel_execution import TransientFuelMachine
from test_primary_fueling_execution import bits, signed

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
LOAD_WRITES = {(a, 4) for a in range(0xFFFFB428, 0xFFFFB444, 4)}


class LoadConditioningMachine(TransientFuelMachine):
    def __init__(self, image, load=.7, rpm=1200, coolant=40):
        super().__init__(image, load, rpm, coolant)
        for a in (0xFFFFB428, 0xFFFFB42C, 0xFFFFB430, 0xFFFFB438, 0xFFFFB440):
            self.put_float(a, load)
        self.put_float(0xFFFFB434, 1)
        self.put_float(0xFFFFB43C, 0)
        self.put_float(0xFFFFB318, 0)
        self.put_float(0xFFFFB550, rpm)
        self.write(0xFFFFB444, 0, 1)

    def table(self, target, descriptor, x, y):
        if descriptor != 0x5EB6C:
            return super().table(target, descriptor, x, y)
        assert target == 0x2150
        nx, ny = self.read(descriptor, 2), self.read(descriptor + 2, 2)
        ax = self.array(self.read(descriptor + 4, 4), nx)
        ay = self.array(self.read(descriptor + 8, 4), ny)
        data = self.read(descriptor + 12, 4)
        assert self.read(descriptor + 16, 4) == 0x04000000
        scale, bias = self.get_float(descriptor + 20), self.get_float(descriptor + 24)
        rows = [self.interpolate(ax, [self.read(data + row * nx + i, 1) * scale + bias
                                     for i in range(nx)], x) for row in range(ny)]
        return self.interpolate(ay, rows, y)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        if op & 0xF00F == 0x000D:  # mov.w @(r0,Rm),Rn, sign extended.
            n, m = (op >> 8) & 15, (op >> 4) & 15
            address = (self.r[0] + self.r[m]) & 0xFFFFFFFF
            self.r[n] = signed(self.load(address, 2), 16) & 0xFFFFFFFF
            self.pc += 2
            self.instructions += 1
            assert self.instructions < self.INSTRUCTION_LIMIT
        else:
            super().step(in_delay)

    def condition(self, airflow, rpm, coolant=40, map_mmhg=310, throttle=0, flags=0):
        previous = self.get_float(0xFFFFB438)
        self.put_float(0xFFFFB420, airflow)
        self.put_float(0xFFFFB544, rpm)
        self.put_float(0xFFFFB3AC, coolant)
        self.write(0xFFFFB444, flags, 1)
        self.r = self.original_r.copy()
        self.fr = self.original_fr.copy()
        self.r[15] = frame = self.STACK - 0x80
        self.r[9], self.r[10] = 0x2150, 0x209C
        self.r[13], self.r[14] = 0xFFFFB438, 0xFFFFB444
        self.fr[12], self.fr[15] = bits(previous), bits(rpm)
        self.put_float(frame, coolant)
        self.put_float(frame + 4, map_mmhg)
        self.put_float(frame + 0x18, throttle)
        self.write(frame + 0x1C, 0, 1)  # Local patched status getter returns 0.
        self.write(frame + 0x20, 15000, 2)  # Running; native threshold is zero.
        self.write(frame + 0x24, 0, 1)  # Running selector; not startup fixture.
        self.pc, self.pr = 0x1753A, self.STOP
        self.instructions, self.min_sp = 0, frame
        self.writes.clear()
        self.reads.clear()
        self.entered.clear()
        self.table_calls.clear()
        while self.pc != 0x1770A:
            self.step()
        assert self.r[15] == frame, 'Unbalanced helper stack'
        for address, size in self.writes:
            assert (address, size) in LOAD_WRITES or self.min_sp <= address < frame, (
                hex(address), size)
        self.put_float(0xFFFFB318, throttle)
        self.put_float(0xFFFFB550, rpm)
        return self.get_float(0xFFFFB438)


class LoadConditioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x1753A, 0x17726), (0x1775E, 0x17788),
                           (0x2424, 0x2458), (0x24A0, 0x24E0), (0x73968, 0x739AC)):
            assert cls.image[start:end] == stock[start:end], hex(start)

    def test_normal_filter_six_percent_per_update_both_directions(self):
        for address, entry in ((0x11D20, 0x172A4), (0x11D70, 0x1E7E8)):
            self.assertEqual(int.from_bytes(self.image[address:address + 4], 'big'), entry)
        for target in (.3, 1.2):
            cpu = LoadConditioningMachine(self.image)
            for count in range(1, 31):
                actual = cpu.condition(target * 1200 / 60, 1200)
                expected = target + (.7 - target) * .94 ** count
                self.assertAlmostEqual(actual, expected, delta=2e-6)
                self.assertAlmostEqual(cpu.get_float(0xFFFFB42C), actual, delta=1e-7)
                self.assertEqual(cpu.get_float(0xFFFFB434), 1)

    def test_raw_limit_and_no_divide_at_zero_rpm(self):
        cpu = LoadConditioningMachine(self.image)
        cpu.condition(100, 600)
        self.assertEqual(cpu.get_float(0xFFFFB428), 4)
        cpu.condition(100, 0)
        self.assertEqual(cpu.get_float(0xFFFFB428), 4)  # Retained previous raw value.

    def test_latched_flag_holds_rising_load_and_bypasses_filter_when_falling(self):
        cpu = LoadConditioningMachine(self.image)
        self.assertAlmostEqual(cpu.condition(24, 1200, flags=0x20), .7, places=6)
        self.assertAlmostEqual(cpu.condition(6, 1200, flags=0x20), .3, places=6)
        # Normal log-range RPM forces bit 0x20 clear in the upstream builder:
        # 173AA/173AE reject ECT < 160; 174A2/174A6 clear at RPM < 10000.
        self.assertEqual(struct.unpack_from('>f', self.image, 0x73990)[0], 160)
        self.assertEqual(struct.unpack_from('>f', self.image, 0x739A8)[0], 10000)

    def test_faster_filter_changes_transient_compensation_as_well_as_base_load(self):
        faster = bytearray(self.image)
        struct.pack_into('>f', faster, 0x73968, .2)
        slow, fast = LoadConditioningMachine(self.image), LoadConditioningMachine(faster)
        values = []
        for cpu in (slow, fast):
            current = cpu.condition(6, 1200)
            values.append((current, cpu.transient()))
        self.assertLess(values[1][0], values[0][0])
        self.assertLess(values[1][1], values[0][1])


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(LoadConditioningTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Load conditioning: {result.testsRun} execution test groups passed')
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
