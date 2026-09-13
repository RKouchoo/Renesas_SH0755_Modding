#!/usr/bin/env python3
"""Execute startup RAM self-test and the complete retained-bank reset/validation.

All CPU callees run native instructions, including all 58 cold initializers
and all 18 top-level validators. DMA completion is an explicit hardware event;
RAM read faults are imposed at the self-test readback instruction. This is not
an EEPROM-transport, ordinary-task-startup, electrical or deadline simulation.
"""
import _test_paths
from itertools import product
import unittest

from test_avcs_diagnostic_process_flow import AVCSDiagnosticMachine, RAM, ROOT
from test_primary_fueling_execution import bits
from test_runtime_rom_checksum_execution import before_pump_scaling

HEADER, RESET, RAM_RESULT = (RAM+a for a in (0x8000, 0xB134, 0xB135))
PROTECTED_START, PROTECTED_END = RAM+0x8000, RAM+0x9300
WORK_START, WORK_END = RAM+0x9300, RAM+0xDFFC
DMAOR, SAR0, DAR0, TCR0, CHCR0 = (RAM+a for a in
                                (0xECB0, 0xECC0, 0xECC4, 0xECC8, 0xECCC))
DMA_WRITES = {(DMAOR, 2), (CHCR0+2, 2)} | {
    (a, 4) for a in (SAR0, DAR0, TCR0, CHCR0)}
BANK_WRITES = {(a, n) for a in range(PROTECTED_START, WORK_END)
               for n in (1, 2, 4) if a+n <= WORK_END}
SELF_TEST_WRITES = {(a, 4) for a in range(RAM+0x6000, RAM+0x8000, 4)} | {
    (a, 4) for a in range(WORK_START, WORK_END, 4)} | DMA_WRITES | {
    (RAM_RESULT, 1), (RAM+0xF738, 2)}
RESET_WORK_WRITES = {(RAM+a, 1) for a in (0xB134, 0xB13D, 0xB13E)}
PATCH_CANARIES = (0xAE60, 0xAE64, 0xAE68, 0xAE6C, 0xAE70, 0xAE74,
                  0xAE8C, 0xAE90, 0xAE9C, 0xAEA0, 0xC85C, 0xC860)
LEARNED = ((0x803C, .125), (0x81D0, .125), (0x8264, 37),
           (0x831C, -2.5), (0x851C, .625), (0x8E04, 700))


