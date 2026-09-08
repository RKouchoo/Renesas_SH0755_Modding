#!/usr/bin/env python3
"""Execute the retained idle/base timing selection with bounded input fixtures.

27DE8 and 28166 execute native instructions, including scalar helpers and the
idle-flag getter. The five upstream base-map producers called by 28166 are an
explicit boundary: C150 is supplied by the fixture, not reconstructed runtime
AVCS/knock state. These tests do not assert measured final spark timing.
"""
from io import StringIO
from pathlib import Path
import unittest

from test_transient_fuel_execution import TransientFuelMachine

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
BASE_PRODUCERS = {0x281FC, 0x28304, 0x28354, 0x28418, 0x284B8}


class IdleTimingMachine(TransientFuelMachine):
    def __init__(self, image, rpm=1000, idle=True, base=0.0390625, blend=0):
        super().__init__(image, rpm=rpm)
        self.write(0xFFFFB2BC, 2 if idle else 0, 1)
        self.put_float(0xFFFFB538, 0)
        self.put_float(0xFFFFC134, blend)
        self.put_float(0xFFFFC138, 15.1953125)
        self.put_float(0xFFFFC150, base)
        self.base_boundaries = []

    def call_lookup(self, target):
        if target in BASE_PRODUCERS:
            self.base_boundaries.append(target)
            self.poison_scratch()
        else:
            super().call_lookup(target)

    def update_blend(self):
        self.invoke(0x27DE8, {(0xFFFFC134, 4)})
        return self.get_float(0xFFFFC134)

    def select(self):
        self.invoke(0x28166, {(0xFFFFC130, 4)})
        assert self.base_boundaries[-5:] == [0x281FC, 0x28304, 0x28354, 0x28418, 0x284B8]
        return self.get_float(0xFFFFC130)


class IdleTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / 'master_patch/candidates/D2WD610H_idle_recovery_candidate.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x27DE8, 0x27F3E), (0x28166, 0x281D0),
                           (0x281EC, 0x281FC), (0x15192, 0x151A6),
                           (0x2424, 0x2458), (0x24FC, 0x251C)):
            assert cls.image[start:end] == stock[start:end], hex(start)

    def test_stationary_idle_flag_selects_endpoint_at_both_boundaries(self):
        for rpm in (558, 1000, 1532, 1990):
            for initial in (0, 1):
                for idle in (False, True):
                    cpu = IdleTimingMachine(self.image, rpm, idle, blend=initial)
                    self.assertEqual(cpu.update_blend(), 0 if idle else 1)

    def test_partial_blend_uses_stock_per_call_step(self):
        for idle in (False, True):
            cpu = IdleTimingMachine(self.image, idle=idle, blend=.5)
            self.assertAlmostEqual(cpu.update_blend(), .492 if idle else .508, places=6)

    def test_recognized_idle_holds_target_despite_low_base_timing(self):
        for base in (0.0390625, .37, 8.59, 12.21, 27.5):
            cpu = IdleTimingMachine(self.image, idle=True, base=base)
            cpu.update_blend()
            self.assertAlmostEqual(cpu.select(), 15.1953125, places=5)

    def test_leaving_idle_selects_low_base_value(self):
        for base in (0.0390625, .37, 8.59, 12.21, 27.5):
            cpu = IdleTimingMachine(self.image, idle=False, base=base)
            cpu.update_blend()
            self.assertAlmostEqual(cpu.select(), base, places=5)

    def test_return_to_idle_removes_low_base_and_negative_control_detects_gate(self):
        cpu = IdleTimingMachine(self.image, idle=False)
        cpu.update_blend()
        self.assertAlmostEqual(cpu.select(), .0390625)
        cpu.write(0xFFFFB2BC, 2, 1)
        cpu.update_blend()
        self.assertAlmostEqual(cpu.select(), 15.1953125)
        # Retain the wrong off-idle blend deliberately: the output must differ.
        cpu.put_float(0xFFFFC134, 1)
        self.assertAlmostEqual(cpu.select(), .0390625)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(IdleTimingTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Idle timing: {result.testsRun} execution test groups passed')
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
