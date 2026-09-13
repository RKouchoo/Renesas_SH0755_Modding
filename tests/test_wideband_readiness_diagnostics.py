#!/usr/bin/env python3
"""Execute the remaining direct WB-readiness diagnostic consumers.

The heater/feedback producers, prerequisite-list walker and local diagnostic
workers are native. Retained records, run permission and counter-boundary
controls are explicit fixtures, not observations from the vehicle.
"""
import _test_paths
import unittest

from test_wideband_heater_process_flow import WidebandHeaterMachine
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT, RAM = _test_paths.ROOT, 0xFFFF0000
HEATER_DIAG_WRITES = {(RAM+a, 4) for a in (0xD1D8, 0xD1DC)} | {
    (RAM+a, 2) for a in (0xD1EA, 0xD1EC, 0xD1F6)} | {
    (RAM+a, 1) for a in (0xD1E0, 0xD1E1)}
REAR_DIAG_WRITES = {(RAM+a, 1) for a in (*range(0xDA18, 0xDA20), 0xDA0E, 0xDA0F)} | {
    (RAM+a, 2) for a in (0xDA00, 0xDA02)} | {
    (RAM+a, 4) for a in (0xDA10, 0xDA14)}


class WBReadinessDiagnosticMachine(WidebandHeaterMachine):
    LOOKUPS = WidebandHeaterMachine.LOOKUPS | {
        0x4711E, 0x47132, 0x56E64, 0x56E96, 0x6174A, 0x6186E,
        0x50FF6, 0x5108C, 0x22050, 0x22064, 0x70CD6,
    }

    def __init__(self, image):
        super().__init__(image)
        for a, size in HEATER_DIAG_WRITES | REAR_DIAG_WRITES:
            self.write(a, 0, size)
        self.write(RAM+0xDB25, 1, 1)  # Separate native run-permission boundary.
        self.write(RAM+0xDE08, 0, 1)
        self.write(RAM+0xD804, 0, 2)
        for a in range(0x8E58, 0x8EC4, 2):
            self.write(RAM+a, 0x00FF, 2)  # Clear protected DTC records.
        for a in range(0xDAEC, 0xDB22):
            self.write(RAM+a, 0, 1)
        for a in (0xBD1C, 0xBD1D):
            self.write(RAM+a, 0, 1)
        self.put_float(RAM+0xBD0C, 1)

    def heater_monitor(self):
        self.execute(0x6166C, HEATER_DIAG_WRITES)
        self.execute(0x616CE, HEATER_DIAG_WRITES)
        return tuple(self.read(RAM+a, 1) & 12 for a in (0xD1E0, 0xD1E1))


class WBReadinessDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x1331E, 0x13360), (0x6166C, 0x61934),
                         (0x70B5C, 0x70DF0), (0x56E64, 0x56F0C),
                         (0x57633, 0x57726), (0x57C10, 0x57CB8),
                         (0x4CB18, 0x4CB48), (0x4CC48, 0x4CCC0),
                         (0x5F2C0, 0x5F2D4), (0x7683C, 0x76869)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_heater_history_is_initialized_and_then_updated_through_computed_bank_fields(self):
        for image in self.images:
            cpu = WBReadinessDiagnosticMachine(image)
            cpu.update_wideband(18000)
            cpu.execute(0x1331E, {(RAM+0xB1A4, 4), (RAM+0xB1A8, 4)})
            self.assertEqual(cpu.array(RAM+0xB1A4, 2), [50, 50])
            cpu.heater(0)
            self.assertEqual(cpu.array(RAM+0xB1A4, 2), [0, 0])
            cpu.heater(18000)
            self.assertEqual(cpu.array(RAM+0xB1A4, 2), [50, 50])
            for index, entry in ((0x44, 0x319AE), (0x45, 0x319BA)):
                self.assertEqual(cpu.read(0x4B6FC+4*index, 4), entry)
                self.assertEqual(cpu.invoke(entry, set()), 50)

    def test_heater_activity_metric_50_passes_but_other_permissions_control_retention(self):
        for image in self.images:
            cpu = WBReadinessDiagnosticMachine(image)
            cpu.heater(18000)
            for _ in range(522):
                flags = cpu.heater_monitor()
            self.assertEqual(flags, (0, 0))
            self.assertEqual(cpu.heater_monitor(), (4, 4))
            # Below500 readiness passes; the accumulated heater-duty threshold
            # applies to failure qualification, not this good-result branch.
            self.assertLess(cpu.get_float(RAM+0xD1D8), 30000)
            cpu.heater(0)
            self.assertEqual(cpu.heater_monitor(), (4, 4))
            self.assertEqual(cpu.read(RAM+0xD1EC, 2), 0)
            self.assertEqual(cpu.get_float(RAM+0xD1D8), 0)
            cpu.write(RAM+0xDB25, 0, 1)
            self.assertEqual(cpu.heater_monitor(), (0, 0))

    def test_activity_failure_control_is_separate_and_disabled_reporters_do_not_publish(self):
        for image in self.images:
            cpu = WBReadinessDiagnosticMachine(image)
            cpu.heater(18000)
            cpu.write(RAM+0xD1EC, 523, 2)
            for metric, duty_sum, count, expected in ((600, 29999, 102, 0),
                                                    (600, 30000, 101, 0),
                                                    (600, 30000, 102, 8),
                                                    (500, 30000, 102, 8),
                                                    (499, 30000, 102, 4),
                                                    (50, 30000, 102, 4)):
                for a in (0xAE70, 0xAE74):
                    cpu.put_float(RAM+a, metric)  # Native-input boundary control.
                for a in (0xD1D8, 0xD1DC):
                    cpu.put_float(RAM+a, duty_sum)
                for a in (0xD1EA, 0xD1F6):
                    cpu.write(RAM+a, count, 2)
                for a in (0xD1E0, 0xD1E1):
                    cpu.write(RAM+a, 0, 1)
                cpu.execute(0x616CE, HEATER_DIAG_WRITES)
                self.assertEqual(tuple(cpu.read(RAM+a, 1) & 12 for a in (0xD1E0, 0xD1E1)),
                                 (expected, expected))
                cpu.execute(0x61858, set())
                self.assertEqual(cpu.read(RAM+0xB744, 2), 0)

    def test_rear_monitor_uses_native_feedback_state_and_retains_counter_when_disqualified(self):
        for image in self.images:
            cpu = WBReadinessDiagnosticMachine(image)
            cpu.sensor(18000)
            cpu.qualify()
            cpu.phase(0)
            cpu.phase(4)
            for a in (0xDA0E, 0xDA0F):
                cpu.write(RAM+a, 0xD5, 1)
            for a in (0xDA00, 0xDA02):
                cpu.write(RAM+a, 123, 2)
            cpu.execute(0x70B5C, REAR_DIAG_WRITES)
            for a in (0xDA0E, 0xDA0F):
                self.assertEqual(cpu.read(RAM+a, 1), 0x55)
            for a in (0xDA00, 0xDA02):
                self.assertEqual(cpu.read(RAM+a, 2), 123)
            self.assertEqual(cpu.read(RAM+0xDA1A, 1), 0)
            self.assertEqual(cpu.read(RAM+0xDA1B, 1), 0)
            # Explicit eligible-state control. This is not the installed
            # publisher's settled feedback state or an observed ECU state.
            for a in (0xB91E, 0xB91F):
                cpu.write(RAM+a, 1, 1)
            for a in (0xBD1C, 0xBD1D):
                cpu.write(RAM+a, 128, 1)
            for a in (0xB8D4, 0xB8D8):
                cpu.put_float(RAM+a, 1.1)
            for a in (0xB920, 0xB924):
                cpu.put_float(RAM+a, 1.5)
            for a in (0xDA00, 0xDA02):
                cpu.write(RAM+a, 3124, 2)
            for index in (75, 111):
                base = 0x5BDF0+20*index
                offset, mask = image[base+1:base+3]
                cpu.write(RAM+0xDAEC+offset, mask, 1)
            cpu.put_float(RAM+0xB420, 20)
            cpu.put_float(RAM+0xB3AC, 85)
            cpu.execute(0x70B5C, REAR_DIAG_WRITES)
            for a in (0xDA0E, 0xDA0F):
                self.assertEqual(cpu.read(RAM+a, 1), 0xD5)
            for a in (0xDA00, 0xDA02):
                self.assertEqual(cpu.read(RAM+a, 2), 3125)
            cpu.write(RAM+0xB52C, 128, 1)
            cpu.execute(0x70B5C, REAR_DIAG_WRITES)
            for a in (0xDA00, 0xDA02):
                self.assertEqual(cpu.read(RAM+a, 2), 0)
            self.assertEqual(cpu.read(RAM+0xB744, 2), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
