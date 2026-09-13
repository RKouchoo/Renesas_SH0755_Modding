#!/usr/bin/env python3
"""Follow deleted purge producers through retained filter and PWM consumers.

All helpers on these paths execute ROM instructions, including fixed-point
multiply, filter, ratio bounds and PWM compare service. Timer/input states are
fixtures; no external valve or physical output polarity is simulated.
"""
import _test_paths
from itertools import product
import unittest

from test_load_conditioning_execution import LoadConditioningMachine
from test_injector_device_process_flow import InjectorDeviceMachine, ROOT
from test_primary_fueling_execution import signed
from test_runtime_rom_checksum_execution import before_pump_scaling

NATIVE = {0xB182, 0x2390, 0x2088, 0x2098, 0x24FC, 0x24C0, 0x2534,
          0x2424, 0x1BFBC, 0x46FE8, 0x23238, 0x231D6, 0x230E8, 0x23054}
FLOW_WRITES = {(0xFFFF0000+a, 4) for a in
               (0xBE60, 0xBE64, 0xBE6C, 0xBE70, 0xBE74, 0xBE7C, 0xBE80, 0xBE84)} | {
    (0xFFFF0000+a, 1) for a in (0xBE68, 0xBE69, 0xBE6A, 0xBE78, 0xBE79)}
COMMAND_WRITES = {(0xFFFF0000+a, 4) for a in (0xB6D4, 0xB6D8, 0xAE4C)} | {
    (0xFFFFB720, 1), (0xFFFFAB64, 2)}
PWM_WRITES = {(0xFFFF0000+a, 2) for a in (0xAB62, 0xAB66, 0xF480, 0xF4C4)} | {
    (0xFFFF0000+a, 1) for a in (0xAB68, 0xAB69, 0xAB6A, 0xF4CB)}


class PurgeProcessMachine(LoadConditioningMachine, InjectorDeviceMachine):
    def __init__(self, image):
        super().__init__(image, rpm=3000, coolant=85)
        self.mach = 0x5AA55AA5
        for a in range(0xFFFFBE60, 0xFFFFBE88):
            self.write(a, 0, 1)
        self.write(0xFFFFB705, 0, 1)
        for a in (0xFFFFB6D4, 0xFFFFB6D8):
            self.put_float(a, 0)
        self.put_float(0xFFFFB420, 50)
        self.put_float(0xFFFFB730, .25)
        self.put_float(0xFFFFB734, -.25)
        for a in range(0xFFFFAB54, 0xFFFFAB6C):
            self.write(a, 0, 1)
        for a, value in ((0xFFFFAB60, 4000), (0xFFFFAB62, 2000),
                         (0xFFFFAB64, 2000), (0xFFFFAB66, 2000),
                         (0xFFFFF480, 65535), (0xFFFFF4C4, 1000),
                         (0xFFFFF4C0, 1001)):
            self.write(a, value, 2)
        self.write(0xFFFFF4CB, 0x85, 1)

    def call_lookup(self, target):
        if target in NATIVE:
            self.entered.append(target)
            ret = self.pr
            self.pc = target
            while self.pc != ret:
                self.step()
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x300D:  # DMULS.L Rm,Rn.
            value = signed(self.r[n], 32)*signed(self.r[m], 32)
            self.mach, self.macl = (value >> 32) & 0xFFFFFFFF, value & 0xFFFFFFFF
        elif op & 0xF0FF == 0x000A:  # STS MACH,Rn.
            self.r[n] = self.mach
        elif op & 0xF0FF == 0x400A:  # LDS Rm,MACH (register in n field).
            self.mach = self.r[n]
        elif op & 0xF0FF == 0x401A:
            self.macl = self.r[n]
        elif op & 0xF0FF == 0x4025:  # ROTCR, including T exchange.
            value, old_t = self.r[n], int(self.t)
            self.r[n], self.t = (value >> 1) | (old_t << 31), bool(value & 1)
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT


class PurgeProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/f).read_bytes() for f in
                      ('master_patch/D2WD610H_master_patch.bin',
                       'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x22FE8, 0x23054), (0x2305C, 0x23300),
                         (0x1BFBC, 0x1BFD2), (0x46FE8, 0x46FEC),
                         (0xB182, 0xB1E8), (0x57DA, 0x58E6), (0x5976, 0x5990),
                         (0x2390, 0x240C), (0x2424, 0x2458), (0x24C0, 0x24DC),
                         (0x24FC, 0x251A), (0x2534, 0x254C)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_zero_producer_stays_zero_through_native_filter_transitions(self):
        for image in self.images:
            cpu = PurgeProcessMachine(image)
            cpu.invoke(0x22FE8, FLOW_WRITES)
            for coolant, delta, airflow, flag in product((20, 85), (-1, 0, 1), (0, 50), (0, 64)):
                cpu.put_float(0xFFFFB3AC, coolant)
                cpu.put_float(0xFFFFB43C, delta)
                cpu.put_float(0xFFFFB420, airflow)
                cpu.write(0xFFFFB705, flag, 1)
                cpu.invoke(0x2300A, FLOW_WRITES)
                for a in (0xBE60, 0xBE64, 0xBE6C, 0xBE70, 0xBE7C, 0xBE80):
                    self.assertEqual(cpu.get_float(0xFFFF0000+a), 0, hex(a))

    def test_stale_filter_state_decays_without_bank_fuel_subtraction(self):
        for image in self.images:
            cpu = PurgeProcessMachine(image)
            cpu.invoke(0x22FE8, FLOW_WRITES)
            cpu.put_float(0xFFFFBE70, 2)
            previous = 2
            for _ in range(100):
                cpu.invoke(0x2300A, FLOW_WRITES)
                current = cpu.get_float(0xFFFFBE70)
                self.assertLessEqual(current, previous)
                self.assertGreaterEqual(current, 0)
                self.assertEqual(cpu.get_float(0xFFFFBE60), 0)
                self.assertEqual(cpu.get_float(0xFFFFBE64), 0)
                self.assertTrue(0 <= cpu.get_float(0xFFFFBE6C) <= .125)
                previous = current
            self.assertLess(previous, .001)

    def test_zero_request_reaches_native_pwm_and_clears_prior_duty(self):
        for image, phase in product(self.images, (0, 1)):
            cpu = PurgeProcessMachine(image)
            cpu.write(0xFFFFAB68, phase, 1)
            cpu.write(0xFFFFAB69, 1, 1)
            saved_mach, saved_macl = cpu.mach, cpu.macl
            cpu.invoke(0x1BAF0, COMMAND_WRITES)
            self.assertEqual((cpu.mach, cpu.macl), (saved_mach, saved_macl))
            self.assertEqual(cpu.read(0xFFFFAB64, 2), 0)
            self.assertEqual(cpu.read(0xFFFFAE4C, 4), 0)
            for _ in range(8):
                cpu.invoke(0x57DA, PWM_WRITES)
                self.assertEqual(cpu.read(0xFFFFAB62, 2), 0)
                self.assertEqual(cpu.read(0xFFFFAB66, 2), 4000)
                self.assertEqual(cpu.read(0xFFFFF4CB, 1) & 0x8F, 0x85)
            self.assertEqual(cpu.read(0xFFFFAB68, 1), 0)
            self.assertEqual(cpu.read(0xFFFFAB6A, 1), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
