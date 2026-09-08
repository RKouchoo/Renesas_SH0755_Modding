#!/usr/bin/env python3
"""Execute native IRQ frames, task dispatch and cut-wrapper resumption.

An explicitly injected IRQ uses the stock vector wrapper, 340C/3454 entry/exit,
3A28 activation, ready queues, 3930 dispatch, 3F2C completion and RTE restores.
The IRQ body is scripted. Task 5's payload is actual 263EE, not its entire
engine task. Debug hook 37A0 and device/math boundaries from SchedulerMachine
remain substitutes. No real timer clock, interrupt arrival rate or device exists.
"""

import _test_paths  # Shared offline-test imports and repository root.
from io import StringIO
from itertools import product
from pathlib import Path
import sys
import unittest

from test_injector_scheduler_execution import (
    SchedulerMachine, CUT_WRITES, SCHEDULER_WRITES, RECORDS, CACHED_WORD,
    DEGREE, ROOT, INHIBIT_WORD, safety, boost,
)
from test_wideband_fuel_guard_execution import signed, bits

IMAGE = None
KERNEL = 0xFFFF72B0
TASK5_RAM = 0xFFFF71C4
TASK6_RAM = 0xFFFF71CC
IRQ_VECTOR = 0x33F4
IRQ_BODY = 0x60F4
TASK5_ENTRY = 0x6938
PAYLOAD_RETURN = 0xDEADBEE4
NATIVE_KERNEL_CALLS = {0x340C, 0x3A28, 0x3B8E, 0x3BFC, 0x3E54, 0x3DC8}
KERNEL_WRITES = {(KERNEL + o, n) for o, n in (
    (0, 1), (4, 2), (6, 2), (8, 4), (12, 4), (20, 4), (24, 4))}
KERNEL_WRITES |= {(r + o, n) for r in (TASK5_RAM, TASK6_RAM)
                 for o, n in ((0, 1), (1, 1), (3, 1), (4, 4))}
KERNEL_WRITES |= {(a, 2) for a in range(0xFFFF7234, 0xFFFF72A2, 2)}
KERNEL_WRITES |= {(a, 1) for a in range(0xFFFF72E0, 0xFFFF72F0)}


