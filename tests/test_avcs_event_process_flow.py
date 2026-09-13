#!/usr/bin/env python3
"""Follow native cam-period conversion, queued bank callback and observation.

Capture registers, synchronization selectors, an already-active message
queue and callback-delivery time are explicit fixtures. Native enqueue and
callback instructions run; RTOS activation, real interrupts and physical cam
motion are not simulated. A full-queue control is a conditional counterexample,
not evidence that the vehicle exhausted this queue.
"""
import _test_paths
import unittest

from test_avcs_controller_process_flow import (
    AVCSControllerMachine, OBSERVATION_WRITES, RAM, ROOT,
)

CAPTURE_WRITES = {(RAM+a, 4) for a in (0xB0B0, 0xB0B4, 0xB0BC, 0xB0C0)} | {
    (RAM+a, 2) for a in (0xB0C4, 0xB0C6)} | {
    (RAM+a, 1) for a in (0xB0B8, 0xB0B9, *range(0xB0CC, 0xB0D6))}
QUEUE_WRITES = {(RAM+a, 1) for a in range(0x930A, 0x930D)} | {
    (RAM+a, 4) for a in range(0x94A0, 0x96F8, 4)}
DELIVERY_WRITES = QUEUE_WRITES | OBSERVATION_WRITES | {
    (RAM+a, 4) for a in range(0xAFB8, 0xAFCC, 4)}


class AVCSEventMachine(AVCSControllerMachine):
    LOOKUPS = AVCSControllerMachine.LOOKUPS | {0xD004, 0xC700, 0x6170, 0x6270, 0x11EC8}

    def __init__(self, image, queued=1):
        super().__init__(image)
        for a in range(0xB0B0, 0xB0D6):
            self.write(RAM+a, 0, 1)
        self.execute(0xE3CA, CAPTURE_WRITES)
        # Supplied synchronized tooth identities and capture times. The two
        # bank lists have three entries, as bounded by E468's native loop.
        for i, v in enumerate((0, 4, 8, 2, 6, 10, 0, 2, 1, 1)):
            self.write(RAM+0xC6A0+i, v, 1)
        self.put_float(RAM+0xAC00, 2800)
        self.write(RAM+0xAC08, 64000, 4)
        self.write(RAM+0xAC1C, 32000, 4)
        for bank in (0, 1):
            self.write(RAM+0xB0C8+2*bank, 1000, 2)
            self.write(RAM+0xB0CC+bank, 1, 1)
        for a in range(0x94A0, 0x96F8, 4):
            self.write(RAM+a, 0xA55A5AA5, 4)
        # Queue 2 (FA1C) has 30 records and belongs to RTOS task 3.
        self.write(RAM+0x930A, queued % 30, 1)
        self.write(RAM+0x930B, 0, 1)
        self.write(RAM+0x930C, queued, 1)
        # C700 copies a fixed 20-byte record although this event carries one
        # payload word; unused stack words are arbitrary and never consumed
        # by 11EC8. Give those words explicit canaries, not zero assumptions.
        for a in range(self.STACK-512, self.STACK, 4):
            self.write(a, 0x5AA55AA5, 4)
        self.task_terminated = False

    def call_lookup(self, target):
        if target == 0x3F2C:
            # End at the actual task-completion call. Common kernel context
            # restoration is covered by test_cut_interrupt_execution; this
            # harness does not synthesize a scheduler or claim dispatch time.
            self.entered.append(target)
            self.task_terminated = True
        else:
            super().call_lookup(target)

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

    def edge(self, bank):
        slot = self.read(RAM+0x930A, 1)
        self.original_r[4] = 2*bank
        self.execute(0xE468, CAPTURE_WRITES | QUEUE_WRITES)
        return RAM+0x94A0+20*slot

    def deliver(self, record):
        self.original_r[4] = record+4
        self.execute(self.read(record, 4), OBSERVATION_WRITES)

    def drain_task(self):
        self.r = self.original_r.copy()
        self.fr = self.original_fr.copy()
        self.pr, self.pc = self.STOP, 0xC844
        self.instructions, self.min_sp = 0, self.STACK
        self.trace.clear()
        self.writes.clear()
        self.entered.clear()
        self.task_terminated = False
        while not self.task_terminated:
            self.step()
        # C844 is a task entry, not a C-ABI subroutine. Its 12-byte frame is
        # still live at this kernel-completion boundary.
        assert self.r[15] == self.STACK-12
        assert self.sr & 0xF0 == 0x20
        for a, n in self.writes:
            assert (a, n) in DELIVERY_WRITES or self.min_sp <= a < self.STACK, (hex(a), n)


class AVCSEventProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        for image in cls.images:
            for a, b in ((0xE3CA, 0xE6B0), (0xD004, 0xD01C),
                         (0xC700, 0xC76E), (0x6170, 0x6328),
                         (0xC844, 0xC898), (0xC8EC, 0xC908),
                         (0x49CC, 0x49DC), (0xFA1C, 0xFA24),
                         (0xFCC8, 0xFCD0), (0x11EC8, 0x11ED2),
                         (0x11F84, 0x11F88)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_capture_conversion_queues_each_bank_then_native_callback_updates_observation(self):
        for image in self.images:
            for bank in (0, 1):
                cpu = AVCSEventMachine(image)
                record = cpu.edge(bank)
                self.assertEqual(cpu.read(record, 4), 0x11EC8)
                self.assertEqual(cpu.read(record+4, 4), bank)
                self.assertEqual(cpu.read(RAM+0x930C, 1), 2)
                self.assertEqual(cpu.read(RAM+0xB0CC+bank, 1), 0)
                raw = cpu.get_float(RAM+0xB0B0+4*bank)
                offset = cpu.get_float(RAM+0xB0BC+4*bank)
                self.assertAlmostEqual(raw, max(0, min(120, offset+120*1000/4000)), delta=.00001)
                before = cpu.get_float(RAM+0xC8B0+4*bank)
                cpu.deliver(record)
                self.assertIn(0x34194, [pc for pc, _ in cpu.trace])
                self.assertNotEqual(cpu.get_float(RAM+0xC8B0+4*bank), before)
                self.assertEqual(cpu.get_float(RAM+0xC8B0+4*(1-bank)), 0)

    def test_invalid_capture_publishes_zero_and_queues_native_zero_observation(self):
        for image in self.images:
            cpu = AVCSEventMachine(image)
            cpu.write(RAM+0xB0CC, 0, 1)
            cpu.put_float(RAM+0xB0B0, 50)
            record = cpu.edge(0)
            self.assertEqual(cpu.get_float(RAM+0xB0B0), 0)
            self.assertEqual(cpu.read(RAM+0xB0C4, 2), 0)
            cpu.deliver(record)
            self.assertEqual(cpu.get_float(RAM+0xC8B0), 0)

    def test_full_queue_drops_callback_while_latest_capture_still_changes(self):
        for image in self.images:
            cpu = AVCSEventMachine(image, queued=30)
            prior = cpu.get_float(RAM+0xC8B0)
            record = cpu.edge(0)
            self.assertGreater(cpu.get_float(RAM+0xB0B0), 0)
            self.assertEqual(cpu.get_float(RAM+0xC8B0), prior)
            self.assertEqual(cpu.read(RAM+0x930C, 1), 30)
            self.assertEqual(cpu.read(record, 4), 0xA55A5AA5)
            self.assertIn(0x6170, cpu.entered)

    def test_native_consumer_drains_bank_records_and_requests_task_completion(self):
        for image in self.images:
            cpu = AVCSEventMachine(image)
            # Make the existing queued record a valid observation for bank1.
            cpu.write(RAM+0x94A0, 0x11EC8, 4)
            cpu.write(RAM+0x94A4, 1, 4)
            cpu.put_float(RAM+0xB0B4, 60)
            cpu.edge(0)
            cpu.drain_task()
            self.assertEqual(cpu.read(RAM+0x930C, 1), 0)
            self.assertEqual(cpu.read(RAM+0x930B, 1), 2)
            self.assertEqual(cpu.entered.count(0x11EC8), 2)
            self.assertEqual(cpu.entered.count(0x3F2C), 1)
            self.assertTrue(all(cpu.get_float(RAM+a) > 0 for a in (0xC8B0, 0xC8B4)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
