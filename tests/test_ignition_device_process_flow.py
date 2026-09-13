#!/usr/bin/env python3
"""Connect native spark scheduling to the six coil timer descriptors.

Crank phase, period, timer snapshots and completion remain explicit fixtures.
No electrical spark, crank synchronization or interrupt delivery is simulated.
The inherited dwell LUT and bounded integer-division math boundaries remain;
timing conversion, queue transitions and device routines execute ROM opcodes.
"""
import _test_paths
from itertools import product
from collections import Counter
import unittest

from test_ignition_permission_execution import IgnitionMachine, SPARK_WORD
from test_injector_scheduler_execution import DEGREE
from test_primary_fueling_execution import bits, signed
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT = _test_paths.ROOT
RAM = 0xFFFF0000
RECORDS = tuple(RAM+0xC204+44*i for i in range(3))
DEVICES = tuple(RAM+0xAD14+8*i for i in range(6))
DEVICE_WRITES = {(a+o, n) for a in DEVICES for o, n in
                 ((0, 4), (4, 1), (5, 1), (6, 1))} | {
    (RAM+a, 4) for a in (*range(0xAD44, 0xAD5C, 4), 0xAD60, 0xAD64, 0xAD68)
} | {(RAM+a, 2) for a in (0xAD5C, 0xAD6C, 0xF666,
                            *range(0xF604, 0xF620, 2),
                            *range(0xF650, 0xF65C, 2))}
RECORD_WRITES = {(r+o, n) for r in RECORDS for o, n in
    ((0, 1), (1, 1), (2, 1), (4, 4), (8, 1), (9, 1))} | {
    (r+s+o, n) for r in RECORDS for s in (12, 28) for o, n in
    ((0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1),
     (6, 1), (7, 1), (8, 4), (12, 4))}
SCHEDULE_WRITES = DEVICE_WRITES | RECORD_WRITES | {
    (RAM+0xC288, 1), (RAM+0xC28A, 2), (RAM+0xC28C, 1), (RAM+0xC28D, 1)}
TIMER_INIT_WRITES = {(RAM+a, 1) for a in (
    0xF401, 0xF400, 0xF402, 0xF404, 0xF406, 0xF408, 0xF40A,
    0xF424, 0xF426, 0xF428, 0xF45D, 0xF45C, 0xF466, 0xF62B,
    0xF62A, 0xF484, 0xF4AC, 0xF4CC, 0xF4EC, 0xF521, 0xF520,
    0xF526, 0xF5A1, 0xF5A0, 0xF668, 0xF66E, 0xF5C8,
    0xF627, 0xF626, 0xF629)} | {(RAM+a, 2) for a in (
    0xF666, 0xF662, 0xF664, 0xF630, 0xF66C)}
NATIVE = {
    0x3AF4, 0x3B08, 0x9952, 0x997A, 0x99B4, 0x99E0, 0x9AA4, 0x9C54, 0x9D3A, 0x9F9C,
    0x29AA8, 0x29C5C, 0x29C62, 0x29C92, 0x29CA8, 0x29D04,
    0x29E14, 0x29F72, 0x2A018, 0x2A0A6, 0x2A0C0, 0x2A17A,
    0x2A262, 0x2A282, 0x2A2BC, 0x2A3B2, 0x2A3C0, 0x2A3CE, 0x27442,
    0x6521C, 0x80F8, 0x470F4, 0x47198, 0x46F52,
}


