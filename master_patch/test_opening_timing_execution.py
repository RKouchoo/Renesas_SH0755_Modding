#!/usr/bin/env python3
"""Execute base-map selection and final spark composition with bounded fixtures.

The AVCS tracking ratio, all six base-map blends, selector, idle/base blend,
final limits and six-cylinder composer execute retained ROM instructions.
Table helpers are mathematical boundaries with poisoned scratch registers.
Cam positions/targets, mode history, idle target and other timing corrections
are explicit inputs, not reconstructed measurements or an engine simulation.
"""
from io import StringIO
from itertools import product
from pathlib import Path
import struct
import unittest

from test_transient_fuel_execution import TransientFuelMachine
from test_primary_fueling_execution import number

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
BASE_DESCRIPTORS = tuple(0x60108 + i * 28 for i in range(6))
LIMIT_DESCRIPTORS = (0x5FB78, 0x5FB8C, 0x5FC18)
BASE_PRODUCERS = (0x281FC, 0x28304, 0x28354, 0x28418, 0x284B8)
NATIVE = {*BASE_PRODUCERS, 0x27088, 0x6504C, 0x1D228, 0x3BB26,
          0x19BE2, 0x18CF4, 0x12C12, 0x35ED2, 0x1487E}
BASE_WRITES = {(a, 4) for a in range(0xFFFFC150, 0xFFFFC180, 4)} | {
    (0xFFFFC184, 4), (0xFFFFC188, 4), (0xFFFFC180, 1),
    (0xFFFFC19C, 1), (0xFFFFC19D, 1),
    *((a, 2) for a in (0xFFFFC18C, 0xFFFFC18E, 0xFFFFC192,
                       0xFFFFC194, 0xFFFFC19A))}
LIMIT_WRITES = {(0xFFFFC104, 4), (0xFFFFC124, 4),
                (0xFFFFC12D, 1), (0xFFFFC12E, 1)}
FINAL_WRITES = {(a, 4) for a in range(0xFFFFC0EC, 0xFFFFC104, 4)} | {
    (0xFFFFC12B, 1), (0xFFFFC12C, 1)}


