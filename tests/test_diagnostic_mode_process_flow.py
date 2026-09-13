#!/usr/bin/env python3
"""Trace retained diagnostic mode selection and its normal-mode reset branch.

Connector, stopped status, runtime, battery and retained records are supplied.
The mode publisher and selected native dispatcher execute; no transport or
physical ignition/connector state is inferred from these controlled cases.
"""
import _test_paths
from itertools import product
import unittest

from test_cam_sensor_process_flow import CamSensorMachine, ROOT, RAM
from test_avcs_diagnostic_process_flow import RAW_STATUS_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_native_fault_cut_execution import FaultCutMachine, FAULT_WRITES

MODE_WRITES = {(RAM+0x8FA0, 2), (RAM+0xDB22, 2)} | {
    (RAM+a, 1) for a in (0xDC08, 0xDC09, 0xDC10, 0xDC11, 0xDB2A, 0xDB2C,
                         0xDAB4, 0xDAB5)}


class DiagnosticModeMachine(CamSensorMachine):
    LOOKUPS = CamSensorMachine.LOOKUPS | {
        0x567B4, 0x56856, 0x5690E, 0x56992, 0x19BE2, 0x1A256,
        0x564B0, 0x56E12, 0x569F0, 0x56AA2, 0x56B54, 0x56C14,
        0x56CAE, 0x56D60,
        0x5652C, 0x565A2, 0x53408, 0x534F0, 0x3BC38,
    }

    def __init__(self, image):
        super().__init__(image)
        # Explicit clean paired diagnostic history bytes. These immediately
        # follow the three 54-byte status banks and include protected mode.
        for a in range(0x8F9C, 0x8FC0, 2):
            self.write(RAM+a, 0x00FF, 2)
        for a, n in MODE_WRITES:
            self.write(a, 0, n)
        self.write(RAM+0x8FA0, 0x00FF, 2)
        self.write(RAM+0x8260, 0x00FF, 2)
        self.write(RAM+0xB51E, 0x10, 1)
        self.write(RAM+0xB52C, 0, 1)
        self.put_float(RAM+0xB194, 67)
        self.write(RAM+0xDAB4, 0, 1)
        self.write(RAM+0xDAB5, 0, 1)

    def select_mode(self):
        self.execute(0x567B4, MODE_WRITES)
        mode = self.read(RAM+0x8FA0, 1)
        assert self.read(RAM+0x8FA0, 2) == mode << 8 | (mode ^ 255)
        return mode


class DiagnosticModeProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x51124, 0x5116E), (0x511C8, 0x511E0),
                         (0x564B0, 0x5652C), (0x567B4, 0x56E64),
                         (0x7C980, 0x7C986), (0x7C994, 0x7C998),
                         (0x19BE2, 0x19BF6)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_connector_selects_mode_once_per_running_qualification_and_stopped_state_rearms_it(self):
        for image, connector in product(self.images.values(), (0, 0x80)):
            cpu = DiagnosticModeMachine(image)
            cpu.write(RAM+0xB51E, 0x10 | connector, 1)
            self.assertEqual(cpu.select_mode(), 0xFF if connector else 0)
            self.assertEqual(cpu.read(RAM+0xDC11, 1), 1)
            cpu.write(RAM+0xB51E, 0x10 | (connector ^ 0x80), 1)
            self.assertEqual(cpu.select_mode(), 0xFF if connector else 0)
            cpu.write(RAM+0xB52C, 0x80, 1)
            cpu.put_float(RAM+0xB544, 0)
            self.assertEqual(cpu.select_mode(), 0xFF if connector else 0)
            self.assertEqual(cpu.read(RAM+0xDC11, 1), 0)
            cpu.write(RAM+0xB52C, 0, 1)
            cpu.put_float(RAM+0xB544, 400)
            self.assertEqual(cpu.select_mode(), 0 if connector else 0xFF)

    def test_mode_selection_uses_runtime_rpm_and_battery_boundaries_and_retained_a5_override(self):
        for image in self.images.values():
            for rpm, runtime, battery in product((399, 400), (62, 63), (7.99, 8)):
                cpu = DiagnosticModeMachine(image)
                cpu.put_float(RAM+0xB544, rpm)
                cpu.write(RAM+0xB688, runtime, 2)
                cpu.put_float(RAM+0xABB4, battery)
                cpu.write(RAM+0xB51E, 0x90, 1)
                expected = 0xFF if rpm >= 400 and runtime > 62 and battery >= 8 else 0
                self.assertEqual(cpu.select_mode(), expected)
                cpu.write(RAM+0x8260, 0xA55A, 2)
                self.assertEqual(cpu.select_mode(), 0xA5)

    def test_normal_mode_transition_resets_eligible_raw_cam_latches_but_holds_current_status(self):
        for image in self.images.values():
            cpu = DiagnosticModeMachine(image)
            # A recovered cam current has separate raw history. Include a
            # still-current OCV fault to prove raw reset does not clear it.
            cpu.write(RAM+0xDAE4, 0x18, 1)
            cpu.write(RAM+0xDAE5, 0xA0, 1)
            cpu.write(RAM+0x8EB6, 0xA05F, 2)
            cpu.write(RAM+0x8FA0, 0xFF00, 2)
            cpu.write(RAM+0xDB2C, 0, 1)
            cpu.write(RAM+0xDC11, 0, 1)
            cpu.execute(0x51124, MODE_WRITES | RAW_STATUS_WRITES)
            self.assertEqual(cpu.read(RAM+0x8FA0, 2), 0x00FF)
            self.assertEqual(cpu.read(RAM+0xDC08, 1), 0xFF)
            self.assertEqual(cpu.read(RAM+0xDAE4, 1), 0)
            self.assertEqual(cpu.read(RAM+0xDAE5, 1), 0)
            self.assertEqual(cpu.read(RAM+0x8EB6, 2), 0xA05F)
            self.assertIn(0x5339C, cpu.entered)

    def test_complete_mode_dispatch_honors_enabled_descriptor_rules_without_changing_current_status(self):
        for image, mode in product(self.images.values(), (0xFF, 0xA5)):
            field = 7 if mode == 0xFF else 8
            cpu = DiagnosticModeMachine(image)
            cpu.write(RAM+0xB51E, 0x90, 1)
            if mode == 0xA5:
                cpu.write(RAM+0x8260, 0xA55A, 2)
            initial = [0xA5]*54
            expected = initial.copy()
            for identifier in range(153):
                desc = 0x5BDF0+20*identifier
                offset, mask = image[desc+1:desc+3]
                if image[0x5BD54+identifier] != 1:
                    continue
                rule = image[desc+field]
                if rule == 0 and identifier != 0x65 and image[desc+16] == 1:
                    expected[offset] &= mask ^ 255
                elif rule in (1, 2):
                    expected[offset] |= mask
            for i, value in enumerate(initial):
                cpu.write(RAM+0xDAB6+i, value, 1)
            cpu.execute(0x51124, MODE_WRITES | RAW_STATUS_WRITES)
            self.assertEqual(cpu.read(RAM+0x8FA0, 1), mode)
            self.assertEqual([cpu.read(RAM+0xDAB6+i, 1) for i in range(54)], expected)
            self.assertEqual(cpu.read(RAM+0x8EB4, 2), 0x00FF)
            self.assertIn(0x53408 if mode == 0xFF else 0x534F0,
                          [pc for pc, op in cpu.trace])
            if mode == 0xFF:
                self.assertIn(0x3BC38, cpu.entered)
                self.assertNotIn(0x4F6F4, cpu.entered)  # Installed getter returns0.

    def test_native_startup_resets_mode_latch_and_samples_connector_before_running(self):
        for image, retained, connector in product(self.images.values(),
                                                  (0, 0xA5), (0, 0x80)):
            cpu = DiagnosticModeMachine(image)
            cpu.write(RAM+0xDB2C, 0xA5, 1)
            cpu.write(RAM+0x8260, retained << 8 | (retained ^ 255), 2)
            cpu.write(RAM+0xB51E, 0x10 | connector, 1)
            cpu.execute(0x51378, MODE_WRITES)
            expected = 0xFF if connector and retained != 0xA5 else 0
            self.assertEqual(cpu.read(RAM+0x8FA0, 1), expected)
            self.assertEqual(cpu.read(RAM+0xDB2C, 1), expected)
            self.assertEqual(cpu.read(RAM+0xDC08, 1), expected)
            self.assertEqual(cpu.read(RAM+0xDC11, 1), 0)

    def test_diagnostic_inhibit_timer_uses_raw_history_rpm_and_temperature_with_distinct_modes(self):
        for image, mode, temperature in product(self.images.values(),
                (0, 0xFF, 0xA5), (-16, 0)):
            threshold = 313 if temperature <= -15 and mode == 0xFF else 156
            cpu = DiagnosticModeMachine(image)
            cpu.write(RAM+0x8FA0, mode << 8 | (mode ^ 255), 2)
            cpu.write(RAM+0xDC08, mode, 1)
            cpu.write(RAM+0xDAE4, 0x18, 1)
            cpu.put_float(RAM+0xB194, temperature)
            cpu.put_float(RAM+0xB544, 1999)
            cpu.execute(0x56856, MODE_WRITES)
            self.assertEqual(cpu.read(RAM+0xDB22, 2), 0)
            cpu.put_float(RAM+0xB544, 2000)
            for _ in range(threshold):
                cpu.execute(0x56856, MODE_WRITES)
            cpu.execute(0x5690E, MODE_WRITES)
            self.assertEqual(cpu.read(RAM+0xDB2A, 1), int(mode != 0))
            cpu.execute(0x56856, MODE_WRITES)
            cpu.execute(0x5690E, MODE_WRITES)
            self.assertEqual(cpu.read(RAM+0xDB2A, 1), 0)
            if mode == 0xFF:
                cpu.write(RAM+0xDAE4, 0, 1)
                cpu.execute(0x56856, MODE_WRITES)
                self.assertEqual(cpu.read(RAM+0xDB22, 2), 65535)

    def test_selected_modes_do_not_request_cut_with_other_fault_inputs_clear(self):
        for image, mode in product(self.images.values(), (0, 0xFF, 0xA5)):
            cpu = DiagnosticModeMachine(image)
            if mode == 0xFF:
                cpu.write(RAM+0xB51E, 0x90, 1)
            if mode == 0xA5:
                cpu.write(RAM+0x8260, 0xA55A, 2)
            cpu.execute(0x51124, MODE_WRITES | RAW_STATUS_WRITES)
            cpu.fallback_status()
            self.assertEqual(cpu.read(RAM+0xD26C, 5), 0)
            target = FaultCutMachine(image)
            # Transfer real mode outputs, its descriptor-produced raw bank
            # and all protected current bytes. Other endpoint/DBW faults
            # remain the receiving harness's explicitly clear fixture.
            for i in range(54):
                target.write(RAM+0xDAB6+i, cpu.read(RAM+0xDAB6+i, 1), 1)
                target.write(RAM+0x8E58+2*i, cpu.read(RAM+0x8E58+2*i, 2), 2)
            for address, size in ((0x8FA0, 2), (0xDB2A, 1), (0xB51E, 1)):
                target.write(RAM+address, cpu.read(RAM+address, size), size)
            target.invoke(0x64874, FAULT_WRITES)
            for rpm in (2500, 2800, 2999, 3000, 3200, 3500, 4144):
                self.assertEqual(target.fault_cut(rpm), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
