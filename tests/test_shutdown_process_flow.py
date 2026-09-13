#!/usr/bin/env python3
"""Trace AVLS callback accounting and the native ignition-off state machine.

Ignition, received status and stopped flags are explicit inputs. Native
callbacks, shutdown initiation and queue publication execute. CCBA is a
nonreturning terminal boundary; its power-management loop is not represented
as a returning helper or physical ECU behavior. The queued counter callback
and its native task worker execute through the task-completion boundary.
"""
import _test_paths
from itertools import product
import unittest

from test_avls_actuator_process_flow import AVLSActuatorMachine, ROOT, RAM
from test_avls_phase_process_flow import PERIODIC_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling

MODE_WRITES = {(RAM+a, 1) for a in (0x825C, 0xC778, 0xC779, 0xC77A,
                0xC77B, 0xC780, 0xC781)} | {(RAM+0xC77C, 2), (RAM+0xC77E, 2)}
QUEUE_WRITES = {(RAM+a, 1) for a in range(0x930D, 0x9310)} | {
    (RAM+a, 4) for a in range(0x96F8, 0xAAE4, 4)}


class ShutdownTerminal(Exception):
    pass


class ShutdownTaskComplete(Exception):
    pass


class ShutdownMachine(AVLSActuatorMachine):
    def __init__(self, image):
        super().__init__(image)
        for a in (0xC618, 0xC6F5, 0xC6F6, 0xC774, 0xDA90, 0x825C,
                  0xC778, 0xC779, 0xC77A, 0xC77B, 0xC780, 0xC781):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xB51E, 0x10, 1)
        for a in (0xC77C, 0xC77E):
            self.write(RAM+a, 0, 2)
        # Descriptor FA24: queue 3, task 4, 255 records of 20 bytes.
        self.write(RAM+0x930D, 1, 1)
        self.write(RAM+0x930E, 0, 1)
        self.write(RAM+0x930F, 1, 1)
        for a in range(0x96F8, 0xAAE4, 4):
            self.write(RAM+a, 0xA55A5AA5, 4)
        for a in range(self.STACK-512, self.STACK, 4):
            self.write(a, 0x5AA55AA5, 4)
        self.invoke(0x30FD4, MODE_WRITES)
        self.invoke(0x31002, MODE_WRITES)

    def call_lookup(self, target):
        if target == 0xCCBA:
            raise ShutdownTerminal
        if target == 0x3F2C:
            raise ShutdownTaskComplete
        if target in (0x19C04, 0x2F658, 0x1A256, 0x472C6, 0x30E66,
                      0xCFA4, 0xC700, 0x6170, 0x11EE8, 0x11EEE,
                      0x3107C, 0x31094, 0x3AF4, 0x3B08, 0x6270,
                      0x6A06, 0x6A0C, 0x4EEC4, 0x2534, 0x24DC):
            self.entered.append(target)
            return_pc, self.pc = self.pr, target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x0006:
            self.write((self.r[0]+self.r[n]) & 0xFFFFFFFF, self.r[m], 4, record=True)
            self.pc += 2
            self.instructions += 1
        elif op & 0xF0FF == 0x4010:  # DT: decrement and test for zero.
            self.r[n] = (self.r[n]-1) & 0xFFFFFFFF
            self.t = self.r[n] == 0
            self.pc += 2
            self.instructions += 1
        elif op & 0xF0FF == 0x4018:  # SHLL8; T unchanged.
            self.r[n] = self.r[n] << 8 & 0xFFFFFFFF
            self.pc += 2
            self.instructions += 1
        elif op & 0xF00F == 0x6007:  # NOT; T unchanged.
            self.r[n] = ~self.r[m] & 0xFFFFFFFF
            self.pc += 2
            self.instructions += 1
        else:
            super().step(in_delay)

    def mode_update(self):
        try:
            self.invoke(0x310D8, MODE_WRITES | QUEUE_WRITES)
        except ShutdownTerminal:
            for a, n in self.writes:
                assert (a, n) in MODE_WRITES | QUEUE_WRITES or self.min_sp <= a < self.STACK
            return 'terminal'
        return self.read(RAM+0xC778, 1)

    def drain_shutdown_task(self):
        writes = QUEUE_WRITES | {(RAM+0x8E34, 2)} | {
            (RAM+a, 4) for a in range(0xAFCC, 0xAFE0, 4)}
        try:
            self.invoke(0xC898, writes)
        except ShutdownTaskComplete:
            assert self.r[15] == self.STACK-12
            assert self.sr & 0xF0 == 0x20
            for a, n in self.writes:
                assert (a, n) in writes or self.min_sp <= a < self.STACK, (hex(a), n)
            return
        raise AssertionError('Task did not reach native completion boundary')


class ShutdownProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x30FD4, 0x312B4), (0x11EE8, 0x11EF4),
                         (0x11F8C, 0x11F94), (0xFD14, 0xFD24),
                         (0xFCB8, 0xFCC0), (0xFBC8, 0xFBCC),
                         (0x4EEC4, 0x4EF22), (0x4EFF0, 0x4EFFC),
                         (0xC898, 0xC8EC), (0x11E64, 0x11E80)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_ignition_on_prevents_shutdown_and_resets_callback_accounting(self):
        for image in self.images.values():
            cpu = ShutdownMachine(image)
            cpu.write(RAM+0xC779, 2, 1)
            cpu.write(RAM+0xC77A, 1, 1)
            for _ in range(100):
                self.assertEqual(cpu.mode_update(), 0)
            self.assertEqual(cpu.read(RAM+0xC779, 1), 0)
            self.assertEqual(cpu.read(RAM+0xC77A, 1), 0)
            self.assertEqual(cpu.read(RAM+0x930F, 1), 1)

    def test_native_ignition_off_queues_shutdown_then_waits_for_callback_completion(self):
        for image in self.images.values():
            cpu = ShutdownMachine(image)
            cpu.mode_update()
            cpu.write(RAM+0xB51E, 0, 1)
            cpu.write(RAM+0xB52C, 0x80, 1)
            for _ in range(6):
                self.assertEqual(cpu.mode_update(), 0)
            self.assertEqual(cpu.mode_update(), 1)
            self.assertEqual(cpu.read(RAM+0x930F, 1), 2)
            self.assertEqual(cpu.read(RAM+0x970C, 4), 0x6A06)
            cpu.invoke(0x3107C, MODE_WRITES)
            for _ in range(20):
                self.assertEqual(cpu.mode_update(), 1)
            cpu.invoke(0x31094, MODE_WRITES)
            self.assertEqual(cpu.mode_update(), 'terminal')
            self.assertEqual(cpu.read(RAM+0xC778, 1), 2)

    def test_avls_zero_payload_events_reach_only_their_native_callback_counters(self):
        for image, event in product(self.images.values(), (2, 3)):
            cpu = ShutdownMachine(image)
            counter = 0xC779 if event == 2 else 0xC77A
            cpu.original_r[4], cpu.original_r[5], cpu.original_r[6] = 0, event, RAM+0xAF00
            cpu.invoke(0xC700, MODE_WRITES)
            self.assertEqual(cpu.read(RAM+counter, 1), 1)
            self.assertEqual(cpu.read(RAM+0xC778, 1), 0)
            self.assertEqual(cpu.read(RAM+0x930F, 1), 1)
            self.assertEqual(cpu.read(RAM+0xF400, 1), 0xAC)

    def test_installed_avls_special_mode_gates_do_not_emit_shutdown_events(self):
        for image, rpm, shutdown, cranking, special, oil in product(self.images.values(),
                (0, 3000), (0, 1, 2), (0, 0x80), (0, 0x80), (9, 10, 150, 151)):
            cpu = ShutdownMachine(image)
            cpu.put_float(RAM+0xB544, rpm)
            cpu.put_float(RAM+0xCF94, oil)
            cpu.write(RAM+0xC778, shutdown, 1)
            cpu.write(RAM+0xB748, cranking, 1)
            cpu.write(RAM+0xCC50, special, 1)
            cpu.periodic_output()
            for bank in (0, 1):
                flags = cpu.read(RAM+0xCE0A+bank, 1)
                self.assertEqual(flags & 0x20, 0)  # Installed7D464=00, requiresFF.
                self.assertEqual(bool(flags & 8), bool(cranking and special and 10 <= oil <= 150))
            self.assertEqual(cpu.read(RAM+0xC779, 1), 0)
            self.assertEqual(cpu.read(RAM+0xC77A, 1), 0)

    def test_avls_enabled_control_emits_one_start_and_completion_event_per_bank(self):
        for image in self.images.values():
            # Positive control only: this selector is disabled in every BIN.
            enabled = bytearray(image)
            enabled[0x7D464] = 0xFF
            cpu = ShutdownMachine(bytes(enabled))
            cpu.put_float(RAM+0xB544, 0)
            cpu.write(RAM+0xC778, 1, 1)
            for _ in range(150):
                for entry in (0x40D94, 0x40764, 0x40E0A):
                    cpu.invoke(entry, PERIODIC_WRITES | MODE_WRITES)
            self.assertEqual(cpu.read(RAM+0xC779, 1), 2)
            self.assertEqual(cpu.read(RAM+0xC77A, 1), 2)
            self.assertEqual(cpu.read(RAM+0xC778, 1), 1)
            self.assertEqual(cpu.read(RAM+0x930F, 1), 1)

    def test_last_shutdown_queue_record_stops_before_digital_sample_workspace(self):
        for image in self.images.values():
            cpu = ShutdownMachine(image)
            cpu.write(RAM+0x930D, 254, 1)
            cpu.write(RAM+0x930F, 254, 1)
            cpu.write(RAM+0xAAE4, 0xA55A5AA5, 4)
            cpu.invoke(0xCFA4, QUEUE_WRITES)
            self.assertEqual(cpu.read(RAM+0x930D, 1), 0)
            self.assertEqual(cpu.read(RAM+0x930F, 1), 255)
            self.assertEqual(cpu.read(RAM+0xAAD0, 4), 0x6A06)
            self.assertEqual(cpu.read(RAM+0xAAE4, 4), 0xA55A5AA5)
            previous = bytes(cpu.read(RAM+a, 1) for a in range(0x96F8, 0xAAE8))
            cpu.invoke(0xCFA4, QUEUE_WRITES)
            self.assertEqual(cpu.read(RAM+0x930F, 1), 255)
            self.assertEqual(bytes(cpu.read(RAM+a, 1) for a in range(0x96F8, 0xAAE8)), previous)

    def test_queued_shutdown_task_runs_counter_callback_before_native_completion(self):
        for image, old, reset, eligible in product(self.images.values(),
                (3, 255), (0, 1), (0, 1)):
            cpu = ShutdownMachine(image)
            # The already-queued fixture is native no-op event1/7, not an
            # uninitialized callback or simulated return from unknown code.
            cpu.write(RAM+0x96F8, 0x6A0C, 4)
            cpu.write(RAM+0x8E34, old << 8 | (old ^ 255), 2)
            cpu.write(RAM+0xDA8A, reset, 1)
            cpu.write(RAM+0xDC06, eligible, 1)
            cpu.invoke(0xCFA4, QUEUE_WRITES)
            cpu.drain_shutdown_task()
            expected = 0 if reset else min(255, old+1) if eligible else old
            self.assertEqual(cpu.read(RAM+0x8E34, 2), expected << 8 | (expected ^ 255))
            self.assertEqual(cpu.read(RAM+0x930F, 1), 0)
            self.assertEqual(cpu.read(RAM+0x930E, 1), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
