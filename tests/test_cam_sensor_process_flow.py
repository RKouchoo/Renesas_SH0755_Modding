#!/usr/bin/env python3
"""Connect cam edge capture, count/absence monitors and native fault recovery.

Hardware capture values, crank selector events and call spacing are explicit
inputs. Actual E6B0/E6DA callbacks, E468 classification, diagnostic publishers
and fault aggregation execute. This is not a model of physical cam waveforms,
interrupt response time, or the entire interrupt/RTOS entry and exit paths.
"""
import _test_paths
from itertools import product
import unittest

from test_diagnostic_readiness_process_flow import DiagnosticReadinessMachine, ROOT, RAM
from test_avcs_event_process_flow import CAPTURE_WRITES, QUEUE_WRITES
from test_shutdown_process_flow import QUEUE_WRITES as DIAGNOSTIC_QUEUE_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling

CAM_WRITES = {(RAM+a, 1) for a in range(0xD370, 0xD379)} | {
    (RAM+a, 1) for a in (0xB0D0, 0xB0D1, 0xDAE4, 0xDB1A, 0xDBB0, 0xDBB1)} | {
    (RAM+0x8EB4, 2)}


class CamSensorMachine(DiagnosticReadinessMachine):
    LOOKUPS = DiagnosticReadinessMachine.LOOKUPS | {
        0x69326, 0x69382, 0x69394, 0x6942C, 0x69442, 0x694C2,
        0x19CB8, 0xE314, 0xD004, 0xC700, 0x6170,
        0x53CD8,
    }

    def __init__(self, image):
        super().__init__(image)
        for a in range(0xB0B0, 0xB0D6):
            self.write(RAM+a, 0, 1)
        self.execute(0xE3CA, CAPTURE_WRITES)
        for a, n in CAM_WRITES:
            self.write(a, 0, n)
        self.write(RAM+0x8EB4, 0x00FF, 2)
        # Normal healthy reports clear the request state. Let a later fault
        # create its native queue-3 request rather than forcing it prequeued.
        self.write(RAM+0xB51C, 8, 1)
        for i, value in enumerate((0, 4, 8, 2, 6, 10, 0, 2, 1, 1)):
            self.write(RAM+0xC6A0+i, value, 1)
        self.put_float(RAM+0xAC00, 3000)
        self.write(RAM+0xAC08, 64000, 4)
        self.write(RAM+0xAC1C, 32000, 4)
        self.write(RAM+0xF4A2, 1000, 2)
        self.write(RAM+0xF4A4, 1000, 2)
        for a in range(0x94A0, 0x96F8, 4):
            self.write(RAM+a, 0xA55A5AA5, 4)
        self.write(RAM+0x930A, 1, 1)
        self.write(RAM+0x930B, 0, 1)
        self.write(RAM+0x930C, 1, 1)
        for a in range(0x96F8, 0xAAE4, 4):
            self.write(RAM+a, 0xA55A5AA5, 4)
        self.write(RAM+0x930D, 1, 1)
        self.write(RAM+0x930E, 0, 1)
        self.write(RAM+0x930F, 1, 1)
        # C700 copies unused words in its short message frame. Supply those
        # words without overwriting DE08 diagnostic mode: that live byte lies
        # inside the larger 512-byte region used by the event-only fixture.
        for a in range(self.STACK-128, self.STACK, 4):
            self.write(a, 0x5AA55AA5, 4)
        assert self.read(RAM+0xDE08, 1) == 0
        self.gates()

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        if op & 0xF00F == 0x0006:  # MOV.L Rm,@(R0,Rn).
            n, m = (op >> 8) & 15, (op >> 4) & 15
            self.write((self.r[0]+self.r[n]) & 0xFFFFFFFF, self.r[m], 4, record=True)
            self.trace.append((pc, op))
            self.pc += 2
            self.instructions += 1
        else:
            return super().step(in_delay)

    def capture(self, bank):
        self.execute(0xE6B0 if bank == 0 else 0xE6DA, CAPTURE_WRITES | {
            (RAM+0xB0C8, 2), (RAM+0xB0CA, 2)})

    def classify(self, bank):
        self.original_r[4] = bank*2
        self.execute(0xE468, CAPTURE_WRITES | QUEUE_WRITES)
        return self.read(RAM+0xB0B8+bank, 1)

    def slow(self):
        self.execute(0x69318, CAM_WRITES | DIAGNOSTIC_QUEUE_WRITES)
        return self.read(RAM+0x8EB4, 1)

    def fast(self):
        self.execute(0x69314, CAM_WRITES)


class CamSensorProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x69314, 0x69568), (0xE314, 0xE730),
                         (0x74D22, 0x74D24), (0x74F10, 0x74F14),
                         (0x5BDD7, 0x5BDD9), (0x5C82C, 0x5C854),
                         (0x11E50, 0x11E54), (0x117A8, 0x117AC)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_native_capture_callbacks_publish_bank_specific_latches_counts_and_timestamps(self):
        for image, bank in product(self.images.values(), (0, 1)):
            cpu = CamSensorMachine(image)
            cpu.write(RAM+0xF4A2+bank*2, 0x8123, 2)
            for _ in range(260):
                cpu.capture(bank)
            self.assertEqual(cpu.read(RAM+0xB0C8+bank*2, 2), 0x8123)
            self.assertEqual(cpu.read(RAM+0xB0D2+bank, 1), 255)
            self.assertEqual(cpu.read(RAM+0xB0D2+(1-bank), 1), 0)
            self.assertEqual(cpu.read(RAM+0xB0CC+bank, 1), 1)
            for expected in (1, 0):
                cpu.original_r[4] = bank
                cpu.execute(0xE314, CAM_WRITES)
                self.assertEqual(cpu.r[0], expected)
            self.assertEqual(cpu.read(RAM+0xB0CC+bank, 1), 1)

    def test_event_count_classification_feeds_fast_fault_qualification_and_recovers(self):
        for image, bank, edges in product(self.images.values(), (0, 1), (0, 1, 2)):
            expected = (1, 0, 2)[edges]
            cpu = CamSensorMachine(image)
            cpu.slow()  # Publishes D370/01 monitor qualification.
            cpu.classify(bank)  # First anchor initializes count window.
            for _ in range(5):
                cpu.classify(bank)  # Five subsequent anchors hold/decrement.
            for _ in range(edges):
                cpu.capture(bank)
            self.assertEqual(cpu.classify(bank), expected)
            for _ in range(4):
                cpu.fast()
                self.assertEqual(cpu.read(RAM+0xD371+bank, 1) & 1, 0)
            cpu.fast()
            self.assertEqual(cpu.read(RAM+0xD371+bank, 1) & 1, int(edges != 1))
            self.assertEqual(cpu.slow() & (0x10 if bank == 0 else 8),
                             (0x10 if bank == 0 else 8) if edges != 1 else 0)
            for _ in range(5):
                cpu.classify(bank)
            cpu.capture(bank)
            self.assertEqual(cpu.classify(bank), 0)
            cpu.fast()
            self.assertEqual(cpu.slow() & (0x10 if bank == 0 else 8), 0)

    def test_missing_capture_uses_separate_running_counter_and_current_raw_recovery(self):
        for image in self.images.values():
            cpu = CamSensorMachine(image)
            for _ in range(94):
                self.assertEqual(cpu.slow(), 0)
            self.assertEqual(cpu.slow(), 0x18)
            self.assertEqual(cpu.fallback_status(), 0x10)
            self.assertEqual(cpu.read(RAM+0xD270, 1) & 0x80, 0x80)
            cpu.capture(0)
            cpu.capture(1)
            self.assertEqual(cpu.slow(), 0)
            self.assertEqual(cpu.read(RAM+0x8EB4, 2), 0x00FF)
            self.assertEqual(cpu.fallback_status(), 0x10)
            self.assertEqual(cpu.read(RAM+0xD270, 1) & 0x80, 0)
            self.assertEqual(cpu.read(RAM+0xDAE4, 1), 0x18)

    def test_qualification_loss_resets_counters_but_holds_local_and_reported_faults(self):
        for image in self.images.values():
            cpu = CamSensorMachine(image)
            for _ in range(95):
                cpu.slow()
            cpu.write(RAM+0xC778, 1, 1)
            cpu.gates()
            self.assertEqual(cpu.slow(), 0x18)
            cpu.fast()
            self.assertEqual(cpu.read(RAM+0xD375, 4), 0)
            self.assertEqual(cpu.read(RAM+0xD371, 1) & 2, 2)
            cpu.write(RAM+0xC778, 0, 1)
            cpu.gates()
            cpu.capture(0)
            cpu.capture(1)
            self.assertEqual(cpu.slow(), 0)

    def test_fault_snapshot_payload_and_full_queue_leave_current_fault_publication_independent(self):
        for image, full in product(self.images.values(), (False, True)):
            cpu = CamSensorMachine(image)
            if full:
                cpu.write(RAM+0x930F, 255, 1)
            before = bytes(cpu.read(RAM+a, 1) for a in range(0x96F8, 0xAAE4))
            for _ in range(95):
                cpu.slow()
            self.assertEqual(cpu.read(RAM+0x8EB4, 1), 0x18)
            self.assertEqual(cpu.read(RAM+0xDBB0, 2), 0x2020)
            if full:
                self.assertEqual(cpu.read(RAM+0x930F, 1), 255)
                self.assertEqual(bytes(cpu.read(RAM+a, 1) for a in range(0x96F8, 0xAAE4)), before)
                # Supplied freed capacity does not synthesize a retry: the
                # reporter already marks its request queued even on failure.
                cpu.write(RAM+0x930F, 254, 1)
                cpu.slow()
                self.assertEqual(cpu.read(RAM+0x930F, 1), 254)
            else:
                self.assertEqual(cpu.read(RAM+0x930F, 1), 3)
                for address, identifier in ((0x970C, 0x84), (0x9720, 0x83)):
                    self.assertEqual([cpu.read(RAM+address+4*i, 4) for i in range(4)],
                                     [0x53D10, identifier, 0x20, 0])

    def test_crank_running_flag_and_cam_battery_gate_are_distinct_from_ocv_readiness(self):
        for image in self.images.values():
            cpu = CamSensorMachine(image)
            cpu.put_float(RAM+0xABB4, 8)
            self.assertEqual(cpu.gates()[:2], (1, 0))
            cpu.write(RAM+0xB51C, 0, 1)
            for _ in range(100):
                self.assertEqual(cpu.slow(), 0)
            self.assertEqual(cpu.read(RAM+0xD370, 1) & 1, 1)
            self.assertEqual(cpu.read(RAM+0xD377, 2), 0)
            cpu.put_float(RAM+0xABB4, 7.99)
            cpu.slow()
            self.assertEqual(cpu.read(RAM+0xD370, 1) & 1, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
