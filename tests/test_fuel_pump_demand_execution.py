#!/usr/bin/env python3
"""Trace the native pulse-to-pump-demand dependency using explicit inputs.

The B1C4-producing prefix of 13CA8, full mode selector 2A910, scalar
filter/comparison helpers and command publisher 2A53A execute ROM opcodes.
The remaining 13CA8 communications body is outside this test. Pump threshold
lookups use descriptor interpolation; DEAA is a recorded hardware boundary.
Startup/test-mode qualifiers, voltage and processed relative MAP are fixtures.
This does not recover pump duty or rail pressure from an unlogged vehicle run.
"""

import _test_paths
from io import StringIO
from itertools import product
from pathlib import Path
import struct
import sys
import unittest

from test_transient_fuel_execution import TransientFuelMachine
from test_primary_fueling_execution import number

ROOT = _test_paths.ROOT
IMAGE = None
DEMAND_SCALE = 0x72D54
INJECTOR_SCALE = 0x76014
MODE_WRITES = {(a, 4) for a in (0xFFFFC29C, 0xFFFFC2A0, 0xFFFFC2A4)} | {
    (0xFFFFC2AC, 1), (0xFFFFC2B2, 1)}


def proportional_scale(stock, image):
    old_demand = struct.unpack_from('>f', stock, DEMAND_SCALE)[0]
    old_duration = struct.unpack_from('>f', stock, INJECTOR_SCALE)[0]
    new_duration = struct.unpack_from('>f', image, INJECTOR_SCALE)[0]
    return old_demand * old_duration / new_duration


def with_proportional_scale(stock, image):
    result = bytearray(image)
    struct.pack_into('>f', result, DEMAND_SCALE, proportional_scale(stock, image))
    return bytes(result)  # In-memory arithmetic comparison, not a flash image.


class PumpDemandMachine(TransientFuelMachine):
    def __init__(self, image):
        super().__init__(image)
        self.output_ratios = []
        self.write(0xFFFFC778, 0, 1)
        self.write(0xFFFFC2AC, 1, 1)
        self.write(0xFFFFC2AD, 0, 1)
        self.write(0xFFFFC2B2, 0, 1)
        for a in (0xFFFFBE40, 0xFFFFC2A4, 0xFFFFB1C4, 0xFFFFB2A4):
            self.put_float(a, 0)
        self.put_float(0xFFFFABB4, 14)

    def table(self, target, descriptor, x, y):
        if descriptor not in (0x60204, 0x60220):
            return super().table(target, descriptor, x, y)
        assert target == 0x2150
        nx, ny, ax, ay, data, kind, scale, bias = struct.unpack_from(
            '>HHIIIIff', self.image, descriptor)
        assert kind == 0x08000000
        rows = [self.interpolate(self.array(ax, nx),
                [self.read(data + 2*(j*nx+i), 2)*scale+bias for i in range(nx)], x)
                for j in range(ny)]
        return self.interpolate(self.array(ay, ny), rows, y)

    def step(self, in_delay=False):
        if self.pc == 0xDEAA:
            assert not in_delay
            self.output_ratios.append(number(self.fr[4]))
            self.poison_scratch()
            self.pc = self.pr
        else:
            super().step(in_delay)

    def consumption(self, rpm, effective_pulse_us):
        self.put_float(0xFFFFB544, rpm)
        self.put_float(0xFFFFC0B8, effective_pulse_us)
        self.r, self.fr = self.original_r.copy(), self.original_fr.copy()
        self.pr, self.pc = self.STOP, 0x13CA8
        self.instructions, self.min_sp = 0, self.STACK
        self.writes.clear()
        self.reads.clear()
        while self.pc != 0x13CE6:  # B1C4 publication precedes telemetry conversion.
            self.step()
        assert self.instructions == 31
        for a, size in self.writes:
            assert (a, size) in {(0xFFFFB1E6, 1), (0xFFFFB1C4, 4)} or (
                self.min_sp <= a < self.STACK), (hex(a), size)
        return self.get_float(0xFFFFB1C4)

    def select(self, relative_map_mmhg=0, voltage=14, settled=False):
        self.put_float(0xFFFFB2A4, relative_map_mmhg)
        self.put_float(0xFFFFABB4, voltage)
        if settled:
            self.put_float(0xFFFFC2A4, self.get_float(0xFFFFB1C4)*3.6)
        self.invoke(0x2A910, MODE_WRITES)
        self.invoke(0x2A53A, {(0xFFFFC298, 4)})
        return self.get_float(0xFFFFC298)


class PumpDemandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        for start, end in ((0x13CA8, 0x13DEA), (0x2A50C, 0x2AAAC),
                           (0x60204, 0x6023C), (0x794D8, 0x79524)):
            assert cls.image[start:end] == cls.stock[start:end], hex(start)

    def test_installed_coefficient_matches_the_injector_duration_calibration(self):
        self.assertAlmostEqual(struct.unpack_from('>f', self.image, DEMAND_SCALE)[0],
                               proportional_scale(self.stock, self.image), places=5)

    def test_native_consumption_prefix_and_former_maf_independence(self):
        scale = struct.unpack_from('>f', self.image, DEMAND_SCALE)[0]
        for rpm, pulse, raw in product((800, 2800, 3500, 4144),
                                       (0, 2000, 9000, 12000), (0, 65535)):
            cpu = PumpDemandMachine(self.image)
            cpu.write(0xFFFFAB06, raw, 2)
            value = cpu.consumption(rpm, pulse)
            expected = rpm / 60 * pulse * scale * 3e-6
            # Independent real-valued equation versus several native f32 ops.
            self.assertAlmostEqual(value, expected, delta=max(1e-6, abs(expected)*5e-7))
            self.assertNotIn(0xFFFFAB06, cpu.reads)

    def test_paired_calibration_preserves_same_fuel_demand_after_injector_resize(self):
        old_duration = struct.unpack_from('>f', self.stock, INJECTOR_SCALE)[0]
        new_duration = struct.unpack_from('>f', self.image, INJECTOR_SCALE)[0]
        paired = with_proportional_scale(self.stock, self.image)
        for rpm, pulse in product((1500, 2800, 3200, 4144), (3000, 9000, 18000)):
            a, b = PumpDemandMachine(self.stock), PumpDemandMachine(paired)
            self.assertAlmostEqual(a.consumption(rpm, pulse),
                b.consumption(rpm, pulse * new_duration / old_duration), delta=5e-6)

    def test_stock_coefficient_is_a_negative_control_for_resized_injectors(self):
        restored = bytearray(self.image)
        restored[DEMAND_SCALE:DEMAND_SCALE+4] = self.stock[DEMAND_SCALE:DEMAND_SCALE+4]
        ratio = (struct.unpack_from('>f', self.image, INJECTOR_SCALE)[0] /
                 struct.unpack_from('>f', self.stock, INJECTOR_SCALE)[0])
        a, b = PumpDemandMachine(self.stock), PumpDemandMachine(bytes(restored))
        original = a.consumption(3000, 12000)
        stale = b.consumption(3000, 12000*ratio)
        self.assertAlmostEqual(stale/original, ratio, places=6)
        self.assertLess(stale/original, .5)

    def test_settled_native_modes_and_output_off_override(self):
        for relative, demand, expected in ((0, 1, 33.3), (0, 10, 66.7),
                (0, 65, 100), (-400, 10, 33.3), (-400, 25, 66.7), (-400, 80, 100)):
            cpu = PumpDemandMachine(self.image)
            cpu.put_float(0xFFFFB1C4, demand/3.6)
            self.assertAlmostEqual(cpu.select(relative, settled=True), expected, places=4)
            self.assertAlmostEqual(cpu.output_ratios[-1], expected/100, places=5)
            cpu.write(0xFFFFC2AD, 1, 1)
            cpu.invoke(0x2A53A, {(0xFFFFC298, 4)})
            self.assertEqual(cpu.output_ratios[-1], 0)

    def test_native_filter_follows_a_demand_step_with_99_percent_current_weight(self):
        cpu = PumpDemandMachine(self.image)
        cpu.put_float(0xFFFFB1C4, 80/3.6)
        self.assertEqual(cpu.select(), 100)
        self.assertAlmostEqual(cpu.get_float(0xFFFFC2A4), 79.2, places=4)
        self.assertEqual(cpu.select(), 100)
        self.assertAlmostEqual(cpu.get_float(0xFFFFC2A4), 80, places=4)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(PumpDemandTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    if len(sys.argv) > 1:
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
