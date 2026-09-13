#!/usr/bin/env python3
"""Connect IAT filtered-ADC electrical faults to substitution and recovery.

Diagnostic readiness/mode and raw ADC counts are supplied. Native conversion,
electrical classification, reporting and the entire fallback aggregator run.
P0111 is disabled in stock and both patches; the separate diagnostic-record
suite verifies its report gate and retained-status masking. Physical sensor
faults and diagnostic transport are not modeled here.
"""
import _test_paths
import unittest

from test_avcs_diagnostic_process_flow import AVCSDiagnosticMachine, RAM, ROOT

IAT_FAULT_WRITES = {(RAM+0xD338, 1), (RAM+0xD339, 1),
                    (RAM+0x8E84, 2), (RAM+0xDACC, 1), (RAM+0xDB02, 1),
                    (RAM+0xDB7F, 1), (RAM+0xDB80, 1)}


class IATFaultMachine(AVCSDiagnosticMachine):
    LOOKUPS = AVCSDiagnosticMachine.LOOKUPS | {0x47124, 0x78AC, 0x685D2, 0x6864C}

    def __init__(self, image, raw):
        super().__init__(image)
        for a, n in IAT_FAULT_WRITES:
            self.write(a, 0, n)
        self.write(RAM+0x8E84, 0x00FF, 2)
        for a in (0xDB7F, 0xDB80):
            self.write(RAM+a, 0x20, 1)  # Snapshot already queued, as in OCV tests.
        self.write(RAM+0xDB24, 1, 1)
        self.sample_adc(raw)

    def sample_adc(self, raw):
        # Set current and prior ADC equal for a settled electrical sample.
        self.write(RAM+0xAB3A, raw, 2)
        self.write(RAM+0xABB0, raw, 2)
        return self.convert()

    def monitor_iat(self):
        self.execute(0x685C8, IAT_FAULT_WRITES)
        self.fallback_status()
        return self.update()


class IATFaultProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        for image in cls.images:
            for a, b in ((0x78AC, 0x7904), (0x685C8, 0x686F0),
                         (0x7B288, 0x7B28C), (0x74D12, 0x74D14),
                         (0x5BDA6, 0x5BDA9)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_electrical_thresholds_use_unsigned_filtered_counts_and_native_boundaries(self):
        for image in self.images:
            low = int.from_bytes(image[0x7B28A:0x7B28C], 'big')
            high = int.from_bytes(image[0x7B288:0x7B28A], 'big')
            self.assertEqual((low, high), (2150, 61814))
            for raw, status in ((0, 2), (low-1, 2), (low, 0),
                                (high-1, 0), (high, 1), (65535, 1)):
                cpu = IATFaultMachine(image, raw)
                cpu.execute(0x78AC, set())
                self.assertEqual(cpu.r[0], status)

    def test_fault_reporting_substitutes_twenty_c_and_healthy_confirmation_recovers(self):
        for image in self.images:
            for raw, mask in ((0, 1), (65535, 2)):
                cpu = IATFaultMachine(image, raw)
                for _ in range(8):
                    cpu.monitor_iat()
                    self.assertEqual(cpu.read(RAM+0xD26C, 1) & 0x20, 0)
                self.assertEqual(cpu.monitor_iat(), 20)
                self.assertEqual(cpu.read(RAM+0x8E84, 1), mask)
                self.assertEqual(cpu.read(RAM+0xD26C, 1) & 0x20, 0x20)
                self.assertNotEqual(cpu.get_float(RAM+0xABAC), 20)
                restored = cpu.sample_adc(32768)
                self.assertEqual(cpu.monitor_iat(), restored)
                self.assertEqual(cpu.read(RAM+0xD26C, 1) & 0x20, 0)
                self.assertEqual(cpu.read(RAM+0x8E84, 2), 0x00FF)
                # IAT substitution uses current status. Its separate raw
                # diagnostic latch may remain without forcing substitution.
                self.assertEqual(cpu.read(RAM+0xDACC, 1), mask)

    def test_readiness_loss_resets_electrical_qualification_counter(self):
        for image in self.images:
            cpu = IATFaultMachine(image, 65535)
            for _ in range(7):
                cpu.monitor_iat()
            self.assertEqual(cpu.read(RAM+0xD338, 1), 7)
            cpu.write(RAM+0xDB24, 0, 1)
            cpu.monitor_iat()
            self.assertEqual(cpu.read(RAM+0xD338, 1), 0)
            self.assertEqual(cpu.read(RAM+0xD26C, 1) & 0x20, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
