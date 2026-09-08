#!/usr/bin/env python3
"""Native execution tests for the unintegrated, in-memory SD repair.

Native converter, SD lookups, fault publication, retained cut composition and
injector scheduler execute ROM instructions. IRQ arbitration/body and hardware
enqueue/cancel devices remain explicit test boundaries. These tests establish
neither sensor accuracy, real timing deadlines nor the vehicle's stall cause.
"""
import struct
import unittest

import prototype_sd_fault_repair as p
from audit_map_intercept import MapConversionMachine
from audit_fpu_usage import NativeSDMachine
from test_primary_fueling_execution import bits, number, signed
from test_cut_interrupt_execution import InterruptMachine, KERNEL_WRITES
from test_injector_scheduler_execution import (
    CUT_WRITES, SCHEDULER_WRITES,
)
from test_wideband_fuel_guard_execution import OTHER_CUTS, AGGREGATOR, AGGREGATED_FLAG

WRITES = p.AIR_WRITES | p.STATE_WRITES | p.CUT_WRITES


def initialize_state(cpu, rpm=1500):
    for address, size in p.STATE_WRITES:
        cpu.write(address, 0, size)
    cpu.write(p.ADC, 16000, 2)
    cpu.put_float(p.sd.IAT_ADDR, 25)
    cpu.write(p.sd.AVLS_COMMITTED_MODE_ADDR, 1, 1)
    cpu.original_fr[15] = bits(rpm)
    cpu.put_float(p.boost.RPM_ADDR, rpm)


class FaultMachine(MapConversionMachine):
    LOOKUPS = MapConversionMachine.LOOKUPS | NativeSDMachine.LOOKUPS | {
        p.PUBLISHER, p.boost.TASK_LOCK, p.boost.TASK_UNLOCK,
        p.safety.LEAN_CUT_WRAPPER_ADDR, p.boost.REVWRAP_ADDR,
        p.boost.REVLIMITER, 0x24FC, 0x1A256,
        0x46EE0, 0x46EEE, 0x46F02, 0x46F16, 0x46F2A, 0x46F3E,
    }

    def __init__(self, image, rpm=1500):
        super().__init__(image)
        initialize_state(self, rpm)

    def calculate(self):
        self.trace.clear()
        self.invoke(p.WRAPPER, WRITES)
        value = self.get_float(p.sd.FINAL_MASS_AIRFLOW_ADDR)
        assert all(self.get_float(a) == value for a, _ in p.AIR_WRITES)
        assert not self.reads[p.sd.FAILSAFE_AIRFLOW_ADDR]
        return value

    def composed_cut(self):
        self.trace.clear()
        self.invoke(p.CUT_WRAPPER, CUT_WRITES)
        return self.read(p.boost.FUELCUT_INHIBIT_WORD, 2)


class FaultInterruptMachine(InterruptMachine):
    """Reuse the native IRQ/kernel fixture, adding native float LUT execution."""
    def __init__(self, image, rpm=1500):
        super().__init__(image)
        initialize_state(self, rpm)

    def call_lookup(self, target):
        if target in NativeSDMachine.LOOKUPS | {
                p.PUBLISHER, p.safety.LEAN_CUT_WRAPPER_ADDR, p.boost.TASK_UNLOCK}:
            self.entered.append(target)
            self.subroutine(target)
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x200F:  # MULS.W, native lookup helper.
            self.macl = (signed(self.r[n] & 65535, 16) *
                         signed(self.r[m] & 65535, 16)) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x4009:  # SHLR2.
            self.r[n] >>= 2
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        self.visited.add(pc)
        assert self.instructions < self.INSTRUCTION_LIMIT