class OpeningTimingMachine(TransientFuelMachine):
    def __init__(self, image, rpm=1363, load=1.25, coolant=29, idle=False,
                 actual_cams=(0, 0), target_cams=(20, 20)):
        super().__init__(image, load=load, rpm=rpm, coolant=coolant)
        # Ordinary running, stationary, stable low-lift fixture. No active
        # transient ignition override or other additive/subtractive correction.
        for address, value in {
            0xFFFFB2BC: 2 if idle else 0, 0xFFFFB484: 0,
            0xFFFFB151: 0, 0xFFFFB289: 0, 0xFFFFCA10: 0,
            0xFFFFCC4C: 0x40, 0xFFFFD141: 0, 0xFFFFD26D: 0,
            0xFFFFCD86: 1, 0xFFFFC120: 3, 0xFFFFC121: 0,
            0xFFFFC12B: 0, 0xFFFFC12C: 0, 0xFFFFC12D: 0,
            0xFFFFC12E: 0, 0xFFFFC180: 0,
            0xFFFFC19C: 1, 0xFFFFC19D: 0,
        }.items():
            self.write(address, value, 1)
        for address in range(0xFFFFC18C, 0xFFFFC19C, 2):
            self.write(address, 1000, 2)
        self.write(0xFFFFC128, 1000, 2)
        for address in (
            0xFFFFB2F8, 0xFFFFB834, 0xFFFFB89C, 0xFFFFB538,
            0xFFFFC118, 0xFFFFC1A0, 0xFFFFC1A4, 0xFFFFC1A8,
            0xFFFFC1BC, 0xFFFFC1C8, 0xFFFFC1D0, 0xFFFFC1D4,
            0xFFFFC1E0, 0xFFFFC1E4, 0xFFFFCA18, 0xFFFFCD44,
            0xFFFFD0F8, 0xFFFFD12C, 0xFFFFD11C,
            *range(0xFFFFCCC8, 0xFFFFCCE0, 4),
            *range(0xFFFFC150, 0xFFFFC180, 4),
            0xFFFFC184, 0xFFFFC188, 0xFFFFC124,
        ):
            self.put_float(address, 0)
        self.put_float(0xFFFFB314, 8 if idle else 100)
        self.put_float(0xFFFFC104, 90)
        self.put_float(0xFFFFC108, 90)
        self.put_float(0xFFFFC134, 0 if idle else 1)
        self.put_float(0xFFFFC138, 15.1953125)
        self.put_float(0xFFFFC13C, 15.1953125)
        for address, value in zip((0xFFFFC8C8, 0xFFFFC8CC,
                                   0xFFFFC974, 0xFFFFC978),
                                  (*actual_cams, *target_cams)):
            self.put_float(address, value)

    def table(self, target, descriptor, x, y):
        if descriptor in LIMIT_DESCRIPTORS:
            assert target == 0x209C
            n, kind, axis, data, scale, bias = struct.unpack_from(
                '>HHIIff', self.image, descriptor)
            assert kind == 0x400
            return self.interpolate(self.array(axis, n),
                                    [self.read(data+i, 1)*scale+bias for i in range(n)], x)
        if descriptor in BASE_DESCRIPTORS:
            assert target == 0x2150
            nx, ny, axis_x, axis_y, data, kind, scale, bias = struct.unpack_from(
                '>HHIIIIff', self.image, descriptor)
            assert kind == 0x04000000
            rows = [self.interpolate(self.array(axis_x, nx),
                    [self.read(data+j*nx+i, 1)*scale+bias for i in range(nx)], x)
                    for j in range(ny)]
            return self.interpolate(self.array(axis_y, ny), rows, y)
        return super().table(target, descriptor, x, y)

    def call_lookup(self, target):
        if target in NATIVE:
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        elif target == 0x2118:
            # Integer 1-axis lookup used only by the lift-history producer.
            descriptor, x = self.r[4], number(self.fr[4])
            assert descriptor == 0x5FFF8
            n, kind, axis, data = struct.unpack_from('>HHII', self.image, descriptor)
            assert kind == 0
            value = int(self.interpolate(self.array(axis, n),
                        [self.read(data+2*i, 2) for i in range(n)], x))
            self.table_calls.append((target, descriptor, x, None))
            self.poison_scratch()
            self.r[0] = value
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        if op & 0xF00F == 0x0004:  # mov.b Rm,@(R0,Rn)
            n, m = (op >> 8) & 15, (op >> 4) & 15
            self.write((self.r[0]+self.r[n]) & 0xFFFFFFFF,
                       self.r[m], 1, record=True)
            self.pc += 2
            self.instructions += 1
            assert self.instructions < self.INSTRUCTION_LIMIT
        else:
            super().step(in_delay)

    def tracking(self):
        self.invoke(0x28354, {(0xFFFFC17C, 4)})
        return self.get_float(0xFFFFC17C)

    def base_and_idle(self):
        self.invoke(0x27DE8, {(0xFFFFC134, 4)})
        self.table_calls.clear()
        self.invoke(0x28166, BASE_WRITES | {(0xFFFFC130, 4)})
        assert [a for a in self.entered if a in BASE_PRODUCERS] == list(BASE_PRODUCERS)
        return self.get_float(0xFFFFC130)

    def final(self):
        self.invoke(0x2777C, LIMIT_WRITES)
        self.invoke(0x279CC, FINAL_WRITES)
        return tuple(self.get_float(a) for a in range(0xFFFFC0EC, 0xFFFFC104, 4))


class OpeningTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch/candidates/D2WD610H_idle_recovery_candidate.bin').read_bytes()
        cls.stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x2777C, 0x27D68), (0x27DE8, 0x27F3E),
                           (0x28166, 0x287A4), (0x287DE, 0x2880C),
                           (0x1D228, 0x1D23C), (0x3BB26, 0x3BB3A),
                           (0x6504C, 0x65060), (0x27088, 0x2708C),
                           (0x2424, 0x2484), (0x24A0, 0x2534)):
            assert cls.image[start:end] == cls.stock[start:end], hex(start)

    def test_native_cam_tracking_ratio_and_status_fallbacks(self):
        for actual, target, expected in ((0, 20, 0), (5, 20, .25),
                                         (10, 20, .5), (20, 20, 1),
                                         (30, 20, 1), (-5, 20, 0), (0, 0, 0)):
            cpu = OpeningTimingMachine(self.image, actual_cams=(actual, actual),
                                       target_cams=(target, target))
            self.assertAlmostEqual(cpu.tracking(), expected)
            self.assertGreater(cpu.reads[0xFFFFC8C8], 0)
            self.assertGreater(cpu.reads[0xFFFFC974], 0)
        for address, value in ((0xFFFFB748, 0x80), (0xFFFFCC4C, 0)):
            cpu = OpeningTimingMachine(self.image)
            cpu.write(address, value, 1)
            self.assertEqual(cpu.tracking(), 1)

    def test_six_native_map_blends_and_low_lift_selection(self):
        from analyze_20260908_recovery import timing_endpoint, timing_floor
        for rpm, load, k in product((992, 1363, 1794, 2014), (.78, 1.25, 1.58), (0, .5, 1)):
            cpu = OpeningTimingMachine(self.image, rpm=rpm, load=load,
                                       actual_cams=(20*k, 20*k))
            value = cpu.base_and_idle()
            endpoints = [timing_endpoint(self.image, i, rpm, load) for i in range(6)]
            for i, expected in enumerate(endpoints):
                self.assertAlmostEqual(cpu.get_float(0xFFFFC154+4*i), expected, delta=5e-6)
            for i in range(3):
                expected = endpoints[i]*k + endpoints[i+3]*(1-k)
                self.assertAlmostEqual(cpu.get_float(0xFFFFC16C+4*i), expected, delta=5e-6)
            expected = max(endpoints[0]*k + endpoints[3]*(1-k), timing_floor(self.image, 29))
            self.assertAlmostEqual(value, expected, delta=5e-6)
            self.assertEqual(cpu.get_float(0xFFFFC178), rpm)

    def test_final_cold_floor_explains_two_degrees_versus_zero(self):
        for image, coolant in product((self.stock, self.image), (29, 35, 45)):
            expected = {29: 2.1484375, 35: 1.09375, 45: .0390625}[coolant]
            cpu = OpeningTimingMachine(image, coolant=coolant)
            self.assertAlmostEqual(cpu.base_and_idle(), .0390625, places=5)
            for value in cpu.final():
                self.assertAlmostEqual(value, expected, places=5)
            self.assertAlmostEqual(cpu.get_float(0xFFFFC124), expected, places=5)

    def test_idle_selection_restores_fifteen_degrees(self):
        for rpm, coolant in product((558, 1000, 1363, 1990), (29, 45)):
            cpu = OpeningTimingMachine(self.image, rpm=rpm, coolant=coolant, idle=True)
            self.assertAlmostEqual(cpu.base_and_idle(), 15.1953125, places=5)
            for value in cpu.final():
                self.assertAlmostEqual(value, 15.1953125, places=5)

    def test_final_composer_preserves_signs_and_separate_cylinders(self):
        cpu = OpeningTimingMachine(self.image)
        cpu.put_float(0xFFFFC130, 20)
        cpu.put_float(0xFFFFC1BC, 2)  # Subtractive term.
        cpu.put_float(0xFFFFC1A4, 3)  # Additive term.
        for cylinder in range(6):
            cpu.put_float(0xFFFFCCC8+4*cylinder, cylinder*.5)
        self.assertEqual(cpu.final(), tuple(21+i*.5 for i in range(6)))

    def test_current_caps_change_interpolated_timing_below_2000(self):
        stock, tuned = (OpeningTimingMachine(im, rpm=2014, load=1.35,
                       actual_cams=(20, 20)) for im in (self.stock, self.image))
        self.assertGreater(stock.base_and_idle()-tuned.base_and_idle(), 10)
        stock, tuned = (OpeningTimingMachine(im, rpm=1794, load=1.58,
                       actual_cams=(20, 20)) for im in (self.stock, self.image))
        self.assertGreater(stock.base_and_idle()-tuned.base_and_idle(), .9)
        # Negative control: restoring the stock timing axis/maps removes this
        # calibration effect without changing any firmware or idle-VE bytes.
        restored = bytearray(self.image)
        restored[0x780BC:0x780F8] = self.stock[0x780BC:0x780F8]
        from master_calibration import TIMING_MAPS
        for _, data, _, rows in TIMING_MAPS:
            restored[data:data+15*rows] = self.stock[data:data+15*rows]
        cpu = OpeningTimingMachine(restored, rpm=2014, load=1.35, actual_cams=(20, 20))
        reference = OpeningTimingMachine(self.stock, rpm=2014, load=1.35, actual_cams=(20, 20))
        self.assertEqual(cpu.base_and_idle(), reference.base_and_idle())


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(OpeningTimingTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Opening timing: {result.testsRun} execution test groups passed')
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
