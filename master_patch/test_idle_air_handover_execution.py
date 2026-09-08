#!/usr/bin/env python3
"""Execute the timer divider and stationary deceleration-air handover.

D390/D3C2 and task-activation wrappers are native instructions; activation
acceptance is a fixture, not a hardware timer or full task/IRQ simulation.
2B9F2/2BB26/2BA10 run with explicit switch, pressure and base-air fixtures.
Table interpolation is mathematical. No vehicle response is predicted.
"""
from io import StringIO
from pathlib import Path
import unittest

from test_idle_air_execution import IdleAirOutputMachine

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
TIMER_WRITES = {(0xFFFFB01E, 1), (0xFFFFB01C, 2)}
DECEL_WRITES = {(0xFFFFC456, 2)} | {
    (a, 1) for a in (0xFFFFC454, 0xFFFFC458, 0xFFFFC459)} | {
    (a, 4) for a in (0xFFFFC438, 0xFFFFC43C, 0xFFFFC440, 0xFFFFC444,
                     0xFFFFC448, 0xFFFFC44C, 0xFFFFC450)}


class TimerMachine(IdleAirOutputMachine):
    def __init__(self, image):
        super().__init__(image)
        self.write(0xFFFFF718, 0, 2)
        self.write(0xFFFFB01E, 0, 1)
        self.write(0xFFFFB01C, 0, 2)
        self.activations = []
        self.tick_number = 0

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        if op & 0xF0FF == 0x4008:  # shll2 Rn; T is unchanged.
            n = (op >> 8) & 15
            self.r[n] = (self.r[n] << 2) & 0xFFFFFFFF
        elif op & 0xF00F == 0x000E:  # mov.l @(R0,Rm),Rn.
            n, m = (op >> 8) & 15, (op >> 4) & 15
            self.r[n] = self.load((self.r[0] + self.r[m]) & 0xFFFFFFFF, 4)
        elif op & 0xF0FF == 0x4001:  # shlr Rn; shifted-out bit goes to T.
            n = (op >> 8) & 15
            self.t = bool(self.r[n] & 1)
            self.r[n] >>= 1
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        assert self.instructions < 2000

    def call_lookup(self, target):
        if target == 0x3A28:
            self.activations.append((self.tick_number, self.r[4]))
            self.poison_scratch()
            self.r[0] = 0  # Activation accepted; no task execution modeled.
        elif target in (0xCE24, 0xCE40, 0xCE5C, 0xCE78, 0xCE94, 0xCEB0,
                        0xCECC, 0xCEE8, 0xCF04, 0xCF20, 0xCF3C):
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def tick(self):
        self.tick_number += 1
        self.invoke(0xD3C2, TIMER_WRITES)


