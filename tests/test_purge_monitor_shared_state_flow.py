#!/usr/bin/env python3
"""Trace zero purge and WB readiness into the shared diagnostic workspace.

Native qualification, counters, history writers and cylinder-disable
publishers execute ROM opcodes. Other monitor prerequisites and prior
records are explicit fixtures. The whole low-RPM diagnostic parent and
asynchronous task/interrupt delivery are not simulated.
"""
import _test_paths
from itertools import product
import unittest

from test_wideband_feedback_process_flow import WidebandFeedbackMachine, RAM, ROOT
from test_cylinder_disable_process_flow import (
    CONFIGURATION, PRODUCER_WRITES, NATIVE_CALLEES)
from test_wideband_monitor_process_flow import WRITES as SPAN_WRITES
from test_wideband_fuel_guard_execution import INHIBIT_GETTERS
from test_runtime_rom_checksum_execution import before_pump_scaling

STABILITY_WRITES = {(RAM+a, 1) for a in
                    (0xD993, 0xD994, 0xD995, 0xD99D, 0xD99E, 0xD9A6, 0xD9A8)} | {
    (RAM+0xD984, 4)}
QUALIFICATION_WRITES = {(RAM+0xD94B, 1), (RAM+0xD852, 1)}
HISTORY_WRITES = {(RAM+0xD853+39*bank+cell, 1)
                  for bank in range(6) for cell in range(39)} | {
    (RAM+0xD438+156*bank+4*cell, 4)
    for bank in range(6) for cell in range(39)}
SNAPSHOT_WRITES = {(RAM+a, 4) for a in
                   (0xD96C, 0xD9B0, 0xD9B4, 0xD9B8, 0xD9BC, 0xD9C0, 0xD9C4)} | {
    (RAM+0xD9AC, 1), (RAM+0xD96A, 1)}


class PurgeMonitorMachine(WidebandFeedbackMachine):
    LOOKUPS = WidebandFeedbackMachine.LOOKUPS | NATIVE_CALLEES | set(INHIBIT_GETTERS) | {
        0x19CA4, 0x240A2, 0x3BB8A, 0x3BBC6, 0x6E5F4, 0x1C5D4, 0x2088, 0x2098,
    }

    def __init__(self, image):
        super().__init__(image)
        for a, size in (STABILITY_WRITES | QUALIFICATION_WRITES | HISTORY_WRITES |
                        SNAPSHOT_WRITES | SPAN_WRITES | PRODUCER_WRITES):
            self.write(a, 0, size)
        for a in (0xD800, 0xD80C, 0x8CE0, 0x8CE4):
            self.write(RAM+a, 0, 2)
        for a in (0xD851, 0x8CF0, 0xCD50, 0xCE28, 0xD94A, 0xBF1C, 0xB058):
            self.write(RAM+a, 0, 1)
        for a in (0xB31C, 0xB294, 0xB6D4, 0xD434, 0xD3AC,
                  0xB038, 0xB03C, 0xB044, 0xB048, 0xB050, 0xB054):
            self.put_float(RAM+a, 0)
        for ram, rom in CONFIGURATION:
            self.write(ram, image[rom], 1)
        self.write(RAM+0xCC4E, 128, 1)
        self.write(RAM+0xD94A, 128, 1)
        self.put_float(RAM+0xB3AC, 85)
        self.put_float(RAM+0xD96C, 800)
        self.put_float(RAM+0xB544, 800)
        self.write(RAM+0xD852, image[0x74CF9], 1)
        self.write(RAM+0xD800, 600, 2)  # Native pattern-enable comparison point.

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x200E:  # MULU.W Rm,Rn, unsigned low words.
            self.macl = (self.r[n] & 65535)*(self.r[m] & 65535)
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1

    def stability(self, rpm=800):
        self.put_float(RAM+0xB544, rpm)
        self.execute(0x6A618, STABILITY_WRITES)
        return tuple(self.read(RAM+a, 1) for a in (0xD993, 0xD994, 0xD995))

    def monitor(self):
        self.execute(0x6E338, QUALIFICATION_WRITES)
        self.execute(0x6DE50, SPAN_WRITES)
        self.execute(0x6E704, HISTORY_WRITES)
        return self.read(RAM+0xD94B, 1), self.read(RAM+0xD852, 1)

    def disable(self, rpm=800, phase=0):
        self.put_float(RAM+0xB544, rpm)
        self.original_r[4] = phase
        self.execute(0x6A636, PRODUCER_WRITES)
        return self.read(RAM+0xB744, 2), self.read(RAM+0xC0DC, 2)


class PurgeMonitorSharedStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x6A618, 0x6A9B8), (0x6E338, 0x6E804),
                         (0x6DE50, 0x6DF70), (0x6F4B8, 0x6FEF4),
                         (0x6DA4C, 0x6DA94), (0x6DB56, 0x6DB7C),
                         (0xD8EE, 0xD914), (0xD92C, 0xDAC0),
                         (0x5EDF0, 0x5EDFC), (0x75304, 0x75345),
                         (0x74CF5, 0x74D04), (0x74D44, 0x74D48),
                         (0x74E10, 0x74E14), (0x74E50, 0x74E70)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_zero_duty_stability_resets_on_class_change_and_holds_above_low_rpm_gate(self):
        for image in self.images:
            cpu = PurgeMonitorMachine(image)
            self.assertEqual(cpu.stability(), (1, 1, 1))
            self.assertEqual(cpu.stability(1000), (2, 2, 2))
            cpu.put_float(RAM+0xB6D4, .1)  # Imposed previous nonzero-duty control.
            self.assertEqual(cpu.stability(), (3, 3, 0))
            self.assertEqual(cpu.stability(), (4, 4, 1))
            cpu.put_float(RAM+0xB6D4, 0)
            self.assertEqual(cpu.stability(), (5, 5, 0))
            for _ in range(300):
                cpu.stability()
            self.assertEqual(cpu.stability(), (255, 255, 255))
            for rpm in (1001, 2800, 3500):
                self.assertEqual(cpu.stability(rpm), (255, 255, 255))
                self.assertNotIn(0x6E5F4, cpu.entered)
                # Execute the other native parent's snapshot and early exit.
                # Its <=1000 body, containing many more monitors, is separate.
                cpu.execute(0x6A6AC, SNAPSHOT_WRITES)
                self.assertEqual(cpu.get_float(RAM+0xD96C), rpm)
                self.assertNotIn(0x6E338, cpu.entered)
                self.assertEqual(cpu.read(RAM+0xD852, 1), 12)

    def test_wb_readiness_revokes_monitor_and_resets_span_but_holds_learned_history(self):
        for image in self.images:
            cpu = PurgeMonitorMachine(image)
            for _ in range(16):
                cpu.stability()
            cpu.sensor(18000)
            # Native ready-state positive control; installed publisher remains
            # unchanged and still supplies 50 on the following sensor call.
            cpu.native_ready_control()
            for remaining in range(11, -1, -1):
                self.assertEqual(cpu.monitor(), (0x20, remaining))
            cpu.put_float(RAM+0xD438, .75)
            cpu.write(RAM+0xD853, 9, 1)
            cpu.write(RAM+0xD94F, 0xA7, 1)
            for raw in (18000, 0, 65535, 18000):
                cpu.sensor(raw)
                other_bits = cpu.read(RAM+0xD94B, 1) & 0xDF
                self.assertEqual(cpu.monitor(), (other_bits, 12))
                self.assertEqual(cpu.read(RAM+0xD94F, 1), 0xA3)
                self.assertEqual(cpu.read(RAM+0xD944, 1), 0)
                self.assertEqual(cpu.array(RAM+0xD7EC, 4), [-2, -2, 2, 2])
                self.assertEqual(cpu.get_float(RAM+0xD438), .75)
                self.assertEqual(cpu.read(RAM+0xD853, 1), 9)
                self.assertEqual(cpu.disable(), (0, 0))

    def test_shared_monitor_flags_do_not_create_default_cylinder_disable_patterns(self):
        for image in self.images:
            cpu = PurgeMonitorMachine(image)
            cpu.sensor(18000)
            for shared in range(256):
                cpu.write(RAM+0xD94B, shared, 1)
                cpu.execute(0x6E338, QUALIFICATION_WRITES)
                self.assertEqual(cpu.read(RAM+0xD94B, 1), shared & 0xDF)
                self.assertEqual(cpu.disable(), (0, 0))
                self.assertTrue(all(cpu.read(ram, 1) == 0 for ram, _ in CONFIGURATION))
            # Other-bit preservation also keeps an independently imposed cut.
            cpu.write(RAM+0xD93F, 4, 1)
            cpu.write(RAM+0xD94B, 0xA0, 1)
            cpu.write(RAM+0x8CE4, 20, 2)
            cpu.execute(0x6E338, QUALIFICATION_WRITES)
            self.assertEqual(cpu.read(RAM+0xD94B, 1), 128)
            self.assertEqual(cpu.disable(), (4, 0))

    def test_history_computed_writes_stay_in_six_by_39_bank_storage(self):
        for image in self.images:
            cpu = PurgeMonitorMachine(image)
            cpu.write(RAM+0xD852, 0, 1)
            cpu.write(RAM+0xD80C, 1, 2)
            cpu.put_float(RAM+0xD434, 800)
            cpu.put_float(RAM+0xD3AC, .5)
            for a, size in ((0xC85C, 2), (0xC860, 1), (0xD851, 1), (0xD7E0, 4),
                            (0xD93D, 1), (0xD93E, 1), (0xD93F, 1)):
                cpu.write(RAM+a, 0xA5, size)
            for bank, cell in product(range(6), range(39)):
                cpu.write(RAM+0xD9AC, bank, 1)
                cpu.write(RAM+0xD851, cell, 1)
                count = RAM+0xD853+39*bank+cell
                value = RAM+0xD438+156*bank+4*cell
                cpu.execute(0x6E704, {(count, 1), (value, 4)})
                self.assertEqual(cpu.read(count, 1), 1)
                self.assertEqual(cpu.get_float(value), .5)
                cpu.put_float(RAM+0xD3AC, .75)
                cpu.execute(0x6E704, {(count, 1), (value, 4)})
                self.assertEqual(cpu.read(count, 1), 2)
                self.assertTrue(.5 < cpu.get_float(value) < .75)
                cpu.put_float(RAM+0xD3AC, .5)
            for a, size in ((0xC85C, 2), (0xC860, 1), (0xD7E0, 4),
                            (0xD93D, 1), (0xD93E, 1), (0xD93F, 1)):
                self.assertEqual(cpu.read(RAM+a, size), 0xA5)

    def test_native_cell_selector_bounds_its_rpm_and_pressure_bands(self):
        for image in self.images:
            cpu = PurgeMonitorMachine(image)
            # Native startup initializes the source channel to zero. The only
            # identified running writer D92C publishes its bounded loop index
            # 0..5; the crank event that reaches that writer is a separate edge.
            cpu.write(RAM+0xB058, 255, 1)
            cpu.execute(0xD8EE, {(RAM+a, 1) for a in
                                (0xB058, 0xB07E, 0xB07F, *range(0xB078, 0xB07E))})
            self.assertEqual(cpu.read(RAM+0xB058, 1), 0)
            axis = cpu.array(0x75304, 13)
            self.assertEqual(list(image[0x75338:0x75345]), list(range(13)))
            reached = set()
            for index, rpm in enumerate(axis):
                for pressure, offset in ((0, 0), (399.99, 0), (400, 13),
                                          (599.99, 13), (600, 26), (2000, 26)):
                    cpu.put_float(RAM+0xD96C, rpm)
                    cpu.put_float(RAM+0xB2A0, pressure)
                    cpu.execute(0x6DA4C, {(RAM+0xD991, 1), (RAM+0xD851, 1)})
                    self.assertEqual(cpu.read(RAM+0xD991, 1), index)
                    self.assertEqual(cpu.read(RAM+0xD851, 1), index+offset)
                    reached.add(index+offset)
            self.assertEqual(reached, set(range(39)))
            for rpm, expected in ((-1, 0), (8000, 12), (float('inf'), 12)):
                cpu.put_float(RAM+0xD96C, rpm)
                cpu.put_float(RAM+0xB2A0, 800)
                cpu.execute(0x6DA4C, {(RAM+0xD991, 1), (RAM+0xD851, 1)})
                self.assertEqual(cpu.read(RAM+0xD851, 1), expected+26)


if __name__ == '__main__':
    unittest.main(verbosity=2)