class IgnitionDeviceMachine(IgnitionMachine):
    def __init__(self, image, rpm=3000, timing=16, snapshot=1000):
        super().__init__(image)
        self.coil_calls = []
        self.write(RAM+0xC0E2, 0, 1)  # No native initial-charge override.
        for a in (*range(0xAD14, 0xAD70), *range(0xC204, 0xC292)):
            self.write(RAM+a, 0, 1)
        for a in (*range(0xF604, 0xF620, 2), *range(0xF650, 0xF65C, 2)):
            self.write(RAM+a, 0, 2)
        self.write(RAM+0xF602, snapshot, 2)
        self.write(RAM+0xAC08, round(4_000_000*20/rpm))
        self.write(RAM+0xAC1C, snapshot*16)
        self.put_float(RAM+0xAC18, 0)
        self.put_float(RAM+0xAC00, rpm)
        self.put_float(RAM+0xB544, rpm)
        self.put_float(RAM+0xABB4, 14)
        for i in range(6):
            self.put_float(RAM+0xC0EC+4*i, timing)
        self.invoke(0x9FEC, DEVICE_WRITES)
        self.invoke(0x296F0, SCHEDULE_WRITES)
        self.invoke(0x29C00, SCHEDULE_WRITES)
        self.poll()

    def call_lookup(self, target):
        if target in NATIVE:
            self.entered.append(target)
            if target in (0x9952, 0x997A, 0x99B4):
                self.coil_calls.append((target, self.r[4] & 255,
                                        self.fr[4] if target != 0x99B4 else None))
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF0FF == 0x0023:  # BRAF Rn; signed offset modulo32.
            assert not in_delay
            target = (pc+4+self.r[n]) & 0xFFFFFFFF
            self.pc = pc+2
            self.step(in_delay=True)
            self.pc = target
        elif op & 0xF0FF in (0x4009, 0x4019, 0x4029):
            self.r[n] >>= {0x09: 2, 0x19: 8, 0x29: 16}[op & 255]
            self.pc += 2
        elif op & 0xF0FF == 0x4021:  # SHAR.
            self.t = bool(self.r[n] & 1)
            self.r[n] = (signed(self.r[n], 32) >> 1) & 0xFFFFFFFF
            self.pc += 2
        elif op & 0xF00F == 0x600F:  # EXTS.W.
            self.r[n] = signed(self.r[m] & 65535, 16) & 0xFFFFFFFF
            self.pc += 2
        elif op & 0xF00F == 0x6004:  # MOV.B @Rm+,Rn; suppress increment if n=m.
            address = self.r[m]
            self.r[n] = signed(self.load(address, 1), 8) & 0xFFFFFFFF
            if n != m:
                self.r[m] = (address+1) & 0xFFFFFFFF
            self.pc += 2
        else:
            return super().step(in_delay)
        self.visited.add(pc)
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def poll(self):
        self.invoke(0x9BCC, DEVICE_WRITES)

    def enqueue(self, channel, angle):
        self.original_r[4] = channel
        self.original_fr[4] = bits(angle)
        self.invoke(0x997A, DEVICE_WRITES)

    def tick(self, phase):
        self.original_r[4] = phase
        self.write(RAM+0xAC17, phase, 1)
        self.invoke(0x29794, SCHEDULE_WRITES)

    def phase_fixture(self, phase, elapsed_counts):
        """Supply equal TCNT2A/B advance and GR2 termination between calls.

        Manual11.2.13: an enabled GR2 terminate match clears the associated
        down-counter and DSTR bit. Other hardware events, oscillator drift,
        interrupt timing and coil current are outside this bounded fixture.
        """
        previous = self.read(RAM+0xF602, 2)
        current = (previous+elapsed_counts) & 65535
        for channel in range(6):
            end = self.read(RAM+0xF604+2*channel, 2)
            if 0 < ((end-previous) & 65535) <= elapsed_counts:
                self.write(RAM+0xF650+2*channel, 0, 2)
                self.write(RAM+0xF666,
                           self.read(RAM+0xF666, 2) & ~(0x100 << channel), 2)
        self.write(RAM+0xF602, current, 2)
        self.write(RAM+0xAC1C, current*16)
        self.put_float(RAM+0xAC18, phase*30)
        # Native task6938 calls device poll9BCC before11958->29794.
        self.poll()
        self.tick(phase)


class IgnitionDeviceProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x296F0, 0x2A44C), (0x98FC, 0xA034),
                         (0x4E8C, 0x5044),
                         (0x63174, 0x64874), (0x1A202, 0x1A280),
                         (0x6521C, 0x65230), (0x65322, 0x65324),
                         (0x4B6B4, 0x4B6FC), (0x4C690, 0x4C6B4),
                         (0xFADC, 0xFB6C), (0xD744, 0xD77C),
                         (0x60998, 0x609A8), (0x7BBE0, 0x7BCC6)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_native_timer_initialization_retains_all_six_coil_links(self):
        for image in self.images.values():
            cpu = IgnitionDeviceMachine(image)
            cpu.invoke(0x4E8C, TIMER_INIT_WRITES)
            # Native9AA4 performs RMW on these registers. Reset fixtures;
            # test with every bit initially set to check unrelated bits hold.
            for a, n in ((0xF627, 1), (0xF626, 1), (0xF629, 1),
                         (0xF630, 2), (0xF66C, 2)):
                cpu.write(RAM+a, (1 << (8*n))-1, n)
            cpu.invoke(0x9A54, TIMER_INIT_WRITES | DEVICE_WRITES)
            self.assertEqual(cpu.read(RAM+0xF662, 2), 0xFFFF)  # TCNR.
            self.assertEqual(cpu.read(RAM+0xF664, 2), 0x7F00)  # OTR.
            self.assertEqual(cpu.read(RAM+0xF66E, 1), 0)       # Reload disabled.
            for a in (0xF627, 0xF626, 0xF629):
                self.assertEqual(cpu.read(RAM+a, 1), 0x99)  # Compare mode1, bit3 retained.
            self.assertEqual(cpu.read(RAM+0xF630, 2), 0xFFC0)
            self.assertEqual(cpu.read(RAM+0xF66C, 2), 0xC0FF)
            self.assertTrue(all(cpu.read(RAM+0xF650+2*n, 2) == 0 for n in range(6)))

    def test_native_record_setup_and_timing_conversion_preserve_all_six_values(self):
        for image in self.images.values():
            cpu = IgnitionDeviceMachine(image)
            angles = [15, 16, 17, 18, 19, 20]
            for i, angle in enumerate(angles):
                cpu.put_float(RAM+0xC0EC+4*i, angle)
            for record in RECORDS:
                cpu.write(record, 1, 1)
                for phase_half in (0, 1):
                    channel = cpu.read(record+14+phase_half, 1)
                    other = cpu.read(record+30+phase_half, 1)
                    logical = cpu.read(record+16+phase_half, 1)
                    cpu.write(record+13, logical, 1)
                    cpu.original_r[4] = record
                    cpu.invoke(0x2A2BC, RECORD_WRITES)
                    self.assertEqual(cpu.read(record+24, 4), (angles[channel]-10)*DEGREE)
                    self.assertEqual(cpu.read(record+40, 4),
                                     (angles[other]-10)*DEGREE)

    def test_coil_enqueue_publishes_start_end_and_nonzero_downcounter(self):
        for image, rpm, channel, snapshot in product(self.images.values(),
                (2500, 2800, 3000, 3200, 3500, 4144), range(6), (1000, 65500)):
            cpu = IgnitionDeviceMachine(image, rpm, snapshot=snapshot)
            # Ten degrees ahead of the supplied crank snapshot. At these
            # speeds, nominal dwell has already started: native start clamps
            # to current counter+3 and end retains at least half dwell.
            cpu.enqueue(channel, 10)
            descriptor = 0xFADC+24*channel
            down, start, end = (cpu.read(descriptor+o, 4) for o in (0, 4, 8))
            self.assertGreater(cpu.read(down, 2), 0)
            self.assertEqual(cpu.read(start, 2), (snapshot+3) & 65535)
            self.assertGreaterEqual((cpu.read(end, 2)-cpu.read(start, 2)) & 65535,
                                    cpu.read(RAM+0xAD5C, 2)//2)
            self.assertEqual(cpu.read(DEVICES[channel]+5, 1), 1)
            self.assertEqual(cpu.read(DEVICES[channel]+6, 1), 1)

    def test_running_phase_cycles_continue_for_all_coils_across_logged_range(self):
        for name, image in self.images.items():
            for rpm, timing, snapshot in product(
                    (2500, 2800, 3000, 3200, 3500, 4144), (15, 18.5, 41.5), (1000, 65500)):
                cpu = IgnitionDeviceMachine(image, rpm, timing, snapshot)
                counts = round(4_000_000*5/rpm/16)
                calls = Counter()
                for index in range(72):
                    cpu.coil_calls.clear()
                    cpu.phase_fixture(index % 24, counts)
                    if index >= 24:
                        calls.update(channel for entry, channel, _ in cpu.coil_calls
                                     if entry == 0x997A)
                # Two coil commands per720 degrees in this native pair
                # scheduling layout; warm-up cycle is excluded from count.
                self.assertEqual(calls, Counter({n: 4 for n in range(6)}),
                                 (name, rpm, timing, snapshot))
                self.assertEqual(cpu.read(RAM+0xC288, 1), 2)
                self.assertTrue(all(cpu.read(r, 1) == 1 for r in RECORDS))

    def test_every_native_cylinder_cut_releases_without_a_stuck_queue(self):
        for name, image in self.images.items():
            for mask, auxiliary in product(range(64), (0, 0xFC0)):
                cpu = IgnitionDeviceMachine(image)
                cpu.write(RAM+0xC290, auxiliary, 2)
                for phase in range(24):
                    cpu.phase_fixture(phase, 417)
                for current_mask in (mask, 0):
                    cpu.write(RAM+0xD94C, (current_mask & 3) << 6, 1)
                    cpu.write(RAM+0xD94D, current_mask >> 2, 1)
                    cpu.invoke(0x27090, {(SPARK_WORD, 2)})
                    calls = Counter()
                    for phase in range(48):
                        cpu.coil_calls.clear()
                        cpu.phase_fixture(phase % 24, 417)
                        if phase >= 24:
                            calls.update(channel for entry, channel, _ in cpu.coil_calls
                                         if entry == 0x997A)
                    self.assertEqual(calls, Counter({n: 1 if auxiliary else 2 for n in range(6)
                                     if not current_mask & (1 << n)}),
                                     (name, mask, current_mask, auxiliary))

    def test_device_cancellation_waits_for_an_armed_event_to_complete(self):
        for image, channel in product(self.images.values(), range(6)):
            cpu = IgnitionDeviceMachine(image)
            cpu.enqueue(channel, 300)
            cpu.original_r[4] = channel
            cpu.invoke(0x99B4, DEVICE_WRITES)
            self.assertEqual(cpu.read(DEVICES[channel]+4, 1), 0)
            cpu.enqueue(channel, 10)
            before = tuple(cpu.read(RAM+a+2*channel, 2)
                           for a in (0xF604, 0xF614, 0xF650))
            cpu.invoke(0x99B4, DEVICE_WRITES)
            self.assertEqual(cpu.read(DEVICES[channel]+4, 1), 2)
            self.assertEqual(before, tuple(cpu.read(RAM+a+2*channel, 2)
                                          for a in (0xF604, 0xF614, 0xF650)))
            # Explicit completed timer event, then native device polling.
            cpu.write(RAM+0xF650+2*channel, 0, 2)
            cpu.poll()
            self.assertEqual(cpu.read(DEVICES[channel]+4, 1), 0)
            self.assertEqual(cpu.read(DEVICES[channel]+5, 1), 0)

    def test_native_auxiliary_mask_changes_pulse_count_without_removing_all_coils(self):
        for image, fault in product(self.images.values(), (False, True)):
            cpu = IgnitionDeviceMachine(image)
            cpu.write(RAM+0xD270, 0x80 if fault else 0, 1)
            cpu.invoke(0x1A202, {(RAM+0xB52C, 1), (RAM+0xAC20, 1)})
            self.assertEqual(cpu.read(RAM+0xB52C, 1) & 0x20, 0x20 if fault else 0)
            self.assertEqual(cpu.read(RAM+0xAC20, 1), int(fault))
            calls = Counter()
            for phase in range(48):
                cpu.original_r[4] = phase % 24
                cpu.invoke(0x2A214, {(RAM+0xC290, 2)})
                self.assertEqual(cpu.read(RAM+0xC290, 2), 0 if fault else 0xFC0)
                cpu.coil_calls.clear()
                cpu.phase_fixture(phase % 24, 417)
                if phase >= 24:
                    calls.update(channel for entry, channel, _ in cpu.coil_calls
                                 if entry == 0x997A)
            self.assertEqual(calls, Counter({n: 2 if fault else 1 for n in range(6)}))

    def test_mode_handoffs_and_phase_resynchronization_resume_running_outputs(self):
        for image in self.images.values():
            for jump in (0, 3, 12, 23):
                cpu = IgnitionDeviceMachine(image)
                for mode in (0, 1, 2, 0, 2):
                    cpu.write(RAM+0xC0E1, mode, 1)
                    calls = Counter()
                    for index in range(48):
                        cpu.coil_calls.clear()
                        cpu.phase_fixture((index+jump) % 24, 417)
                        if index >= 24:
                            calls.update((entry, channel) for entry, channel, _ in cpu.coil_calls
                                         if entry in (0x9952, 0x997A))
                    expected = {} if mode == 0 else {
                        (0x9952 if mode == 1 else 0x997A, n): 2 for n in range(6)}
                    self.assertEqual(calls, Counter(expected), (mode, jump))

    def test_cam_current_diagnostics_select_secondary_spark_and_healthy_recovery(self):
        for image, index in product(self.images.values(), (0x2D, 0x2E, 0x83, 0x84)):
            cpu = IgnitionDeviceMachine(image)
            descriptor = 0x5BDF0+20*index
            bank, mask = cpu.read(descriptor+1, 1), cpu.read(descriptor+2, 1)
            expected_codes = {0x2D: 0x11, 0x2E: 0x21, 0x83: 0x345, 0x84: 0x340}
            self.assertEqual(cpu.read(descriptor+4, 2), expected_codes[index])
            for i in range(54):
                cpu.write(RAM+0x8E58+2*i, 0x00FF, 2)
                cpu.write(RAM+0xDAB6+i, 0, 1)
            for a in (0x8FA0, 0xD952, *range(0xD26C, 0xD271)):
                cpu.write(RAM+a, 0, 1)
            cpu.write(RAM+0xDAA4, 1, 1)
            for current in (True, False):
                status = mask if current else 0
                cpu.write(RAM+0x8E58+2*bank, status << 8 | (status ^ 255), 2)
                # Historical/raw fault stays set across healthy recovery.
                cpu.write(RAM+0xDAB6+bank, mask, 1)
                cpu.invoke(0x63174, {(RAM+a, 1) for a in range(0xD26C, 0xD271)})
                self.assertEqual(bool(cpu.read(RAM+0xD270, 1) & 0x80), current)
                cpu.invoke(0x1A202, {(RAM+0xB52C, 1), (RAM+0xAC20, 1)})
                cpu.original_r[4] = 0
                cpu.invoke(0x2A214, {(RAM+0xC290, 2)})
                self.assertEqual(cpu.read(RAM+0xC290, 2), 0 if current else 0xFC0)
                calls = Counter()
                for phase in range(48):
                    cpu.coil_calls.clear()
                    cpu.phase_fixture(phase % 24, 417)
                    if phase >= 24:
                        calls.update(channel for entry, channel, _ in cpu.coil_calls
                                     if entry == 0x997A)
                self.assertEqual(calls, Counter({n: 2 if current else 1 for n in range(6)}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
