#!/usr/bin/env python3
"""Execute AVLS transitions and current feedback through native timer writes.

The ROM controls all four timer-6 channels shared by AVCS and AVLS. ADC samples
and timer cycle matches are explicit inputs; this does not simulate hydraulic
lift, crank interrupt latency or the physical output pin waveform.
"""
import _test_paths
from itertools import product
import unittest

from test_avls_phase_process_flow import (
    AVLSPhaseMachine, AVLSMachine, ROOT, RAM, BANK_WRITES, PERIODIC_WRITES,
)
from test_avcs_actuator_process_flow import DEVICE_WRITES as AVCS_WRITES
from test_primary_fueling_execution import bits, number, signed
from test_runtime_rom_checksum_execution import before_pump_scaling

CURRENT_WRITES = {(RAM+a, n) for a, n in (
    (0xB118, 2), (0xB11A, 2), (0xB11C, 4), (0xB120, 4))}
HARDWARE_WRITES = CURRENT_WRITES | {(RAM+0xF400, 1)} | {
    (RAM+a, 2) for a in (0xAB90, 0xAB92, 0xF50C, 0xF50E,
        0xF504, 0xF506, 0xF514, 0xF516, 0xF51C, 0xF51E)}


class AVLSActuatorMachine(AVLSPhaseMachine):
    def __init__(self, image, rpm=3200):
        self.mach, self.macl = 0x12345678, 0x76543210
        super().__init__(image, rpm)
        self.sr = 0x20
        self.write(RAM+0xF400, 0xA0, 1)
        for a in (0xAB24, 0xAB1E, 0xAB20, 0xAB0C):
            self.write(RAM+a, 0, 2)
        self.invoke(0xF2A2, HARDWARE_WRITES)
        self.cycle_match()

    def invoke(self, entry, allowed_writes):
        accumulator = self.mach, self.macl
        result = super().invoke(entry, allowed_writes | HARDWARE_WRITES)
        assert (self.mach, self.macl) == accumulator
        return result

    def step(self, in_delay=False):
        if self.pc in (0xF12A, 0xF0C0):
            assert not in_delay
            self.pwm.append((self.r[4], number(self.fr[4])))
            # Execute the native first instruction instead of the phase
            # suite's explicitly bounded PWM callback.
            return AVLSMachine.step(self, in_delay)
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x300D:  # DMULS.L, signed 64-bit product.
            value = signed(self.r[n], 32)*signed(self.r[m], 32)
            self.mach, self.macl = (value >> 32) & 0xFFFFFFFF, value & 0xFFFFFFFF
        elif op & 0xF0FF == 0x000A:
            self.r[n] = self.mach
        elif op & 0xF0FF == 0x001A:
            self.r[n] = self.macl
        elif op & 0xF0FF == 0x400A:
            self.mach = self.r[n]
        elif op & 0xF0FF == 0x401A:
            self.macl = self.r[n]
        elif op & 0xF0FF == 0x4021:  # SHAR, sign preserved.
            value = self.r[n]
            self.r[n] = (value >> 1) | (value & 0x80000000)
            self.t = bool(value & 1)
        elif op & 0xF0FF == 0x4025:  # ROTCR through old T.
            value, old_t = self.r[n], int(self.t)
            self.r[n], self.t = (value >> 1) | (old_t << 31), bool(value & 1)
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1

    def call_lookup(self, target):
        if target in (0x2088, 0x2098, 0x2390, 0xF39C, 0xE0D0,
                      0xDF00, 0xE290):
            self.entered.append(target)
            return_pc, self.pc = self.pr, target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def cycle_match(self):
        # SH7055S manual 11.2.22--24: the cycle match transfers BFR to DTR.
        for bank in (0, 1):
            self.write(RAM+0xF51C+2*bank, self.read(RAM+0xF514+2*bank, 2), 2)

    def command(self, entry, bank, fraction):
        self.original_r[4] = bank
        self.original_fr[4] = bits(fraction)
        self.invoke(entry, HARDWARE_WRITES)
        return self.read(RAM+0xF514+2*bank, 2)


class AVLSActuatorProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0xF0C0, 0xF414), (0x72854, 0x72860), (0x2390, 0x240C)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_native_startup_initializes_only_the_avls_timer_channels(self):
        for image in self.images.values():
            cpu = AVLSActuatorMachine(image)
            self.assertEqual(cpu.read(RAM+0xF400, 1), 0xAC)
            for a in (0xAB90, 0xAB92, 0xF50C, 0xF50E):
                self.assertEqual(cpu.read(RAM+a, 2), 6666)
            for a in (0xF514, 0xF516, 0xF51C, 0xF51E):
                self.assertEqual(cpu.read(RAM+a, 2), 0)

    def test_transition_and_periodic_duty_have_the_same_bank_and_q16_scaling(self):
        for image, bank, fraction in product(self.images.values(), (0, 1), (0, .071, .71, 1)):
            cpu = AVLSActuatorMachine(image)
            expected = int(fraction*65536)*6666 >> 16
            for entry in (0xF12A, 0xF0C0):
                self.assertEqual(cpu.command(entry, bank, fraction), expected)
                self.assertEqual(cpu.read(RAM+0xF514+2*(1-bank), 2), 0)
                self.assertEqual(cpu.read(RAM+0xF400, 1), 0xAC)
                cpu.cycle_match()
                self.assertEqual(cpu.read(RAM+0xF51C+2*bank, 2), expected)

    def test_full_lift_transition_and_periodic_controller_reach_native_pwm(self):
        for image, rpm in product(self.images.values(), (3200, 3500, 4144)):
            cpu = AVLSActuatorMachine(image, rpm)
            cpu.request(rpm)
            for phase in range(72):
                cpu.phase(phase % 24)
            self.assertEqual(tuple(cpu.read(RAM+a, 2) for a in (0xF514, 0xF516)), (6666, 6666))
            for _ in range(80):
                duty = cpu.periodic_output()
                cpu.cycle_match()
                for bank in (0, 1):
                    self.assertEqual(cpu.read(RAM+0xF51C+2*bank, 2),
                                     int(duty[bank]/100*65536)*6666 >> 16)
            self.assertEqual(cpu.read(RAM+0xCD86, 1), 3)

    def test_native_adc_current_conversion_preserves_two_independent_banks(self):
        for image in self.images.values():
            cpu = AVLSActuatorMachine(image)
            cpu.write(RAM+0xAB24, 20000, 2)
            cpu.write(RAM+0xAB1E, 40000, 2)
            cpu.invoke(0xF39C, CURRENT_WRITES)
            for bank, counts in enumerate((20000, 40000)):
                self.assertEqual(cpu.read(RAM+0xB118+2*bank, 2), counts)
                self.assertAlmostEqual(cpu.get_float(RAM+0xB11C+4*bank),
                                       counts*5/65536*.334-.035, delta=2e-7)

    def test_avcs_and_avls_updates_preserve_each_others_shared_timer_channels(self):
        for name in ('main', 'v2'):
            cpu = AVLSActuatorMachine(self.images[name])
            cpu.command(0xF12A, 0, .71)
            cpu.command(0xF12A, 1, .8)
            avls = tuple(cpu.read(RAM+a, 2) for a in (0xF514, 0xF516))
            cpu.invoke(0xDFE8, AVCS_WRITES)
            cpu.original_r[4] = 0
            cpu.original_fr[4] = bits(.4)
            cpu.invoke(0xDF00, AVCS_WRITES)
            cpu.original_r[4] = 1
            cpu.original_fr[4] = bits(.45)
            cpu.invoke(0xDF00, AVCS_WRITES)
            self.assertEqual(tuple(cpu.read(RAM+a, 2) for a in (0xF514, 0xF516)), avls)
            avcs = tuple(cpu.read(RAM+a, 2) for a in (0xF510, 0xF512))
            self.assertEqual(avcs, (2666, 2999))
            self.assertEqual(cpu.read(RAM+0xF400, 1), 0xAF)
            cpu.command(0xF12A, 0, 1)
            cpu.command(0xF0C0, 1, 0)
            self.assertEqual(tuple(cpu.read(RAM+a, 2) for a in (0xF510, 0xF512)), avcs)
            self.assertEqual(cpu.read(RAM+0xF400, 1), 0xAF)


if __name__ == '__main__':
    unittest.main(verbosity=2)
