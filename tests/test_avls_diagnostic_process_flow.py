#!/usr/bin/env python3
"""Connect native AVLS electrical/switch monitors to fault-status consumers.

Current samples, switch bits, oil temperature and readiness are explicit inputs.
The native report/recovery routines execute, with snapshot requests already
queued. The output consumer receives the exact protected word produced by the
diagnostic machine; task timing and hydraulic response are not simulated.
"""
import _test_paths
from itertools import product
import unittest

from test_avcs_diagnostic_process_flow import (
    AVCSDiagnosticMachine, ROOT, RAM, FALLBACK_WRITES,
)
from test_avls_phase_process_flow import AVLSPhaseMachine
from test_runtime_rom_checksum_execution import before_pump_scaling

ELECTRICAL_WRITES = {(RAM+a, 1) for a in range(0xD38C, 0xD394)} | {
    (RAM+0x8EBA, 2), (RAM+0xDAE7, 1), (RAM+0xDB1D, 1)} | {
    (RAM+0xDB2D+i, 1) for i in range(0x8E, 0x92)}
PERFORMANCE_WRITES = {(RAM+a, 1) for a in (0xD9D8, 0xD9D9, 0xD9DA)} | {
    (RAM+a, 2) for a in range(0xD9DC, 0xD9EC, 2)} | {
    (RAM+0x8EBC, 2), (RAM+0xDAE8, 1), (RAM+0xDB1E, 1),
    (RAM+0xDBC3, 1), (RAM+0xDBC4, 1)}


class AVLSDiagnosticMachine(AVCSDiagnosticMachine):
    LOOKUPS = AVCSDiagnosticMachine.LOOKUPS | {
        0x69CB2, 0x69EF4, 0x3BC10, 0x2450,
        0x70608, 0x706B4, 0x706DE, 0x70842, 0x70852, 0x19E4C, 0x19E74,
    }

    def __init__(self, image):
        super().__init__(image)
        for a, n in ELECTRICAL_WRITES | PERFORMANCE_WRITES:
            self.write(a, 0, n)
        for a in (0x8EBA, 0x8EBC):
            self.write(RAM+a, 0x00FF, 2)
        for i in (*range(0x8E, 0x92), 0x96, 0x97):
            self.write(RAM+0xDB2D+i, 0x20, 1)
        self.write(RAM+0xCC4D, 1, 1)
        self.write(RAM+0xB688, 1000, 2)
        self.put_float(RAM+0xCF94, 50)
        self.electrical_sample(40, .2, .2)

    def electrical_sample(self, duty, measured, reference):
        for pair, value in ((0xCDF8, duty), (0xCDC0, measured), (0xCDD0, reference)):
            for bank in (0, 1):
                self.put_float(RAM+pair+4*bank, value)

    def electrical(self):
        self.execute(0x69CA8, ELECTRICAL_WRITES)
        return self.read(RAM+0x8EBA, 1)

    def performance(self, duty, switches):
        for a in (0xCDF8, 0xCDFC):
            self.put_float(RAM+a, duty)
        self.write(RAM+0xB51C, switches, 1)
        self.execute(0x705FA, PERFORMANCE_WRITES)
        return self.read(RAM+0x8EBC, 1)


class AVLSDiagnosticProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x69CA8, 0x6A128), (0x705FA, 0x708F8),
                         (0x4CC28, 0x4CC48), (0x74F78, 0x74F9C),
                         (0x74D29, 0x74D2B), (0x74D8A, 0x74D92),
                         (0x19E4C, 0x19E88), (0x5C908, 0x5C9E0)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_native_electrical_reports_are_bank_specific_and_clear_after_healthy_current(self):
        for image, (duty, measured, reference, mask) in product(self.images.values(), (
                (40, 0, .2, 0x24), (0, .5, 0, 0x12))):
            cpu = AVLSDiagnosticMachine(image)
            cpu.electrical_sample(duty, measured, reference)
            for _ in range(125):
                self.assertEqual(cpu.electrical(), 0)
            self.assertEqual(cpu.electrical(), mask)
            self.assertEqual(cpu.read(RAM+0x8EBA, 2), (mask << 8) | (mask ^ 255))
            cpu.electrical_sample(40, .2, .2)
            for _ in range(125):
                self.assertEqual(cpu.electrical(), mask)
            self.assertEqual(cpu.electrical(), 0)
            self.assertEqual(cpu.read(RAM+0xDAE7, 1), mask)

    def test_performance_qualification_uses_oil_runtime_readiness_and_feature(self):
        for image, oil, runtime, ready, feature in product(self.images.values(),
                (-1, 0, 50), (749, 750), (0, 1), (0, 1)):
            cpu = AVLSDiagnosticMachine(image)
            cpu.put_float(RAM+0xCF94, oil)
            cpu.write(RAM+0xB688, runtime, 2)
            cpu.write(RAM+0xDB25, ready, 1)
            cpu.write(RAM+0xCC4D, feature, 1)
            cpu.performance(70, 0)
            self.assertEqual(bool(cpu.read(RAM+0xD9D8, 1) & 0x80),
                             oil >= 0 and runtime >= 750 and bool(ready and feature))

    def test_switch_failure_reports_after_native_settle_and_mismatch_counters(self):
        for image, (duty, switch, calls) in product(self.images.values(),
                ((70, 0, 62), (0, 0x30, 376))):
            cpu = AVLSDiagnosticMachine(image)
            for _ in range(calls-1):
                self.assertEqual(cpu.performance(duty, switch), 0)
            self.assertEqual(cpu.performance(duty, switch), 0xC0)
            self.assertEqual(cpu.read(RAM+0xDAE8, 1), 0xC0)
            self.assertEqual(cpu.read(RAM+0xD9D9, 1) & 0xF0, 0)

    def test_healthy_confirmation_requires_success_in_both_output_states(self):
        for image in self.images.values():
            cpu = AVLSDiagnosticMachine(image)
            for _ in range(62):
                cpu.performance(70, 0)
            for _ in range(200):
                self.assertEqual(cpu.performance(70, 0x30), 0xC0)
            self.assertEqual(cpu.read(RAM+0xD9D9, 1) & 0x30, 0x20)
            for _ in range(187):
                self.assertEqual(cpu.performance(0, 0), 0xC0)
            self.assertEqual(cpu.performance(0, 0), 0)
            self.assertEqual(cpu.read(RAM+0x8EBC, 2), 0x00FF)
            self.assertEqual(cpu.read(RAM+0xDAE8, 1), 0xC0)

    def test_native_reported_status_reaches_the_periodic_output_override(self):
        for image in self.images.values():
            cpu = AVLSDiagnosticMachine(image)
            for _ in range(62):
                cpu.performance(70, 0)
            consumer = AVLSPhaseMachine(image)
            consumer.request(3200)
            for phase in range(72):
                consumer.phase(phase % 24)
            self.assertEqual(consumer.read(RAM+0xCD86, 1), 3)
            consumer.periodic_output()
            # Copy the exact producer output, including its complement byte.
            consumer.write(RAM+0x8EBC, cpu.read(RAM+0x8EBC, 2), 2)
            observed = [consumer.periodic_output() for _ in range(300)]
            self.assertIn((0, 0), observed)
            self.assertIn((100, 100), observed)
            self.assertEqual(consumer.read(RAM+0xCE08, 1) & 0x20, 0x20)
            self.assertEqual(consumer.read(RAM+0xCE09, 1) & 0x20, 0x20)
            self.assertEqual(consumer.read(RAM+0xCD86, 1), 3)

    def test_current_fault_aggregation_forces_low_lift_and_healthy_status_releases_it(self):
        for image, kind in product(self.images.values(), ('open', 'short', 'switch')):
            cpu = AVLSDiagnosticMachine(image)
            if kind == 'switch':
                for _ in range(62):
                    cpu.performance(70, 0)
            else:
                cpu.electrical_sample(40 if kind == 'open' else 0,
                                      0 if kind == 'open' else .5,
                                      .2 if kind == 'open' else 0)
                for _ in range(126):
                    cpu.electrical()
            cpu.execute(0x63174, FALLBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xD26E, 1) & 4, 4)
            consumer = AVLSPhaseMachine(image)
            self.assertEqual(consumer.request(3200)[0], 3)
            consumer.write(RAM+0xD26E, cpu.read(RAM+0xD26E, 1), 1)
            self.assertEqual(consumer.request(3200)[0], 1)
            if kind == 'switch':
                for _ in range(13):
                    cpu.performance(70, 0x30)
                for _ in range(188):
                    cpu.performance(0, 0)
            else:
                cpu.electrical_sample(40, .2, .2)
                for _ in range(126):
                    cpu.electrical()
            cpu.execute(0x63174, FALLBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xD26E, 1) & 4, 0)
            self.assertNotEqual(cpu.read(RAM+0xDAE7, 1) | cpu.read(RAM+0xDAE8, 1), 0)
            consumer.write(RAM+0xD26E, cpu.read(RAM+0xD26E, 1), 1)
            self.assertEqual(consumer.request(3200)[0], 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
