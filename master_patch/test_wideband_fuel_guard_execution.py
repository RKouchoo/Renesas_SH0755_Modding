#!/usr/bin/env python3
"""Execute the emitted wideband/guard chain and retained limiter/aggregator.

The decoder is independent of sh2_asm/sh2_disasm and the policy models.
Stock 24B24 (rev limiter), 24FC (comparison helper), and 23FC0 (cut aggregator)
execute from ROM, as do the 24BC6 reset and its 1A256 state helper. The running
path of the 22AC2 permission reset is covered. The 1C5D4 injector-inhibit tail
and its six D94C getters execute from ROM. Here 22454 is a stand-in with
poisoned scratch registers; test_primary_fueling_execution covers it and 1DD04.
This does not emulate the scheduler, interrupts, peripheral hardware, or FP
exception delivery/flags, and cannot validate controller health or an engine.
"""
from collections import Counter
from io import StringIO
from itertools import product
import math
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
for directory in (ROOT / "speed_density", ROOT / "fueling_safety", ROOT / "patch"):
    sys.path.insert(0, str(directory))

import fueling_safety_component as safety
import patch_boost as boost
import wideband_component as wideband
from test_hook_execution import Machine, bits, number, signed, f32
import sh2e_test_fpu as fpu

IMAGE = None
AGGREGATOR = 0x23FC0
INHIBIT_BUILDER = 0x1C5D4
INHIBIT_WORD = 0xFFFFB744
INHIBIT_GETTERS = (0x46EE0, 0x46EEE, 0x46F02, 0x46F16, 0x46F2A, 0x46F3E)
RPM_FLAGS = 0xFFFFBF6D
AGGREGATED_FLAG = 0xFFFFBF1C
OTHER_CUTS = ((0xFFFFBF20, 128), (0xFFFFBF70, 128), (0xFFFFBF74, 128),
              (0xFFFFBF8C, 1), (0xFFFFCE24, 1), (0xFFFFBF90, 2),
              (0xFFFFCCB9, 1), (0xFFFFBF9C, 2), (0xFFFFCF24, 128),
              (0xFFFFCFA0, 1))
WIDEBAND_OUTPUTS = (wideband.FRONT_LAMBDA_BANK1, wideband.FRONT_LAMBDA_BANK2,
                    wideband.WIDEBAND_LOG_LAMBDA_BANK1, wideband.WIDEBAND_LOG_LAMBDA_BANK2,
                    wideband.FRONT_CURRENT_BANK1, wideband.FRONT_CURRENT_BANK2,
                    wideband.FRONT_READY_METRIC_BANK1, wideband.FRONT_READY_METRIC_BANK2)


