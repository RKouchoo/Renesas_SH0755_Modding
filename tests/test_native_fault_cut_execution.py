#!/usr/bin/env python3
"""Execute the retained diagnostic fuel-cut selector, including its 3000-RPM path.

Fault inputs are imposed fixtures, not observations from a vehicle capture.
The native fault aggregator, RPM hysteresis, selector and B744 publisher run
from ROM. No serial endpoint, diagnostic detection or engine is simulated.
"""

import _test_paths
from io import StringIO
import struct
import unittest

from test_throttle_link_execution import LinkMachine, frame_with_status
from test_idle_air_override_execution import FAULT_WRITES
from test_wideband_fuel_guard_execution import INHIBIT_WORD, INHIBIT_GETTERS

ROOT = _test_paths.ROOT
IMAGE = None
CUT_WRITES = {(0xFFFFBF90, 1), (0xFFFFBF91, 1), (0xFFFFBF92, 1),
              (0xFFFFBF93, 1), (INHIBIT_WORD, 2)}
GETTERS = {0x6537A, 0x6538E, 0x65230, 0x65258, 0x6526C,
           0x65366, 0x30B26, 0x6508E, 0x148EE,
           0x47178, 0x19D88, 0x19BE2, 0x19C7C}


class FaultCutMachine(LinkMachine):
    def __init__(self, image):
        super().__init__(image)
        for address in range(0xFFFFBF90, 0xFFFFBF94):
            self.write(address, 0, 1)
        # 148E4 copies ROM configuration byte 737C9 here. This is not the
        # physical test connector; that input is B51E/80 (SSM 61 bit 5).
        self.write(0xFFFFB28C, image[0x737C9], 1)
        self.put_float(0xFFFFB2C8, 60)
        self.put_float(0xFFFFB538, 35)

    def call_lookup(self, target):
        if target in GETTERS or target in INHIBIT_GETTERS or 0x2564C <= target < 0x25AC0:
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def fault_cut(self, rpm):
        self.put_float(0xFFFFB544, rpm)
        self.invoke(0x253A8, CUT_WRITES)
        return self.read(INHIBIT_WORD, 2)


class NativeFaultCutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x253A8, 0x25AC0), (0x64874, 0x64F7C),
                           (0x6508E, 0x653E4), (0x764A8, 0x764DC),
                           (0x75E3A, 0x75E46),
                           (0x1C5D4, 0x1C91E)):
            assert cls.image[start:end] == stock[start:end], hex(start)

    def test_clear_diagnostics_have_no_3000_rpm_cut_in_either_lift_mode(self):
        for mode in (1, 3):
            cpu = FaultCutMachine(self.image)
            cpu.write(0xFFFFCD86, mode, 1)
            for rpm in (2500, 2800, 2999, 3000, 3200, 3500, 4000):
                self.assertEqual(cpu.fault_cut(rpm), 0, (mode, rpm))

    def test_d273_mask_02_path_has_3000_2500_hysteresis(self):
        cpu = FaultCutMachine(self.image)
        cpu.write(0xFFFFD273, 2, 1)
        for rpm, expected in ((2800, 0), (2999, 0), (3000, 63),
                              (3500, 63), (2800, 63), (2500, 63),
                              (2499, 0), (2800, 0)):
            self.assertEqual(cpu.fault_cut(rpm), expected, rpm)
        self.assertEqual(struct.unpack_from('>ff', self.image, 0x764C4),
                         (3000, 500))

    def test_test_mode_signal_is_independent_of_diagnostic_cut_request(self):
        self.assertEqual(int.from_bytes(self.image[0x4B880:0x4B884], 'big'),
                         0x31A34)
        for connected in (False, True):
            cpu = FaultCutMachine(self.image)
            # Explicit post-input-poll fixtures. No hardware input is read.
            cpu.write(0xFFFFB51E, 0x90 if connected else 0x10, 1)
            cpu.write(0xFFFFB51A, int(connected), 1)
            cpu.write(0xFFFFB51B, 0, 1)
            cpu.write(0xFFFFDB2A, 0, 1)
            ssm61 = cpu.invoke(0x31A34, set())
            self.assertEqual(bool(ssm61 & 0x20), connected)
            cpu.invoke(0x64874, FAULT_WRITES)
            self.assertEqual(cpu.fault_cut(3200), 0)
            # A fault on the received link can still request all-six cut
            # with the connector disconnected. This does not test every
            # other test-mode consumer or establish a vehicle fault.
            cpu.write(0xFFFFC6FC, 0x10, 1)
            cpu.invoke(0x64874, FAULT_WRITES)
            self.assertEqual(cpu.fault_cut(3200), 63)

    def test_clearing_fault_releases_even_above_threshold(self):
        cpu = FaultCutMachine(self.image)
        cpu.write(0xFFFFD273, 2, 1)
        self.assertEqual(cpu.fault_cut(3200), 63)
        cpu.write(0xFFFFD273, 0, 1)
        self.assertEqual(cpu.fault_cut(3200), 0)
        # An unrelated per-cylinder cut must remain after this fault clears.
        cpu.write(0xFFFFD94C, 0x12, 1)
        self.assertEqual(cpu.fault_cut(3200), 0x12)

    def test_received_fault_reaches_all_cylinders_after_two_accepted_frames(self):
        cpu = FaultCutMachine(self.image)
        # C6FC/10 is one received source of D273/80, then D273/02.
        values = [0] * 7
        values[5] = 0x10
        for expected in (0, 63):
            cpu.receive(frame_with_status(values))
            cpu.invoke(0x64874, FAULT_WRITES)
            self.assertEqual(cpu.fault_cut(3200), expected)
        for expected in (63, 0):
            cpu.receive(frame_with_status([0] * 7))
            cpu.invoke(0x64874, FAULT_WRITES)
            self.assertEqual(cpu.fault_cut(3200), expected)

    def test_received_pattern_request_bypasses_d273_and_uses_pedal_hysteresis(self):
        cpu = FaultCutMachine(self.image)
        cpu.put_float(0xFFFFB46C, 45)
        values = [0x40, 0, 0, 0, 0, 0, 0]
        for expected in (0, 0x15):
            cpu.receive(frame_with_status(values))
            cpu.invoke(0x64874, FAULT_WRITES)
            self.assertEqual(cpu.read(0xFFFFD273, 1), 0)
            self.assertEqual(cpu.fault_cut(2700), expected)
        # 30B26 reads C6F7/40 directly. The selector does not read the DTC
        # bitmap to qualify this request. The remote status producer and
        # DTC reporting task are not simulated by this fixture.
        for pedal, expected in ((80, 0), (60, 0), (50, 0x15), (20, 0x3F)):
            cpu.put_float(0xFFFFB46C, pedal)
            self.assertEqual(cpu.fault_cut(2700), expected, pedal)
        self.assertEqual(cpu.fault_cut(700), 0)
        cpu.put_float(0xFFFFB46C, 45)
        self.assertEqual(cpu.fault_cut(2700), 0x15)
        for expected in (0x15, 0):
            cpu.receive(frame_with_status([0] * 7))
            cpu.invoke(0x64874, FAULT_WRITES)
            self.assertEqual(cpu.fault_cut(2700), expected)

    def test_combined_received_faults_can_keep_cutting_below_2500_rpm(self):
        # The 3000/2500 latch is not a complete model of diagnostic cuts.
        # C6FA/02 sets D271/80 as well as D273=27; C6F8/01 sets D273=27
        # with D271/80 clear, permitting the more restrictive first branch.
        for offset, mask, d271, released_word, high_pedal_word in (
                (3, 0x02, 0x80, 0x15, 0), (1, 0x01, 0, 0x3F, 0x3F)):
            cpu = FaultCutMachine(self.image)
            cpu.put_float(0xFFFFB46C, 45)
            values = [0] * 7
            values[offset] = mask
            for _ in range(2):
                cpu.receive(frame_with_status(values))
            cpu.invoke(0x64874, FAULT_WRITES)
            self.assertEqual(cpu.read(0xFFFFD271, 1), d271)
            self.assertEqual(cpu.read(0xFFFFD273, 1), 0x27)
            self.assertEqual(cpu.fault_cut(3200), 0x3F)
            self.assertEqual(cpu.fault_cut(2400), released_word)
            self.assertEqual(cpu.read(0xFFFFBF93, 1) & 0x80, 0)
            self.assertEqual(cpu.fault_cut(2700), released_word)
            cpu.put_float(0xFFFFB46C, 80)
            self.assertEqual(cpu.fault_cut(2700), high_pedal_word)
            for _ in range(2):
                cpu.receive(frame_with_status([0] * 7))
            cpu.invoke(0x64874, FAULT_WRITES)
            self.assertEqual(cpu.fault_cut(2700), 0)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(NativeFaultCutTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Native fault fuel cut: {result.testsRun} execution test groups passed')
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