class HandoverMachine(IdleAirOutputMachine):
    def __init__(self, image, rpm=1000):
        super().__init__(image, rpm=rpm)
        self.put_float(0xFFFFB3AC, 40)
        self.put_float(0xFFFFB2AC, 760)  # Unlogged pressure input to 6080C.
        self.put_float(0xFFFFC498, 300)
        for a in (0xFFFFC4A0, 0xFFFFC4A4, 0xFFFFC4A8):
            self.put_float(a, 0)
        self.write(0xFFFFD26F, 0, 1)
        # 19D96's digital-state producer is outside this bounded fixture.
        self.write(self.read(0x19EDC, 4), 0, 1)
        self.write(0xFFFF8E20, 0, 1)
        self.write(0xFFFFC456, 0, 2)
        for a in (0xFFFFC454, 0xFFFFC458, 0xFFFFC459):
            self.write(a, 0, 1)
        for a in (0xFFFFC438, 0xFFFFC43C, 0xFFFFC440, 0xFFFFC444,
                  0xFFFFC448, 0xFFFFC44C, 0xFFFFC450):
            self.put_float(a, 0)

    def call_lookup(self, target):
        if target in (0x2BB26, 0x2BA10, 0x19D96, 0x65168):
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def table(self, target, descriptor, x, y):
        if descriptor not in (0x602F0, 0x60408, 0x6080C):
            return super().table(target, descriptor, x, y)
        n, kind = self.read(descriptor, 2), self.read(descriptor + 2, 2)
        ax = self.array(self.read(descriptor + 4, 4), n)
        if target == 0x209C:
            assert kind in (0x400, 0x800)
            size = kind >> 10
            data = self.read(descriptor + 8, 4)
            scale, bias = self.get_float(descriptor + 12), self.get_float(descriptor + 16)
            values = [self.read(data + i*size, size) * scale + bias for i in range(n)]
            return self.interpolate(ax, values, x)
        assert target == 0x2150 and descriptor == 0x6080C
        ay = self.array(self.read(descriptor + 8, 4), kind)
        data = self.read(descriptor + 12, 4)
        assert self.read(descriptor + 16, 4) == 0x08000000
        scale, bias = self.get_float(descriptor + 20), self.get_float(descriptor + 24)
        rows = [self.interpolate(ax, [self.read(data + 2*(j*n + i), 2) * scale + bias
                                     for i in range(n)], x) for j in range(kind)]
        return self.interpolate(ay, rows, y)

    def decel_air(self):
        self.invoke(0x2B9F2, DECEL_WRITES)
        return self.get_float(0xFFFFC438)

    def release_step(self, pedal=0):
        # 10A28: pedal qualification precedes 2C760; pressure output at
        # 10E54 precedes deceleration air at 10E5A. Other producers remain
        # explicit fixtures, including pressure, shaped RPM and gain history.
        self.pedal_gate(pedal)
        flags = self.gate()
        self.pressure_output()
        decel = self.decel_air()
        return decel, flags


class HandoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0xD390, 0xD444), (0xCE24, 0xCF58), (0xD0AC, 0xD0B0),
                           (0xFB94, 0xFBC0), (0xFBFC, 0xFC05), (0x4A2C, 0x4A3C),
                           (0x10A4E, 0x10A5A), (0x10C8C, 0x10C94),
                           (0x10E10, 0x10E5E), (0x11054, 0x11088),
                           (0x179DC, 0x179E2), (0x17A9C, 0x17AA0),
                           (0x2B9F2, 0x2BD5C), (0x19D96, 0x19DA4), (0x19EDC, 0x19EE0),
                           (0x65168, 0x6517C), (0x65206, 0x65208), (0x79538, 0x7953E),
                           (0x79628, 0x7965C), (0x602F0, 0x60304), (0x60408, 0x6041C),
                           (0x6080C, 0x60828), (0x7AD24, 0x7ADAC)):
            assert cls.image[start:end] == stock[start:end], hex(start)

    def test_native_timer_initialization_and_every_eighth_tick_task(self):
        cpu = TimerMachine(self.image)
        cpu.invoke(0xD390, {(a, 2) for a in (0xFFFFF710, 0xFFFFF718,
                                            0xFFFFF71A, 0xFFFFF71C)})
        self.assertEqual(cpu.read(0xFFFFF710, 2), 2)
        self.assertEqual(cpu.read(0xFFFFF718, 2), 0xC0)
        self.assertEqual(cpu.read(0xFFFFF71C, 2), 2499)
        for _ in range(1024):
            cpu.tick()
        task9 = [tick for tick, task in cpu.activations if task == 9]
        self.assertEqual(task9, list(range(3, 1025, 8)))
        self.assertEqual(cpu.read(0x4A34, 4), 0x684C)
        self.assertEqual(cpu.read(0x6A40, 4), 0x10A28)
        # Renesas CMT CKS=00 selects Pphi/8. Pphi=phi/2. At the project's
        # nominal 40-MHz CPU clock this is a 1-ms timer and 8-ms task period.
        # This arithmetic does not measure oscillator frequency or lost IRQs.
        self.assertEqual((2499 + 1) * 8 / (40_000_000 / 2) * 8, .008)

    def test_task_calls_gate_and_pressure_output_before_deceleration_air(self):
        cpu = HandoverMachine(self.image)
        # Pin the call instructions and their PC-relative targets. This is
        # call-order evidence, not execution of every intervening task routine.
        for pc, pool, target in ((0x10A54, 0x10C90, 0x17984),
                                 (0x179DC, 0x17A9C, 0x18B14),
                                 (0x10E10, 0x11054, 0x2C760),
                                 (0x10E52, 0x11080, 0x2D0AC),
                                 (0x10E58, 0x11084, 0x2B9F2)):
            op = cpu.read(pc, 2)
            self.assertEqual(op >> 12, 0xD)
            self.assertEqual(((pc + 4) & ~3) + (op & 255)*4, pool)
            reg = (op >> 8) & 15
            self.assertEqual(cpu.read(pc + 2, 2), 0x400B | reg << 8)
            self.assertEqual(cpu.read(pool, 4), target)
        self.assertEqual(cpu.read(0x10C8C, 4), 0x1A838)  # B688, same task.

    def test_stationary_handover_all_initial_controller_phases(self):
        for phase in range(1, 9):
            with self.subTest(phase=phase):
                cpu = HandoverMachine(self.image, rpm=558)
                for _ in range(16):
                    cpu.release_step(20)
                self.assertAlmostEqual(cpu.get_float(0xFFFFC438), .666, places=6)
                cpu.write(0xFFFFC4D6, phase, 2)
                for count in range(1, 57):
                    air, flags = cpu.release_step()
                    self.assertEqual(bool(flags & 8), count >= 40)
                    expected = .666 if count < 40 else .066 if count < 48 else 0
                    self.assertAlmostEqual(air, expected, places=6)
                    if count >= 40:
                        self.assertGreater(cpu.get_float(0xFFFFC45C), 0)
                # Reopening resets qualification. The same .6-per-boundary
                # slew restores the decel term over two updates.
                for _ in range(8):
                    air, flags = cpu.release_step(20)
                self.assertFalse(flags & 8)
                self.assertEqual(cpu.read(0xFFFFC456, 2), 0)
                self.assertAlmostEqual(air, .6, places=6)
                for _ in range(8):
                    air, flags = cpu.release_step(20)
                self.assertAlmostEqual(air, .666, places=6)

    def test_inhibit_flags_do_not_retain_the_stationary_decel_allowance(self):
        for address, mask in ((0xFFFFD26C, 0x10), (0xFFFFD272, 0x80)):
            with self.subTest(address=hex(address), mask=mask):
                cpu = HandoverMachine(self.image, rpm=558)
                for _ in range(16):
                    cpu.release_step(20)
                cpu.write(address, mask, 1)
                for count in range(1, 57):
                    air, flags = cpu.release_step()
                    self.assertFalse(flags & 8)
                    self.assertEqual(cpu.get_float(0xFFFFC45C), 0)
                    expected = .666 if count < 40 else .066 if count < 48 else 0
                    self.assertAlmostEqual(air, expected, places=6)
                # Negative control: clear only the imposed inhibit. This is
                # not an instruction to clear/bypass vehicle fault protection.
                cpu.write(address, 0, 1)
                for _ in range(8):
                    cpu.release_step()
                self.assertTrue(cpu.read(0xFFFFC4D9, 1) & 8)
                self.assertGreater(cpu.get_float(0xFFFFC45C), 0)

    def test_maf_and_speed_fallbacks_have_distinct_air_effects(self):
        # Native 65168 (MAF fallback) and 64F7C (speed fallback) both
        # impose a 1.0 decel-air minimum. Only the latter gates feedback.
        for address, mask, eligible in ((0xFFFFD26F, 0x40, True),
                                         (0xFFFFD26C, 0x80, False)):
            with self.subTest(address=hex(address), mask=mask):
                cpu = HandoverMachine(self.image, rpm=558)
                cpu.write(address, mask, 1)
                for _ in range(16):
                    cpu.release_step(20)
                for _ in range(56):
                    air, _ = cpu.release_step()
                self.assertEqual(air, 1)
                self.assertEqual(bool(cpu.read(0xFFFFC4D9, 1) & 8), eligible)
                self.assertEqual(cpu.get_float(0xFFFFC45C) > 0, eligible)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(HandoverTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Idle handover: {result.testsRun} execution test groups passed')
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
