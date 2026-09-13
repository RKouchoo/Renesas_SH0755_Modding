#!/usr/bin/env python3
"""Execute native AVLS phase selection and both bank command calculations.

Crank phases, cam phase inputs, qualifiers and actuator-current samples are
explicit fixtures. Native 405CC executes through 40C94/40798/40CE6 to the
F12A hardware-driver boundary. PWM peripheral timing, hydraulics and the
engine are not simulated. Lookup interpolation is a mathematical boundary.
"""
import _test_paths
from itertools import product
import unittest

from test_avls_oil_gate_execution import AVLSMachine, WRITES as SELECT_WRITES
from test_primary_fueling_execution import number, signed
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT = _test_paths.ROOT
RAM = 0xFFFF0000
PHASE_WRITES = {(RAM+a, 1) for a in (0xCD88, 0xCD8B, 0xCD8C,
                0xCD8D, 0xCD8E, 0xCD90, 0xCD91, 0xCD92, 0xCD93)}
BANK_WRITES = {(RAM+a, 1) for a in (0xCD89, 0xCD8A, 0xCD9D,
                0xCDD8, 0xCDD9, 0xCE08, 0xCE09)} | {
    (RAM+a, 4) for a in (0xCDA0, 0xCDA4, 0xCDA8, 0xCDAC,
        0xCDB0, 0xCDB4, 0xCDB8, 0xCDBC, 0xCDC0, 0xCDC4,
        0xCDC8, 0xCDCC, 0xCDD0, 0xCDD4, 0xCDDC, 0xCDE0,
        0xCDF0, 0xCDF4, 0xCDF8, 0xCDFC)}
PERIODIC_WRITES = BANK_WRITES | {(RAM+a, 1) for a in (0xCE0A, 0xCE0B)} | {
    (RAM+a, 4) for a in (0xCE00, 0xCE04)} | {
    (RAM+a, 2) for a in (*range(0xCDE4, 0xCDF0, 2), *range(0xCE0C, 0xCE24, 2))}
MODE_WRITES = SELECT_WRITES | {(RAM+a, 1) for a in
                (0xCD86, 0xCD89, 0xCD8A, 0xCD9C)}
NATIVE = {0x258C, 0x406A4, 0x40C94, 0x40798, 0x40CE6,
          0x40F8C, 0x4108E, 0x40C2C, 0x40B1A, 0x407C6, 0x41160,
          0xF298, 0x3AF4, 0x3FFDA, 0x400EE, 0x40138,
          0x40168, 0x405B2, 0x40682, 0x18CF4, 0x18D08, 0x3B430,
          0x40D94, 0x40764, 0x40E0A, 0x40A30, 0x40F28, 0x41230, 0x3BE62}
TABLES = {0x60F08, 0x60F1C, 0x60F30, 0x60F44}


class AVLSPhaseMachine(AVLSMachine):
    def __init__(self, image, rpm=3200, cam=(0, 0)):
        super().__init__(image, rpm=rpm, speed=30, oil=50)
        # Normal DMA-zeroed AVLS state, followed by its native mode initializer.
        for address in range(RAM+0xCD84, RAM+0xCE24):
            self.write(address, 0, 1)
        for address, value in ((0xC8B0, cam[0]), (0xC8B4, cam[1]),
                               (0xB11C, 0), (0xB120, 0),
                               (0xCDA0, 1), (0xCDB0, 1)):
            self.put_float(RAM+address, value)
        self.pwm = []
        self.write(RAM+0xB484, 0, 1)  # Running pedal flags supplied explicitly.
        self.write(RAM+0xCC00, 0, 1)  # Separate native 3B430 qualifier clear.
        self.write(RAM+0xCC50, 0, 1)  # Native 3BE62 special-mode qualifier clear.
        self.write(RAM+0x8EBC, 0x00FF, 2)  # Protected AVLS DTC status group clear.
        self.invoke(0x3FD9C, {(RAM+a, 1) for a in
                    (0xCD86, 0xCD87, 0xCD88, 0xCD89, 0xCD8A, 0xCD8F)})

    def step(self, in_delay=False):
        if self.pc in (0xF12A, 0xF0C0):
            assert not in_delay
            self.pwm.append((self.r[4], number(self.fr[4])))
            self.poison_scratch()
            self.pc = self.pr
            self.instructions += 1
            return
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF0FF == 0x4008:  # SHLL2, T unchanged.
            self.r[n] = (self.r[n] << 2) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x4000:  # SHLL; T receives outgoing high bit.
            self.t = bool(self.r[n] & 0x80000000)
            self.r[n] = (self.r[n] << 1) & 0xFFFFFFFF
        elif op & 0xF00F == 0x000E:  # MOV.L @(R0,Rm),Rn.
            self.r[n] = self.load((self.r[0]+self.r[m]) & 0xFFFFFFFF, 4)
        elif op & 0xF00F == 0x600F:  # EXTS.W Rm,Rn.
            self.r[n] = signed(self.r[m] & 0xFFFF, 16) & 0xFFFFFFFF
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def call_lookup(self, target):
        if target in NATIVE or target in (0xF12A, 0xF0C0):
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def table(self, target, descriptor, x, y):
        if descriptor not in TABLES:
            return super().table(target, descriptor, x, y)
        assert target == 0x209C and self.read(descriptor+2, 2) == 0x800
        count = self.read(descriptor, 2)
        axis, data = self.read(descriptor+4, 4), self.read(descriptor+8, 4)
        scale, bias = self.get_float(descriptor+12), self.get_float(descriptor+16)
        return self.interpolate(self.array(axis, count),
                    [self.read(data+2*i, 2)*scale+bias for i in range(count)], x)

    def request(self, rpm):
        self.put_float(RAM+0xB544, rpm)
        self.invoke(0x3FDBC, MODE_WRITES)
        self.invoke(0x3FE14, PHASE_WRITES)
        return tuple(self.read(RAM+a, 1) for a in (0xCD86, 0xCD8B, 0xCD8C))

    def phase(self, value):
        self.write(RAM+0xB528, value, 1)
        self.invoke(0x405CC, BANK_WRITES)
        return tuple(self.read(RAM+a, 1) for a in (0xCD89, 0xCD8A))

    def periodic_output(self):
        # Actual parent 1081A order after request/phase publication.
        for entry in (0x40D94, 0x40764, 0x40E0A):
            self.invoke(entry, PERIODIC_WRITES)
        return tuple(self.get_float(RAM+a) for a in (0xCDF8, 0xCDFC))


class AVLSPhaseFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        cls.images = {
            'main': (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes(),
            'v2': (ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes(),
        }
        cls.images['captured'] = before_pump_scaling(cls.images['v2'])
        for image in cls.images.values():
            for a, b in ((0x3FD9C, 0x41230), (0x4C808, 0x4CA5C),
                         (0x7D3E4, 0x7D4B0), (0x7D4C0, 0x7D65E)):
                assert image[a:b] == cls.stock[a:b], hex(a)

    def test_transition_phase_targets_stay_in_the_24_phase_domain(self):
        for name, image in self.images.items():
            for rpm, cam_a, cam_b in product((2800, 3000, 3200, 3500, 4144),
                                            (-10, 39.9, 40, 69.9, 70, 90, 120),
                                            (0, 70, 120)):
                cpu = AVLSPhaseMachine(image, rpm, (cam_a, cam_b))
                for mode, previous in ((3, 1), (1, 3)):
                    cpu.write(RAM+0xCD86, mode, 1)
                    cpu.write(RAM+0xCD88, previous, 1)
                    cpu.invoke(0x3FE14, PHASE_WRITES)
                    phases = tuple(cpu.read(RAM+a, 1) for a in (0xCD8B, 0xCD8C))
                    self.assertTrue(all(0 <= p < 24 for p in phases), (name, rpm, phases))
                    self.assertEqual(cpu.read(RAM+0xCD88, 1), mode)
                    self.assertIn(0x406A4, cpu.entered)

    def test_bank_one_precedes_bank_zero_and_extra_wait_clears(self):
        for name, image in self.images.items():
            cpu = AVLSPhaseMachine(image)
            mode, phase_a, phase_b = cpu.request(3200)
            self.assertEqual(mode, 3, name)
            self.assertEqual(cpu.phase(phase_a), (1, 1))
            self.assertEqual(cpu.pwm, [])  # Bank zero cannot lead bank one.
            self.assertEqual(cpu.phase(phase_b), (1, 3))
            self.assertEqual(cpu.pwm, [(1, 1.0)])  # Native initial high-mode duty.
            self.assertEqual(cpu.phase(phase_a), (1, 3))
            self.assertEqual(cpu.read(RAM+0xCD9D, 1), 1)
            self.assertEqual(cpu.phase(phase_a), (3, 3))
            self.assertEqual(cpu.read(RAM+0xCD9D, 1), 0)
            self.assertEqual(cpu.pwm, [(1, 1.0), (0, 1.0)])
            cpu.phase(phase_a)
            cpu.phase(phase_b)
            self.assertEqual(len(cpu.pwm), 2)  # No duplicate transition output.

    def test_every_start_phase_completes_each_requested_transition(self):
        for image in self.images.values():
            for start, cam in product(range(24), ((0, 0), (70, 0), (0, 70))):
                cpu = AVLSPhaseMachine(image, cam=cam)
                for rpm, expected in ((3200, 3), (2800, 1), (3500, 3), (2999, 1)):
                    # Native moving release also needs a qualifying pedal state.
                    cpu.write(RAM+0xB484, 0x80 if expected == 1 else 0, 1)
                    self.assertEqual(cpu.request(rpm)[0], expected)
                    for step in range(72):
                        cpu.phase((start+step) % 24)
                    self.assertEqual(cpu.phase(start), (expected, expected))
                    self.assertEqual(cpu.read(RAM+0xCD9D, 1), 0)
                self.assertEqual(len(cpu.pwm), 8)
                self.assertTrue(all(0 <= duty <= 1 for _, duty in cpu.pwm))

    def test_moving_rpm_release_latch_alone_does_not_force_a_low_mode_request(self):
        for image in self.images.values():
            cpu = AVLSPhaseMachine(image)
            self.assertEqual(cpu.request(3200)[0], 3)
            self.assertEqual(cpu.request(2800)[0], 3)
            self.assertEqual(cpu.read(RAM+0xCD9E, 1) & 4, 0)
            self.assertEqual(cpu.read(RAM+0xCD8F, 1) & 0x10, 0)
            cpu.write(RAM+0xB484, 0x80, 1)
            self.assertEqual(cpu.request(2800)[0], 1)

    def test_inhibit_holds_phase_and_bank_state_then_recovers(self):
        for image in self.images.values():
            cpu = AVLSPhaseMachine(image)
            _, phase_a, phase_b = cpu.request(3200)
            cpu.write(RAM+0xCD8F, cpu.read(RAM+0xCD8F, 1) | 0x80, 1)
            cpu.write(RAM+0xCD86, 1, 1)
            cpu.invoke(0x3FE14, PHASE_WRITES)
            self.assertEqual(cpu.read(RAM+0xCD88, 1), 3)
            self.assertEqual(cpu.phase(phase_b), (1, 1))
            self.assertEqual(cpu.pwm, [])
            self.assertEqual(cpu.request(3200)[0], 3)  # Parent clears <6000 inhibit.
            for phase in (phase_b, phase_a, phase_a):
                cpu.phase(phase)
            self.assertEqual(cpu.phase(0), (3, 3))

    def test_stopped_bank_reset_and_command_zero_are_separate_native_steps(self):
        for image in self.images.values():
            cpu = AVLSPhaseMachine(image)
            _, phase_a, phase_b = cpu.request(3200)
            for phase in (phase_b, phase_a, phase_a):
                cpu.phase(phase)
            cpu.write(RAM+0xB52C, 0x80, 1)
            cpu.invoke(0x40682, {(RAM+0xCD89, 1), (RAM+0xCD8A, 1)})
            self.assertEqual(cpu.phase(0), (1, 1))
            for bank in (0, 1):
                cpu.original_r[4] = bank
                cpu.invoke(0x40C94, BANK_WRITES)
                cpu.invoke(0x40CE6, BANK_WRITES)
            self.assertEqual(cpu.pwm[-2:], [(0, 0), (1, 0)])

    def test_periodic_output_uses_bank_modes_through_initial_and_running_intervals(self):
        for image in self.images.values():
            cpu = AVLSPhaseMachine(image)
            cpu.request(2800)
            self.assertEqual(cpu.periodic_output(), (0, 0))
            _, phase_a, phase_b = cpu.request(3200)
            cpu.phase(phase_b)
            cpu.phase(phase_a)
            cpu.phase(phase_a)
            for _ in range(80):  # Beyond native initial 55/67-call intervals.
                duties = cpu.periodic_output()
                self.assertTrue(all(0 <= d <= 100 for d in duties))
                self.assertEqual(cpu.read(RAM+0xCE08, 1) & 0x20, 0)
                self.assertEqual(cpu.read(RAM+0xCE09, 1) & 0x20, 0)
            self.assertEqual(tuple(cpu.get_float(RAM+a) for a in (0xCDF0, 0xCDF4)),
                             (71, 71))
            self.assertEqual(cpu.phase(0), (3, 3))

    def test_stored_bank_fault_can_override_output_without_changing_mode(self):
        for image in self.images.values():
            for mask, bank in ((0x80, 0), (0x40, 1)):
                cpu = AVLSPhaseMachine(image)
                _, phase_a, phase_b = cpu.request(3200)
                for phase in (phase_b, phase_a, phase_a):
                    cpu.phase(phase)
                # Actual native descriptor indices 151/150 both select 8EBC.
                cpu.write(RAM+0x8EBC, (mask << 8) | (mask ^ 0xFF), 2)
                observed = []
                for _ in range(300):
                    duty = cpu.periodic_output()
                    observed.append((cpu.read(RAM+0xCE08+bank, 1), duty[bank]))
                self.assertTrue(any(flags & 0x20 for flags, _ in observed))
                self.assertTrue(any(flags & 0x20 and duty == 0 for flags, duty in observed))
                self.assertTrue(any(flags & 0x20 and duty == 100 for flags, duty in observed))
                self.assertEqual(cpu.read(RAM+0xCD86, 1), 3)
                self.assertEqual(cpu.phase(0), (3, 3))


if __name__ == '__main__':
    unittest.main(verbosity=2)
