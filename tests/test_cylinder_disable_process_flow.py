#!/usr/bin/env python3
"""Execute the native configured cylinder-disable producers and RPM gate.

Configuration requests are imposed negative controls, not logged faults.
This fixture executes 6A636, its three producers, their integer helpers and
both native inhibit publishers. It does not simulate a physical diagnostic
request, global startup, crank interrupts or electrical outputs.
"""
import _test_paths
from io import StringIO
import unittest

from test_native_fault_cut_execution import FaultCutMachine

ROOT = _test_paths.ROOT
IMAGE = None
CONFIGURATION = tuple(zip(range(0xFFFFD93E, 0xFFFFD944),
                          (0x74CFD, 0x74CFE, 0x74CFF, 0x74D00, 0x74D02, 0x74D03)))
PRODUCER_WRITES = ({(a, 1) for a in range(0xFFFFD93D, 0xFFFFD944)} |
                   {(a, 1) for a in (0xFFFFD94B, 0xFFFFD94C, 0xFFFFD94D)} |
                   {(a, 1) for a in range(0xFFFFD996, 0xFFFFD99D)} |
                   {(a, 2) for a in (0xFFFFD80E, 0xFFFFD810, 0xFFFFB744, 0xFFFFC0DC)})
NATIVE_CALLEES = {0x6F4B8, 0x6FA3E, 0x6FAD4, 0x2534, 0x251C,
                  0x27090, 0x46F66, 0x46F7A, 0x46F8E, 0x46F9C, 0x46FB0, 0x46FC4}


class CylinderDisableMachine(FaultCutMachine):
    def __init__(self, image):
        super().__init__(image)
        for address in range(0xFFFFD93D, 0xFFFFD94E):
            self.write(address, 0, 1)
        for address in range(0xFFFFD996, 0xFFFFD99D):
            self.write(address, 0, 1)
        for address in (0xFFFFD800, 0xFFFFD80E, 0xFFFFD810, 0xFFFF8CE0, 0xFFFF8CE4):
            self.write(address, 0, 2)
        for address in (0xFFFF8CF0, 0xFFFFCD50, 0xFFFFCE28):
            self.write(address, 0, 1)
        self.write(0xFFFFC0DC, 0, 2)
        # The six unconditional byte copies at 6A2E2..6A312. The rest of
        # initializer 6A156 and the global RAM clear are explicit boundaries.
        for ram, rom in CONFIGURATION:
            self.write(ram, image[rom], 1)

    def call_lookup(self, target):
        if target in NATIVE_CALLEES:
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def tick(self, rpm, phase):
        self.put_float(0xFFFFB544, rpm)
        self.original_r[4] = phase
        self.invoke(0x6A636, PRODUCER_WRITES)
        return tuple(self.read(a, size) for a, size in (
            (0xFFFFD94C, 1), (0xFFFFD94D, 1), (0xFFFFB744, 2), (0xFFFFC0DC, 2)))


class CylinderDisableFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x6A2E2, 0x6A314), (0x6A636, 0x6A65E),
                           (0x6A66A, 0x6A6AC), (0x6F4B8, 0x6FEF4),
                           (0x27090, 0x2716C), (0x74CFD, 0x74D04),
                           (0x74E10, 0x74E14)):
            assert cls.image[start:end] == stock[start:end], hex(start)
        assert all(cls.image[rom] == 0 for _, rom in CONFIGURATION)

    def test_default_configuration_stays_clear_across_idle_and_loaded_rpm(self):
        cpu = CylinderDisableMachine(self.image)
        for rpm in (0, 800, 1000, 1001, 2800, 3500, 800, 1000, 3200):
            for phase in range(6):
                self.assertEqual(cpu.tick(rpm, phase), (0, 0, 0, 0))
                self.assertEqual(0x6F4B8 in cpu.entered, rpm <= 1000)

    def test_configured_injection_cut_is_copied_not_inverted(self):
        for bit in (1, 2, 4, 8, 16, 32):
            cpu = CylinderDisableMachine(self.image)
            cpu.write(0xFFFFD93F, bit, 1)
            cpu.write(0xFFFFD94B, 0x80, 1)
            cpu.write(0xFFFF8CE4, 20, 2)
            self.assertEqual(cpu.tick(800, 0), (bit, 0, bit, 0))
            self.assertEqual(cpu.read(0xFFFFD996, 1), bit)

    def test_rpm_gate_does_not_clear_a_preexisting_request(self):
        cpu = CylinderDisableMachine(self.image)
        cpu.write(0xFFFFD93F, 1, 1)
        cpu.write(0xFFFFD94B, 0x80, 1)
        cpu.write(0xFFFF8CE4, 20, 2)
        self.assertEqual(cpu.tick(1000, 0), (1, 0, 1, 0))
        for rpm in (1001, 2800, 3200, 3500):
            self.assertEqual(cpu.tick(rpm, 0), (1, 0, 1, 0))
            self.assertEqual([item for item in cpu.writes if item[0] < cpu.min_sp], [])
            cpu.invoke(0x1C5D4, {(0xFFFFB744, 2)})
            self.assertEqual(cpu.read(0xFFFFB744, 2), 1)
        cpu.write(0xFFFFD93F, 0, 1)
        # Even removing configuration does not publish a cleared word until
        # this low-RPM task is next allowed to run.
        self.assertEqual(cpu.tick(2800, 0), (1, 0, 1, 0))
        self.assertEqual(cpu.tick(800, 0), (0, 0, 0, 0))


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(CylinderDisableFlowTests))
        if not result.wasSuccessful():
            raise SystemExit(report.getvalue())
        print(f'  Cylinder-disable process: {result.testsRun} execution groups passed')
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main(verbosity=2)
