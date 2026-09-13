#!/usr/bin/env python3
"""Follow WB validity through cruise cancellation, pedal selection and overrun.

Native routines and lookup helpers execute from each saved image. Button,
gear, speed, pedal samples and other faults are explicit fixtures; this is
not a reconstruction of unlogged cruise state or physical throttle motion.
"""
import _test_paths
from itertools import product
import unittest

from test_wideband_status_dependency_flow import WidebandStatusMachine
from test_wideband_fuel_guard_execution import INHIBIT_GETTERS
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_avls_phase_process_flow import AVLSPhaseMachine

ROOT, RAM = _test_paths.ROOT, 0xFFFF0000
SET_WRITES = {(RAM+a, 1) for a in (0xCC00, 0xCC01, 0xCC2C)}
PEDAL_WRITES = {(RAM+a, 4) for a in (0xB474, 0xB478, 0xB470)}
RELEASE_WRITES = {(RAM+a, 1) for a in (0xB483, 0xB484)} | {(RAM+0xB4CE, 2)}
OVERRUN_WRITES = {(RAM+a, 1) for a in (0xBF20, 0xBF21, 0xBF68)} | {
    (RAM+a, 2) for a in (0xBF64, 0xBF66, 0xBF62, 0xBF2C, 0xB744)}
THRESHOLD_WRITES = {(RAM+a, 2) for a in (*range(0xBF2E, 0xBF3A, 2),
                                      *range(0xBF48, 0xBF54, 2),
                                      *range(0xBF56, 0xBF62, 2))} | {(RAM+0xBF40, 4)}


class WBCruiseMachine(WidebandStatusMachine):
    LOOKUPS = WidebandStatusMachine.LOOKUPS | set(INHIBIT_GETTERS) | {
        0x368C6, 0x3C616, 0x450F0, 0x1474C, 0x14738, 0x14724,
        0x3B430, 0x65280, 0x65294, 0x653A6, 0x3C62A, 0x2BD04,
        0x65244, 0x19D08, 0x15192, 0x35DF6, 0x4520C, 0x3B4B0,
        0x2483C, 0x247BC, 0x254C,
    }

    def __init__(self, image, rpm=2800):
        super().__init__(image)
        for a in (0xCC00, 0xCC01, 0xCC02, 0xCC2C, 0xCC6D, 0xCEE5,
                  0xCA49, 0xB24D, 0xCBFD, 0xCBFE, 0xCAAB, 0xB483,
                  0xB484, 0xB51D, 0xB51C, 0xBF68, 0xB2BC, 0xCC54, 0xCEF8,
                  0xC454):
            self.write(RAM+a, 0, 1)
        for a in (0xB4CE, 0xB480, 0xBF64, 0xBF66, 0xBF62, 0xBF2C):
            self.write(RAM+a, 0, 2)
        self.write(RAM+0xB744, 0, 2)
        self.write(RAM+0xB28C, image[0x737C9], 1)
        self.write(RAM+0xCD49, 2, 1)
        self.write(RAM+0xB688, 1000, 2)
        for a, value in ((0xB544, rpm), (0xB54C, 0), (0xCAC4, 40),
                         (0xCBEC, 32), (0xCBF0, 255), (0xCB60, 60),
                         (0xB498, 40), (0xB49C, 40), (0xBF24, 1500),
                         (0xBF3C, 0), (0xBF44, 200)):
            self.put_float(RAM+a, value)
        self.execute(0x240F6, THRESHOLD_WRITES)

    def cruise_step(self, raw):
        self.aggregate_and_permission(raw)
        self.execute(0x39CFC, {(RAM+0xCBFE, 1)})
        self.execute(0x3A0C8, SET_WRITES)
        self.execute(0x3A482, {(RAM+0xCC00, 1)})
        return bool(self.read(RAM+0xCC00, 1) & 1)

    def engage(self):
        self.write(RAM+0xCAA9, self.read(RAM+0xCAA9, 1) | 4, 1)
        assert self.cruise_step(18000)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x0004:  # MOV.B Rm,@(R0,Rn).
            self.write((self.r[0]+self.r[n]) & 0xFFFFFFFF, self.r[m], 1, record=True)
        elif op & 0xF00F == 0x000D:  # MOV.W @(R0,Rm),Rn; sign extend.
            value = self.load((self.r[0]+self.r[m]) & 0xFFFFFFFF, 2)
            self.r[n] = (value if value < 32768 else value-65536) & 0xFFFFFFFF
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1

    def pedal_step(self, sample):
        self.put_float(RAM+0xB498, sample)
        self.put_float(RAM+0xB49C, sample)
        self.execute(0x181EA, PEDAL_WRITES)
        self.execute(0x182AC, PEDAL_WRITES)
        self.execute(0x1831A, RELEASE_WRITES)
        self.execute(0x183CE, RELEASE_WRITES)
        return self.get_float(RAM+0xB470)

    def overrun(self):
        self.execute(0x24374, {(RAM+a, 4) for a in (0xBF24, 0xBF28, 0xBF44, 0xBF3C)})
        self.execute(0x24570, OVERRUN_WRITES)
        return self.read(RAM+0xB744, 2)


class WidebandCruiseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x39CFC, 0x3A1B0), (0x3A482, 0x3A4FA),
                         (0x181EA, 0x184BC), (0x240F6, 0x24B24),
                         (0x4B46C, 0x4B64C), (0x75EBC, 0x75EC8),
                         (0x7CC10, 0x7CC20), (0x73A14, 0x73A18),
                         (0x5EB54, 0x5EB60), (0x741D4, 0x74224),
                         (0x1C5D4, 0x1C91E)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_invalid_wb_cancels_native_cruise_without_automatic_reengagement(self):
        for image, rpm, raw in product(self.images, (2500, 2800, 3200, 3500, 4144),
                                       (0, 65535)):
            cpu = WBCruiseMachine(image, rpm)
            cpu.engage()
            self.assertEqual(cpu.read(RAM+0xCBFE, 1) & 4, 4)
            self.assertFalse(cpu.cruise_step(raw))
            self.assertEqual(cpu.read(RAM+0xCBFE, 1) & 4, 0)
            self.assertEqual(cpu.read(RAM+0xCC00, 1) & 7, 0)
            self.assertEqual(cpu.read(RAM+0xB744, 2), 0)
            self.assertFalse(cpu.cruise_step(18000))

    def test_cancelled_cruise_restores_driver_sample_instead_of_low_substitute(self):
        for image, sample, demand in product(self.images, (0, 10, 40, 80), (0, 20, 100)):
            cpu = WBCruiseMachine(image)
            cpu.put_float(RAM+0xCB60, demand)
            cpu.engage()
            cpu.pedal_step(sample)
            self.assertEqual(cpu.get_float(RAM+0xB474), max(sample, demand))
            cpu.cruise_step(0)
            selected = cpu.pedal_step(sample)
            self.assertEqual(cpu.get_float(RAM+0xB474), sample)
            axis, values = cpu.array(0x741D4, 10), cpu.array(0x741FC, 10)
            self.assertAlmostEqual(selected, cpu.interpolate(axis, values, sample), delta=.0001)

    def test_overrun_still_requires_pedal_release_after_wb_cancellation(self):
        for image, rpm, sample in product(self.images, (2500, 2800, 3200, 3500, 4144),
                                          (10, 40, 80)):
            cpu = WBCruiseMachine(image, rpm)
            cpu.engage()
            cpu.cruise_step(0)
            for _ in range(16):
                cpu.pedal_step(sample)
                self.assertEqual(cpu.overrun(), 0)
                self.assertEqual(cpu.read(RAM+0xBF20, 1) & 0x20, 0)
            # Positive control: the same RPM/invalid-WB fixture can cut on
            # release, then restores all channels after the native delay.
            for _ in range(120):
                cpu.pedal_step(0)
                mask = cpu.overrun()
            self.assertEqual(mask, 63)
            masks = []
            for _ in range(13):
                cpu.pedal_step(sample)
                masks.append(cpu.overrun())
            self.assertEqual(masks, [42]*12+[0])

    def test_pedal_fault_substitution_is_independent_of_cruise_permission(self):
        for image, faults, paired in product(self.images, (8, 16, 24), (0, 128)):
            cpu = WBCruiseMachine(image)
            cpu.write(RAM+0xD271, faults, 1)
            cpu.write(RAM+0xD274, paired, 1)
            outputs = []
            for active in (0, 1):
                cpu.write(RAM+0xCC00, active, 1)
                cpu.put_float(RAM+0xB498, 40)
                cpu.put_float(RAM+0xB49C, 25)
                cpu.execute(0x181EA, PEDAL_WRITES)
                outputs.append(cpu.get_float(RAM+0xB474))
            self.assertEqual(outputs[0], outputs[1])
            self.assertAlmostEqual(outputs[0], 25 if paired and faults != 24 else 5.9,
                                   delta=.00001)

    def test_avls_cruise_override_has_a_separate_disabled_speed_gate(self):
        for image in self.images:
            producer = WBCruiseMachine(image)
            producer.engage()
            active = producer.read(RAM+0xCC00, 1) & 1
            producer.cruise_step(0)
            cancelled = producer.read(RAM+0xCC00, 1) & 1
            for speed in (30, 53, 9999, 10000):
                modes = []
                for state in (active, cancelled):
                    consumer = AVLSPhaseMachine(image, rpm=2800)
                    consumer.write(RAM+0xCC00, state, 1)
                    consumer.put_float(RAM+0xB538, speed)
                    modes.append(consumer.request(2800)[0])
                # 10,000 is an intentional calibration-boundary control,
                # not a plausible vehicle state or a logged cruise event.
                self.assertEqual(modes, [3, 1] if speed == 10000 else [1, 1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
