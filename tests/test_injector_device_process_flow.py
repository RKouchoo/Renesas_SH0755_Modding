#!/usr/bin/env python3
"""Follow native injector enqueue/update code to timer-register publications.

Extends the scheduler audit's former device-call boundaries. Timer snapshots,
period counts, pulse inputs and elapsed crank phases are explicit fixtures;
no elapsed timer, electrical current or delivered fuel is simulated. DSTR's
documented write-one/start, write-zero/no-change semantics are modeled; tests
supply down-counter completion and interrupt entry explicitly.
The existing bounded integer-division boundary remains documented.
"""
import _test_paths
from itertools import product
import unittest

from test_injector_scheduler_execution import (
    SchedulerMachine, HARDWARE, HARDWARE_WRITES, DEGREE,
)
from test_primary_fueling_execution import signed
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT = _test_paths.ROOT
DEVICE_WRITES = HARDWARE_WRITES | {
    (h+offset, size) for h in HARDWARE for offset, size in
    ((0, 4), (4, 4), (8, 4), (12, 4), (16, 2), (18, 1), (19, 1), (20, 1))
} | {(0xFFFFF666, 2), (0xFFFFF66A, 2)}
NATIVE = {0x900A, 0x8F84, 0x8F80, 0x90F8, 0x92DA, 0x938C, 0x93D4,
          0x961A, 0x96FC, 0x4832}
END_HANDLERS = (0x5BD4, 0x5BE2, 0x5C30, 0x5C3E, 0x5C4C, 0x5C5A)


class InjectorDeviceMachine(SchedulerMachine):
    def write(self, address, value, size=4, record=False):
        if record and address == 0xFFFFF666 and size == 2:
            # SH7055S manual11.2.11/11.6: CPU zeros cannot clear DSTR.
            # Starting a channel requires a nonzero down-counter. Time and
            # hardware clearing remain explicit test inputs (record=False).
            startable = sum(1 << n for n in range(16)
                            if value & (1 << n) and self.read(0xFFFFF640+2*n, 2) != 0)
            value = self.read(address, 2) | (value & startable)
        super().write(address, value, size, record)

    def __init__(self, image, rpm=3000, latency=2736):
        super().__init__(image)
        # Count units derive from native duration*4 and logger counts/4.
        # They are consistent input fixtures, not measured timer frequency.
        self.write(0xFFFFAC04, round(4_000_000*5/rpm))    # 30-degree interval.
        self.write(0xFFFFAC08, round(4_000_000*20/rpm))   # 120-degree interval.
        self.write(0xFFFFAC1C, 16000)  # Timer snapshot; shifts by4 to1000.
        self.write(0xFFFFAC7C, latency)
        self.write(0xFFFFAD10, 0)
        self.put_float(0xFFFFAC18, 0)
        self.write(0xFFFFF440, 1000, 2)
        self.write(0xFFFFF66A, 0, 2)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n = (op >> 8) & 15
        if op & 0xF0FF in (0x4009, 0x4019, 0x4029):  # SHLR2/8/16, T unchanged.
            self.r[n] >>= {0x09: 2, 0x19: 8, 0x29: 16}[op & 255]
        elif op & 0xF0FF == 0x4021:  # SHAR, T receives outgoing low bit.
            self.t = bool(self.r[n] & 1)
            self.r[n] = (signed(self.r[n], 32) >> 1) & 0xFFFFFFFF
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def call_lookup(self, target):
        if target in NATIVE:
            if target in (0x900A, 0x8F84, 0x90F8):
                self.device_calls.append((target, self.r[4] & 255, self.r[5], self.r[6]))
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def enqueue(self, channel, end_angle, pulse_counts, start_mode=False):
        self.original_r[4:7] = [channel, round(end_angle*DEGREE), pulse_counts]
        self.invoke(0x8F84 if start_mode else 0x900A, DEVICE_WRITES)

    def update(self, channel, pulse_counts):
        self.original_r[4:6] = [channel, pulse_counts]
        self.invoke(0x90F8, DEVICE_WRITES)

    def poll(self):
        self.invoke(0x8F08, DEVICE_WRITES)


class InjectorDeviceFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        cls.images = {
            'main': (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes(),
            'v2': (ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes(),
        }
        cls.images['captured'] = before_pump_scaling(cls.images['v2'])
        for image in cls.images.values():
            for a, b in ((0x8F08, 0x98CC), (0x4832, 0x4844), (0x5BD4, 0x5C66),
                         (0x4DB2, 0x4E88), (0x7FF18, 0x7FF1C),
                         (0xFA94, 0xFADC), (0xD744, 0xD77C)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_observed_pulse_range_reaches_nonzero_timer_words_at_all_rpms(self):
        for name, image in self.images.items():
            for rpm, gross_us, channel in product((2500, 2800, 3000, 3200, 3500, 4144),
                                                 (7680, 8192, 9472, 9984, 10752, 12288),
                                                 range(6)):
                cpu = InjectorDeviceMachine(image, rpm)
                counts = gross_us*4-2736
                cpu.put_float(0xFFFFAC18, 300)  # Intentionally late: immediate scheduling.
                cpu.enqueue(channel, 300, counts)
                width_register = cpu.read(0xFA94+12*channel, 4)
                self.assertEqual(cpu.read(width_register, 2), gross_us//4,
                                 (name, rpm, gross_us, channel))
                self.assertEqual(cpu.read(HARDWARE[channel]+19, 1), 0)
                self.assertEqual(cpu.read(HARDWARE[channel]+12, 4), counts)
                self.assertEqual(cpu.sr & 0xF0, 0x20)

    def test_pending_end_angle_request_keeps_duration_when_promoted(self):
        for image in self.images.values():
            for rpm in (2800, 3000, 3500):
                cpu = InjectorDeviceMachine(image, rpm)
                counts = 9984*4-2736
                cpu.enqueue(0, 600, counts)
                self.assertEqual(cpu.read(HARDWARE[0]+19, 1), 2)
                # Native 938C advances pending distance by30 degrees per call.
                # Timer snapshots stay fixtures; no interrupt delivery is claimed.
                for _ in range(24):
                    cpu.poll()
                    if cpu.read(HARDWARE[0]+19, 1) == 0:
                        break
                self.assertEqual(cpu.read(HARDWARE[0]+19, 1), 0)
                self.assertEqual(cpu.read(cpu.read(0xFA94, 4), 2), 9984//4)

    def test_pending_duration_update_recalculates_start_distance_without_zeroing(self):
        for image in self.images.values():
            cpu = InjectorDeviceMachine(image)
            cpu.enqueue(0, 600, 8000*4-2736)
            before = signed(cpu.read(HARDWARE[0]+4, 4), 32)
            cpu.update(0, 10000*4-2736)
            after = signed(cpu.read(HARDWARE[0]+4, 4), 32)
            self.assertLess(after, before)
            self.assertEqual(cpu.read(HARDWARE[0], 4), 10000*4-2736)
            self.assertEqual(cpu.read(HARDWARE[0]+19, 1), 2)

    def test_active_duration_changes_and_shortening_clamp(self):
        for image, channel in product(self.images.values(), range(6)):
            hw = HARDWARE[channel]
            register = 0xFFFFF640+2*channel
            cpu = InjectorDeviceMachine(image)
            cpu.write(hw+12, 8000*4-2736)
            cpu.write(register, 2000, 2)
            cpu.update(channel, 10000*4-2736)
            self.assertEqual(cpu.read(register, 2), 2500)
            cpu.update(channel, 8000*4-2736)
            self.assertEqual(cpu.read(register, 2), 2000)
            # Only 400 us remain. Removing 2 ms must end this pulse, not wrap.
            cpu.write(register, 100, 2)
            cpu.update(channel, 6000*4-2736)
            self.assertEqual(cpu.read(register, 2), 0)

    def test_deferred_request_uses_updated_width_in_native_end_handler(self):
        for image, channel in product(self.images.values(), range(6)):
            cpu = InjectorDeviceMachine(image)
            hw = HARDWARE[channel]
            register = 0xFFFFF640+2*channel
            mask = 1 << channel
            cpu.put_float(0xFFFFAC18, 300)
            cpu.write(0xFFFFF666, mask, 2)  # DSTR: earlier pulse is counting.
            cpu.write(register, 100, 2)
            cpu.enqueue(channel, 330, 10000*4-2736, start_mode=True)
            self.assertEqual(cpu.read(hw+20, 1), 1)
            self.assertEqual(cpu.read(0xFFFFF66C, 2) & mask, mask)
            self.assertEqual(cpu.read(register, 2), 100)
            cpu.update(channel, 9000*4-2736)
            self.assertEqual(cpu.read(register, 2), 100)
            # Explicit hardware-completion fixture, not an emulated event.
            cpu.write(0xFFFFF440, 1100, 2)
            cpu.write(0xFFFFF666, 0, 2)
            cpu.write(register, 0, 2)
            cpu.write(0xFFFFF66A, mask, 2)
            cpu.invoke(END_HANDLERS[channel], DEVICE_WRITES)
            self.assertEqual(cpu.read(register, 2), 2250)
            self.assertEqual(cpu.read(hw+20, 1), 0)
            self.assertEqual(cpu.read(0xFFFFF66C, 2) & mask, 0)

    def test_active_reschedule_with_bounded_snapshot_age_and_counter_wrap(self):
        for image, rpm, channel, snapshot in product(
                self.images.values(), (2800, 3000, 3500, 4144), range(6), (1000, 65500)):
            cpu = InjectorDeviceMachine(image, rpm)
            elapsed = round(4_000_000*5/rpm)//16  # One 30-degree input interval.
            cpu.write(0xFFFFAC1C, snapshot*16)
            cpu.write(0xFFFFF440, (snapshot+elapsed) & 65535, 2)
            cpu.write(0xFFFFF666, 1 << channel, 2)
            cpu.write(0xFFFFF640+2*channel, 100, 2)
            cpu.put_float(0xFFFFAC18, 300)
            cpu.enqueue(channel, 300, 10000*4-2736)
            self.assertEqual(cpu.read(0xFFFFF640+2*channel, 2), 2500-elapsed)

    def test_excessively_stale_timestamp_reproduces_native_counter_wrap(self):
        # A counterexample to unconditional range safety, NOT an observed ECU
        # state or a desired safety behavior. Establishing reachability from
        # crank IRQ/task timing is separate work; do not turn it into a cure.
        for image in self.images.values():
            cpu = InjectorDeviceMachine(image)
            cpu.write(0xFFFFF440, 4000, 2)  # Snapshot remains1000: 12 ms stale.
            cpu.write(0xFFFFF666, 1, 2)
            cpu.write(0xFFFFF640, 100, 2)
            cpu.put_float(0xFFFFAC18, 300)
            cpu.enqueue(0, 300, 10000*4-2736)
            self.assertEqual(cpu.read(0xFFFFF640, 2), 65036)
            self.assertIn(0x9554, cpu.visited)

    def test_native_interrupt_priorities_keep_crank_above_wideband_task(self):
        # VBR7FC50 + vector178*4 ->3094 ->340C ->5DAE ->8218.
        # SH7055S manual table7.3 identifies vector178 as CMI10B, IPRI[7:4].
        for image in self.images.values():
            cpu = InjectorDeviceMachine(image)
            cpu.invoke(0x4DB2, {(a, 2) for a in range(0xFFFFED00, 0xFFFFED1A, 2)})
            self.assertEqual(cpu.read(0xFFFFED10, 2), 0x99B0)
            self.assertEqual((cpu.read(0xFFFFED10, 2) >> 4) & 15, 11)
            self.assertEqual(cpu.read(0xFFFFED0E, 2), 0x9999)
            self.assertEqual(cpu.read(0x7FF18, 4), 0x3094)


if __name__ == '__main__':
    unittest.main(verbosity=2)
