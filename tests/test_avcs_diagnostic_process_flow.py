#!/usr/bin/env python3
"""Trace restored OCV monitors through native current-DTC publication/reset.

Electrical observations and DB25 diagnostic readiness are supplied inputs.
The snapshot-request state starts at 0x20 (already queued), so this suite
executes fault qualification and protected current-status publication without
claiming to execute the separate snapshot queue or diagnostic transport.
"""
import _test_paths
import unittest

from test_avcs_controller_process_flow import (
    AVCSControllerMachine, RAM, ROOT, CONTROLLER_WRITES,
)
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_primary_fueling_execution import signed

COUNTER_WRITES = {(RAM+a, 1) for a in range(0xD37C, 0xD384)}
STATUS_WRITES = {(RAM+0x8EB6, 2), (RAM+0xDAE5, 1), (RAM+0xDB1B, 1)} | {
    (RAM+0xDB2D+i, 1) for i in range(0x86, 0x8A)}
FALLBACK_WRITES = {(RAM+a, 1) for a in range(0xD26C, 0xD271)}
RAW_STATUS_WRITES = {(RAM+0xDAB6+i, 1) for i in range(54)}


class AVCSDiagnosticMachine(AVCSControllerMachine):
    LOOKUPS = AVCSControllerMachine.LOOKUPS | {
        0x69572, 0x697B4, 0x47132, 0x4711E, 0x56E64, 0x56E96,
        0x50FF6, 0x5108C, 0x535C0, 0x53BD8, 0x55EC4, 0x56036, 0x24DC,
        0x47198, 0x46F52, 0x470F4, 0x5339C, 0x19C18,
    }

    def __init__(self, image):
        super().__init__(image)
        # Explicit clean diagnostic status banks. Each protected status byte
        # has its native complement byte; the raw bank is DAB6..DAEB.
        for i in range(54):
            self.write(RAM+0x8E58+2*i, 0x00FF, 2)
            self.write(RAM+0xDAB6+i, 0, 1)
        for a, n in COUNTER_WRITES | STATUS_WRITES | FALLBACK_WRITES:
            self.write(a, 0, n)
        self.write(RAM+0x8EB6, 0x00FF, 2)
        self.write(RAM+0xDB25, 1, 1)
        self.write(RAM+0xDE08, 0, 1)
        self.write(RAM+0x8FA0, 0, 1)
        self.write(RAM+0xDAA4, 1, 1)
        self.write(RAM+0xD952, 0, 1)
        for i in range(0x86, 0x8A):
            self.write(RAM+0xDB2D+i, 0x20, 1)

    def sample(self, duty, measured, reference):
        for pair, value in ((0xC91C, duty), (0xC86C, measured), (0xC87C, reference)):
            for bank in (0, 1):
                self.put_float(RAM+pair+4*bank, value)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        if op & 0xF00F in (0x600E, 0x600F):  # EXTS.B/W.
            n, m = (op >> 8) & 15, (op >> 4) & 15
            self.r[n] = signed(self.r[m], 8 if op & 15 == 14 else 16) & 0xFFFFFFFF
            self.trace.append((pc, op))
            self.pc += 2
            self.instructions += 1
        else:
            return super().step(in_delay)

    def monitor(self):
        self.execute(self.read(0x114A0, 4), COUNTER_WRITES | STATUS_WRITES)
        return self.read(RAM+0x8EB6, 1)

    def fallback_status(self):
        self.execute(0x63174, FALLBACK_WRITES)
        return self.read(RAM+0xD26F, 1) & 0x10


class AVCSDiagnosticProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.captured = before_pump_scaling(cls.images[1])
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        for image in cls.images:
            for a, b in ((0x69568, 0x699E8), (0x5BDDA, 0x5BDDE),
                         (0x50FF6, 0x511B8), (0x535C0, 0x53CD8),
                         (0x55EC4, 0x56078), (0x56E64, 0x56F0C)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_restored_open_and_short_detection_reaches_correct_enabled_dtc_bits(self):
        for image in self.images:
            for duty, measured, reference, mask in ((100, 0, 1, 0xA0), (0, 1, 0, 0x50)):
                cpu = AVCSDiagnosticMachine(image)
                cpu.sample(duty, measured, reference)
                for _ in range(125):
                    self.assertEqual(cpu.monitor(), 0)
                self.assertEqual(cpu.monitor(), mask)
                self.assertEqual(cpu.read(RAM+0x8EB6, 2), mask << 8 | (mask ^ 255))
                self.assertIn(0x535C0, cpu.entered)
                self.assertEqual(image[0x5BDDA:0x5BDDE], bytes([1]*4))
                self.assertEqual(cpu.sr & 0xF0, 0x20)

    def test_native_healthy_confirmation_clears_current_fault_and_preserves_integrity(self):
        for image in self.images:
            cpu = AVCSDiagnosticMachine(image)
            cpu.sample(100, 0, 1)
            for _ in range(126):
                cpu.monitor()
            self.assertEqual(cpu.read(RAM+0x8EB6, 1), 0xA0)
            cpu.sample(40, .5, .5)
            for _ in range(125):
                self.assertEqual(cpu.monitor(), 0xA0)
            self.assertEqual(cpu.monitor(), 0)
            self.assertEqual(cpu.read(RAM+0x8EB6, 2), 0x00FF)
            self.assertIn(0x55EC4, cpu.entered)

    def test_native_readiness_and_feature_loss_reset_qualification(self):
        for image in self.images:
            for address in (0xDB25, 0xCC4C):
                cpu = AVCSDiagnosticMachine(image)
                cpu.sample(100, 0, 1)
                for _ in range(100):
                    cpu.monitor()
                previous = cpu.read(RAM+address, 1)
                cpu.write(RAM+address, 0, 1)
                self.assertEqual(cpu.monitor(), 0)
                self.assertEqual(cpu.read(RAM+0xD37C, 8), 0)
                cpu.write(RAM+address, previous, 1)
                self.assertEqual(cpu.monitor(), 0)
                self.assertEqual(cpu.read(RAM+0xD37C, 1), 1)

    def test_ocv_fault_enters_native_fallback_and_revokes_learned_permission(self):
        for image in self.images:
            cpu = AVCSDiagnosticMachine(image)
            cpu.write(RAM+0x8274, 1, 1)
            cpu.write(RAM+0xC908, 7, 1)
            self.assertEqual(cpu.fallback_status(), 0)
            cpu.sample(100, 0, 1)
            for _ in range(126):
                cpu.monitor()
            self.assertEqual(cpu.fallback_status(), 0x10)
            for entry in (0x34880, 0x34920):
                cpu.execute(entry, CONTROLLER_WRITES)
            self.assertEqual(cpu.read(RAM+0x8274, 1) & 3, 2)

            self.assertEqual(cpu.read(RAM+0xC908, 1) & 4, 0)
            cpu.sample(40, .5, .5)
            for _ in range(126):
                cpu.monitor()
            self.assertEqual(cpu.read(RAM+0x8EB6, 1), 0)
            self.assertEqual(cpu.read(RAM+0xDAE5, 1), 0xA0)
            self.assertEqual(cpu.fallback_status(), 0x10)
            # Native eligibility/reset metadata (+16 in each 20-byte DTC
            # descriptor) is 1 for both cam sensors and all four OCV codes.
            # 564B0 calls this reset when its diagnostic mode bytes differ;
            # that mode transition is an explicit boundary of this fixture.
            cpu.execute(0x5339C, RAW_STATUS_WRITES)
            self.assertEqual(cpu.fallback_status(), 0)
            cpu.execute(0x34920, CONTROLLER_WRITES)
            # Clearing a current fault does not forge a successful cam-rest
            # learning result. Native learning must qualify again.
            self.assertEqual(cpu.read(RAM+0x8274, 1) & 3, 2)

    def test_cam_and_ocv_latched_status_sources_feed_the_same_fallback(self):
        for image in self.images:
            for identifier in (0x83, 0x84, 0x86, 0x87, 0x88, 0x89):
                cpu = AVCSDiagnosticMachine(image)
                descriptor = 0x5BDF0+20*identifier
                offset, mask = image[descriptor+1:descriptor+3]
                self.assertEqual(image[0x5BD54+identifier], 1)
                cpu.write(RAM+0xDAB6+offset, mask, 1)
                self.assertEqual(cpu.fallback_status(), 0x10)
                cpu.write(RAM+0xDAA4, 0, 1)
                self.assertEqual(cpu.fallback_status(), 0)
                self.assertEqual(cpu.read(RAM+0xDAB6+offset, 1), mask)
                cpu.write(RAM+0xDAA4, 1, 1)
                self.assertEqual(cpu.fallback_status(), 0x10)

    def test_avcs_fallback_transition_resets_knock_grid_without_overwriting_iam(self):
        grid_writes = {(RAM+0xCD10, 1)} | {
            (RAM+0x831C+8*i+offset, width)
            for i in range(64) for offset, width in ((0, 4), (4, 2), (6, 2))}
        for image in self.images:
            for running in (False, True):
                cpu = AVCSDiagnosticMachine(image)
                for i in range(64):
                    cpu.put_float(RAM+0x831C+8*i, -1)
                    cpu.write(RAM+0x831C+8*i+4, 0xA55A5AA5, 4)
                cpu.put_float(RAM+0x851C, 1)
                cpu.write(RAM+0xCD10, 0, 1)
                cpu.write(RAM+0xB51D, 0x40 if running else 0, 1)
                cpu.write(RAM+0xDAE5, 0xA0, 1)
                self.assertEqual(cpu.fallback_status(), 0x10)
                cpu.execute(0x3DF56, grid_writes)
                self.assertEqual(cpu.read(RAM+0xCD10, 1), 2)
                for i in range(64):
                    self.assertEqual(cpu.get_float(RAM+0x831C+8*i), -1 if running else 0)
                self.assertEqual(cpu.get_float(RAM+0x851C), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
