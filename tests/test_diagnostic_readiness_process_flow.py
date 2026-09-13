#!/usr/bin/env python3
"""Execute the six native diagnostic gates and their fault-counter consumers.

The entire 5116E publisher runs in native order. Shutdown, battery, barometric
estimate, temperature history and other condition flags are explicit inputs.
Reset helpers execute; their full 4F6F4 caller and snapshot transport do not.
Direct OCV-monitor calls in the captured image test its retained native body,
not the historical task pointer, which bypassed that body.
"""
import _test_paths
from itertools import product
import struct
import unittest

from test_avls_diagnostic_process_flow import (
    AVLSDiagnosticMachine, ROOT, RAM, ELECTRICAL_WRITES,
)
from test_avcs_diagnostic_process_flow import COUNTER_WRITES, STATUS_WRITES
from test_iat_fault_process_flow import IATFaultMachine, IAT_FAULT_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling

GATE_WRITES = {(RAM+a, 1) for a in (*range(0xDB24, 0xDB2A),
                                   *range(0xDC0A, 0xDC10), 0xDB2B)}


class DiagnosticReadinessMachine(AVLSDiagnosticMachine):
    LOOKUPS = AVLSDiagnosticMachine.LOOKUPS | IATFaultMachine.LOOKUPS | {
        0x565BE, 0x565F8, 0x56668, 0x56694, 0x566D4, 0x56700,
        0x1487E, 0x25FE2, 0x3D50A,
    }

    def __init__(self, image):
        super().__init__(image)
        for a, n in GATE_WRITES | IAT_FAULT_WRITES:
            self.write(a, 0, n)
        self.write(RAM+0x8E84, 0x00FF, 2)
        for a in (0xDB7F, 0xDB80):
            self.write(RAM+a, 0x20, 1)  # Snapshot already queued.
        for a, value in ((0xC778, 0), (0xB289, 4), (0xBF9C, 0), (0xCCBB, 0)):
            self.write(RAM+a, value, 1)
        for a, value in ((0xABB4, 14), (0xCFBC, 760),
                         (0xB3D0, 20), (0xB6C0, 67)):
            self.put_float(RAM+a, value)
        self.write(RAM+0xABB0, 65535, 2)
        self.sample(100, 0, 1)
        self.electrical_sample(40, 0, .2)

    def gates(self):
        self.execute(0x5116E, GATE_WRITES)
        self_gate = tuple(self.read(RAM+a, 1) for a in range(0xDB24, 0xDB2A))
        assert self_gate == tuple(self.read(RAM+a, 1) for a in range(0xDC0A, 0xDC10))
        return self_gate

    def native_monitors(self):
        self.execute(0x69568, COUNTER_WRITES | STATUS_WRITES)
        self.electrical()
        self.execute(0x685C8, IAT_FAULT_WRITES)


class DiagnosticReadinessProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x5116E, 0x51194), (0x511E0, 0x511F8),
                         (0x565BE, 0x567B4), (0x50E16, 0x50E20),
                         (0x50F00, 0x50F08), (0x7C95C, 0x7C95D),
                         (0x7C988, 0x7C994), (0x1487E, 0x148B2),
                         (0x25FE2, 0x25FFC), (0x3D50A, 0x3D524)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_reset_countdown_and_shutdown_control_all_six_native_publications(self):
        for image in self.images.values():
            cpu = DiagnosticReadinessMachine(image)
            self.assertEqual(cpu.gates(), (1,)*6)
            cpu.execute(0x50E16, GATE_WRITES)
            cpu.execute(0x56748, GATE_WRITES)
            self.assertEqual(cpu.read(RAM+0xDB2B, 1), 63)
            self.assertEqual(cpu.read(RAM+0xDB24, 6), 0)
            # Reset clears publications; the six private DC0A..DC0F bytes
            # are recomputed by the next ordered publisher invocation.
            self.assertEqual(cpu.read(RAM+0xDC0A, 6), 0x010101010101)
            for remaining in range(62, -1, -1):
                self.assertEqual(cpu.gates(), (0,)*6)
                self.assertEqual(cpu.read(RAM+0xDB2B, 1), remaining)
            self.assertEqual(cpu.gates(), (1,)*6)
            for shutdown in (1, 2, 255):
                cpu.write(RAM+0xC778, shutdown, 1)
                self.assertEqual(cpu.gates(), (0,)*6)
            cpu.write(RAM+0xC778, 0, 1)
            self.assertEqual(cpu.gates(), (1,)*6)

    def test_entire_publisher_preserves_distinct_battery_barometric_and_condition_gates(self):
        for image in self.images.values():
            battery = struct.unpack_from('>f', image, 0x56660)[0]
            condition_threshold = struct.unpack_from('>f', image, 0x7C98C)[0]
            cases = (
                (0xABB4, battery-.01, (1, 0, 0, 0, 0, 1)),
                (0xABB4, battery, (1,)*6),
                (0xCFBC, 562.99, (1, 1, 0, 0, 1, 1)),
                (0xCFBC, 563, (1,)*6),
                (0xB6C0, -7.01, (1, 1, 1, 1, 0, 1)),
                (0xB6C0, -7, (1,)*6),
            )
            for address, value, expected in cases:
                cpu = DiagnosticReadinessMachine(image)
                cpu.put_float(RAM+address, value)
                self.assertEqual(cpu.gates(), expected)
            for flags, value in product((0, 2, 4, 6),
                                        (condition_threshold-.01, condition_threshold)):
                cpu = DiagnosticReadinessMachine(image)
                cpu.write(RAM+0xB289, flags, 1)
                cpu.put_float(RAM+0xB3D0, value)
                self.assertEqual(cpu.gates()[3], int(value >= condition_threshold or bool(flags & 4)))
            for first, second in product((0, 4), repeat=2):
                cpu = DiagnosticReadinessMachine(image)
                cpu.write(RAM+0xBF9C, first, 1)
                cpu.write(RAM+0xCCBB, second, 1)
                self.assertEqual(cpu.gates(), (1, 1, 1, 1, 1, int(not(first or second))))

    def test_installed_configuration_publisher_bypasses_only_its_specific_condition(self):
        for image in self.images.values():
            cpu = DiagnosticReadinessMachine(image)
            cpu.write(RAM+0xB289, 0x35, 1)
            cpu.execute(0x147C0, {(RAM+0xB288, 1), (RAM+0xB289, 1)})
            self.assertEqual(cpu.read(RAM+0xB288, 1), 0x81)
            self.assertEqual(cpu.read(RAM+0xB289, 1), 0xF4)
            cpu.put_float(RAM+0xB3D0, -100)
            self.assertEqual(cpu.gates(), (1,)*6)
            cpu.put_float(RAM+0xCFBC, 562)
            self.assertEqual(cpu.gates(), (1, 1, 0, 0, 1, 1))

    def test_native_temperature_history_uses_iat_and_retains_the_minimum_until_reinitialization(self):
        writes = {(RAM+0xB6C0, 4), (RAM+0xB6C4, 1),
                  (RAM+0x812C, 4), (RAM+0x8130, 2), (RAM+0x8132, 2)}
        for image in self.images.values():
            cpu = DiagnosticReadinessMachine(image)
            cpu.write(RAM+0xB51D, 0, 1)
            cpu.write(RAM+0xCC4C, 0, 1)
            cpu.write(RAM+0xB688, 0, 2)
            cpu.put_float(RAM+0xAD8C, 37)
            cpu.put_float(RAM+0xB3AC, 37)
            cpu.put_float(RAM+0xB3B8, 37)
            cpu.execute(0x1AEFC, writes)
            self.assertEqual(cpu.get_float(RAM+0xB6C0), 120)
            for _ in range(2):
                cpu.execute(0x1AE04, writes)
            self.assertEqual(cpu.get_float(RAM+0xB6C0), 37)
            self.assertEqual(cpu.get_float(RAM+0x812C), 37)
            cpu.write(RAM+0xB688, 250, 2)
            cpu.put_float(RAM+0xB3AC, 67)
            cpu.put_float(RAM+0xB3B8, -10)
            cpu.execute(0x1AE04, writes)
            self.assertEqual(cpu.get_float(RAM+0xB6C0), -10)
            self.assertEqual(cpu.gates()[4], 0)
            cpu.put_float(RAM+0xB3B8, 37)
            cpu.execute(0x1AE04, writes)
            self.assertEqual(cpu.get_float(RAM+0xB6C0), -10)
            self.assertEqual(cpu.get_float(RAM+0x812C), 37)
            cpu.execute(0x1AEFC, writes)
            cpu.execute(0x1AE04, writes)
            self.assertEqual(cpu.get_float(RAM+0xB6C0), 37)
            self.assertEqual(cpu.gates()[4], 1)

    def test_native_gate_loss_resets_partial_ocv_avls_and_iat_qualification(self):
        for image in self.images.values():
            cpu = DiagnosticReadinessMachine(image)
            for _ in range(7):
                cpu.gates()
                cpu.native_monitors()
            self.assertEqual(cpu.read(RAM+0xD338, 1), 7)
            self.assertEqual(cpu.read(RAM+0xD37C, 1), 7)
            self.assertEqual(cpu.read(RAM+0xD38C, 1), 7)
            cpu.write(RAM+0xC778, 1, 1)
            self.assertEqual(cpu.gates(), (0,)*6)
            cpu.native_monitors()
            for address in (0xD338, 0xD37C, 0xD38C):
                self.assertEqual(cpu.read(RAM+address, 1), 0)
            cpu.write(RAM+0xC778, 0, 1)
            cpu.put_float(RAM+0xABB4, 10)
            self.assertEqual(cpu.gates()[:2], (1, 0))
            cpu.native_monitors()
            self.assertEqual(cpu.read(RAM+0xD338, 1), 1)
            self.assertEqual(cpu.read(RAM+0xD37C, 1), 0)
            self.assertEqual(cpu.read(RAM+0xD38C, 1), 0)

    def test_readiness_loss_retains_acquired_fault_until_native_healthy_confirmation(self):
        for image in self.images.values():
            cpu = DiagnosticReadinessMachine(image)
            cpu.gates()
            for _ in range(126):
                cpu.native_monitors()
            self.assertEqual(cpu.read(RAM+0x8EB6, 1), 0xA0)
            self.assertEqual(cpu.read(RAM+0x8EBA, 1), 0x24)
            self.assertEqual(cpu.read(RAM+0x8E84, 1), 2)
            cpu.write(RAM+0xC778, 1, 1)
            cpu.gates()
            cpu.native_monitors()
            self.assertEqual(cpu.read(RAM+0x8EB6, 1), 0xA0)
            self.assertEqual(cpu.read(RAM+0x8EBA, 1), 0x24)
            self.assertEqual(cpu.read(RAM+0x8E84, 1), 2)
            cpu.write(RAM+0xC778, 0, 1)
            cpu.sample(40, .2, .2)
            cpu.electrical_sample(40, .2, .2)
            cpu.write(RAM+0xABB0, 32768, 2)
            cpu.gates()
            for _ in range(126):
                cpu.native_monitors()
            for address in (0x8EB6, 0x8EBA, 0x8E84):
                self.assertEqual(cpu.read(RAM+address, 2), 0x00FF)
            for address, mask in ((0xDAE5, 0xA0), (0xDAE7, 0x24), (0xDACC, 2)):
                self.assertEqual(cpu.read(RAM+address, 1), mask)


if __name__ == '__main__':
    unittest.main(verbosity=2)
