#!/usr/bin/env python3
"""Execute lean-cut latch/release with the installed v2 hysteresis calibration.

The emitted wrapper and retained limiter/inhibit publisher execute in the
existing instruction fixture. This tests commands, not physical injection.
"""

import _test_paths
from io import StringIO
from pathlib import Path
import struct
import sys
import unittest

from test_wideband_fuel_guard_execution import (
    GuardMachine, INHIBIT_WORD, safety, boost, wideband,
)

ROOT = _test_paths.ROOT
IMAGE = None


class LeanCutHysteresisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / "master_patch_v2/D2WD610H_master_patch_v2.bin").read_bytes()

    def fixture(self, *, arm=128.0, reset=64.0, delta=0.0, rpm=3200.0):
        image = bytearray(self.image)
        struct.pack_into('>f', image, safety.LEAN_ARM_DELTA_ADDR, arm)
        struct.pack_into('>f', image, safety.LEAN_RESET_DELTA_ADDR, reset)
        cpu = GuardMachine(bytes(image))
        cpu.put_float(safety.ATMOSPHERIC_PRESSURE, 768)
        cpu.put_float(safety.MAP_PRESSURE, 768 + delta)
        cpu.put_float(boost.RPM_ADDR, rpm)
        cpu.put_float(wideband.FRONT_READY_METRIC_BANK1, 50)
        cpu.put_float(wideband.WIDEBAND_LOG_LAMBDA_BANK1, .8)
        cpu.write(safety.LEAN_STATE_RAM, 3, 1)
        return cpu

    def test_installed_v2_latch_releases_in_vacuum(self):
        cpu = GuardMachine(self.image)
        cpu.put_float(safety.ATMOSPHERIC_PRESSURE, 760)
        cpu.put_float(safety.MAP_PRESSURE, 650)
        cpu.write(safety.LEAN_STATE_RAM, 3, 1)
        self.assertEqual(cpu.cut_step(), (0, 0, False))
        self.assertEqual(cpu.read(INHIBIT_WORD, 2), 0)

    def test_negative_zero_and_positive_reset_boundaries(self):
        for reset in (-32.0, 0.0, 64.0):
            for delta in (reset - .25, reset, reset + .25):
                with self.subTest(reset=reset, delta=delta):
                    cpu = self.fixture(reset=reset, delta=delta)
                    held = delta > reset
                    self.assertEqual(cpu.cut_step(), (3 if held else 0, 0, held))
                    self.assertEqual(cpu.read(INHIBIT_WORD, 2), 0xFFFF if held else 0)

    def test_bad_hysteresis_cannot_release_latched_cut(self):
        for arm, reset in ((128, 128), (128, 129), (128, float('nan')),
                           (128, float('inf')), (float('nan'), 64)):
            with self.subTest(arm=arm, reset=reset):
                self.assertEqual(self.fixture(arm=arm, reset=reset, delta=-100).cut_step(),
                                 (3, 0, True))

    def test_release_does_not_suppress_retained_rev_or_overboost_cut(self):
        cpu = self.fixture(delta=-100, rpm=6800)
        self.assertEqual(cpu.cut_step(), (0, 0, True))
        cpu = self.fixture(delta=-100)
        # Isolate simultaneous overboost by lowering its threshold in the
        # fixture; a lean-latch release must preserve the earlier cut request.
        image = bytearray(cpu.image)
        struct.pack_into('>f', image, boost.OVERB_FC_ADDR, 600)
        cpu.image = bytes(image)
        self.assertEqual(cpu.cut_step(), (0, 0, True))

    def test_arming_delay_confirmation_and_release(self):
        cpu = self.fixture(delta=140)
        cpu.write(safety.LEAN_STATE_RAM, 0, 1)
        cpu.put_float(wideband.WIDEBAND_LOG_LAMBDA_BANK1, 1.2)
        transport = cpu.read(safety.LEAN_TRANSPORT_COUNT_ADDR, 2)
        confirm = cpu.read(safety.LEAN_CONFIRM_COUNT_ADDR, 2)
        self.assertEqual(cpu.cut_step(), (1, 0, False))
        for _ in range(transport):
            self.assertFalse(cpu.cut_step()[-1])
        self.assertEqual(cpu.read(safety.LEAN_STATE_RAM, 1), 2)
        for _ in range(confirm - 1):
            self.assertFalse(cpu.cut_step()[-1])
        self.assertEqual(cpu.cut_step(), (3, 0, True))
        cpu.put_float(wideband.WIDEBAND_LOG_LAMBDA_BANK1, .8)
        self.assertEqual(cpu.cut_step(), (3, 0, True))
        cpu.put_float(safety.MAP_PRESSURE, 800)
        self.assertEqual(cpu.cut_step(), (0, 0, False))


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(LeanCutHysteresisTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    if len(sys.argv) == 2 and not sys.argv[1].startswith('-'):
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
