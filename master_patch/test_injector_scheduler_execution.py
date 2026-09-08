#!/usr/bin/env python3
"""Execute retained injector queue transitions under both added cuts.

The phase scheduler, resynchronizer, transition handler, running-mode callbacks,
cancel routine, interrupt-mask helpers and pulse logger execute ROM opcodes.
Device enqueue/update calls are recorded boundaries. Timer registers are inert
fixtures; no timer events, ISR interleaving or physical output is simulated.
21CC fixed-point division and 4280 integer division are mathematical boundaries
on bounded positive operands. Cranking angle/pulse producers are fixture inputs.
"""
from io import StringIO
from itertools import product
from pathlib import Path
import sys
import unittest

from test_injector_cut_execution import ChannelGateMachine
from test_wideband_fuel_guard_execution import INHIBIT_WORD, safety, boost, bits, signed

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
RECORDS = tuple(0xFFFFBFB8 + 40 * i for i in range(6))
HARDWARE = tuple(0xFFFFAC80 + 24 * i for i in range(6))
CACHED_WORD = 0xFFFFC0B2
CACHED_MODE = 0xFFFFC0B1
LAST_PHASE = 0xFFFFC0B4
DEGREE = 1 << 16
CYCLE = 720 * DEGREE
NATIVE_CALLS = {
    0x2088, 0x2098, 0x2378, 0x251C, 0x920C, 0xD744, 0x1D228,
    0x26088, 0x261A6, 0x263EE, 0x2672A, 0x26944, 0x26958, 0x26960,
    0x26990, 0x269A4, 0x26AEC, 0x26C50, 0x26D44, 0x26D92,
    0x26DFC, 0x26E02, 0x26E1E, 0x26E9A, 0x26F78, 0x26F7E, 0x26F8C,
}
RECORD_WRITES = {(r + o, n) for r in RECORDS for o, n in (
    (0, 1), (1, 1), (2, 1), (3, 1), (4, 2), (6, 1), (7, 1),
    (17, 1), (20, 4), (24, 4), (28, 4), (32, 4), (36, 1))}
HARDWARE_WRITES = {(h + o, 1) for h in HARDWARE for o in (19, 20)} | {
    (a, 2) for a in (0xFFFFF66C, *range(0xFFFFF640, 0xFFFFF650, 2),
                     *range(0xFFFFF444, 0xFFFFF450, 2))}
SCHEDULER_WRITES = RECORD_WRITES | HARDWARE_WRITES | {
    (0xFFFFC0A8, 2), (0xFFFFC0AC, 4), (0xFFFFC0B0, 1),
    (CACHED_MODE, 1), (CACHED_WORD, 2), (LAST_PHASE, 1), (0xFFFFC0B5, 1)}
LOGGER_WRITES = {(a, 4) for a in range(0xFFFFC0B8, 0xFFFFC0DC, 4)}
CUT_WRITES = {(safety.FUEL_CUT_FLAG, 1), (0xFFFFBF6D, 1),
              (safety.LEAN_STATE_RAM, 1), (safety.LEAN_COUNTER_RAM, 2), (INHIBIT_WORD, 2)}


