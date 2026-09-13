#!/usr/bin/env python3
"""Execute throttle-monitor enable, angle lookups, persistence and native cut.

The received voltage, learned offset and physical blade are explicit inputs.
Native callback lists, helpers and fault aggregation run from the ROM. These
fixtures establish conditional behavior, not a fault observed in the car.
"""
import _test_paths
from itertools import product
import unittest

from test_dbw_arbitration_process_flow import DBWArbitrationMachine
from test_throttle_link_execution import LOCAL_GETTERS, TX_GETTERS
from test_idle_air_override_execution import FAULT_WRITES
from test_native_fault_cut_execution import GETTERS, CUT_WRITES
from test_wideband_fuel_guard_execution import INHIBIT_GETTERS, INHIBIT_WORD
from test_primary_fueling_execution import signed
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT = _test_paths.ROOT
ENABLE_WRITES = {(0xFFFFD298, 1), (0xFFFFD29A, 2)}
TRACK_WRITES = {(0xFFFF0000+a, 1) for a in (0x8150, 0xD280, 0xD290, 0xD294)} | {
    (0xFFFF0000+a, 2) for a in (0xD278, 0xD27A, 0xD27C, 0xD27E, 0xD292)
} | {(0xFFFF0000+a, 4) for a in (0xD284, 0xD288, 0xD28C)}


class ThrottleTrackingMachine(DBWArbitrationMachine):
    LOOKUPS = DBWArbitrationMachine.LOOKUPS | LOCAL_GETTERS | TX_GETTERS | GETTERS | set(INHIBIT_GETTERS) | {
        0x2118, 0x4711E, 0x56E64, 0x56F0C, 0x5742C, 0x65432, 0x654A6,
        0x2088, 0x312CA,
    } | set(range(0x2564C, 0x25AC0, 2))

    def __init__(self, image):
        super().__init__(image)
        for address, size in ENABLE_WRITES | TRACK_WRITES | CUT_WRITES:
            self.write(address, 0, size)
        for a in (0x8134, 0x8138, 0x813C, 0x8194, 0x81AC,
                  0x81A8, 0x814C, 0x8198, 0x81A0, 0xD364):
            self.write(0xFFFF0000+a, 0, 1)
        for a in range(0xFFFFD271, 0xFFFFD275):
            self.write(a, 0, 1)
        self.write(0xFFFFB28C, image[0x737C9], 1)
        self.put_float(0xFFFFC6DC, 13.5)
        self.put_float(0xFFFF80A8, 0)  # Additional measured-angle learned offset.
        self.put_float(0xFFFFABD4, 60)
        self.put_float(0xFFFFC2B4, 60)
        self.put_float(0xFFFFB2C8, 60)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF0FF == 0x0023:  # BRAF Rn with a delay slot.
            assert not in_delay
            self.trace.append((pc, op))
            target = (pc+4+self.r[n]) & 0xFFFFFFFF
            self.pc += 2
            self.step(in_delay=True)
            self.pc = target
            self.instructions += 1
            return
        if op & 0xF00F == 0x0004:  # MOV.B Rm,@(R0,Rn).
            self.write((self.r[0]+self.r[n]) & 0xFFFFFFFF, self.r[m], 1, record=True)
        elif op & 0xF00F == 0x000D:  # MOV.W @(R0,Rm),Rn; sign extend.
            self.r[n] = signed(self.load((self.r[0]+self.r[m]) & 0xFFFFFFFF, 2), 16) & 0xFFFFFFFF
        elif op & 0xF00F in (0x600E, 0x600F):  # EXTS.B/W.
            self.r[n] = signed(self.r[m], 8 if op & 15 == 14 else 16) & 0xFFFFFFFF
        elif op & 0xF00F == 0x200A:  # XOR Rm,Rn.
            self.r[n] ^= self.r[m]
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1

    def monitor(self, request, measured, rpm=2800, offset=0):
        for a, value in ((0xC2B4, request), (0xABD4, measured),
                         (0xB544, rpm), (0x80F0, offset)):
            self.put_float(0xFFFF0000+a, value)
        # Consecutive native calls in task 10A28, at 10FBC and 10FC2.
        self.execute(0x66244, ENABLE_WRITES)
        self.execute(0x65424, TRACK_WRITES)
        return self.read(0xFFFF8150, 1) & 3

    def cut(self, rpm=2800):
        self.put_float(0xFFFFB544, rpm)
        self.execute(0x64874, FAULT_WRITES)
        self.execute(0x14CC6, {(0xFFFFB2C4, 4)})
        self.execute(0x14CE6, {(0xFFFFB2C8, 4)})
        self.execute(0x253A8, CUT_WRITES)
        return self.read(INHIBIT_WORD, 2)


class ThrottleTrackingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in
                      ('master_patch/D2WD610H_master_patch.bin',
                       'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x653D4, 0x65694), (0x66244, 0x66344),
                         (0x14CC6, 0x14D1E), (0x14D88, 0x14DBC),
                         (0x15238, 0x15410), (0x157D8, 0x15920),
                         (0x7387C, 0x738A0), (0x737E0, 0x737E2),
                         (0x737CB, 0x737CC),
                         (0x49530, 0x49576), (0x4963A, 0x4969C),
                         (0x64874, 0x64F7C), (0x253A8, 0x25AC0),
                         (0x5EFDC, 0x5EFFC), (0x756F8, 0x75728),
                         (0x74DA6, 0x74DAC), (0x74DE4, 0x74DEC),
                         (0x74FAC, 0x74FB4), (0x56E64, 0x57434),
                         (0x579B0, 0x579FC), (0x75E02, 0x75E03),
                         (0x209C, 0x20D8), (0x2118, 0x2150)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_native_position_axes_use_learned_offset_and_not_rpm(self):
        for image, rpm in product(self.images, (2500, 2800, 3000, 3500, 4144)):
            cpu = ThrottleTrackingMachine(image)
            self.assertEqual(cpu.monitor(25, 25, rpm, offset=3), 0)
            self.assertEqual(cpu.read(0xFFFFD280, 1) & 1, 1)
            self.assertEqual(cpu.read(0xFFFFD290, 1), 1)
            self.assertEqual(cpu.get_float(0xFFFFD284), 22)
            self.assertEqual(cpu.get_float(0xFFFFD288), 22)
            self.assertEqual(cpu.read(0xFFFFD292, 2), 31)
            self.assertEqual(cpu.cut(rpm), 0)

        for image in self.images:
            cpu = ThrottleTrackingMachine(image)
            for measured, count in ((0, 125), (5.5, 125), (9, 50),
                                    (13, 38), (22, 31), (84, 31)):
                cpu.monitor(measured, measured)
                self.assertEqual(cpu.read(0xFFFFD292, 2), count)
            for request, raw in ((0, 0x0625), (6.15, 0x0625), (9.65, 0x0A3D),
                                 (14.65, 0x1893), (26.65, 0x3333), (84, 0x3333)):
                cpu.monitor(request, request)
                self.assertAlmostEqual(cpu.get_float(0xFFFFD28C),
                                       raw*cpu.get_float(0x5EFF4), delta=.00001)

    def test_excess_opening_fault_reaches_cut_and_remains_latched(self):
        for image in self.images:
            cpu = ThrottleTrackingMachine(image)
            for _ in range(30):
                self.assertEqual(cpu.monitor(0, 40), 0)
                self.assertEqual(cpu.cut(), 0)
            self.assertEqual(cpu.monitor(0, 40), 1)
            self.assertEqual(cpu.read(0xFFFFD278, 2), 31)
            self.assertEqual(cpu.cut(), 63)
            self.assertEqual([cpu.read(0xFFFFD271+i, 1) for i in range(4)],
                             [2, 0xC0, 0x27, 0])
            # The next enable call stops monitoring, but cannot clear 8150.
            self.assertEqual(cpu.monitor(40, 40), 1)
            self.assertEqual(cpu.read(0xFFFFD280, 1) & 1, 0)
            self.assertEqual(cpu.read(0xFFFFD278, 2), 0)
            self.assertEqual(cpu.cut(), 63)
            # A separate selector branch depends on selected throttle;
            # do not collapse the whole 8150 fault to D273/02 alone.
            cpu.put_float(0xFFFFABD4, 10)
            for rpm, expected in ((2800, 0), (2999, 0), (3000, 63),
                                  (2800, 63), (2499, 0), (2800, 0)):
                self.assertEqual(cpu.cut(rpm), expected)

    def test_request_shortfall_uses_fixed_125_calls_and_sign_resets(self):
        for image in self.images:
            cpu = ThrottleTrackingMachine(image)
            for _ in range(30):
                self.assertEqual(cpu.monitor(0, 22), 0)
            for _ in range(124):
                self.assertEqual(cpu.monitor(60, 0), 0)
            self.assertEqual(cpu.read(0xFFFFD278, 2), 0)
            self.assertEqual(cpu.read(0xFFFFD27A, 2), 124)
            self.assertEqual(cpu.monitor(60, 0), 1)
            self.assertEqual(cpu.cut(), 0)
            self.assertEqual(cpu.cut(3000), 63)

    def test_low_rpm_has_separate_counter_and_500_300_hysteresis(self):
        for image in self.images:
            cpu = ThrottleTrackingMachine(image)
            for rpm, active in ((499, 0), (500, 1), (300, 1), (299, 0), (400, 0)):
                cpu.monitor(0, 0, rpm)
                self.assertEqual(cpu.read(0xFFFFD294, 1), active)
            for _ in range(2499):
                self.assertEqual(cpu.monitor(0, 40, 250), 0)
            self.assertEqual(cpu.read(0xFFFFD27C, 2), 2499)
            self.assertEqual(cpu.monitor(0, 40, 250), 1)
            self.assertEqual(cpu.cut(250), 0)
            self.assertEqual(cpu.cut(2800), 63)

    def test_each_enable_gate_clears_persistence_without_erasing_fault(self):
        gates = ((0xB51E, 0, 1), (0xC650, 0, 1), (0xABB4, 5.99, 4),
                 (0xC6DC, 5.99, 4), (0xC618, 1, 1), (0xD364, 0x80, 1),
                 (0x8194, 1, 1), (0x8150, 1, 1))
        for image, (a, value, size) in product(self.images, gates):
            cpu = ThrottleTrackingMachine(image)
            self.assertEqual(cpu.monitor(0, 22), 0)
            self.assertEqual(cpu.read(0xFFFFD278, 2), 1)
            if size == 4:
                cpu.put_float(0xFFFF0000+a, value)
            else:
                cpu.write(0xFFFF0000+a, value, size)
            cpu.monitor(0, 22)
            self.assertEqual(cpu.read(0xFFFFD280, 1) & 1, 0, hex(a))
            self.assertEqual([cpu.read(0xFFFF0000+x, 2) for x in
                              (0xD278, 0xD27A, 0xD27C, 0xD27E)], [0]*4)
            if a == 0x8150:
                self.assertEqual(cpu.read(0xFFFF8150, 1) & 3, 1)

    def test_shared_readiness_bits_have_distinct_hold_and_clear_rules(self):
        for image in self.images:
            cpu = ThrottleTrackingMachine(image)
            cpu.execute(0x66244, ENABLE_WRITES)
            self.assertEqual(cpu.read(0xFFFFD298, 1), 15)
            cpu.put_float(0xFFFFABB4, 5.99)
            cpu.execute(0x66244, ENABLE_WRITES)
            self.assertEqual(cpu.read(0xFFFFD298, 1), 14)
            cpu.execute(0x66244, ENABLE_WRITES)
            self.assertEqual(cpu.read(0xFFFFD298, 1), 12)
            cpu.put_float(0xFFFFABB4, 6)
            cpu.execute(0x66244, ENABLE_WRITES)
            self.assertEqual(cpu.read(0xFFFFD298, 1), 15)
            cpu.write(0xFFFFB51E, 0, 1)
            cpu.execute(0x66244, ENABLE_WRITES)
            self.assertEqual(cpu.read(0xFFFFD298, 1), 10)
            cpu.write(0xFFFFC6F7, 0, 1)
            cpu.execute(0x66244, ENABLE_WRITES)
            self.assertEqual(cpu.read(0xFFFFD298, 1), 2)

    def test_good_qualification_and_both_native_reset_entries(self):
        for image in self.images:
            cpu = ThrottleTrackingMachine(image)
            for _ in range(249):
                cpu.monitor(22, 22)
            self.assertEqual(cpu.read(0xFFFFD280, 1), 1)
            cpu.monitor(22, 22)
            self.assertEqual(cpu.read(0xFFFFD280, 1), 5)
            for packed, expected in ((0, 0xF1), (0x80, 0xF1),
                                     (0x40, 0xF2), (0xC0, 0xF2)):
                cpu.write(0xFFFF8150, 0xF1, 1)
                cpu.write(0xFFFF825C, packed, 1)
                cpu.execute(0x653D4, {(0xFFFF8150, 1)})
                self.assertEqual(cpu.read(0xFFFF8150, 1), expected)
            cpu.write(0xFFFF8150, 0xF1, 1)
            cpu.execute(0x653F8, {(0xFFFF8150, 1)})
            self.assertEqual(cpu.read(0xFFFF8150, 1), 0xF2)
            self.assertEqual(cpu.monitor(22, 22), 2)
            self.assertEqual(cpu.cut(), 0)

    def test_driver_and_final_request_feed_same_monitor_storage(self):
        for image in self.images:
            cpu = ThrottleTrackingMachine(image)
            for pedal in (0, 10, 70, 100, 0):
                cpu.put_float(0xFFFFB46C, pedal)
                cpu.put_float(0xFFFFB470, pedal)
                request = cpu.final_step()
                self.assertEqual(cpu.monitor(request, request), 0)
                self.assertEqual(cpu.cut(), 0)

    def test_measured_angle_offset_learning_is_bounded_and_protected(self):
        records = (0x8080, 0x8088, 0x8090, 0x8098, 0x80A0, 0x80A8)
        writes = {(0xFFFF0000+a, size) for base in records
                  for a, size in ((base, 4), (base+4, 2), (base+6, 2))} | {
                      (0xFFFF80B0, 1), (0xFFFF80B1, 1), (0xFFFFB358, 1)}
        for image in self.images:
            cpu = ThrottleTrackingMachine(image)
            cpu.write(0xFFFF80B1, 0, 1)
            cpu.execute(0x15238, writes)
            self.assertEqual(cpu.get_float(0xFFFF80A8), 0)
            for first, second, expected in ((100, 0, .428), (0, 100, -.428),
                                            (20, 20.2, -.2)):
                cpu.execute(0x15238, writes)
                for a, value in ((0xB344, first), (0xB2C0, second), (0xB348, 21)):
                    cpu.put_float(0xFFFF0000+a, value)
                cpu.write(0xFFFFB354, 7, 2)
                cpu.write(0xFFFFB356, 4, 1)
                cpu.execute(0x157D8, writes)
                self.assertEqual(cpu.get_float(0xFFFF80A8), 0)
                cpu.write(0xFFFFB354, 8, 2)
                cpu.execute(0x157D8, writes)
                self.assertAlmostEqual(cpu.get_float(0xFFFF80A8), expected, delta=.00001)
                self.assertEqual(cpu.read(0xFFFF80B0, 1) & 15, 5)
                self.assertEqual(cpu.read(0xFFFFB358, 1) & 4, 4)
                # Re-entering after acquisition holds this learned record.
                before = bytes(cpu.read(0xFFFF80A8+i, 1) for i in range(8))
                saved_argument = cpu.original_r[4]
                cpu.original_r[4] = 0xFFFF80A8
                cpu.execute(0x4963A, writes)
                self.assertEqual(cpu.r[0], 0)
                cpu.write(0xFFFF80AC, cpu.read(0xFFFF80AC, 2) ^ 1, 2)
                cpu.execute(0x4963A, writes)
                self.assertEqual(cpu.r[0], 0)
                self.assertEqual(bytes(cpu.read(0xFFFF80A8+i, 1) for i in range(8)), before)
                cpu.original_r[4] = saved_argument
                cpu.put_float(0xFFFFB344, 0)
                cpu.execute(0x157D8, writes)
                self.assertEqual(bytes(cpu.read(0xFFFF80A8+i, 1) for i in range(8)), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