class InterruptMachine(SchedulerMachine):
    INSTRUCTION_LIMIT = 24000

    def __init__(self, image):
        super().__init__(image)
        self.sr = 0
        self.fpscr = 0x40001
        self.fpul = 0x11224488
        self.mach = 0xAADD1122
        self.gbr = 0xFFFF8120
        self.irq_depth = 0
        self.nest_irq = False
        self.activate_in_irq = True
        self.inject_at = None
        self.inject_level = 2
        self.injections = []
        self.task_runs = []
        self.task_depths = []
        self.irq_returns = []
        self.rte_frames = []
        self.dispatch_entries = []
        self.debug_calls = 0
        # Real stack RAM contains unspecified old values. Native 3DCC reserves
        # an R0 slot without writing it; 39E6 reloads that caller-scratch slot.
        # Seed a bounded fixture with nonzero poison, never default all RAM to 0.
        self.stack_floor = self.STACK - 512
        for address in range(self.stack_floor, self.STACK, 4):
            self.write(address, address ^ 0xCAFECAFE)
        for address in range(TASK5_RAM, TASK6_RAM + 8):
            self.write(address, 0, 1)
        for address in range(0xFFFF7234, 0xFFFF72F0):
            self.write(address, 0, 1)
        self.write(KERNEL, 2, 1)
        self.write(KERNEL + 4, 6, 2)
        self.write(KERNEL + 6, 6, 2)
        self.write(KERNEL + 12, self.STACK)
        self.write(KERNEL + 16, 0xB0)
        self.write(KERNEL + 20, TASK6_RAM)
        self.write(KERNEL + 24, 0x49FC)
        self.write(KERNEL + 32, 0x4AD0)
        self.write(KERNEL + 36, 0xFFFF7234)
        self.write(TASK5_RAM + 3, 2, 1)
        self.write(TASK6_RAM + 1, 2, 1)
        self.write(TASK6_RAM + 3, 1, 1)
        self.write(TASK6_RAM + 4, self.STACK)
        for priority in range(5):
            descriptor = 0x4AD0 + priority * 8
            pointer = self.read(descriptor + 4, 4)
            self.write(pointer, 0xFFFF, 2)
            self.write(pointer + 2, 0, 2)
        # The running task is present in its native priority-2 ready queue.
        slot = self.read(0x4AE0, 2)
        pointer = self.read(0x4AE4, 4)
        self.write(pointer, slot, 2)
        self.write(pointer + 2, slot, 2)
        self.write(0xFFFF7234 + slot * 2, 6, 2)
        self.write(0xFFFF72E0, 1 << 2, 1)
        # Ready-to-release records make any unintended temporary cut release
        # observable as an enqueue through actual scheduler instructions.
        self.write(CACHED_WORD, 0xFFFF, 2)
        for record in RECORDS:
            self.write(record + 1, 1, 1)
            self.write(record + 8, 400 * DEGREE)

    def state(self):
        return (tuple(self.r), tuple(self.fr), self.pr, self.pc,
                (self.sr & ~1) | int(self.t), self.fpscr, self.fpul,
                self.macl, self.mach, self.gbr)

    def subroutine(self, address):
        return_pc = self.pr
        self.pc = address
        while self.pc != return_pc:
            self.step()

    def call_lookup(self, target):
        if target == 0x37A0:
            # Optional task-switch debug callback, not a scheduling decision.
            self.debug_calls += 1
            self.poison_scratch()
        else:
            super().call_lookup(target)

    def interrupt(self, level=2):
        assert level > (self.sr >> 4 & 15), "Masked IRQ cannot arrive"
        before = self.state()
        return_pc, saved_sr = before[3:5]
        self.injections.append((return_pc, saved_sr, level))
        # Architectural exception entry. The vector/frame processing below
        # executes actual ROM instructions; IRQ arbitration is this boundary.
        self.push(saved_sr)
        self.push(return_pc)
        frame = self.r[15]
        return_count = len(self.rte_frames)
        self.sr = (saved_sr & ~0xF0) | (level << 4)
        self.pc = IRQ_VECTOR
        self.irq_depth += 1
        # A nested IRQ starts at the same scripted handler address as the
        # interrupted outer IRQ. Only an RTE of this frame completes the IRQ.
        while not (len(self.rte_frames) > return_count and
                   self.rte_frames[-1] == (frame, return_pc, saved_sr)):
            self.step()
        self.irq_depth -= 1
        self.irq_returns.append(self.state())
        assert self.min_sp >= self.stack_floor, "Exceeded modeled stack fixture"
        assert self.state() == before, "IRQ or preempted-task context was corrupted"

    def irq_body(self):
        # The interrupt body may request the real higher-priority task. It
        # obeys the C ABI; native kernel entry saves its scratch FP/GPR state.
        assert self.read(KERNEL + 8, 4) == self.irq_depth
        if self.nest_irq and self.irq_depth == 1:
            self.interrupt(3)
        if self.activate_in_irq:
            saved_pr = self.pr
            self.pr = PAYLOAD_RETURN
            self.r[4] = 5
            self.subroutine(0x3A28)
            assert self.r[0] == 0
            self.pr = saved_pr
        self.poison_scratch()
        self.fpscr = 0x40021  # Scripted IRQ changes status; entry/exit must restore it.
        self.pc = self.pr

    def task_payload(self):
        assert self.read(KERNEL + 4, 2) == 5 and self.sr & 0xF0 == 0
        self.task_runs.append((self.read(INHIBIT_WORD, 2), self.read(safety.FUEL_CUT_FLAG, 1)))
        self.task_depths.append(self.irq_depth)
        outgoing_state = self.read(TASK6_RAM, 1)
        assert outgoing_state in (4, 12)
        self.r[4] = 0
        self.pr = PAYLOAD_RETURN
        self.subroutine(0x263EE)
        # A different task may use all registers. Its own execution-time and
        # hardware body are outside this audit; native completion resumes task 6.
        for i in range(15):
            self.r[i] = 0xAA000000 + i
        for i in range(16):
            self.fr[i] = bits(-800 - i)
        self.fpul = 0xCAFEBABE
        self.macl, self.mach, self.gbr = 0x123, 0x456, 0xFFFF9990
        if outgoing_state == 12:
            self.fpscr = 0x40041  # Full interrupt context also saves FPSCR.
        self.t = not self.t
        self.pc = 0x3F2C

    def step(self, in_delay=False):
        pc = self.pc
        if pc == IRQ_BODY:
            assert not in_delay
            self.irq_body()
            return
        if pc == TASK5_ENTRY:
            assert not in_delay
            self.task_payload()
            return
        op = self.read(pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        handled = True
        self.pc += 2
        if pc == 0x3F84:
            # Execute the instruction which the earlier guard suite replaced
            # with a dispatcher stand-in, then continue through native code.
            assert op == 0x2FE6
            self.dispatch_entries.append((self.read(INHIBIT_WORD, 2), self.sr & 0xF0))
            self.push(self.r[14])
        elif op == 0x002B:
            assert not in_delay and self.read(pc + 2, 2) == 0x0009
            frame = self.r[15]
            target, status = self.pop(), self.pop()
            self.step(in_delay=True)
            self.pc, self.sr, self.t = target, status, bool(status & 1)
            self.rte_frames.append((frame, target, status))
        elif op & 0xF0FF == 0x400B or op & 0xF000 == 0xB000:
            assert not in_delay
            target = self.r[n] if op & 0xF000 != 0xB000 else pc + 4 + signed(op & 0xFFF, 12) * 2
            self.pr = pc + 4
            self.step(in_delay=True)
            if target in NATIVE_KERNEL_CALLS:
                # A context-save call can resume through RTE with a different
                # PR. Follow its instructions directly; do not synthesize RTS.
                self.entered.append(target)
                self.pc = target
            else:
                self.call_lookup(target)
                self.pc = self.pr
        elif op & 0xF0FF == 0x402A:
            self.pr = self.r[n]
        elif op & 0xF00F == 0x0005:
            self.write((self.r[0] + self.r[n]) & 0xFFFFFFFF, self.r[m], 2, record=True)
        elif op & 0xF0FF == 0x4021:
            self.t = bool(self.r[n] & 1)
            self.r[n] = signed(self.r[n], 32) >> 1 & 0xFFFFFFFF
        elif op & 0xF00F == 0x600F:
            self.r[n] = signed(self.r[m] & 65535, 16) & 0xFFFFFFFF
        elif op in (0x4F52, 0x4F62, 0x4F13, 0x4F02):
            self.push({0x4F52: self.fpul, 0x4F62: self.fpscr,
                       0x4F13: self.gbr, 0x4F02: self.mach}[op])
        elif op in (0x4F56, 0x4F66, 0x4F17, 0x4F06):
            setattr(self, {0x4F56: 'fpul', 0x4F66: 'fpscr',
                           0x4F17: 'gbr', 0x4F06: 'mach'}[op], self.pop())
        else:
            handled = False
        if handled:
            self.instructions += 1
            self.visited.add(pc)
            assert self.instructions < self.INSTRUCTION_LIMIT
        else:
            self.pc = pc
            super().step(in_delay)
        if pc == self.inject_at and not self.irq_depth and not in_delay:
            self.inject_at = None
            self.interrupt(self.inject_level)

    def cut_with_irq(self, entry=safety.LEAN_CUT_WRAPPER_ADDR, site=0x1C90A, level=2):
        self.inject_at = site  # Default: after native B744 store, before reassertion.
        self.inject_level = level
        self.invoke(entry, CUT_WRITES | SCHEDULER_WRITES | KERNEL_WRITES)
        assert self.inject_at is None
        assert self.min_sp >= self.stack_floor, "Exceeded modeled stack fixture"


class CutInterruptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x33F4, 0x357C), (0x3930, 0x3A28), (0x3A28, 0x3C94),
                           (0x3DC8, 0x3E54), (0x3E54, 0x3FE4), (0x49EC, 0x4A0C),
                           (0x4ACC, 0x4AFC), (0x4B10, 0x4B50)):
            assert cls.image[start:end] == stock[start:end], f'Kernel contract changed at {start:#x}'

    def test_irq_return_restores_every_register_with_and_without_pending_task(self):
        for imask, pending in product(range(15), (False, True)):
            cpu = InterruptMachine(self.image)
            cpu.activate_in_irq = pending
            cpu.sr, cpu.t = 0x300 | (imask << 4), True
            cpu.pc = cpu.STOP
            cpu.interrupt(level=15)
            self.assertEqual(len(cpu.task_runs), int(pending and imask == 0))
            self.assertEqual(cpu.read(KERNEL + 8, 4), 0)
            self.assertEqual(cpu.read(KERNEL + 4, 2), 6)
            self.assertEqual(cpu.read(KERNEL + 6, 2), 5 if pending and imask else 6)
            self.assertEqual(cpu.read(TASK5_RAM, 1), 0)

    def test_nested_irq_defers_dispatch_until_unmasked_outer_return(self):
        for imask in (0, 1):
            cpu = InterruptMachine(self.image)
            cpu.nest_irq = True
            cpu.sr, cpu.t = imask << 4, True
            cpu.pc = cpu.STOP
            cpu.interrupt()
            self.assertEqual(len(cpu.injections), 2)
            self.assertEqual(cpu.read(KERNEL + 8, 4), 0)
            self.assertEqual(len(cpu.task_runs), 2 if imask == 0 else 0)
            self.assertNotIn(2, cpu.task_depths)

    def test_actual_cut_irq_deferred_until_complete_unlock(self):
        for entry, pressure, state in ((boost.REVWRAP_ADDR, 1150, 0),
                                       (safety.LEAN_CUT_WRAPPER_ADDR, 820, 3)):
            cpu = InterruptMachine(self.image)
            cpu.write(INHIBIT_WORD, 0xFFFF, 2)
            cpu.write(safety.FUEL_CUT_FLAG, 128, 1)
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.write(safety.LEAN_STATE_RAM, state, 1)
            cpu.cut_with_irq(entry)
            self.assertEqual(len(cpu.injections), 1)
            self.assertEqual(cpu.injections[0][1] & 0xF0, 0x10)
            self.assertEqual(cpu.task_runs, [(0xFFFF, 128)])
            self.assertEqual(cpu.device_calls, [])
            self.assertEqual(cpu.read(KERNEL + 8, 4), 0)
            self.assertEqual(cpu.read(KERNEL + 4, 2), 6)
            self.assertEqual(cpu.read(KERNEL + 6, 2), 6)

    def test_irq_at_wrapper_and_unlock_boundaries(self):
        for entry, pressure, state, flag_store, word_store in (
                (boost.REVWRAP_ADDR, 1150, 0, 0x7D8EC, 0x7D8F2),
                (safety.LEAN_CUT_WRAPPER_ADDR, 820, 3, 0x7ED86, 0x7ED8C)):
            # All injection points are after complete, non-delay instructions.
            # The two JMP points include their delay slot before exception entry.
            sites = (entry, entry + 8, entry + 14, 0x1C90A,
                     flag_store, word_store, 0x3B18, 0x3F84)
            for site, nested in product(sites, (False, True)):
                with self.subTest(entry=hex(entry), site=hex(site), nested=nested):
                    cpu = InterruptMachine(self.image)
                    cpu.nest_irq = nested
                    cpu.write(INHIBIT_WORD, 0xFFFF, 2)
                    cpu.write(safety.FUEL_CUT_FLAG, 128, 1)
                    cpu.put_float(safety.MAP_PRESSURE, pressure)
                    cpu.write(safety.LEAN_STATE_RAM, state, 1)
                    cpu.cut_with_irq(entry, site)
                    self.assertEqual(cpu.task_runs, [(0xFFFF, 128)] * (1 + nested))
                    self.assertEqual(cpu.device_calls, [])
                    self.assertNotIn(2, cpu.task_depths)
                    self.assertEqual(cpu.read(KERNEL + 6, 2), 6)

    def test_higher_caller_mask_keeps_task_pending_until_caller_unlock(self):
        for entry, pressure, state in ((boost.REVWRAP_ADDR, 1150, 0),
                                       (safety.LEAN_CUT_WRAPPER_ADDR, 820, 3)):
            for imask in (1, 2, 7, 14):
                cpu = InterruptMachine(self.image)
                cpu.sr = imask << 4
                cpu.write(INHIBIT_WORD, 0xFFFF, 2)
                cpu.write(safety.FUEL_CUT_FLAG, 128, 1)
                cpu.put_float(safety.MAP_PRESSURE, pressure)
                cpu.write(safety.LEAN_STATE_RAM, state, 1)
                cpu.cut_with_irq(entry, level=15)
                self.assertEqual(cpu.sr & 0xF0, imask << 4)
                self.assertEqual(cpu.task_runs, [])
                self.assertEqual(cpu.read(KERNEL + 6, 2), 5)
                saved_r, saved_fr = cpu.r[8:].copy(), cpu.fr[12:].copy()
                cpu.r[4], cpu.pr = 0, cpu.STOP
                cpu.subroutine(0x3B08)  # The caller later releases its own lock.
                self.assertEqual(cpu.task_runs, [(0xFFFF, 128)])
                self.assertEqual(cpu.device_calls, [])
                self.assertEqual(cpu.sr & 0xF0, 0)
                self.assertEqual(cpu.r[8:], saved_r)
                self.assertEqual(cpu.fr[12:], saved_fr)
                self.assertEqual(cpu.pr, cpu.STOP)
                self.assertEqual(cpu.read(KERNEL + 6, 2), 6)

    def test_removed_lock_reproduces_irq_or_inner_unlock_release(self):
        for entry, pressure, state in ((boost.REVWRAP_ADDR, 1150, 0),
                                       (safety.LEAN_CUT_WRAPPER_ADDR, 820, 3)):
            image = bytearray(self.image)
            self.assertEqual(image[entry + 6:entry + 8], bytes.fromhex('e410'))
            image[entry + 6:entry + 8] = bytes.fromhex('e400')
            cpu = InterruptMachine(image)
            cpu.write(INHIBIT_WORD, 0xFFFF, 2)
            cpu.write(safety.FUEL_CUT_FLAG, 128, 1)
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.write(safety.LEAN_STATE_RAM, state, 1)
            cpu.cut_with_irq(entry)
            self.assertEqual(cpu.task_runs, [(0, 0)])
            self.assertEqual({event[1] for event in cpu.device_calls}, set(range(6)))
            self.assertEqual(cpu.read(INHIBIT_WORD, 2), 0xFFFF)

    def test_removed_irq_saved_mask_gate_reproduces_temporary_release(self):
        image = bytearray(self.image)
        self.assertEqual(image[0x3486:0x3488], bytes.fromhex('c9f0'))
        image[0x3486:0x3488] = bytes.fromhex('c900')
        for entry, pressure, state in ((boost.REVWRAP_ADDR, 1150, 0),
                                       (safety.LEAN_CUT_WRAPPER_ADDR, 820, 3)):
            cpu = InterruptMachine(image)
            cpu.write(INHIBIT_WORD, 0xFFFF, 2)
            cpu.write(safety.FUEL_CUT_FLAG, 128, 1)
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.write(safety.LEAN_STATE_RAM, state, 1)
            cpu.cut_with_irq(entry)
            self.assertEqual(cpu.injections[0][1] & 0xF0, 0x10)
            self.assertEqual(cpu.task_runs, [(0, 0)])
            self.assertEqual({event[1] for event in cpu.device_calls}, set(range(6)))
            self.assertEqual(cpu.read(INHIBIT_WORD, 2), 0xFFFF)

    def test_damaged_context_restores_are_detected(self):
        for address, original, damaged in (
                (0x3458, '4f56', '4f66'),  # Restore FPUL into FPSCR in IRQ exit.
                (0x39AE, '4f56', '4f66'),  # Same corruption in preempted-task restore.
                (0x39CA, 'fff9', 'fef9'),  # Restore FR15 into FR14.
                (0x39D4, '6ef6', '6df6')):  # Restore R14 into R13.
            with self.subTest(address=hex(address)):
                image = bytearray(self.image)
                self.assertEqual(image[address:address + 2], bytes.fromhex(original))
                image[address:address + 2] = bytes.fromhex(damaged)
                cpu = InterruptMachine(image)
                cpu.pc = cpu.STOP
                with self.assertRaisesRegex(AssertionError, 'context was corrupted'):
                    cpu.interrupt()


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(unittest.defaultTestLoader.loadTestsFromTestCase(CutInterruptTests))
        if not result.wasSuccessful():
            raise SystemExit(report.getvalue())
        print(f'  Cut IRQ/context: {result.testsRun} execution test groups passed')
    finally:
        IMAGE = previous


if __name__ == '__main__':
    if len(sys.argv) > 1:
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