class SchedulerMachine(ChannelGateMachine):
    INSTRUCTION_LIMIT = 16000

    def __init__(self, image):
        super().__init__(image)
        self.macl = 0xA55A5AA5
        self.sr = 0x20
        self.device_calls = []
        self.cancellations = []
        self.math_calls = []
        self.visited = set()
        self.cranking_angle = 300
        self.cranking_pulse = 1200
        for address in range(RECORDS[0], 0xFFFFC0DC):
            self.write(address, 0, 1)
        for address in range(HARDWARE[0], HARDWARE[-1] + 24):
            self.write(address, 0, 1)
        # Snapshots, not a crank/timer simulation. 120-degree interval in counts.
        self.write(0xFFFFAC08, 40000)
        self.write(0xFFFFAC7C, 4000)
        self.write(0xFFFFAC17, 0, 1)
        self.write(0xFFFFB748, 0, 1)  # 26E02 returns index 2 -> running record mode 1.
        self.write(CACHED_MODE, 2, 1)
        self.write(LAST_PHASE, 23, 1)
        self.put_float(0xFFFFB754, 180)  # Actual 26E1E adds 120 degrees.
        for i, record in enumerate(RECORDS):
            self.write(record, 1, 1)
            self.write(record + 4, 1, 2)
            self.write(record + 8, self.read(0x4B690 + i * 4, 4))
            self.write(record + 12, i, 1)
            self.write(record + 16, i, 1)
            self.write(record + 20, 4000 + i * 400)
            self.write(record + 24, 4000 + i * 400)
            self.write(record + 28, 300 * DEGREE)
            self.write(record + 32, 300 * DEGREE)
            self.put_float(0xFFFFB768 + i * 4, 1000 + i * 100)
        for address in (0xFFFFF440, 0xFFFFF666, 0xFFFFF66C,
                        *range(0xFFFFF640, 0xFFFFF650, 2),
                        *range(0xFFFFF444, 0xFFFFF450, 2)):
            self.write(address, 0, 2)

    def call_lookup(self, target):
        if target in NATIVE_CALLS:
            self.entered.append(target)
            if target == 0x920C:
                self.cancellations.append(self.r[4] & 255)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        elif target in (0x900A, 0x8F84, 0x90F8):
            # Record the actual native callback's arguments. Hardware progress
            # remains an explicit test input, never an invented elapsed time.
            self.device_calls.append((target, self.r[4] & 255, self.r[5], self.r[6]))
            self.poison_scratch()
        elif target in (0x21CC, 0x4280):
            dividend, divisor = (self.r[4], self.r[5]) if target == 0x21CC else (self.r[1], self.r[0])
            assert 0 <= signed(dividend, 32) < 2**30 and 0 < divisor < 2**30
            value = (dividend << 16) // divisor if target == 0x21CC else dividend // divisor
            assert value < 2**31
            self.math_calls.append((target, dividend, divisor))
            self.poison_scratch()
            self.r[0] = value
        elif target in (0x1C958, 0x26250, 0x1D450):
            # Upstream cranking producers are outside this scheduler audit.
            self.poison_scratch()
            if target == 0x26250:
                self.r[0] = 0
            else:
                self.fr[0] = bits(self.cranking_angle if target == 0x1C958 else self.cranking_pulse)
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        self.visited.add(pc)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        handled = True
        self.pc += 2
        if op & 0xF000 == 0xB000:
            assert not in_delay
            self.pr = pc + 4
            self.step(in_delay=True)
            self.call_lookup(pc + 4 + signed(op & 0xFFF, 12) * 2)
            self.pc = self.pr
        elif op & 0xF000 == 0x1000:
            self.write((self.r[n] + (op & 15) * 4) & 0xFFFFFFFF, self.r[m], record=True)
        elif op & 0xF000 == 0x5000:
            self.r[n] = self.load((self.r[m] + (op & 15) * 4) & 0xFFFFFFFF, 4)
        elif op & 0xFF00 == 0x8100:
            self.write((self.r[m] + (op & 15) * 2) & 0xFFFFFFFF, self.r[0], 2, record=True)
        elif op & 0xFF00 == 0x8500:
            self.r[0] = signed(self.load((self.r[m] + (op & 15) * 2) & 0xFFFFFFFF, 2), 16) & 0xFFFFFFFF
        elif op & 0xF00F == 0x0004:
            self.write((self.r[0] + self.r[n]) & 0xFFFFFFFF, self.r[m], 1, record=True)
        elif op & 0xF00F == 0x000E:
            self.r[n] = self.load((self.r[0] + self.r[m]) & 0xFFFFFFFF, 4)
        elif op & 0xF00F == 0x6002:
            self.r[n] = self.load(self.r[m], 4)
        elif op & 0xF00F == 0x6007:
            self.r[n] = ~self.r[m] & 0xFFFFFFFF
        elif op & 0xF00F == 0x600E:
            self.r[n] = signed(self.r[m] & 255, 8) & 0xFFFFFFFF
        elif op & 0xF00F == 0x2009:
            self.r[n] &= self.r[m]
        elif op & 0xF00F == 0x3000:
            self.t = self.r[n] == self.r[m]
        elif op & 0xF00F == 0x3003:
            self.t = signed(self.r[n], 32) >= signed(self.r[m], 32)
        elif op & 0xF00F == 0x3007:
            self.t = signed(self.r[n], 32) > signed(self.r[m], 32)
        elif op & 0xF00F == 0x3008:
            self.r[n] = (self.r[n] - self.r[m]) & 0xFFFFFFFF
        elif op & 0xF00F == 0x300E:
            value = self.r[n] + self.r[m] + int(self.t)
            self.r[n], self.t = value & 0xFFFFFFFF, value > 0xFFFFFFFF
        elif op & 0xF00F == 0x300F:
            value = signed(self.r[n], 32) + signed(self.r[m], 32)
            self.r[n], self.t = value & 0xFFFFFFFF, not -2**31 <= value < 2**31
        elif op & 0xF0FF in (0x4011, 0x4015):
            self.t = signed(self.r[n], 32) >= (0 if op & 255 == 0x11 else 1)
        elif op & 0xF0FF == 0x4008:
            self.r[n] = (self.r[n] << 2) & 0xFFFFFFFF
        elif op & 0xF00F == 0x0007:
            self.macl = self.r[n] * self.r[m] & 0xFFFFFFFF
        elif op == 0x4F12:
            self.push(self.macl)
        elif op == 0x4F16:
            self.macl = self.pop()
        elif op & 0xF0FF == 0x001A:
            self.r[n] = self.macl
        elif op & 0xF0FF == 0x0002:
            self.r[n] = (self.sr & ~1) | int(self.t)
        elif op & 0xF0FF == 0x400E:
            self.sr = self.r[n]
            self.t = bool(self.sr & 1)
        else:
            handled = False
        if handled:
            self.instructions += 1
            assert self.instructions < self.INSTRUCTION_LIMIT
        else:
            self.pc = pc
            super().step(in_delay)

    def transition(self, word, phase=0):
        self.original_r[4:6] = [phase, word]
        self.cancellations.clear()
        self.device_calls.clear()
        self.invoke(0x26AEC, RECORD_WRITES | HARDWARE_WRITES)

    def tick(self, phase):
        self.original_r[4] = phase
        self.write(0xFFFFAC17, phase, 1)
        self.cancellations.clear()
        self.device_calls.clear()
        saved_macl = self.macl
        self.invoke(0x263EE, SCHEDULER_WRITES)
        assert self.macl == saved_macl

    def log_pulses(self):
        self.invoke(0x26F8C, LOGGER_WRITES)
        return tuple(self.get_float(0xFFFFC0B8 + i * 4) for i in range(6))


