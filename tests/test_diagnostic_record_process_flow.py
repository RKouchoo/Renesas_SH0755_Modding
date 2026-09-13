#!/usr/bin/env python3
"""Execute fault queue delivery, protected history and snapshot publication.

The actual queue-3/task-4 worker delivers a native cam-fault callback. Other
cases supply explicit descriptor faults and prior-trip status to bound the
computed record writes. No EEPROM timing, transport or physical fault state
is inferred from these controlled executions.
"""
import _test_paths
from itertools import product
import unittest

from test_diagnostic_mode_process_flow import DiagnosticModeMachine, ROOT, RAM
from test_shutdown_process_flow import QUEUE_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_diagnostic_enable_flow import (EnableMachine, WRITE_SET,
                                         PROTECTED_BASES, RAW_BASES, MASK_BASE)

HISTORY_WRITES = {(RAM+base+2*i, 2) for base in (0x8EC4, 0x8F30)
                  for i in range(54)}
RECORD_WRITES = {(RAM+a, 2) for a in range(0x8FBC, 0x8FE2, 2)} | {
    (RAM+a, 4) for a in (0x8FE4, 0x8FE8, 0x8FEC)}
AGE_WRITES = {(RAM+0x8FB8, 2), (RAM+0x8FBA, 2)}


class DiagnosticTaskComplete(Exception):
    pass


class DiagnosticRecordMachine(DiagnosticModeMachine):
    LOOKUPS = DiagnosticModeMachine.LOOKUPS | {
        0x6270, 0x6A0C, 0x53D10, 0x53DA8, 0x54D60, 0x55064,
        0x551F4, 0x55400, 0x55518, 0x5560C, 0x556F6, 0x55722, 0x24EC,
    }

    def __init__(self, image):
        super().__init__(image)
        for a, n in HISTORY_WRITES | RECORD_WRITES | AGE_WRITES:
            self.write(a, 0x00FF if n == 2 else 0x0000FFFF, n)
        self.write(RAM+0x8FE2, 0xA55A, 2)  # Unwritten record padding.
        self.write(RAM+0x8FF0, 0x5AA55AA5, 4)  # Following record sentinel.
        self.write(RAM+0xDC06, 0, 1)
        for a in range(0xDA4D, 0xDA65):
            self.write(RAM+a, a & 255, 1)  # Explicit snapshot-source bytes.
        # First queued item is an actual native no-op callback, as in the
        # shutdown task fixture. Later fault reports append their own frame.
        self.write(RAM+0x96F8, 0x6A0C, 4)
        for a in range(0x96FC, 0x970C, 4):
            self.write(RAM+a, 0, 4)

    def call_lookup(self, target):
        if target == 0x3F2C:
            raise DiagnosticTaskComplete
        return super().call_lookup(target)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        if op & 0xF0FF == 0x4028:  # SHLL16 Rn; T unchanged.
            n = (op >> 8) & 15
            self.r[n] = self.r[n] << 16 & 0xFFFFFFFF
            self.trace.append((pc, op))
            self.pc += 2
            self.instructions += 1
        else:
            return super().step(in_delay)

    def callback(self, identifier, request=0x20):
        for i, value in enumerate((identifier, request, 0)):
            self.write(RAM+0xAFCC+4*i, value, 4)
        self.original_r[4] = RAM+0xAFCC
        self.execute(0x53D10, HISTORY_WRITES | RECORD_WRITES | AGE_WRITES)
        assert self.read(RAM+0x8FE2, 2) == 0xA55A
        assert self.read(RAM+0x8FF0, 4) == 0x5AA55AA5

    def drain(self):
        writes = QUEUE_WRITES | HISTORY_WRITES | RECORD_WRITES | AGE_WRITES | {
            (RAM+a, 4) for a in range(0xAFCC, 0xAFE0, 4)}
        try:
            self.execute(0xC898, writes)
        except DiagnosticTaskComplete:
            assert self.r[15] == self.STACK-12
            assert self.sr & 0xF0 == 0x20
            for a, n in self.writes:
                assert (a, n) in writes or self.min_sp <= a < self.STACK, (hex(a), n)
            return
        raise AssertionError('Native task did not reach completion boundary')

    def descriptor(self, identifier):
        a = 0x5BDF0+20*identifier
        return self.image[a:a+20]

    def raw_fault(self, identifier):
        desc = self.descriptor(identifier)
        address = RAM+0xDAB6+desc[1]
        self.write(address, self.read(address, 1) | desc[2], 1)


class DiagnosticRecordProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x53D10, 0x53E84), (0x54D60, 0x55518),
                         (0x55518, 0x55770), (0x24DC, 0x24FC),
                         (0xC898, 0xC8EC), (0x6170, 0x6340),
                         (0x5BDF0, 0x5C9E4)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_native_missing_cam_fault_queue_drains_into_protected_history_and_snapshot(self):
        for image in self.images.values():
            cpu = DiagnosticRecordMachine(image)
            for _ in range(95):
                cpu.slow()
            self.assertEqual(cpu.read(RAM+0x930F, 1), 3)
            # Recovery before queue delivery clears current faults, while
            # raw history still makes both queued reports eligible.
            cpu.capture(0)
            cpu.capture(1)
            cpu.slow()
            self.assertEqual(cpu.read(RAM+0x8EB4, 2), 0x00FF)
            cpu.drain()
            self.assertEqual(cpu.read(RAM+0x930F, 1), 0)
            self.assertEqual(cpu.read(RAM+0x8F8C, 2), 0x18E7)
            self.assertEqual(cpu.read(RAM+0x8EB4, 2), 0x00FF)
            self.assertEqual(cpu.read(RAM+0xDAE4, 1), 0x18)
            self.assertEqual(cpu.read(RAM+0x8FE4, 4), 0x0340FCBF)
            self.assertIn(0x53D10, cpu.entered)
            self.assertIn(0x55064, cpu.entered)

    def test_all_enabled_class_zero_descriptors_have_bounded_current_independent_history_writes(self):
        for image in self.images.values():
            for identifier in range(153):
                desc = image[0x5BDF0+20*identifier:0x5BDF0+20*identifier+20]
                if image[0x5BD54+identifier] != 1 or desc[0] != 0:
                    continue
                cpu = DiagnosticRecordMachine(image)
                cpu.raw_fault(identifier)
                cpu.write(RAM+0xDC06, 1, 1)
                cpu.write(RAM+0x8EC4+2*desc[1], desc[2] << 8 | (desc[2] ^ 255), 2)
                cpu.callback(identifier)
                self.assertEqual(cpu.read(RAM+0x8F30+2*desc[1], 1), desc[2], hex(identifier))
                self.assertEqual(cpu.read(RAM+0x8E58+2*desc[1], 2), 0x00FF)
                for i in range(54):
                    value = cpu.read(RAM+0x8F30+2*i, 2)
                    self.assertEqual(value & 255, (value >> 8) ^ 255)

    def test_two_trip_promotion_requires_prior_bank_running_and_trip_qualification(self):
        for image, identifier, prior, trip, shutdown, raw in product(
                self.images.values(), (0x2D, 0x2E), (0, 1), (0, 1), (0, 1), (0, 1)):
            cpu = DiagnosticRecordMachine(image)
            desc = cpu.descriptor(identifier)
            self.assertEqual((desc[0], desc[6]), (0, 2))
            if raw:
                cpu.raw_fault(identifier)
            cpu.write(RAM+0xDC06, trip, 1)
            cpu.write(RAM+0xC778, shutdown, 1)
            value = desc[2] if prior else 0
            cpu.write(RAM+0x8EC4+2*desc[1], value << 8 | (value ^ 255), 2)
            cpu.callback(identifier)
            self.assertEqual(cpu.read(RAM+0x8F30+2*desc[1], 1),
                             desc[2] if prior and trip and not shutdown and raw else 0)

    def test_only_fault_request_twenty_runs_callback_and_missing_raw_status_does_not_promote(self):
        for image, request, raw in product(self.images.values(), (0, 0x10, 0x20, 0x21), (0, 1)):
            cpu = DiagnosticRecordMachine(image)
            if raw:
                cpu.raw_fault(0x84)
            cpu.callback(0x84, request)
            self.assertEqual(cpu.read(RAM+0x8F8C, 1), 0x10 if request == 0x20 and raw else 0)
            if request != 0x20:
                self.assertEqual(cpu.writes, [(a, n) for a, n in cpu.writes
                                             if cpu.min_sp <= a < cpu.STACK])

    def test_snapshot_is_retained_for_later_ordinary_faults_and_sources_are_paired_exactly(self):
        byte_sources = tuple(range(0xDA4D, 0xDA56)) + (0xDA58, 0xDA59, 0xDA5A) + tuple(range(0xDA5E, 0xDA65))
        for image in self.images.values():
            cpu = DiagnosticRecordMachine(image)
            cpu.raw_fault(0x84)
            cpu.callback(0x84)
            for index, source in enumerate(byte_sources):
                value = cpu.read(RAM+source, 1)
                self.assertEqual(cpu.read(RAM+0x8FBC+2*index, 2), value << 8 | (value ^ 255))
            for source, target in ((0xDA56, 0x8FE8), (0xDA5C, 0x8FEC)):
                value = cpu.read(RAM+source, 2)
                self.assertEqual(cpu.read(RAM+target, 4), value << 16 | (value ^ 65535))
            saved = cpu.read(RAM+0x8FBC, 0x34)
            cpu.raw_fault(0x87)
            cpu.write(RAM+0xDA4D, 0xA5, 1)
            cpu.callback(0x87)
            self.assertEqual(cpu.read(RAM+0x8FBC, 0x34), saved)
            cpu.execute(0x55518, RECORD_WRITES)
            for a, n in RECORD_WRITES:
                self.assertEqual(cpu.read(a, n), 0x00FF if n == 2 else 0x0000FFFF)
            self.assertEqual(cpu.read(RAM+0x8F8C, 1), 0x10)
            # Resetting only the snapshot leaves older promoted faults
            # eligible. The empty-record loop does not stop after a write:
            # the highest ordinary ID wins this complete 153-record sweep.
            cpu.callback(0x87)
            self.assertEqual(cpu.read(RAM+0x8FE4, 2), 0x2092)
            self.assertEqual(cpu.read(RAM+0x8FBC, 2), 0xA55A)

    def test_misfire_snapshot_needs_aggregate_promotion_and_then_survives_ordinary_faults(self):
        for image in self.images.values():
            cpu = DiagnosticRecordMachine(image)
            cpu.raw_fault(0x84)
            cpu.callback(0x84)
            desc = cpu.descriptor(0x42)  # P0301, native priority list.
            cpu.raw_fault(0x42)
            cpu.write(RAM+0xDC06, 1, 1)
            cpu.write(RAM+0x8EC4+2*desc[1], desc[2] << 8 | (desc[2] ^ 255), 2)
            cpu.callback(0x42)
            # Individual cylinder history alone does not replace an
            # existing snapshot. Supply the separate promoted aggregate
            # and its captured source buffer, then execute actual selection.
            self.assertEqual(cpu.read(RAM+0x8FE4, 2), 0x0340)
            cpu.write(RAM+0x8F58, 0x02FD, 2)  # ID4A, descriptor byte14/mask02.
            cpu.write(RAM+0xD83B, 1, 1)  # Cylinder bitmap: bank's first bit.
            for a in range(0xD83E, 0xD851):
                cpu.write(RAM+a, a & 255, 1)
            cpu.write(RAM+0xD81A, 0x1234, 2)
            cpu.write(RAM+0xD81C, 0x5678, 2)
            cpu.original_r[4] = 0x42
            cpu.execute(0x54D60, RECORD_WRITES)
            self.assertEqual(cpu.read(RAM+0x8FE4, 4), 0x0301FCFE)
            self.assertIn(0x551F4, cpu.entered)
            saved = cpu.read(RAM+0x8FBC, 0x34)
            cpu.raw_fault(0x87)
            cpu.callback(0x87)
            self.assertEqual(cpu.read(RAM+0x8FBC, 0x34), saved)

    def test_disabled_p0111_is_not_reportable_and_periodic_mask_removes_retained_bit(self):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        for image in self.images.values():
            self.assertEqual(stock[0x5BDA8], 0)
            self.assertEqual(image[0x5BDA8], 0)
            self.assertEqual(image[0x5C480:0x5C484], bytes.fromhex('00160400'))
            for entry in (0x50FF6, 0x5108C):
                cpu = EnableMachine(image)
                cpu.write(RAM+0xDE08, 0, 1)
                cpu.original_r[4] = 0x54
                cpu.invoke(entry, set())
                self.assertNotIn(RAM+0x8FA0, cpu.reads)
            cpu = EnableMachine(image)
            for i in range(54):
                value = 4 if i == 0x16 else 0
                cpu.write(MASK_BASE+i, 0, 1)
                for base in RAW_BASES:
                    cpu.write(base+i, value, 1)
                for base in PROTECTED_BASES:
                    cpu.write(base+2*i, value << 8 | (value ^ 255), 2)
            cpu.invoke(0x511F8, WRITE_SET)
            self.assertEqual(cpu.read(MASK_BASE+0x16, 1), 3)
            for base in RAW_BASES:
                self.assertEqual(cpu.read(base+0x16, 1), 0)
            for base in PROTECTED_BASES:
                self.assertEqual(cpu.read(base+0x2C, 2), 0x00FF)
            target = DiagnosticRecordMachine(image)
            target.write(RAM+0x8E84, 0x04FB, 2)
            target.fallback_status()
            self.assertEqual(target.read(RAM+0xD26C, 1) & 0x20, 0x20)
            target.write(RAM+0x8E84, cpu.read(RAM+0x8E84, 2), 2)
            target.fallback_status()
            self.assertEqual(target.read(RAM+0xD26C, 1) & 0x20, 0)

    def test_history_age_reset_is_mode_sensitive_and_uses_distinct_exclusion_masks(self):
        for image, mode, index, mask, prior_age in product(self.images.values(),
                (0, 0xFF, 0xA5), (0, 0x11, 0x13, 0x2C, 0x2E), (1, 0x80), (2, 3)):
            cpu = DiagnosticRecordMachine(image)
            cpu.write(RAM+0x8FA0, mode << 8 | (mode ^ 255), 2)
            cpu.write(RAM+0xDAB6+index, mask, 1)
            cpu.write(RAM+0x8F30+2*index, mask << 8 | (mask ^ 255), 2)
            for a in (0x8FB8, 0x8FBA):
                cpu.write(RAM+a, prior_age << 8 | (prior_age ^ 255), 2)
            cpu.execute(0x5560C, AGE_WRITES)
            cpu.execute(0x556F6, AGE_WRITES)
            keep = {0x11: 0x3F, 0x13: 0x80, 0x2C: 0xBF}.get(index, 0xFF)
            self.assertEqual(cpu.read(RAM+0x8FB8, 1), 0 if mode == 0 and mask & keep else prior_age)
            self.assertEqual(cpu.read(RAM+0x8FBA, 1), 0 if mode == 0 else prior_age)


if __name__ == '__main__':
    unittest.main(verbosity=2)
