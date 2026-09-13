#!/usr/bin/env python3
"""Trace native P0011/P0021 qualification, reporting and healthy recovery.

Bank observations, controller permission and diagnostic readiness are explicit
inputs. Native instructions copy cam errors, qualify the operating window,
count reports/recovery and publish current/raw status. Snapshot requests begin
already queued. No physical cam response or elapsed task time is inferred.
"""
import _test_paths
from itertools import product
import unittest

from test_avcs_diagnostic_process_flow import (
    AVCSDiagnosticMachine, FALLBACK_WRITES, ROOT, RAM,
)
from test_runtime_rom_checksum_execution import before_pump_scaling

PERFORMANCE_WRITES = {(RAM+0xDA28, 1), (RAM+0xDA2C, 4), (RAM+0xDA30, 4)} | {
    (RAM+a, 2) for a in range(0xDA34, 0xDA40, 2)} | {
    (RAM+0x8E70, 2), (RAM+0xDAC2, 1), (RAM+0xDAF8, 1),
    (RAM+0xDB5A, 1), (RAM+0xDB5B, 1)}


class CamPerformanceMachine(AVCSDiagnosticMachine):
    LOOKUPS = AVCSDiagnosticMachine.LOOKUPS | {
        0x719A8, 0x71D2C, 0x71ADE, 0x349EA, 0x35370, 0x24FC, 0x2450,
    }

    def __init__(self, image):
        super().__init__(image)
        for a in range(0xDA28, 0xDA40):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xDAF8, 0, 1)
        self.write(RAM+0xDB5A, 0x20, 1)
        self.write(RAM+0xDB5B, 0x20, 1)
        self.write(RAM+0xC948, 1, 1)
        self.write(RAM+0xC908, 1, 1)
        self.put_float(RAM+0xB3AC, 67)
        self.sample(20, 20)

    def sample(self, target, error, offset=40):
        for bank in (0, 1):
            self.put_float(RAM+0xC974+4*bank, target)
            self.put_float(RAM+0xC8E8+4*bank, error)
            self.put_float(RAM+0x8264+8*bank, offset)

    def monitor(self):
        self.execute(0x7198C, PERFORMANCE_WRITES)
        return self.read(RAM+0x8E70, 1) & 0x0C


class CamPerformanceProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x7198C, 0x71EC0), (0x74F50, 0x74F78),
                         (0x74D82, 0x74D88), (0x5C174, 0x5C19C),
                         (0x349EA, 0x349FA), (0x35370, 0x35380)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_complete_monitor_qualifier_has_different_zero_and_advanced_target_rpm_gates(self):
        for image in self.images.values():
            for rpm, ect, target, enabled, ready in product(
                    (599, 600, 3000, 4144, 12799, 12800), (60, 67),
                    (0, 20), (0, 1), (0, 1)):
                cpu = CamPerformanceMachine(image)
                cpu.put_float(RAM+0xB544, rpm)
                cpu.put_float(RAM+0xB3AC, ect)
                cpu.write(RAM+0xC948, enabled, 1)
                cpu.write(RAM+0xDB25, ready, 1)
                cpu.sample(target, 20)
                cpu.monitor()
                expected = ect > 60 and ready and (
                    rpm >= 600 if target == 0 else rpm >= 12800 and enabled)
                self.assertEqual(bool(cpu.read(RAM+0xDA28, 1) & 0x80), bool(expected),
                                 (rpm, ect, target, enabled, ready))
            cpu = CamPerformanceMachine(image)
            cpu.put_float(RAM+0xB544, 12800)
            cpu.put_float(RAM+0xC974, 0)
            cpu.monitor()
            self.assertEqual(cpu.read(RAM+0xDA28, 1) & 0x80, 0)

    def test_loaded_rpm_with_large_cam_error_does_not_qualify_this_report_path(self):
        for image, rpm in product(self.images.values(), (2500, 3000, 3500, 4144)):
            cpu = CamPerformanceMachine(image)
            cpu.put_float(RAM+0xB544, rpm)
            cpu.sample(25, 25)
            for _ in range(200):
                self.assertEqual(cpu.monitor(), 0)
            self.assertEqual(cpu.get_float(RAM+0xDA2C), 25)
            self.assertEqual(cpu.get_float(RAM+0xDA30), 25)
            self.assertTrue(all(cpu.read(RAM+a, 2) == 0 for a in range(0xDA34, 0xDA40, 2)))

    def test_qualified_positive_control_reports_then_clears_current_with_history_held(self):
        #12800 is a native branch positive control, not a requested vehicle test.
        for image in self.images.values():
            cpu = CamPerformanceMachine(image)
            cpu.put_float(RAM+0xB544, 12800)
            cpu.sample(20, 20)
            for _ in range(47):
                self.assertEqual(cpu.monitor(), 0)
            self.assertEqual(cpu.monitor(), 0x0C)
            cpu.execute(0x63174, FALLBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xD270, 1) & 0x80, 0x80)
            cpu.put_float(RAM+0xB544, 3000)
            cpu.sample(20, 0)
            for _ in range(47):
                self.assertEqual(cpu.monitor(), 0x0C)
            self.assertEqual(cpu.monitor(), 0)
            self.assertEqual(cpu.read(RAM+0x8E70, 2), 0x00FF)
            self.assertEqual(cpu.read(RAM+0xDAC2, 1) & 0x0C, 0x0C)
            cpu.execute(0x63174, FALLBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xD270, 1) & 0x80, 0)

    def test_zero_target_rest_offset_failure_and_disqualification_reset(self):
        for image in self.images.values():
            cpu = CamPerformanceMachine(image)
            cpu.sample(0, 45, offset=0)
            for _ in range(156):
                self.assertEqual(cpu.monitor(), 0)
            self.assertEqual(cpu.monitor(), 0x0C)
            cpu.write(RAM+0xDB25, 0, 1)
            cpu.monitor()
            self.assertEqual(cpu.read(RAM+0xDA28, 1) & 0x80, 0)
            self.assertTrue(all(cpu.read(RAM+a, 2) == 0 for a in range(0xDA34, 0xDA3C, 2)))
            # Losing eligibility does not itself clear the current DTC.
            self.assertEqual(cpu.read(RAM+0x8E70, 1) & 0x0C, 0x0C)


if __name__ == '__main__':
    unittest.main(verbosity=2)