class GuardMachine(Machine):
    def __init__(self, image):
        super().__init__()
        self.image = image
        self.memory.clear()
        self.fpul = 0
        self.stock_target_flags = 0xFF
        self.entered = []
        self.write(safety.FUEL_CUT_FLAG, 0, 1)
        self.write(RPM_FLAGS, 0, 1)
        self.write(safety.LEAN_STATE_RAM, 0, 1)
        self.write(safety.LEAN_COUNTER_RAM, 0, 2)
        self.write(safety.CL_OL_STATE_FLAGS, 0, 1)
        self.write(AGGREGATED_FLAG, 0, 1)
        self.write(0xFFFFB52C, 0, 1)
        self.write(INHIBIT_WORD, 0, 2)
        for address in (0xFFFFBF21, 0xFFFFBF9D, 0xFFFFD94C):
            self.write(address, 0, 1)
        for address, _ in OTHER_CUTS:
            self.write(address, 0, 1)
        self.put_float(boost.RPM_ADDR, 1300)
        self.put_float(0xFFFFB538, 10)  # Outside secondary limiter's zero band.
        self.put_float(safety.MAP_PRESSURE, 315)
        self.put_float(safety.ATMOSPHERIC_PRESSURE, 760)
        for address in WIDEBAND_OUTPUTS:
            self.put_float(address, float("nan"))

    def read(self, address, size):
        if 0 <= address <= len(self.image) - size:
            return int.from_bytes(self.image[address:address + size], "big")
        return super().read(address, size)

    def poison_scratch(self):
        for i in range(8):
            self.r[i] = 0xB5000000 + i
        for i in range(12):
            self.fr[i] = bits(-500 - i)
        self.t = not self.t
        self.fpul = 0xA500A500

    def call_lookup(self, target):
        self.entered.append(target)
        if target == safety.PRIMARY_OL_TARGET_UPDATE:
            self.write(safety.CL_OL_STATE_FLAGS, self.stock_target_flags, 1, record=True)
            self.poison_scratch()
        else:
            assert target in (boost.REVWRAP_ADDR, boost.REVLIMITER, 0x24FC, 0x1A256, *INHIBIT_GETTERS), hex(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()

    def step(self, in_delay=False):
        pc = self.pc
        if pc == INHIBIT_BUILDER:
            self.entered.append(pc)
        op = self.read(pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        self.pc += 2
        handled = True
        if op & 0xF000 == 0x9000:
            self.r[n] = signed(self.load(pc + 4 + (op & 255) * 2, 2), 16) & 0xFFFFFFFF
        elif op & 0xF000 == 0xE000:
            self.r[n] = signed(op & 255, 8) & 0xFFFFFFFF
        elif op & 0xF000 == 0x7000:
            self.r[n] = (self.r[n] + signed(op & 255, 8)) & 0xFFFFFFFF
            if n == 15:
                self.min_sp = min(self.min_sp, self.r[n])
        elif op & 0xF00F == 0x6001:
            self.r[n] = signed(self.load(self.r[m], 2), 16) & 0xFFFFFFFF
        elif op & 0xF00F == 0x6006:
            address = self.r[m]
            self.r[n] = self.load(address, 4)
            if n != m:
                self.r[m] = (address + 4) & 0xFFFFFFFF
        elif op & 0xF00F == 0x600C:
            self.r[n] = self.r[m] & 255
        elif op & 0xF00F == 0x600D:
            self.r[n] = self.r[m] & 65535
        elif op & 0xF00F == 0x600B:
            self.r[n] = (-self.r[m]) & 0xFFFFFFFF
        elif op & 0xF00F in (0x2000, 0x2001, 0x2002):
            self.write(self.r[n], self.r[m], 1 << (op & 15), record=True)
        elif op & 0xF00F == 0x3002:
            self.t = self.r[n] >= self.r[m]
        elif op & 0xF00F == 0x200B:
            self.r[n] |= self.r[m]
        elif op & 0xF00F == 0x2008:
            self.t = (self.r[n] & self.r[m]) == 0
        elif op & 0xFF00 == 0x8000:
            self.write(self.r[m] + (op & 15), self.r[0], 1, record=True)
        elif op & 0xFF00 == 0x8400:
            self.r[0] = signed(self.load(self.r[m] + (op & 15), 1), 8) & 0xFFFFFFFF
        elif op & 0xF00F == 0x000C:
            self.r[n] = signed(self.load((self.r[0] + self.r[m]) & 0xFFFFFFFF, 1), 8) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x0029:
            self.r[n] = int(self.t)
        elif op & 0xFF00 == 0xC800:
            self.t = (self.r[0] & (op & 255)) == 0
        elif op & 0xFF00 == 0xC900:
            self.r[0] &= op & 255
        elif op & 0xFF00 == 0xCB00:
            self.r[0] |= op & 255
        elif op & 0xF0FF == 0x405A:
            self.fpul = self.r[n]
        elif op & 0xF0FF == 0xF02D:
            self.fr[n] = fpu.rational_bits(signed(self.fpul, 32))
        elif op & 0xF0FF == 0x402B:
            assert not in_delay
            target = self.r[n]
            self.step(in_delay=True)
            self.pc = target
        elif op & 0xFF00 in (0x8D00, 0x8F00):
            assert not in_delay
            taken = self.t == ((op & 0xFF00) == 0x8D00)
            self.step(in_delay=True)
            if taken:
                self.pc = pc + 4 + signed(op & 255, 8) * 2
        else:
            handled = False
        if handled:
            self.instructions += 1
            assert self.instructions < 2000
        else:
            self.pc = pc
            super().step(in_delay)

    def invoke(self, entry, allowed_writes):
        self.r = self.original_r.copy()
        self.fr = self.original_fr.copy()
        self.pr = self.STOP
        self.pc = entry
        self.instructions = 0
        self.min_sp = self.STACK
        self.writes.clear()
        self.reads.clear()
        self.entered.clear()
        while self.pc != self.STOP:
            self.step()
        assert self.r[15] == self.STACK and self.pr == self.STOP
        assert self.r[8:15] == self.original_r[8:15]
        assert self.fr[12:] == self.original_fr[12:]
        for address, size in self.writes:
            assert (address, size) in allowed_writes or self.min_sp <= address < self.STACK, (
                hex(entry), hex(address), size)
        return self.r[0]

    def update_wideband(self, raw):
        self.write(wideband.RAW_WIDEBAND_ADC, raw, 2)
        self.invoke(wideband.FRONT_AF_PROCESS_ENTRY, {(a, 4) for a in WIDEBAND_OUTPUTS})
        assert Counter(self.writes) == Counter((a, 4) for a in WIDEBAND_OUTPUTS)
        return tuple(self.get_float(a) for a in WIDEBAND_OUTPUTS)

    def cut_step(self):
        entry = self.read(safety.LEAN_CUT_TASK_PTR, 4)
        self.invoke(entry, {(safety.FUEL_CUT_FLAG, 1), (RPM_FLAGS, 1),
                            (safety.LEAN_STATE_RAM, 1), (safety.LEAN_COUNTER_RAM, 2), (INHIBIT_WORD, 2)})
        assert self.entered.count(boost.REVWRAP_ADDR) == 1
        assert self.entered.count(boost.REVLIMITER) == 1
        assert self.entered.count(INHIBIT_BUILDER) == 1
        return (self.read(safety.LEAN_STATE_RAM, 1), self.read(safety.LEAN_COUNTER_RAM, 2),
                bool(self.read(safety.FUEL_CUT_FLAG, 1) & 128))


class GuardExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / "master_patch/D2WD610H_master_patch.bin").read_bytes()
        stock = (ROOT / "2005 BLE MT.bin").read_bytes()
        for start, end in ((0x24B24, 0x24BFA), (0x24C0E, 0x24C34),
                           (0x24FC, 0x251A), (0x23FC0, 0x24082), (0x240B6, 0x240CE),
                           (0x1A256, 0x1A26C), (0x22AC2, 0x22B08), (0x22B0E, 0x22B38)):
            assert cls.image[start:end] == stock[start:end], f"Retained code changed at {start:#x}"

    def test_wideband_adc_range_outputs_and_both_inhibit_hooks(self):
        cpu = GuardMachine(self.image)
        # Unsigned ADC endpoints, exact validity edges, and a sweep through
        # both signed halves. Every accepted sample is compared after each
        # binary32 operation, independently of the policy model/generator.
        samples = sorted(set(range(0, 65536, 31)) | {65535, 6553, 6554, 58982, 58983, 32767, 32768})
        for raw in samples:
            actual = cpu.update_wideband(raw)
            valid = 6554 <= raw <= 58982
            if valid:
                volts = fpu.binary("mul", bits(raw), bits(5 / 65536))
                lam = number(fpu.binary("add", fpu.binary("mul", volts, bits(2 / 14.64)), bits(10 / 14.64)))
                expected = (lam, lam, lam, lam, 0, 0, 50, 50)
            else:
                expected = (1, 1, 0, 0, 0, 0, 0, 0)
            self.assertEqual(actual, expected, raw)
            for entry in (wideband.BANK1_INHIBIT_ENTRY, wideband.BANK2_INHIBIT_ENTRY):
                self.assertEqual(cpu.invoke(entry, set()), 0 if valid else 2)

    def test_wideband_fault_transitions_and_bad_transfer_constants(self):
        cpu = GuardMachine(self.image)
        for raw in (30000, 0, 30000, 65535, 30000):
            output = cpu.update_wideband(raw)
            self.assertEqual(output[-2:], (50, 50) if raw == 30000 else (0, 0))
        for address, value in ((wideband.LAMBDA_SLOPE_ADDR, math.nan),
                               (wideband.LAMBDA_SLOPE_ADDR, math.inf),
                               (wideband.LAMBDA_OFFSET_ADDR, -10),
                               (wideband.LAMBDA_OFFSET_ADDR, math.nan),
                               (wideband.VALID_MIN_VOLTS_ADDR, math.nan),
                               (wideband.VALID_MAX_VOLTS_ADDR, math.nan)):
            image = bytearray(self.image)
            struct.pack_into(">f", image, address, value)
            self.assertEqual(GuardMachine(bytes(image)).update_wideband(30000), (1, 1, 0, 0, 0, 0, 0, 0))
        for ready in (0, 35, math.nan):
            cpu.put_float(wideband.FRONT_READY_METRIC_BANK1, ready)
            self.assertEqual(cpu.invoke(wideband.BANK1_INHIBIT_ENTRY, set()), 2)

    def test_pressure_wrapper_runs_stock_first_and_changes_only_permission_bit(self):
        cpu = GuardMachine(self.image)
        for flags, (pressure, baro, force) in product(range(256), (
                (315, 760, False), (760, 760, True), (1100, 760, True),
                (math.nan, 760, True), (315, math.nan, True), (315, 299, True))):
            cpu.stock_target_flags = flags
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.put_float(safety.ATMOSPHERIC_PRESSURE, baro)
            cpu.invoke(cpu.read(safety.PRIMARY_OL_TASK_PTR, 4), {(safety.CL_OL_STATE_FLAGS, 1)})
            self.assertEqual(cpu.entered, [safety.PRIMARY_OL_TARGET_UPDATE])
            self.assertEqual(cpu.read(safety.CL_OL_STATE_FLAGS, 1), flags & 127 if force else flags)
        for enable in (0, 2, 255):
            image = bytearray(self.image)
            image[safety.PRESSURE_OL_ENABLE_ADDR] = enable
            cpu = GuardMachine(bytes(image))
            cpu.put_float(safety.MAP_PRESSURE, 1100)
            cpu.invoke(safety.PRESSURE_OL_WRAPPER_ADDR, {(safety.CL_OL_STATE_FLAGS, 1)})
            self.assertEqual(cpu.read(safety.CL_OL_STATE_FLAGS, 1), 255)

    def test_pressure_and_afr_boundaries_and_invalid_pressure_states(self):
        cpu = GuardMachine(self.image)
        margin = cpu.get_float(safety.PRESSURE_OL_MARGIN_ADDR)
        threshold = number(fpu.binary("sub", bits(760), bits(margin)))
        for pressure in (number(bits(threshold) - 1), threshold, number(bits(threshold) + 1)):
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.invoke(safety.PRESSURE_OL_WRAPPER_ADDR, {(safety.CL_OL_STATE_FLAGS, 1)})
            self.assertEqual(cpu.read(safety.CL_OL_STATE_FLAGS, 1), 255 if pressure < threshold else 127)

        arm = cpu.get_float(safety.LEAN_ARM_DELTA_ADDR)
        reset = cpu.get_float(safety.LEAN_RESET_DELTA_ADDR)
        for state, delta_limit in ((0, arm), (3, reset)):
            point = f32(760 + delta_limit)
            for pressure in (number(bits(point) - 1), point, number(bits(point) + 1)):
                cpu.put_float(safety.MAP_PRESSURE, pressure)
                cpu.write(safety.LEAN_STATE_RAM, state, 1)
                delta = number(fpu.binary("sub", bits(pressure), bits(760)))
                expected = (1, 0, False) if state == 0 and delta >= arm else (0, 0, False)
                if state == 3 and delta > reset:
                    expected = (3, 0, True)
                self.assertEqual(cpu.cut_step(), expected)

        threshold = cpu.get_float(safety.LEAN_AFR_THRESHOLD_ADDR)
        for lam in (number(bits(threshold) - 1), threshold, number(bits(threshold) + 1)):
            cpu.put_float(safety.MAP_PRESSURE, 820)
            cpu.put_float(wideband.FRONT_READY_METRIC_BANK1, 50)
            cpu.put_float(wideband.WIDEBAND_LOG_LAMBDA_BANK1, lam)
            cpu.write(safety.LEAN_STATE_RAM, 2, 1)
            cpu.write(safety.LEAN_COUNTER_RAM, 7, 2)
            self.assertEqual(cpu.cut_step(), (2, 0, False) if lam <= threshold else (3, 0, True))

        for state, (pressure, baro) in product(range(4), (
                (math.nan, 760), (99, 760), (1601, 760), (820, math.nan), (820, 299), (820, 851))):
            # Disable only added hard overboost for this test: otherwise MAP
            # 1601 correctly requests that independent cut before lean logic.
            image = bytearray(self.image)
            image[boost.OVERBOOST_ENABLE_ADDR] = 0
            cpu = GuardMachine(bytes(image))
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.put_float(safety.ATMOSPHERIC_PRESSURE, baro)
            cpu.write(safety.LEAN_STATE_RAM, state, 1)
            cpu.write(safety.LEAN_COUNTER_RAM, 7, 2)
            self.assertEqual(cpu.cut_step(), (3, 7, True) if state == 3 else (0, 0, False))

    def test_initializer_zeros_exact_reclaimed_words(self):
        cpu = GuardMachine(self.image)
        for a in range(safety.LEAN_COUNTER_RAM - 4, safety.LEAN_STATE_RAM + 8):
            cpu.write(a, 0xA5, 1)
        cpu.invoke(cpu.read(safety.LEAN_STATE_INIT_TASK_PTR, 4),
                   {(safety.LEAN_COUNTER_RAM, 4), (safety.LEAN_STATE_RAM, 4)})
        self.assertEqual(cpu.read(safety.LEAN_COUNTER_RAM, 4), 0)
        self.assertEqual(cpu.read(safety.LEAN_STATE_RAM, 4), 0)
        self.assertEqual(cpu.read(safety.LEAN_COUNTER_RAM - 4, 4), 0xA5A5A5A5)
        self.assertEqual(cpu.read(safety.LEAN_STATE_RAM + 4, 4), 0xA5A5A5A5)

    def test_lean_delay_confirmation_latch_release_and_rearm(self):
        cpu = GuardMachine(self.image)
        cpu.put_float(safety.MAP_PRESSURE, 820)
        cpu.update_wideband(30000)  # ~14.58 AFR, above the boost trip threshold.
        self.assertEqual(cpu.cut_step(), (1, 0, False))
        for count in range(1, 50):
            self.assertEqual(cpu.cut_step(), (1, count, False))
        self.assertEqual(cpu.cut_step(), (2, 0, False))
        for count in range(1, 8):
            self.assertEqual(cpu.cut_step(), (2, count, False))
        self.assertEqual(cpu.cut_step(), (3, 0, True))
        cpu.update_wideband(13108)  # ~12 AFR must not release our own cut.
        for pressure in (820, 750, math.nan):
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            self.assertEqual(cpu.cut_step(), (3, 0, True))
        cpu.put_float(safety.MAP_PRESSURE, 700)
        self.assertEqual(cpu.cut_step(), (0, 0, False))
        cpu.put_float(safety.MAP_PRESSURE, 820)
        self.assertEqual(cpu.cut_step(), (1, 0, False))

    def test_invalid_wideband_samples_cannot_clear_lean_confirmation(self):
        for ready, lam in ((0, 0), (0, 1), (50, math.nan), (50, math.inf),
                           (50, 0), (50, -1), (50, -math.inf)):
            cpu = GuardMachine(self.image)
            cpu.put_float(safety.MAP_PRESSURE, 820)
            cpu.put_float(wideband.FRONT_READY_METRIC_BANK1, ready)
            cpu.put_float(wideband.WIDEBAND_LOG_LAMBDA_BANK1, lam)
            cpu.write(safety.LEAN_STATE_RAM, 2, 1)
            cpu.write(safety.LEAN_COUNTER_RAM, 7, 2)
            with self.subTest(ready=ready, lam=lam):
                self.assertEqual(cpu.cut_step(), (3, 0, True))

    def test_actual_fault_publisher_intermediate_state_is_not_treated_as_rich(self):
        producer = GuardMachine(self.image)
        producer.put_float(safety.MAP_PRESSURE, 820)
        producer.update_wideband(30000)
        producer.write(safety.LEAN_STATE_RAM, 2, 1)
        producer.write(safety.LEAN_COUNTER_RAM, 7, 2)
        snapshot = {}
        original_write = producer.write

        def observe(address, value, size=4, record=False):
            original_write(address, value, size, record)
            if record and address == wideband.WIDEBAND_LOG_LAMBDA_BANK1 and value == 0:
                snapshot.update(producer.memory)

        producer.write = observe
        producer.update_wideband(0)
        self.assertTrue(snapshot)
        consumer = GuardMachine(self.image)
        consumer.memory = snapshot
        self.assertEqual(consumer.get_float(wideband.FRONT_READY_METRIC_BANK1), 50)
        self.assertEqual(consumer.get_float(wideband.WIDEBAND_LOG_LAMBDA_BANK1), 0)
        self.assertEqual(consumer.cut_step(), (3, 0, True))
        # This reproduces a possible observation, not measured preemption or
        # scheduler timing. Normal completed invalid publication is also safe.
        self.assertEqual(producer.get_float(wideband.FRONT_READY_METRIC_BANK1), 0)

    def test_stock_rev_cut_and_overboost_survive_every_lean_state_and_switch(self):
        for lean_enable, overboost_enable, state, rpm, pressure in product(
                (0, 1, 2), (0, 1, 2), range(4), (1300, 6800), (315, 820, 1150)):
            image = bytearray(self.image)
            image[safety.LEAN_CUT_ENABLE_ADDR] = lean_enable
            image[boost.OVERBOOST_ENABLE_ADDR] = overboost_enable
            cpu = GuardMachine(bytes(image))
            cpu.put_float(boost.RPM_ADDR, rpm)
            cpu.put_float(safety.MAP_PRESSURE, pressure)
            cpu.update_wideband(13108)
            cpu.write(safety.LEAN_STATE_RAM, state, 1)
            cpu.write(safety.FUEL_CUT_FLAG, 0x35, 1)
            _, _, cut = cpu.cut_step()
            expected = rpm >= 6800 or (overboost_enable == 1 and pressure == 1150)
            expected |= lean_enable == 1 and state == 3 and pressure >= 820
            self.assertEqual(cut, expected)
            self.assertEqual(cpu.read(INHIBIT_WORD, 2), 0xFFFF if expected else 0)
            self.assertEqual(cpu.read(safety.FUEL_CUT_FLAG, 1) & 127, 0x35)
            cpu.write(AGGREGATED_FLAG, 0x35, 1)
            cpu.invoke(AGGREGATOR, {(AGGREGATED_FLAG, 1)})
            self.assertEqual(cpu.read(AGGREGATED_FLAG, 1), 0x35 | (128 if expected else 0))

    def test_rev_hysteresis_and_other_aggregated_cuts_remain(self):
        cpu = GuardMachine(self.image)
        cpu.update_wideband(13108)
        for rpm, expected in ((6799, False), (6800, True), (6780, True), (6770, True), (6769, False)):
            cpu.put_float(boost.RPM_ADDR, rpm)
            self.assertEqual(cpu.cut_step()[-1], expected)
        for address, mask in OTHER_CUTS:
            cpu.write(address, mask, 1)
            cpu.cut_step()
            cpu.invoke(AGGREGATOR, {(AGGREGATED_FLAG, 1)})
            self.assertTrue(cpu.read(AGGREGATED_FLAG, 1) & 128)
            cpu.write(address, 0, 1)

    def test_other_stock_resets_do_not_overwrite_guards_in_running_state(self):
        cpu = GuardMachine(self.image)
        for flags in range(256):
            cpu.write(safety.FUEL_CUT_FLAG, flags, 1)
            cpu.write(RPM_FLAGS, flags, 1)
            cpu.write(0xFFFFB52C, 0, 1)
            cpu.invoke(0x24BC6, {(safety.FUEL_CUT_FLAG, 1), (RPM_FLAGS, 1), (INHIBIT_WORD, 2)})
            self.assertEqual(cpu.read(safety.FUEL_CUT_FLAG, 1), flags)
            self.assertEqual(cpu.read(RPM_FLAGS, 1), flags)
            cpu.write(safety.CL_OL_STATE_FLAGS, flags, 1)
            cpu.invoke(0x22AC2, {(safety.CL_OL_STATE_FLAGS, 1)})
            self.assertEqual(cpu.read(safety.CL_OL_STATE_FLAGS, 1), flags)
            cpu.write(0xFFFFB52C, 128, 1)
            cpu.invoke(0x24BC6, {(safety.FUEL_CUT_FLAG, 1), (RPM_FLAGS, 1), (INHIBIT_WORD, 2)})
            self.assertEqual(cpu.read(safety.FUEL_CUT_FLAG, 1), flags & 127)
            self.assertEqual(cpu.read(RPM_FLAGS, 1), flags & 63)

    def test_single_instruction_negative_controls_detect_faults(self):
        # Restoring just the old self-compare recovers the confirmed defect.
        original = bytes(self.image)
        pattern = bytes.fromhex("f018f48df045")
        start, end = safety.LEAN_CUT_WRAPPER_ADDR, safety.COMPONENT_END + 1
        self.assertEqual(original[start:end].count(pattern), 1)
        address = original.index(pattern, start, end) + 4
        mutated = bytearray(original)
        mutated[address:address + 2] = bytes.fromhex("f004")
        cpu = GuardMachine(bytes(mutated))
        cpu.put_float(safety.MAP_PRESSURE, 820)
        cpu.put_float(wideband.FRONT_READY_METRIC_BANK1, 50)
        cpu.put_float(wideband.WIDEBAND_LOG_LAMBDA_BANK1, 0)
        cpu.write(safety.LEAN_STATE_RAM, 2, 1)
        cpu.write(safety.LEAN_COUNTER_RAM, 7, 2)
        self.assertEqual(cpu.cut_step(), (2, 0, False))

        # A wrong bit operation loses a requested lean cut without breaking
        # branch decoding or call counts; the behavioral assertion catches it.
        region = original[start:end]
        self.assertEqual(region.count(bytes.fromhex("cb80")), 1)
        address = original.index(bytes.fromhex("cb80"), start, end)
        mutated = bytearray(original)
        mutated[address:address + 2] = bytes.fromhex("c980")
        cpu = GuardMachine(bytes(mutated))
        cpu.put_float(safety.MAP_PRESSURE, 820)
        cpu.write(safety.LEAN_STATE_RAM, 3, 1)
        self.assertEqual(cpu.cut_step(), (3, 0, False))

        # Removing unsigned conversion rejects otherwise valid upper-half ADC.
        start, end = wideband.WIDEBAND_UPDATE_ADDR, wideband.INHIBIT_HELPER_ADDR
        self.assertEqual(original[start:end].count(bytes.fromhex("600d")), 1)
        address = original.index(bytes.fromhex("600d"), start, end)
        mutated = bytearray(original)
        mutated[address:address + 2] = bytes.fromhex("6003")
        self.assertEqual(GuardMachine(bytes(mutated)).update_wideband(40000), (1, 1, 0, 0, 0, 0, 0, 0))
        self.assertEqual(GuardMachine(original).update_wideband(40000)[-2:], (50, 50))


def verify_execution(image):
    global IMAGE
    previous = IMAGE
    IMAGE = image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(GuardExecutionTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
    finally:
        IMAGE = previous


if __name__ == "__main__":
    if len(sys.argv) == 2 and not sys.argv[1].startswith("-"):
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
