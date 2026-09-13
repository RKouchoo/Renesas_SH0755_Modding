#!/usr/bin/env python3
"""Trace sampled port-E AVLS inputs through debounce and the switch publisher.

GPIO register observations and the separate 766C serial-input transaction
returns are supplied. Native 6B08/6BB4 perform initialization/debounce and
193D0 publishes all of its switch flags with native internal getters. The
serial bus, input pin electrical levels and task cadence are not simulated.
"""
import _test_paths
from itertools import product
import unittest

from test_avls_diagnostic_process_flow import (
    AVLSDiagnosticMachine, ROOT, RAM, PERFORMANCE_WRITES,
)
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_wideband_status_dependency_flow import WidebandStatusMachine, OUTPUT_WRITES

SAMPLE_WRITES = {(RAM+a, 2) for a in (0xAAE4, 0xAAE6, 0xAAE8,
                  0xAAEE, 0xAAF0, 0xAAF2, 0xAAF4, 0xAAF6)} | {
    (RAM+a, 1) for a in (0xAAEA, 0xAAEB, 0xAAEC, 0xAAF8, 0xAAF9, 0xAAFA, 0xAAFB)}
PUBLISH_WRITES = {(RAM+a, 1) for a in range(0xB51A, 0xB522)}


class RuntimeSwitchMachine(AVLSDiagnosticMachine):
    LOOKUPS = AVLSDiagnosticMachine.LOOKUPS | {
        0x3C558, 0x3C57A, 0x3C58E, 0x3C56C, 0x1A4A4, 0x3BE62, 0xF414,
    }

    def __init__(self, image, port_e=0):
        super().__init__(image)
        for a in range(0xAAE4, 0xAAFF):
            self.write(RAM+a, 0, 1)
        for a in range(0xB51A, 0xB522):
            self.write(RAM+a, 0, 1)
        for a in (0xCC6F, 0xCC71, 0xB542, 0xCC50, 0xC778):
            self.write(RAM+a, 0, 1)
        for a, value in ((0xF726, 0), (0xF754, port_e), (0xF74E, 0),
                         (0xF72C, 0), (0xAB10, 0), (0xB540, 0)):
            self.write(RAM+a, value, 2)
        self.serial_inputs = (0, 0, 0)
        self.execute(0x6B08, SAMPLE_WRITES)
        self.execute(0x193D0, PUBLISH_WRITES)

    def call_lookup(self, target):
        if target == 0x766C:
            # Separate multiplexed serial peripheral, not the port-E source.
            channel = self.r[4]
            assert 0 <= channel < 3
            value = self.serial_inputs[channel]
            self.poison_scratch()
            self.r[0] = value
        else:
            super().call_lookup(target)

    def sample_switches(self, port_e):
        self.write(RAM+0xF754, port_e, 2)
        self.execute(0x6BB4, SAMPLE_WRITES)
        self.execute(0x193D0, PUBLISH_WRITES)
        return self.read(RAM+0xB51C, 1) & 0x30


class RuntimeSwitchProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x6B08, 0x6CE4), (0x193D0, 0x19BB0),
                         (0x3C558, 0x3C5A2), (0x1A4A4, 0x1A4BC)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_startup_and_two_sample_debounce_preserve_each_port_e_bank_input(self):
        def expected(value):
            return (0x20 if value & 0x4000 else 0) | (0x10 if value & 0x8000 else 0)
        for image, initial, target in product(self.images.values(),
                (0, 0x4000, 0x8000, 0xC000), (0, 0x4000, 0x8000, 0xC000)):
            cpu = RuntimeSwitchMachine(image, initial)
            self.assertEqual(cpu.read(RAM+0xB51C, 1) & 0x30, expected(initial))
            self.assertEqual(cpu.read(RAM+0xB51E, 1) & 0x06,
                             (4 if initial & 0x4000 else 0) | (2 if initial & 0x8000 else 0))
            self.assertEqual(cpu.sample_switches(target), expected(initial))
            self.assertEqual(cpu.sample_switches(target), expected(target))
            self.assertEqual(cpu.read(RAM+0xAAE6, 2) & 0xC000, target)
            self.assertEqual(cpu.read(RAM+0xAAF4, 2) & 0xC000, target)
            self.assertEqual(cpu.read(RAM+0xB51E, 1) & 0x06,
                             (4 if target & 0x4000 else 0) | (2 if target & 0x8000 else 0))

    def test_retained_reset_input_is_serial_channel_two_bit_two_not_port_e(self):
        for image, port_e, serial in product(self.images.values(),
                (0, 0x4000, 0x8000, 0xC000), (0, 4, 0xFB, 0xFF)):
            cpu = RuntimeSwitchMachine(image, port_e)
            before = cpu.read(RAM+0xB51C, 1) & 0x30
            cpu.serial_inputs = (0, 0, serial)
            self.assertEqual(cpu.sample_switches(port_e), before)
            # AAEC and AAFA are the conditioned/previous serial bytes.
            self.assertEqual(cpu.read(RAM+0xB51A, 1) & 4, 4)
            self.assertEqual(cpu.sample_switches(port_e), before)
            self.assertEqual(cpu.read(RAM+0xAAEC, 1), serial)
            self.assertEqual(cpu.read(RAM+0xB51A, 1) & 4, 0 if serial & 4 else 4)
            self.assertEqual(cpu.read(RAM+0xB51B, 1) & 2, 0 if serial & 4 else 2)

    def test_isolated_port_glitch_is_filtered_before_native_avls_diagnostic(self):
        for image in self.images.values():
            cpu = RuntimeSwitchMachine(image, 0xC000)
            for a in (0xCDF8, 0xCDFC):
                cpu.put_float(RAM+a, 70)
            for tick in range(100):
                self.assertEqual(cpu.sample_switches(0 if tick % 7 == 0 else 0xC000), 0x30)
                cpu.execute(0x705FA, PERFORMANCE_WRITES)
                self.assertEqual(cpu.read(RAM+0x8EBC, 1), 0)
            for _ in range(63):
                cpu.sample_switches(0)
                cpu.execute(0x705FA, PERFORMANCE_WRITES)
            self.assertEqual(cpu.read(RAM+0x8EBC, 1), 0xC0)

    def test_wideband_status_gpio_writes_preserve_avls_input_bits_on_shared_port(self):
        for image, inputs in product(self.images.values(), (0, 0x4000, 0x8000, 0xC000)):
            cpu = RuntimeSwitchMachine(image, inputs)
            status = WidebandStatusMachine(image)
            status.aggregate_and_permission(0)
            status.write(RAM+0xF754, inputs, 2)
            initial = cpu.read(RAM+0xB51C, 1) & 0x30
            for _ in range(260):
                status.execute(0x3B760, OUTPUT_WRITES)
                output = status.read(RAM+0xF754, 2)
                self.assertEqual(output & 0xC000, inputs)
                self.assertEqual(cpu.sample_switches(output), initial)


if __name__ == '__main__':
    unittest.main(verbosity=2)