class StartupRetainedMachine(AVCSDiagnosticMachine):
    STACK = RAM+0x7304
    INSTRUCTION_LIMIT = 1_500_000

    def __init__(self, image):
        self.native_targets = set()
        self.visited = set()
        self.record_checks = []
        self.hardware_writes = []
        self.dma_events = []
        self.ram_read_fault = None
        super().__init__(image)
        # Explicit memory contents before the chosen startup entry. Tests can
        # replace these with canaries; no vehicle retention state is inferred.
        for a in range(RAM+0x6000, RAM+0xE000):
            self.write(a, 0, 1)
        self.sr = 0xF0
        self.write(RAM+0xF738, 0xA55A, 2)
        self.write(DMAOR, 0xA5A6, 2)
        self.native_targets.clear()
        self.visited.clear()
        self.record_checks.clear()

    def call_lookup(self, target):
        # No successful getter, lookup, initializer or validator stand-ins.
        assert 0 <= target < len(self.image)-1 and target % 2 == 0, hex(target)
        self.native_targets.add(target)
        self.entered.append(target)
        return_pc = self.pr
        self.pc = target
        while self.pc != return_pc:
            self.step()

    def step(self, in_delay=False):
        assert self.pc != 0x3F84, 'Kernel dispatch is outside this startup fixture'
        self.visited.add(self.pc)
        if self.pc == 0x4963A:
            self.record_checks.append(self.r[4])
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF0FF in (0x4028, 0x4029):  # SHLL16/SHLR16, T unchanged.
            self.r[n] = ((self.r[n] << 16) & 0xFFFFFFFF
                         if op & 255 == 0x28 else self.r[n] >> 16)
        elif op & 0xF00F == 0x200E:  # MULU.W Rm,Rn -> MACL.
            self.macl = (self.r[n] & 65535) * (self.r[m] & 65535)
        elif op & 0xF00F == 0x2006 and n != 15:  # MOV.L Rm,@-Rn.
            value = self.r[m]
            self.r[n] = (self.r[n]-4) & 0xFFFFFFFF
            self.write(self.r[n], value, 4, record=True)
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def load(self, address, size):
        value = super().load(address, size)
        # F95E MOV.L @R4,R2 is decoded before advancing PC by this parent.
        if address == self.ram_read_fault and size == 4 and self.pc == 0xF95E:
            return value ^ 1
        return value

    def write(self, address, value, size=4, record=False):
        super().write(address, value, size, record)
        if record and address == CHCR0 and size == 4 and value & 1:
            assert value == 0x001F0129
            source, destination, count = (self.read(a, 4) for a in (SAR0, DAR0, TCR0))
            assert (source, destination, count) == (WORK_START, WORK_START, 0x133F)
            assert self.read(source, 4) == 0
            self.dma_events.append((source, destination, count, value))
            # Explicit fixed-source, incrementing-destination longword DMA
            # completion. Separate bookkeeping avoids calling DMA CPU stores.
            for a in range(destination, destination+4*count, 4):
                super().write(a, self.read(source, 4), 4)
                self.hardware_writes.append((a, 4))
            super().write(DAR0, destination+4*count, 4)
            super().write(TCR0, 0, 4)
            super().write(CHCR0, value | 2, 4)

    def bank_entry(self, entry):
        self.execute(entry, BANK_WRITES)

    def reset_work(self):
        self.execute(0xF6D6, RESET_WORK_WRITES)

    def cold_bank(self):
        self.reset_work()
        self.bank_entry(0xF710)
        self.bank_entry(0xF754)

    def protected_bytes(self):
        return bytes(self.memory[a] for a in range(PROTECTED_START, PROTECTED_END))

    def put_record(self, address, value):
        saved_r, saved_fr = self.original_r[4], self.original_fr[4]
        self.original_r[4], self.original_fr[4] = address, bits(value)
        self.execute(0x49530, {(address, 4), (address+4, 2), (address+6, 2)})
        self.original_r[4], self.original_fr[4] = saved_r, saved_fr


class StartupRetainedProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        cls.validators = [int.from_bytes(cls.stock[a:a+4], 'big')
                          for a in range(0xFE8C, 0xFED4, 4)]
        cls.initializers = [int.from_bytes(cls.stock[a:a+4], 'big')
                            for a in range(0x108BC, 0x109A4, 4)]
        assert len(cls.validators) == 18 and len(cls.initializers) == 58
        for image in cls.images.values():
            for a, b in ((0x4C7C, 0x4C86), (0xF5F0, 0xF5FE),
                         (0xF6D6, 0xF774), (0xF820, 0xF97C),
                         (0xF9F0, 0xFA10), (0xFD5C, 0xFEF4),
                         (0x10690, 0x107EE), (0x108BC, 0x109A4),
                         (0x30A84, 0x30AB4)):
                assert image[a:b] == cls.stock[a:b], hex(a)
            for pointer, target in ((0x67DC, 0xF710), (0x6620, 0xF754),
                                    (0x6624, 0xFEF4), (0x66A8, 0xFD5C),
                                    (0x66AC, 0x10690), (0x66B0, 0xB536)):
                assert int.from_bytes(image[pointer:pointer+4], 'big') == target

    def test_ram_self_test_restores_low_ram_preserves_retained_bank_and_clears_patch_work(self):
        for image in self.images.values():
            cpu = StartupRetainedMachine(image)
            for a in range(RAM+0x6000, RAM+0xE000):
                cpu.write(a, ((a * 37) ^ (a >> 8)) & 255, 1)
            protected = cpu.protected_bytes()
            upper_word = cpu.read(WORK_END, 4)
            low = {a: cpu.read(a, 1) for a in range(RAM+0x6000, RAM+0x8000)
                   if not cpu.STACK-0x100 <= a < cpu.STACK}
            cpu.execute(0xF820, SELF_TEST_WRITES)
            self.assertEqual(cpu.protected_bytes(), protected)
            self.assertEqual(cpu.read(WORK_END, 4), upper_word)
            self.assertTrue(all(cpu.read(a, 1) == v for a, v in low.items()))
            self.assertTrue(all(cpu.read(a, 1) == 0 for a in range(WORK_START, WORK_END)))
            self.assertEqual(cpu.dma_events, [(WORK_START, WORK_START, 0x133F, 0x001F0129)])
            self.assertEqual(cpu.hardware_writes[0], (WORK_START, 4))
            self.assertEqual(cpu.hardware_writes[-1], (WORK_END-4, 4))
            self.assertEqual(cpu.read(CHCR0, 4), 0x001F0128)
            self.assertEqual(cpu.read(DMAOR, 2), 0xA5A1)
            self.assertEqual(cpu.read(RAM+0xF738, 2), 0x255A)
            self.assertTrue({0x4C7C, 0x4C82, 0xF950, 0xD6F0, 0x2410} <= cpu.visited)

    def test_ram_readback_failure_selects_native_result_and_never_tests_protected_bank(self):
        for image, failed in product(self.images.values(),
                                     (WORK_START, WORK_END-4, RAM+0x6000, RAM+0x7FFC)):
            cpu = StartupRetainedMachine(image)
            cpu.write(HEADER, 0xAA55, 2)
            before = cpu.protected_bytes()
            cpu.ram_read_fault = failed
            cpu.execute(0xF820, SELF_TEST_WRITES)
            self.assertEqual(cpu.read(RAM_RESULT, 1), 1 if failed >= WORK_START else 2)
            self.assertEqual(cpu.protected_bytes(), before)
            self.assertEqual(0x4C7C in cpu.visited, failed < WORK_START)
            self.assertEqual(len(cpu.dma_events), 1)
            self.assertTrue(all(cpu.read(RAM+a, 4) == 0 for a in PATCH_CANARIES))

    def test_cold_reset_invalidates_before_all_58_initializers_and_commits_last(self):
        for name, image in self.images.items():
            cpu = StartupRetainedMachine(image)
            for i, a in enumerate(PATCH_CANARIES):
                cpu.write(RAM+a, 0xA55A0000+i, 4)
            cpu.reset_work()
            cpu.bank_entry(0xF710)
            self.assertEqual(cpu.read(HEADER, 2), 0x55AA)
            self.assertEqual(cpu.read(RESET, 1), 1)
            self.assertNotIn(0xFD5C, cpu.visited)
            cpu.visited.clear()
            cpu.bank_entry(0xF754)
            self.assertTrue(set(self.initializers) <= cpu.visited)
            self.assertEqual(cpu.writes[-1], (HEADER, 2))
            self.assertEqual(cpu.read(HEADER, 2), 0xAA55)
            self.assertEqual(cpu.get_float(RAM+0x851C), .5 if name == 'main' else 1)
            self.assertEqual(cpu.get_float(RAM+0x8264), 40)
            self.assertEqual(cpu.read(RAM+0x8274, 1) & 3, 2)
            self.assertEqual(cpu.get_float(RAM+0x8E04), 760)
            for i, a in enumerate(PATCH_CANARIES):
                self.assertEqual(cpu.read(RAM+a, 4), 0xA55A0000+i, hex(a))

    def test_valid_warm_bank_executes_all_18_validators_and_retains_learned_values(self):
        for image in self.images.values():
            cpu = StartupRetainedMachine(image)
            cpu.cold_bank()
            for a, value in LEARNED:
                cpu.put_record(RAM+a, value)
            before = cpu.protected_bytes()
            cpu.reset_work()
            cpu.visited.clear()
            cpu.record_checks.clear()
            cpu.bank_entry(0xF710)
            self.assertTrue(set(self.validators) <= cpu.visited)
            self.assertEqual(cpu.read(RESET, 1), 0)
            self.assertEqual(cpu.protected_bytes(), before)
            self.assertTrue({RAM+a for a, _ in LEARNED} <= set(cpu.record_checks))
            cpu.visited.clear()
            cpu.bank_entry(0xF754)
            self.assertNotIn(0x10690, cpu.visited)
            self.assertEqual(cpu.protected_bytes(), before)

    def test_single_checksum_copy_repairs_in_place_without_global_reset(self):
        for image, (a, value), copy in product(self.images.values(), LEARNED, (4, 6)):
            cpu = StartupRetainedMachine(image)
            cpu.cold_bank()
            cpu.put_record(RAM+a, value)
            expected = cpu.protected_bytes()
            old = cpu.read(RAM+a+copy, 2)
            cpu.write(RAM+a+copy, old ^ 1, 2)
            cpu.reset_work()
            cpu.bank_entry(0xF710)
            self.assertEqual(cpu.read(RESET, 1), 0, hex(a))
            self.assertEqual(cpu.protected_bytes(), expected)

    def test_unrecoverable_record_in_any_tested_family_requests_entire_bank_reset(self):
        for name, image in self.images.items():
            for broken, _ in LEARNED:
                cpu = StartupRetainedMachine(image)
                cpu.cold_bank()
                for a, value in LEARNED:
                    cpu.put_record(RAM+a, value)
                for offset, mask in ((4, 1), (6, 2)):
                    old = cpu.read(RAM+broken+offset, 2)
                    cpu.write(RAM+broken+offset, old ^ mask, 2)
                cpu.reset_work()
                cpu.bank_entry(0xF710)
                self.assertEqual(cpu.read(RESET, 1), 1, hex(broken))
                self.assertEqual(cpu.read(HEADER, 2), 0x55AA)
                cpu.visited.clear()
                cpu.bank_entry(0xF754)
                self.assertTrue(set(self.initializers) <= cpu.visited)
                expected = (0, 0, 40, 0, .5 if name == 'main' else 1, 760)
                self.assertEqual(tuple(cpu.get_float(RAM+a) for a, _ in LEARNED), expected)
                cpu.reset_work()
                cpu.bank_entry(0xF710)
                self.assertEqual(cpu.read(RESET, 1), 0)

    def test_diagnostic_sentinel_and_explicit_invalidation_reach_native_reset_and_link_flag(self):
        for image in self.images.values():
            cpu = StartupRetainedMachine(image)
            cpu.cold_bank()
            valid = cpu.protected_bytes()
            for marker, mode in product((0, 0x55AA, 0xAA55), (0, 0xA5, 255)):
                for i, byte in enumerate(valid):
                    cpu.write(PROTECTED_START+i, byte, 1)
                cpu.write(HEADER, marker, 2)
                cpu.write(RAM+0x8260, mode << 8 | (mode ^ 255), 2)
                cpu.write(RAM+0xC6F6, 0xAA, 1)
                cpu.execute(0x30A84, {(RAM+0xC6F6, 1)})
                invalid = marker != 0xAA55 or mode == 0xA5
                self.assertEqual(cpu.read(RAM+0xC6F6, 1), 0xAA | int(invalid))
                cpu.reset_work()
                cpu.bank_entry(0xF710)
                self.assertEqual(cpu.read(RESET, 1), int(invalid))
            cpu.bank_entry(0xF5F6)
            self.assertEqual(cpu.read(HEADER, 2), 0x55AA)
            self.assertEqual(set(cpu.writes), {(HEADER, 2)})


if __name__ == '__main__':
    unittest.main(verbosity=2)
