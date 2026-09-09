#!/usr/bin/env python3
"""Execute v2's local status call/store and downstream load-conditioning body.

172E2..172F2 executes the image's literal load, status helper call and delay-slot
store. The subsequent 1D228 state getter is a boundary after that store.
1753A..1770A then executes with the captured status byte and a supplied running
frame; table interpolation is mathematical. Upstream flag production, scheduler
timing and the physical engine are outside this fixture.
"""
import _test_paths
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
import struct
import sys
import unittest

from test_load_conditioning_execution import LoadConditioningMachine
from test_primary_fueling_execution import PrimaryFuelMachine
from test_wideband_fuel_guard_execution import GuardMachine, bits

ROOT = _test_paths.ROOT
sys.path.insert(0, str(ROOT / "tools"))
from _audit_images import read_audit_image

IMAGE = None
V2_PATH = "master_patch_v2/D2WD610H_master_patch_v2.bin"
PRE_FIX_SHA256 = "2fe5f9cc7f960bff1efd784bb29e6c984ccbc025f1d8029c920fd52a3ce25ac9"
STATUS_POINTER = 0x173FC
NATIVE_STATUS = 0x65168
ZERO_STATUS = 0x27088
MAF_FLAGS = 0xFFFFD26F
CHECKSUM_WORD = 0x7FB88


@lru_cache(maxsize=1)
def pre_fix_image():
    return read_audit_image({"path": V2_PATH, "sha256": PRE_FIX_SHA256})


class StatusCallerMachine(PrimaryFuelMachine):
    def call_lookup(self, target):
        self.entered.append(target)
        if target == 0x1D228:
            # Its call delay slot has already saved the status byte. Its return
            # is irrelevant to this fixture; deliberately make it different.
            self.r[0] = 0xA5
            return
        assert target in (NATIVE_STATUS, ZERO_STATUS), hex(target)
        return_pc = self.pr
        self.pc = target
        while self.pc != return_pc:
            self.step()

    def capture(self, flag):
        self.write(MAF_FLAGS, flag, 1)
        self.r = self.original_r.copy()
        self.fr = self.original_fr.copy()
        self.r[15] = frame = self.STACK - 0x80
        self.r[0], self.fr[3] = 0x10, bits(0.0)
        self.pc, self.pr = 0x172E2, self.STOP
        self.instructions, self.min_sp = 0, frame
        self.writes.clear()
        self.entered.clear()
        while self.pc != 0x172F2:
            self.step()
        assert self.r[15] == frame
        assert set(self.writes) <= {(frame + 0x10, 4), (frame + 0x1C, 1)}
        assert self.read(MAF_FLAGS, 1) == flag
        assert self.entered == [self.read(STATUS_POINTER, 4), 0x1D228]
        return self.read(frame + 0x1C, 1)


class StatusAwareLoadMachine(LoadConditioningMachine):
    status_result = None

    def write(self, address, value, size=4, record=False):
        if address == self.STACK - 0x80 + 0x1C and size == 1 and self.status_result is not None:
            value = self.status_result
        return super().write(address, value, size, record)


def condition(image, flag, airflow, pressure=250):
    status = StatusCallerMachine(image).capture(flag)
    machine = StatusAwareLoadMachine(image, load=.5, rpm=1500, coolant=45)
    machine.status_result = status
    load = machine.condition(airflow, 1500, coolant=45, map_mmhg=pressure)
    return status, load


class V2LoadFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / V2_PATH).read_bytes()
        cls.baseline = pre_fix_image()

    def test_airflow_controls_load_with_fault_bit_clear_or_set(self):
        for flag in (0, 0x40, 0x80, 0xFF):
            for pressure in (110, 250, 500):
                for airflow in (5.0, 12.5, 20.0):
                    with self.subTest(flag=flag, pressure=pressure, airflow=airflow):
                        status, actual = condition(self.image, flag, airflow, pressure)
                        self.assertEqual(status, 0)
                        self.assertAlmostEqual(actual, .5 + .06 * (airflow * 60 / 1500 - .5), delta=2e-6)

    def test_pre_fix_and_removed_bypass_reproduce_the_fault(self):
        removed = bytearray(self.image)
        struct.pack_into(">I", removed, STATUS_POINTER, NATIVE_STATUS)
        for image in (self.baseline, bytes(removed)):
            for airflow in (12.5, 20.0):
                status, actual = condition(image, 0x40, airflow)
                self.assertEqual(status, 2)
                self.assertAlmostEqual(actual, .5749, delta=2e-6)
            self.assertNotAlmostEqual(condition(image, 0, 12.5)[1],
                                      condition(image, 0, 20.0)[1], places=5)

    def test_native_diagnostic_helper_and_flag_are_preserved(self):
        for flag, expected in ((0, 0), (0x40, 2), (0x80, 0), (0xFF, 2)):
            cpu = GuardMachine(self.image)
            cpu.write(MAF_FLAGS, flag, 1)
            self.assertEqual(cpu.invoke(NATIVE_STATUS, set()), expected)
            self.assertEqual(cpu.read(MAF_FLAGS, 1), flag)
        self.assertEqual(self.image[0x172E2:0x172F2], self.baseline[0x172E2:0x172F2])
        self.assertEqual(self.image[0x1753A:0x1770A], self.baseline[0x1753A:0x1770A])

    def test_only_local_pointer_and_checksum_change_from_v2(self):
        self.assertEqual(len(self.image), len(self.baseline))
        self.assertEqual(struct.unpack_from(">I", self.image, STATUS_POINTER)[0], ZERO_STATUS)
        # Checksum validates with local pointer update
        total = sum(struct.unpack_from(">I", self.image, a)[0] for a in range(0x2000, 0x7FAF8, 4))
        stored = struct.unpack_from(">I", self.image, CHECKSUM_WORD)[0]
        self.assertEqual((total + stored) & 0xFFFFFFFF, 0x5AA5A55A)

    def test_component_rejects_unexpected_status_pointer(self):
        spec = spec_from_file_location("v2_sd_for_guard_test", ROOT / "master_patch_v2/speed_density_component.py")
        component = module_from_spec(spec)
        spec.loader.exec_module(component)
        source = bytearray((ROOT / "2005 BLE MT.bin").read_bytes())
        struct.pack_into(">I", source, STATUS_POINTER, 0xDEADBEEF)
        with self.assertRaisesRegex(SystemExit, "load-fallback"):
            component.apply_to_rom(source)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(V2LoadFallbackTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f"  [4/4] Local load fallback   : {result.testsRun} execution/regression groups passed")
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == "__main__":
    unittest.main()