class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = p.SOURCE.read_bytes()
        cls.image, cls.blobs = p.build_experiment(cls.source)

    def test_normal_domain_is_bit_identical_with_native_lookups(self):
        for rpm in (250, 800, 1500, 3200, 4500, 7500):
            for pressure in (100, 150, 315, 760, 1100, 1600):
                for iat, mode in ((-50, 1), (25, 1), (150, 3)):
                    with self.subTest(rpm=rpm, pressure=pressure, iat=iat, mode=mode):
                        old = NativeSDMachine(self.source, rpm, pressure, iat, mode)
                        old.invoke(p.sd.WRAPPER_ADDR, p.AIR_WRITES)
                        new = FaultMachine(self.image, rpm)
                        new.put_float(p.sd.MAP_ADDR, pressure)
                        new.put_float(p.sd.IAT_ADDR, iat)
                        new.write(p.sd.AVLS_COMMITTED_MODE_ADDR, mode, 1)
                        self.assertEqual(bits(new.calculate()), bits(old.get_float(p.sd.FINAL_MASS_AIRFLOW_ADDR)))
                        self.assertEqual(new.read(p.FAULT_REASON, 1), 0)
                        self.assertEqual(new.read(p.boost.FUELCUT_INHIBIT_WORD, 2), 0)

    def test_every_accepted_adc_code_below_first_ve_knot_is_continuous(self):
        cpu = FaultMachine(self.image)
        first = cpu.read(p.ADC_LOW, 2)
        previous = 0
        count = 0
        reference = NativeSDMachine(self.source, 1500, 150, 25, 1)
        reference.invoke(p.sd.WRAPPER_ADDR, p.AIR_WRITES)
        edge_flow = reference.get_float(p.sd.FINAL_MASS_AIRFLOW_ADDR)
        for raw in range(first, 65536):
            pressure = cpu.convert(raw)
            if pressure >= cpu.get_float(p.sd.MAP_AXIS_ADDR):
                break
            self.assertEqual(cpu.classify(), 0)
            flow = cpu.calculate()
            self.assertGreater(flow, previous)
            self.assertEqual(cpu.read(p.FAULT_REASON, 1), 0)
            # Same VE edge with actual pressure in the product, not a pressure floor.
            self.assertAlmostEqual(flow, edge_flow*pressure/150, delta=3e-6)
            previous = flow
            count += 1
        self.assertGreater(count, 1900)

    def test_old_100_mmhg_discontinuity_is_removed(self):
        values = []
        for encoded in (bits(100)-1, bits(100), bits(100)+1):
            cpu = FaultMachine(self.image)
            cpu.write(p.sd.MAP_ADDR, encoded)
            values.append(cpu.calculate())
            self.assertEqual(cpu.read(p.FAULT_REASON, 1), 0)
        self.assertLess(max(values)-min(values), 2e-6)
        old = NativeSDMachine(self.source, 1500, number(bits(100)-1), 25, 1)
        old.invoke(p.sd.WRAPPER_ADDR, p.AIR_WRITES)
        self.assertEqual(old.get_float(p.sd.FINAL_MASS_AIRFLOW_ADDR), 500)

    def test_electrical_and_numeric_faults_publish_both_cut_interfaces(self):
        cases = [(p.ADC, 0xF5B, 2, 2), (p.ADC, 0xFBF5, 2, 3),
                 (p.sd.MAP_ADDR, bits(0), 4, 4),
                 (p.sd.MAP_ADDR, bits(-1), 4, 4),
                 (p.sd.MAP_ADDR, bits(float('nan')), 4, 4),
                 (p.sd.MAP_ADDR, bits(float('inf')), 4, 4),
                 (p.sd.MAP_ADDR, bits(1601), 4, 4),
                 (p.sd.IAT_ADDR, bits(-51), 4, 5),
                 (p.sd.IAT_ADDR, bits(151), 4, 5),
                 (p.sd.IAT_ADDR, bits(float('nan')), 4, 5)]
        for address, value, size, reason in cases:
            with self.subTest(address=hex(address), value=value):
                cpu = FaultMachine(self.image)
                cpu.write(p.boost.FUELCUT_FLAG, 0x35, 1)
                cpu.write(address, value, size)
                self.assertEqual(cpu.calculate(), 0)
                self.assertEqual(cpu.read(p.FAULT_REASON, 1), reason)
                self.assertEqual(cpu.read(p.FAULT_COUNT, 2), 1)
                self.assertEqual(cpu.read(p.FAULT_ADC, 2), cpu.read(p.ADC, 2))
                self.assertEqual(cpu.read(p.boost.FUELCUT_FLAG, 1), 0xB5)
                self.assertEqual(cpu.read(p.boost.FUELCUT_INHIBIT_WORD, 2), 0xFFFF)

    def test_invalid_calibration_and_lookup_results_are_distinguished(self):
        cases = [(p.sd.GLOBAL_MULTIPLIER_ADDR, 0, 6),
                 (p.sd.DISPLACEMENT_ADDR, -1, 6),
                 (p.sd.MAX_AIRFLOW_ADDR, float('inf'), 6),
                 (p.sd.AIRFLOW_CONSTANT_ADDR, float('nan'), 6),
                 (p.sd.MAP_AXIS_ADDR, 0, 6),
                 (p.sd.MAP_MAX_ADDR, float('nan'), 4),
                 (p.sd.IAT_MIN_ADDR, float('nan'), 5),
                 (p.sd.RPM_MAX_ADDR, float('nan'), 1)]
        for address, value, reason in cases:
            image = bytearray(self.image)
            struct.pack_into('>f', image, address, value)
            cpu = FaultMachine(bytes(image))
            self.assertEqual(cpu.calculate(), 0)
            self.assertEqual(cpu.read(p.FAULT_REASON, 1), reason)
        for start, end, reason in ((p.sd.LOW_VE_DATA_ADDR, p.sd.HIGH_VE_DATA_ADDR, 7),
                (p.sd.IAT_DATA_ADDR, p.sd.FINITE_FLOAT_MAX_ADDR, 8)):
            image = bytearray(self.image)
            for address in range(start, end, 4):
                struct.pack_into('>f', image, address, float('nan'))
            cpu = FaultMachine(bytes(image))
            self.assertEqual(cpu.calculate(), 0)
            self.assertEqual(cpu.read(p.FAULT_REASON, 1), reason)
        image = bytearray(self.image)
        for address in (p.sd.DISPLACEMENT_ADDR, p.sd.GLOBAL_MULTIPLIER_ADDR):
            struct.pack_into('>f', image, address, 1e-35)
        cpu = FaultMachine(bytes(image))
        self.assertEqual(cpu.calculate(), 0)
        self.assertEqual(cpu.read(p.FAULT_REASON, 1), 9)

    def test_stopped_rpm_does_not_create_a_fault_or_release_a_latch(self):
        cpu = FaultMachine(self.image, rpm=0)
        cpu.put_float(p.sd.MAP_ADDR, float('nan'))
        cpu.write(p.ADC, 0, 2)
        self.assertEqual(cpu.calculate(), 0)
        self.assertEqual(cpu.read(p.FAULT_REASON, 1), 0)
        self.assertFalse(cpu.reads[p.ADC])
        for rpm in (-1, 7501, float('nan'), float('inf')):
            cpu = FaultMachine(self.image, rpm=rpm)
            self.assertEqual(cpu.calculate(), 0)
            self.assertEqual(cpu.read(p.FAULT_REASON, 1), 1)
        cpu.original_fr[15] = bits(0)
        self.assertEqual(cpu.calculate(), 0)
        self.assertEqual(cpu.read(p.FAULT_REASON, 1), 1)
        self.assertEqual(cpu.composed_cut(), 0xFFFF)

    def test_first_fault_latches_count_saturates_and_valid_input_stays_inhibited(self):
        cpu = FaultMachine(self.image)
        cpu.write(p.ADC, 0xF5B, 2)
        self.assertEqual(cpu.calculate(), 0)
        cpu.write(p.ADC, 0xFBF5, 2)
        self.assertEqual(cpu.calculate(), 0)
        self.assertEqual(cpu.read(p.FAULT_COUNT, 2), 2)
        self.assertEqual(cpu.read(p.FAULT_REASON, 1), 2)
        self.assertEqual(cpu.read(p.FAULT_ADC, 2), 0xF5B)
        cpu.write(p.FAULT_COUNT, 65535, 2)
        self.assertEqual(cpu.calculate(), 0)
        self.assertEqual(cpu.read(p.FAULT_COUNT, 2), 65535)
        cpu.write(p.ADC, 16000, 2)
        self.assertEqual(cpu.calculate(), 0)
        self.assertEqual(cpu.read(p.FAULT_COUNT, 2), 65535)
        # Existing initializer clears the two entire reclaimed four-byte slots.
        cpu.invoke(p.safety.LEAN_STATE_INITIALIZE_ADDR,
                   {(p.safety.LEAN_COUNTER_RAM, 4), (p.safety.LEAN_STATE_RAM, 4)})
        self.assertEqual(cpu.read(p.FAULT_REASON, 1), 0)
        self.assertEqual(cpu.read(p.FAULT_COUNT, 2), 0)
        self.assertEqual(cpu.read(p.FAULT_ADC, 2), 0)
        self.assertGreater(cpu.calculate(), 0)

    def test_cut_composition_preserves_other_cut_reasons_and_all_entry_masks(self):
        for mask in range(0, 256, 16):
            for fault, pressure, rpm, expected in ((0, 315, 1500, 0),
                    (1, 315, 1500, 65535), (0, 1200, 1500, 65535),
                    (0, 315, 7200, 65535), (1, 1200, 7200, 65535)):
                cpu = FaultMachine(self.image, rpm)
                cpu.sr = mask
                cpu.write(p.FAULT_REASON, fault, 1)
                cpu.put_float(p.sd.MAP_ADDR, pressure)
                self.assertEqual(cpu.composed_cut(), expected)
                self.assertEqual(cpu.sr & 0xF0, mask)
        # The later native aggregate is a separate publication stage. A raw
        # source bit need not already appear in this limiter's B744 result.
        for address, mask in OTHER_CUTS:
            cpu = FaultMachine(self.image)
            cpu.write(address, mask, 1)
            cpu.composed_cut()
            self.assertEqual(cpu.read(address, 1), mask)
            cpu.invoke(AGGREGATOR, {(AGGREGATED_FLAG, 1)})
            self.assertTrue(cpu.read(AGGREGATED_FLAG, 1) & 128)

    def test_lean_cut_retains_its_release_rule_but_cannot_release_sd_fault(self):
        for fault in (0, 2):
            cpu = FaultMachine(self.image)
            cpu.write(p.FAULT_REASON, fault, 1)
            cpu.write(p.safety.LEAN_STATE_RAM, 3, 1)
            cpu.put_float(p.sd.MAP_ADDR, 820)
            self.assertEqual(cpu.composed_cut(), 65535)
            self.assertEqual(cpu.read(p.safety.LEAN_STATE_RAM, 1), 3)
            cpu.put_float(p.sd.MAP_ADDR, 700)
            self.assertEqual(cpu.composed_cut(), 65535 if fault else 0)
            self.assertEqual(cpu.read(p.safety.LEAN_STATE_RAM, 1), 0)
            self.assertEqual(cpu.read(p.FAULT_REASON, 1), fault)

    def test_initializer_is_reached_from_initial_activation_task_17(self):
        # Static native dispatch evidence, not an emulation of hardware reset.
        cpu = FaultMachine(self.image)
        self.assertEqual(cpu.read(0x4B00, 4), 0x4AFC)
        self.assertEqual(cpu.read(0x4B04, 2), 2)
        self.assertEqual((cpu.read(0x4AFC, 2), cpu.read(0x4AFE, 2)), (0, 17))
        self.assertEqual(cpu.read(0x499C+17*16+8, 4), 0x6328)
        for pc, pool, target in ((0x6516, 0x6624, 0xFEF4),
                                (0x1033C, 0x1055C, p.safety.LEAN_STATE_INITIALIZE_ADDR)):
            op = cpu.read(pc, 2)
            self.assertEqual(op >> 12, 0xD)
            self.assertEqual(((pc+4)&~3)+(op&255)*4, pool)
            self.assertEqual(cpu.read(pool, 4), target)
            self.assertEqual(cpu.read(pc+2, 2), 0x420B)

    def test_snapshot_lock_defers_irq_activated_task_until_all_inputs_are_read(self):
        class SnapshotCPU(FaultInterruptMachine):
            def task_payload(self):
                self.input_reads_at_dispatch = tuple(self.reads[a] for a in (
                    p.ADC, p.sd.MAP_ADDR, p.sd.IAT_ADDR))
                super().task_payload()
        cpu = SnapshotCPU(self.image)
        # After MOV.W ADC,@R8, before the MAP and IAT loads.
        site = self.blobs['airflow']['labels']['running']+10
        self.assertEqual(cpu.read(site, 2), 0x6811)
        cpu.inject_at = site
        cpu.invoke(p.WRAPPER, WRITES | SCHEDULER_WRITES | KERNEL_WRITES)
        self.assertIsNone(cpu.inject_at)
        self.assertTrue(all(cpu.input_reads_at_dispatch))
        old = NativeSDMachine(self.source, 1500, 315, 25, 1)
        old.invoke(p.sd.WRAPPER_ADDR, p.AIR_WRITES)
        self.assertEqual(cpu.read(p.sd.FINAL_MASS_AIRFLOW_ADDR, 4),
                         old.read(p.sd.FINAL_MASS_AIRFLOW_ADDR, 4))

    def test_fault_inhibits_all_six_native_scheduler_channels(self):
        cpu = FaultInterruptMachine(self.image)
        cpu.write(p.ADC, 0, 2)
        cpu.invoke(p.WRAPPER, WRITES | SCHEDULER_WRITES | KERNEL_WRITES)
        self.assertEqual(cpu.read(p.boost.FUELCUT_INHIBIT_WORD, 2), 65535)
        self.assertEqual(cpu.read(p.FAULT_REASON, 1), 2)
        for phase in range(24):
            cpu.tick(phase)
            self.assertFalse(cpu.device_calls)
        self.assertEqual(cpu.log_pulses(), (0,)*6)

    def test_irq_cannot_dispatch_through_the_stock_limiters_temporary_clear(self):
        sites = (0x1C90A, self.blobs['cut_composition']['labels']['done']-2)
        for site in sites:
            cpu = FaultInterruptMachine(self.image)
            cpu.write(p.FAULT_REASON, 2, 1)
            cpu.write(p.boost.FUELCUT_FLAG, 128, 1)
            cpu.write(p.boost.FUELCUT_INHIBIT_WORD, 65535, 2)
            cpu.inject_at = site
            cpu.invoke(p.CUT_WRAPPER, CUT_WRITES | SCHEDULER_WRITES | KERNEL_WRITES)
            self.assertIsNone(cpu.inject_at)
            self.assertTrue(cpu.task_runs)
            self.assertTrue(all(word == 65535 and flag & 128 for word, flag in cpu.task_runs))
            self.assertFalse(cpu.device_calls)
            self.assertEqual(cpu.read(p.boost.FUELCUT_INHIBIT_WORD, 2), 65535)

    def test_irq_between_fault_flag_and_word_stores_sees_completed_publication(self):
        # Actual BF6C byte store is the fourth instruction at 'publish'.
        site = self.blobs['fault_publication']['labels']['publish'] + 6
        self.assertEqual(int.from_bytes(self.image[site:site+2], 'big'), 0x2100)
        cpu = FaultInterruptMachine(self.image)
        cpu.original_r[4:6] = [2, 0xF5B]
        cpu.inject_at = site
        cpu.invoke(p.PUBLISHER, p.STATE_WRITES | p.CUT_WRITES | SCHEDULER_WRITES | KERNEL_WRITES)
        self.assertIsNone(cpu.inject_at)
        self.assertTrue(cpu.task_runs)
        self.assertTrue(all(word == 65535 and flag & 128 for word, flag in cpu.task_runs))
        self.assertFalse(cpu.device_calls)

    def test_removing_outer_lock_exposes_temporary_release_negative_control(self):
        damaged = bytearray(self.image)
        self.assertEqual(damaged[p.CUT_WRAPPER+6:p.CUT_WRAPPER+8], bytes.fromhex('e410'))
        damaged[p.CUT_WRAPPER+6:p.CUT_WRAPPER+8] = bytes.fromhex('e400')
        cpu = FaultInterruptMachine(bytes(damaged))
        cpu.write(p.FAULT_REASON, 2, 1)
        cpu.write(p.boost.FUELCUT_FLAG, 128, 1)
        cpu.write(p.boost.FUELCUT_INHIBIT_WORD, 65535, 2)
        cpu.inject_at = 0x1C90A
        cpu.invoke(p.CUT_WRAPPER, CUT_WRITES | SCHEDULER_WRITES | KERNEL_WRITES)
        self.assertIsNone(cpu.inject_at)
        self.assertTrue(any(word == 0 for word, flag in cpu.task_runs))
        self.assertTrue(cpu.device_calls)
        # A return-only check would incorrectly accept this damaged wrapper.
        self.assertEqual(cpu.read(p.boost.FUELCUT_INHIBIT_WORD, 2), 65535)

    def test_user_image_and_frozen_calibrations_are_unchanged(self):
        self.assertEqual(p.SOURCE.read_bytes(), self.source)
        for start, end in ((0x72810, 0x7281A), (0x76030, 0x76034),
                (0x76E7E, 0x76E80), (p.sd.LOAD_FILTER_ALPHA_ADDR, p.sd.LOAD_FILTER_ALPHA_ADDR+4),
                (p.sd.LOW_VE_DATA_ADDR, p.sd.DUAL_VE_END+1), (0x7FB80, 0x7FB8C)):
            self.assertEqual(self.image[start:end], self.source[start:end])


if __name__ == '__main__':
    unittest.main(verbosity=2)