class CutPublicationMachine(SchedulerMachine):
    """Capture instruction-produced cut values and the effective interrupt mask."""
    def __init__(self, image):
        self.publications = []
        super().__init__(image)
        self.sr = 0

    def write(self, address, value, size=4, record=False):
        super().write(address, value, size, record)
        if record and address == INHIBIT_WORD:
            self.publications.append((value & 65535, self.read(safety.FUEL_CUT_FLAG, 1), self.sr & 0xF0))


class InjectorSchedulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x2088, 0x209C), (0x2378, 0x2390), (0x251C, 0x2534), (0x920C, 0x92D4),
                           (0x9350, 0x9370), (0xD744, 0xD77C), (0xFA94, 0xFADC),
                           (0x1D228, 0x1D23C), (0x1D296, 0x1D298),
                           (0x26088, 0x261EC), (0x263EE, 0x2687C),
                           (0x26944, 0x26E64), (0x26E9A, 0x27084),
                           (0x4B64C, 0x4B6B4), (0x75FD0, 0x75FD4),
                           (0x3A28, 0x3BFC), (0x49EC, 0x4A0C),
                           (0x6938, 0x6980), (0x6AB4, 0x6ABC),
                           (0x119B6, 0x119BC), (0x11B16, 0x11B1C),
                           (0xCF58, 0xCFA4), (0xD0AC, 0xD0B0)):
            assert cls.image[start:end] == stock[start:end], f'Native scheduler changed at {start:#x}'
        # Native descriptors: task 5 (injector phase) priority 4, task 6
        # (fuel calculations/cuts) priority 2. 3B8E compares larger as higher.
        assert cls.image[0x49EC:0x4A0C] == bytes.fromhex(
            '04000400ffff71c4000069380200000004000200ffff71cc0000696c02000000')

    def test_phase_distance_equality_and_wrap(self):
        cpu = SchedulerMachine(self.image)
        for current, target in product(range(0, 720, 30), range(0, 720, 120)):
            cpu.original_r[4:6] = [current * DEGREE, target * DEGREE]
            value = cpu.invoke(0x26990, set())
            self.assertEqual(value, ((target - current - 1) % 720 + 1) * DEGREE)

    def test_native_cut_transition_matrix(self):
        # 1,728 invocations / 10,368 record decisions. The expectation is a
        # state contract, not a translation of the emitted branch sequence.
        for stage, substate, pending, word in product(range(3), range(3), range(3), range(64)):
            cpu = SchedulerMachine(self.image)
            for record, hw in zip(RECORDS, HARDWARE):
                cpu.write(record + 2, stage, 1)
                cpu.write(record + 17, substate, 1)
                cpu.write(hw + 19, pending, 1)
            cpu.transition(word)
            cancelable = stage == 1 and substate != 2 and (substate != 1 or pending != 0)
            expected_cancels = []
            for i, (record, hw) in enumerate(zip(RECORDS, HARDWARE)):
                cut = bool(word & (1 << i))
                accepted = cut and (stage == 0 or cancelable)
                self.assertEqual(cpu.read(record + 1, 1), int(accepted))
                self.assertEqual(cpu.read(record + 2, 1), 0 if cut and cancelable else stage)
                if cut and cancelable:
                    expected_cancels.append(i)
                    self.assertEqual(cpu.read(hw + 19, 1), 0)
                else:
                    self.assertEqual(cpu.read(hw + 19, 1), pending)
            self.assertEqual(cpu.cancellations, expected_cancels)
            self.assertEqual(cpu.device_calls, [])

    def test_release_obeys_both_native_mode_windows(self):
        for mode, stage, phase in product((0, 1), range(3), (99, 100, 299, 300, 301, 400, 719, 720)):
            cpu = SchedulerMachine(self.image)
            for record in RECORDS:
                cpu.write(record, mode, 1)
                cpu.write(record + 1, 1, 1)
                cpu.write(record + 2, stage, 1)
                cpu.write(record + 8, phase * DEGREE if phase < 720 else 0)
            cpu.transition(0)
            margin = cpu.read(0x75FD0, 4) + 4000
            for i, record in enumerate(RECORDS):
                if mode == 0:
                    permitted = phase >= 300
                else:
                    end = 300 * DEGREE + 120 * (((4000 + i * 400 + margin) << 16) // 40000)
                    permitted = phase > 300 and phase * DEGREE >= end
                released = stage == 1 or (stage == 0 and permitted)
                self.assertEqual(cpu.read(record + 1, 1), 0 if released else 1)
                self.assertEqual(cpu.read(record + 2, 1), 2 if stage == 0 and not permitted else stage)
            self.assertFalse(cpu.cancellations or cpu.device_calls)

    def test_timer_cancel_software_pending_and_register_branches(self):
        for channel, pending, active, timer_bit in product(range(6), (0, 1, 2), (0, 1), (0, 1)):
            cpu = SchedulerMachine(self.image)
            hw = HARDWARE[channel]
            mask = 1 << channel
            cpu.write(hw + 19, pending, 1)
            cpu.write(hw + 20, active, 1)
            cpu.write(0xFFFFF440, 0x1234, 2)
            cpu.write(0xFFFFF66C, 0xAAFF, 2)
            cpu.write(0xFFFFF666, mask if timer_bit else 0, 2)
            cpu.write(0xFFFFF640 + channel * 2, 0x4321, 2)
            cpu.write(0xFFFFF444 + channel * 2, 0xABCD, 2)
            cpu.original_r[4] = channel
            cpu.invoke(0x920C, HARDWARE_WRITES)
            self.assertEqual(cpu.read(hw + 19, 1), 0)
            self.assertEqual(cpu.sr & 0xF0, 0x20)
            self.assertEqual(cpu.read(0xFFFFF66C, 2), (0xAAFF & ~mask) if pending == 0 and active else 0xAAFF)
            self.assertEqual(cpu.read(hw + 20, 1), 0 if pending == 0 and active else active)
            self.assertEqual(cpu.read(0xFFFFF444 + channel * 2, 2), 0x1233 if pending == 0 and not active else 0xABCD)
            self.assertEqual(cpu.read(0xFFFFF640 + channel * 2, 2), 0 if pending == 0 and not active and not timer_bit else 0x4321)

    def test_added_cut_survives_scheduler_wrap_and_releases_fault_mask(self):
        for pressure, state in ((1150, 0), (820, 3)):
            cpu = SchedulerMachine(self.image)
            cpu.write(0xFFFFD94C, 0x12, 1)
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.write(safety.LEAN_STATE_RAM, state, 1)
            self.assertTrue(cpu.cut_step()[-1])
            for phase in list(range(24)) * 2:
                cpu.tick(phase)
                self.assertEqual(cpu.read(CACHED_WORD, 2), 0xFFFF)
                self.assertFalse(cpu.device_calls)
                self.assertEqual(cpu.log_pulses(), (0,) * 6)
            cpu.put_float(safety.MAP_PRESSURE, 700)
            self.assertFalse(cpu.cut_step()[-1])
            resumed = set()
            for phase in list(range(24)) * 2:
                cpu.tick(phase)
                resumed.update(event[1] for event in cpu.device_calls)
                self.assertEqual(cpu.read(CACHED_WORD, 2), 0x12)
            self.assertEqual(resumed, {0, 2, 3, 5})

    def test_already_queued_cut_and_logger_converge_at_phase_boundary(self):
        for (pressure, state), pending in product(((1150, 0), (820, 3)), (0, 1, 2)):
            cpu = SchedulerMachine(self.image)
            for record, hw in zip(RECORDS, HARDWARE):
                cpu.write(record + 2, 1, 1)
                cpu.write(record + 17, 1, 1)
                cpu.write(hw + 19, pending, 1)
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.write(safety.LEAN_STATE_RAM, state, 1)
            self.assertTrue(cpu.cut_step()[-1])
            cpu.tick(0)
            self.assertEqual(cpu.cancellations, list(range(6)) if pending else [])
            expected = (0,) * 6 if pending else (0, 1100, 1200, 1300, 1400, 1500)
            self.assertEqual(cpu.log_pulses(), expected)
            self.assertFalse(cpu.device_calls)
            # The cache is already FFFF. Deferred records become inhibited at
            # their native cycle boundary without another 26AEC invocation.
            for phase in range(1, 24):
                cpu.tick(phase)
                self.assertNotIn(0x26AEC, cpu.entered)
                self.assertFalse(cpu.device_calls)
                self.assertEqual(cpu.read(CACHED_WORD, 2), 0xFFFF)
            self.assertEqual(cpu.log_pulses(), (0,) * 6)
            self.assertTrue(all(cpu.read(r + 1, 1) == 1 for r in RECORDS))

    def test_startup_resync_and_mode_changes_retain_cut_masks(self):
        for phase, cranking, word, startup in product((0, 7, 23, 24, 47), (False, True), (0, 0x12, 0xFFFF), (False, True)):
            cpu = SchedulerMachine(self.image)
            cpu.write(0xFFFFB748, 128 if cranking else 0, 1)
            cpu.write(INHIBIT_WORD, word, 2)
            cpu.write(0xFFFFC0B5, int(startup), 1)
            cpu.tick(phase)
            self.assertEqual(cpu.read(0xFFFFC0B5, 1), 0)
            self.assertEqual(cpu.read(CACHED_WORD, 2), word)
            self.assertEqual(cpu.read(CACHED_MODE, 1), 0 if cranking else 2)
            for _, channel, _, _ in cpu.device_calls:
                self.assertFalse(word & (1 << channel))
            if not startup and phase not in (0, 24):
                self.assertIn(0x2672A, cpu.entered)
                self.assertEqual(cpu.cancellations, list(range(6)))
            # Initialization can defer a mode change for stage-2 records.
            # The per-record mode catches up at its next native cycle boundary.
            for record in RECORDS:
                if cpu.read(record, 1) != (0 if cranking else 1):
                    self.assertTrue(startup and not cranking)
                    self.assertEqual(cpu.read(record + 2, 1), 2)
            for advance in range(1, 25):
                cpu.tick((phase + advance) % 48)
                for _, channel, _, _ in cpu.device_calls:
                    self.assertFalse(word & (1 << channel))
            for record in RECORDS:
                self.assertEqual(cpu.read(record, 1), 0 if cranking else 1)

    def test_logger_does_not_infer_timer_delivery_from_global_word(self):
        for word in range(64):
            cpu = SchedulerMachine(self.image)
            cpu.write(INHIBIT_WORD, 0xFFFF ^ word, 2)  # Deliberately another epoch.
            for i, record in enumerate(RECORDS):
                cpu.write(record + 1, bool(word & (1 << i)), 1)
            expected = tuple(0 if word & (1 << i) else 1000 + i * 100 for i in range(6))
            self.assertEqual(cpu.log_pulses(), expected)
            for i in (0, 1):
                self.assertEqual(cpu.get_float(0xFFFFC0D0 + i * 4), 0 if word & (1 << i) else expected[i] + 1000)
                cpu.write(RECORDS[i] + 36, 1, 1)
            cpu.log_pulses()
            self.assertEqual((cpu.get_float(0xFFFFC0D0), cpu.get_float(0xFFFFC0D4)), (0, 0))

    def test_deleted_native_gate_or_cache_exposes_output(self):
        for address in (0x26BFC, 0x265A2, 0x266AE):
            image = bytearray(self.image)
            self.assertNotEqual(image[address:address + 2], bytes.fromhex('0009'))
            image[address:address + 2] = bytes.fromhex('0009')
            cpu = SchedulerMachine(image)
            cpu.write(INHIBIT_WORD, 0xFFFF, 2)
            cpu.tick(0)
            self.assertTrue(cpu.device_calls, f'Negative control did not escape the cut at {address:#x}')

    def test_guard_lock_restores_all_masks_on_every_policy_state(self):
        for entry, imask, pressure, state, enabled in product(
                (boost.REVWRAP_ADDR, safety.LEAN_CUT_WRAPPER_ADDR), range(0, 256, 16),
                (700, 820, 1150), range(4), (0, 1)):
            image = bytearray(self.image)
            image[safety.LEAN_CUT_ENABLE_ADDR] = enabled
            cpu = CutPublicationMachine(image)
            cpu.sr = imask | 0x300  # Prior Q/M flags are not the mask-return contract.
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.write(safety.LEAN_STATE_RAM, state, 1)
            cpu.invoke(entry, CUT_WRITES)
            self.assertTrue(cpu.publications)
            self.assertTrue(all(mask == max(imask, 0x10) for _, _, mask in cpu.publications))
            self.assertEqual(cpu.sr & 0xF0, imask)
            self.assertEqual(len(cpu.task_handoffs), int(imask == 0))
            for word, flag, mask in cpu.task_handoffs:
                self.assertEqual(mask, 0)
                self.assertEqual(bool(word), bool(flag & 128))
                self.assertEqual(word, cpu.read(INHIBIT_WORD, 2))

    def test_missing_outer_or_standalone_lock_exposes_temporary_release(self):
        for entry, pressure, state in ((boost.REVWRAP_ADDR, 1150, 0),
                                       (safety.LEAN_CUT_WRAPPER_ADDR, 820, 3)):
            for damage in (False, True):
                image = bytearray(self.image)
                self.assertEqual(image[entry + 6:entry + 8], bytes.fromhex('e410'))
                if damage:
                    image[entry + 6:entry + 8] = bytes.fromhex('e400')  # Request no lock.
                cpu = CutPublicationMachine(image)
                cpu.write(INHIBIT_WORD, 0xFFFF, 2)  # The cut was already active.
                cpu.write(safety.FUEL_CUT_FLAG, 128, 1)
                cpu.put_float(safety.MAP_PRESSURE, pressure)
                cpu.write(safety.LEAN_STATE_RAM, state, 1)
                cpu.invoke(entry, CUT_WRITES)
                observations = cpu.publications + cpu.task_handoffs
                unprotected = [(word, flag) for word, flag, mask in observations if word == 0 and mask == 0]
                self.assertEqual(bool(unprotected), damage)
                self.assertEqual(cpu.read(INHIBIT_WORD, 2), 0xFFFF)  # Return-only checks miss it.
                for word, flag in unprotected:
                    # Replay the published state through actual native scheduler
                    # instructions. IRQ arrival/context switching is not simulated.
                    reader = SchedulerMachine(self.image)
                    reader.write(CACHED_WORD, 0xFFFF, 2)
                    reader.write(INHIBIT_WORD, word, 2)
                    reader.write(safety.FUEL_CUT_FLAG, flag, 1)
                    for r in RECORDS:
                        reader.write(r + 1, 1, 1)
                        reader.write(r + 8, 400 * DEGREE)
                    reader.tick(0)
                    self.assertEqual({event[1] for event in reader.device_calls}, set(range(6)))

    def test_changed_scheduler_lock_contract_refuses_before_mutation(self):
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for address in (0x3AF4, 0x3AFA, 0x3B00, 0x3B08, 0x3B10, 0x3B1A, 0x3B20, 0x3B24):
            image = bytearray(stock)
            image[address] ^= 1
            before = bytes(image)
            with self.assertRaisesRegex(SystemExit, 'native scheduler-lock contract'):
                boost.apply_to_rom(image)
            self.assertEqual(bytes(image), before)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(unittest.defaultTestLoader.loadTestsFromTestCase(InjectorSchedulerTests))
        if not result.wasSuccessful():
            raise SystemExit(report.getvalue())
        print(f'  Injector scheduler: {result.testsRun} execution test groups passed')
    finally:
        IMAGE = previous


if __name__ == '__main__':
    if len(sys.argv) > 1:
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
