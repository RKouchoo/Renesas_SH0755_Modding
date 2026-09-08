#!/usr/bin/env python3
"""Execute stock idle-air eligibility and pressure demand with bounded fixtures.

18B14, 2C760, 2CE50, the P30 getter and scalar helpers execute native ROM
instructions. Table interpolation is mathematical. Other digital switch
producers, scheduling, learning, actuator motion and engine response are not
reconstructed from the old log.
"""
from io import StringIO
from pathlib import Path
import unittest

from test_load_conditioning_execution import LoadConditioningMachine
from test_primary_fueling_execution import number, signed

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
GETTERS = {0x24AF2, 0x18CF4, 0x19EC4, 0x19C68, 0x652D0, 0x64FBC,
           0x64F7C, 0x1D228, 0x1A256}
GATE_WRITES = {(a, 2) for a in (0xFFFFC510, 0xFFFFC4FC, 0xFFFFC4D6)} | {
    (a, 1) for a in (0xFFFFC51C, 0xFFFFC51E, 0xFFFFC4D9)} | {
    (a, 4) for a in (0xFFFFC4BC, 0xFFFFC45C, 0xFFFFC4AC)}
DEMAND_WRITES = {(a, 4) for a in (0xFFFFC49C, 0xFFFFC4C8, 0xFFFFC4CC,
                                 0xFFFFC4F8, 0xFFFFC498)}
PEDAL_WRITES = {(0xFFFFB483, 1), (0xFFFFB484, 1), (0xFFFFB4CC, 2)}


class IdleAirMachine(LoadConditioningMachine):
    def __init__(self, image, rpm=1000, target=1000):
        super().__init__(image, rpm=rpm)
        for a in (0xFFFFBF20, 0xFFFFD26C, 0xFFFFD272,
                  0xFFFFB748, 0xFFFFB52C, 0xFFFFC778, 0xFFFFC51C,
                  0xFFFFC51E, 0xFFFFC4D9):
            self.write(a, 0, 1)
        self.write(0xFFFFB51A, 0x80, 1)
        self.write(0xFFFFB51C, 0x80, 1)
        self.write(0xFFFFB484, 0x80, 1)
        self.write(0xFFFFB2BC, 2, 1)
        self.write(0xFFFFC510, 0, 2)
        self.write(0xFFFFC4FC, 0, 2)
        self.write(0xFFFFC4D6, 8, 2)
        self.put_float(0xFFFFC468, target)
        self.put_float(0xFFFFC4BC, rpm)
        for a in (0xFFFFD164, 0xFFFFC588, 0xFFFFB54C,
                  0xFFFFC424, 0xFFFFC568):
            self.put_float(a, 0)
        self.put_float(0xFFFFC45C, .5)
        self.put_float(0xFFFFC4AC, .5)
        self.put_float(0xFFFFC48C, rpm)
        self.put_float(0xFFFFC490, rpm)
        self.put_float(0xFFFFC47C, 300)
        self.write(0xFFFFB483, 0, 1)
        self.write(0xFFFFB4CC, 0, 2)
        self.write(0xFFFFB51D, 0, 1)

    def call_lookup(self, target):
        if target in GETTERS:
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n = (op >> 8) & 15
        if op & 0xF00F == 0x3007:  # cmp/gt Rm,Rn (signed).
            m = (op >> 4) & 15
            self.t = signed(self.r[n], 32) > signed(self.r[m], 32)
        elif op & 0xF0FF == 0xF03D:  # ftrc FRn,FPUL.
            value = number(self.fr[n])
            assert -2**31 <= value < 2**31  # Bounded finite SSM fixtures.
            self.fpul = int(value) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x005A:  # sts FPUL,Rn.
            self.r[n] = self.fpul
        elif op & 0xF0FF == 0x4011:  # cmp/pz Rn.
            self.t = signed(self.r[n], 32) >= 0
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        assert self.instructions < 2000

    def table(self, target, descriptor, x, y):
        if descriptor == 0x604D0:
            assert target == 0x209C
            n, kind = self.read(descriptor, 2), self.read(descriptor + 2, 2)
            assert kind == 0x800
            axis = self.array(self.read(descriptor + 4, 4), n)
            data = self.read(descriptor + 8, 4)
            scale, bias = self.get_float(descriptor + 12), self.get_float(descriptor + 16)
            return self.interpolate(axis, [self.read(data + 2*i, 2) * scale + bias
                                           for i in range(n)], x)
        if descriptor not in (0x60828, 0x60844):
            return super().table(target, descriptor, x, y)
        assert target == 0x2150
        nx, ny = self.read(descriptor, 2), self.read(descriptor + 2, 2)
        ax = self.array(self.read(descriptor + 4, 4), nx)
        ay = self.array(self.read(descriptor + 8, 4), ny)
        data = self.read(descriptor + 12, 4)
        assert self.read(descriptor + 16, 4) == 0x08000000
        scale, bias = self.get_float(descriptor + 20), self.get_float(descriptor + 24)
        rows = [self.interpolate(ax, [self.read(data + 2*(row*nx + i), 2) * scale + bias
                                     for i in range(nx)], x) for row in range(ny)]
        return self.interpolate(ay, rows, y)

    def gate(self):
        self.invoke(0x2C760, GATE_WRITES)
        return self.read(0xFFFFC4D9, 1)

    def pedal_gate(self, pedal):
        self.put_float(0xFFFFB46C, pedal)
        self.invoke(0x18B14, PEDAL_WRITES)
        return self.read(0xFFFFB484, 1)

    def demand(self):
        self.invoke(0x2CE50, DEMAND_WRITES)
        return self.get_float(0xFFFFC498)


class IdleAirTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / 'master_patch/candidates/D2WD610H_idle_recovery_candidate.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for a, b in ((0x2C760, 0x2CB60), (0x2CE50, 0x2CF9C),
                     (0x18B14, 0x18C38), (0x18C80, 0x18C94),
                     (0x3184E, 0x3185C), (0x318DC, 0x318E0),
                     (0x258C, 0x25BC), (0x73802, 0x73804), (0x73A2C, 0x73A3C),
                     (0x7952A, 0x79540), (0x7965C, 0x79670), (0x796F0, 0x79700),
                     (0x604D0, 0x604E4), (0x60828, 0x60860), (0x7ADE4, 0x7AED2)):
            assert cls.image[a:b] == stock[a:b], hex(a)

    def test_b46c_is_ssm_accelerator_pedal_percent(self):
        cpu = IdleAirMachine(self.image)
        # P30 address 0x29 dispatches through the stock standard SSM table.
        entry = cpu.read(0x4B6FC + 4 * 0x29, 4)
        self.assertEqual(entry, 0x3184E)
        for pedal, expected in ((-2, 0), (0, 0), (20, 51), (100, 255), (110, 255)):
            cpu.put_float(0xFFFFB46C, pedal)
            cpu.put_float(0xFFFFB538, 73)  # Independent vehicle speed fixture.
            self.assertEqual(cpu.invoke(entry, set()), expected)

    def test_pedal_release_qualifies_before_air_feedback_delay(self):
        cpu = IdleAirMachine(self.image, rpm=558)
        self.assertFalse(cpu.pedal_gate(20) & 0x80)
        self.assertFalse(cpu.gate() & 8)
        # Actual task order runs pedal qualification before air eligibility.
        for count in range(1, 41):
            pedal_flags = cpu.pedal_gate(0)
            self.assertEqual(bool(pedal_flags & 0x80), count >= 3)
            enabled = cpu.gate()
            self.assertEqual(bool(enabled & 8), count == 40)
        self.assertEqual(cpu.read(0xFFFFC510, 2), 38)
        cpu.put_float(0xFFFFC45C, .5)
        cpu.put_float(0xFFFFC4AC, .5)
        self.assertFalse(cpu.pedal_gate(20) & 0x80)
        # Separate controller update counter can postpone clearing to its boundary.
        for _ in range(8):
            enabled = cpu.gate()
        self.assertFalse(enabled & 8)
        self.assertEqual(cpu.get_float(0xFFFFC45C), 0)
        self.assertEqual(cpu.get_float(0xFFFFC4AC), 0)

    def test_air_feedback_has_its_own_38_call_gate(self):
        for rpm in (558, 1000):
            cpu = IdleAirMachine(self.image, rpm=rpm)
            for count in range(1, 38):
                self.assertFalse(cpu.gate() & 8, count)
            self.assertEqual(cpu.read(0xFFFFC510, 2), 37)
            self.assertEqual(cpu.gate() & 9, 9)
            self.assertEqual(cpu.read(0xFFFFC510, 2), 38)
            self.assertEqual(cpu.read(0xFFFFC4D6, 2), 8)

    def test_ignition_idle_flag_is_not_air_feedback_permission(self):
        for ignition_idle in (0, 2):
            cpu = IdleAirMachine(self.image, rpm=558)
            cpu.write(0xFFFFB2BC, ignition_idle, 1)
            for _ in range(38):
                enabled = cpu.gate()
            self.assertEqual(enabled & 9, 9)
        for inputs in ({0xFFFFB484: 0}, {0xFFFFB51A: 0, 0xFFFFB51C: 0},
                       {0xFFFFD26C: 0x10}, {0xFFFFD26C: 0x80}, {0xFFFFD272: 0x80}):
            cpu = IdleAirMachine(self.image, rpm=558)
            for address, value in inputs.items():
                cpu.write(address, value, 1)
            for _ in range(48):
                self.assertFalse(cpu.gate() & 8, inputs)
            self.assertEqual(cpu.read(0xFFFFB2BC, 1), 2)
            self.assertEqual(cpu.get_float(0xFFFFC45C), 0)
            self.assertEqual(cpu.get_float(0xFFFFC4AC), 0)

    def test_active_pressure_demand_responds_to_rpm_error_and_delta(self):
        for rpm, delta, expected in ((1400, 0, 298.203125),
                                      (558, 0, 304.796875), (558, -50, 330)):
            cpu = IdleAirMachine(self.image, rpm=rpm)
            cpu.write(0xFFFFC4D9, 8, 1)
            cpu.put_float(0xFFFFB54C, delta)
            self.assertAlmostEqual(cpu.demand(), expected, places=5)
            self.assertAlmostEqual(cpu.get_float(0xFFFFC49C), expected-300, places=5)

    def test_pressure_demand_retains_state_when_gated_off(self):
        cpu = IdleAirMachine(self.image, rpm=558)
        cpu.put_float(0xFFFFC498, 300)
        self.assertEqual(cpu.demand(), 300)
        self.assertEqual(cpu.writes, [(a, size) for a, size in cpu.writes
                                     if cpu.min_sp <= a < cpu.STACK])

    def test_unused_mass_target_mode_is_not_the_active_pressure_target(self):
        cpu = IdleAirMachine(self.image, rpm=558)
        cpu.write(0xFFFFC4D9, 8, 1)
        # Native mode byte at 7952C selects C47C+C49C, not C4F8.
        self.assertEqual(self.image[0x7952C], 0)
        self.assertGreater(cpu.demand(), 300)
        altered = bytearray(self.image)
        altered[0x7952C] = 1  # In-memory negative control; never a BIN output.
        other = IdleAirMachine(altered, rpm=558)
        other.write(0xFFFFC4D9, 8, 1)
        self.assertLess(other.demand(), 1)
        self.assertNotAlmostEqual(cpu.get_float(0xFFFFC498), other.get_float(0xFFFFC498))


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(IdleAirTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Idle air: {result.testsRun} execution test groups passed')
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
