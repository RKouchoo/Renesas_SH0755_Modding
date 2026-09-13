#!/usr/bin/env python3
"""Run SD/load into native AVCS qualification, target selection and histories.

Oil/engine state, actual cam observations and task invocations are supplied.
Native lookup helpers execute opcodes. These tests do not simulate hydraulic
response, coil/solenoid hardware, or real task and interrupt scheduling.
"""
import _test_paths
from itertools import product
import struct
import unittest

from test_airflow_task_process_flow import AirflowTaskMachine
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT, RAM = _test_paths.ROOT, 0xFFFF0000
STATE_WRITES = {(RAM+a, 1) for a in (0xC894, 0xC895, 0xC89E)} | {
    (RAM+a, 2) for a in (0xC896, 0xC898, 0xC89A, 0xC89C)}
TARGET_WRITES = {(RAM+a, 4) for a in range(0xC974, 0xC98C, 4)}
TRACK_WRITES = {(RAM+a, 4) for a in (*range(0xC98C, 0xC99C, 4),
                                    *range(0xC9A0, 0xC9C4, 4))} | {
    (RAM+0xC99C, 1), (RAM+0xC9C4, 2)}


class AVCSTargetMachine(AirflowTaskMachine):
    LOOKUPS = AirflowTaskMachine.LOOKUPS | {
        0x148EE, 0x19D88, 0x18D08, 0x3BB26, 0x33FFC, 0x33DDC,
        0x33EA0, 0x2118,
    }

    def __init__(self, image, rpm=2800, oil=85):
        super().__init__(image, rpm=rpm)
        # Explicit zero initialization of this subsystem's work, then native
        # state/target services. Actual angle and learned offsets start at 0.
        for a in range(0xC894, 0xC9D0):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xB28C, image[0x737C9], 1)
        self.write(RAM+0xCC4C, 0x40, 1)
        self.put_float(RAM+0xCF94, oil)
        self.put_float(RAM+0xB6C0, 10)
        self.execute(0x35734, TRACK_WRITES)

    def state(self):
        self.execute(0x33B92, STATE_WRITES)
        return self.read(RAM+0xC894, 1)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        if op & 0xF00F == 0x0004:  # MOV.B Rm,@(R0,Rn).
            n, m = (op >> 8) & 15, (op >> 4) & 15
            self.write((self.r[n]+self.r[0]) & 0xFFFFFFFF, self.r[m], 1, record=True)
            self.trace.append((pc, op))
            self.pc += 2
            self.instructions += 1
        else:
            return super().step(in_delay)

    def targets(self):
        self.execute(0x353B0, TARGET_WRITES)
        return tuple(self.get_float(RAM+a) for a in (0xC974, 0xC978, 0xC97C, 0xC980))

    def tracking(self):
        self.execute(0x35750, TRACK_WRITES)

    def independent_target(self, mode):
        # Independent table decode/interpolation; execution above still uses
        # actual table helpers, including packed-word format dispatch.
        desc = 0x60C34 if mode == 1 else 0x60C50
        nx, ny, ax, ay, data, fmt, scale, bias = struct.unpack_from('>HHIIIIff', self.image, desc)
        assert fmt == 0x08000000
        x = self.get_float(RAM+0xB438)
        rows = [self.interpolate(self.array(ax, nx),
                [self.read(data+2*(j*nx+i), 2)*scale+bias for i in range(nx)], x)
                for j in range(ny)]
        angle = self.interpolate(self.array(ay, ny), rows, self.get_float(RAM+0xB544))
        count, fmt, axis, values, scale, bias = struct.unpack_from('>HHIIff', self.image, 0x60A80)
        assert fmt == 0x400
        gain = self.interpolate(self.array(axis, count),
                                [self.read(values+i, 1)*scale+bias for i in range(count)],
                                self.get_float(RAM+0xCF94))
        return angle*gain


class AVCSTargetProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x33B92, 0x34194), (0x353B0, 0x35A3C),
                         (0x60A80, 0x60B74), (0x7BE30, 0x7BF60)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_complete_sd_state_and_target_chain_selects_each_lift_map(self):
        for image, rpm, mode, oil in product(self.images, (2500, 2800, 3000, 3500),
                                             (1, 3), (20, 85)):
            cpu = AVCSTargetMachine(image, rpm, oil)
            cpu.write(RAM+0xCD86, mode, 1)
            for _ in range(3):
                cpu.airflow_task()
            self.assertEqual(cpu.state() & 0x5D, 0x10)
            first, second, filtered0, filtered1 = cpu.targets()
            expected = cpu.independent_target(mode)
            self.assertAlmostEqual(first, expected, delta=.00001)
            self.assertEqual(first, second)
            self.assertAlmostEqual(filtered0, first*.96875, delta=.00001)
            self.assertEqual(filtered0, filtered1)

    def test_feature_crank_and_unsupported_modes_clear_targets_and_histories(self):
        for image, boundary in product(self.images, ('feature', 'crank', 'mode2', 'mode4')):
            cpu = AVCSTargetMachine(image)
            cpu.airflow_task()
            cpu.state()
            self.assertGreater(cpu.targets()[0], 0)
            if boundary == 'feature':
                cpu.write(RAM+0xCC4C, 0, 1)
            elif boundary == 'crank':
                cpu.write(RAM+0xB748, 128, 1)
            else:
                cpu.write(RAM+0xCD86, int(boundary[-1]), 1)
            self.assertEqual(cpu.targets(), (0, 0, 0, 0))
            self.assertEqual(cpu.get_float(RAM+0xC984), 0)

    def test_stored_state_fault_has_priority_and_native_low_runtime_qualifies_inhibit(self):
        for image in self.images:
            cpu = AVCSTargetMachine(image)
            cpu.airflow_task()
            self.assertEqual(cpu.state() & 0x5D, 0x10)
            cpu.targets()
            cpu.write(RAM+0xC895, 2, 1)
            self.assertEqual(cpu.state() & 0x5D, 1)
            self.assertEqual(cpu.targets()[:2], (0, 0))
            cpu.write(RAM+0xC895, 1, 1)
            self.assertEqual(cpu.state() & 0x5D, 0x40)
            cpu.write(RAM+0xC895, 0, 1)
            cpu.write(RAM+0xB688, 124, 2)
            self.assertEqual(cpu.state() & 0x5D, 8)
            cpu.write(RAM+0xB688, 125, 2)
            self.assertEqual(cpu.state() & 0x5D, 0x10)

    def test_tracking_consumer_publishes_history_and_resets_qualification_when_disabled(self):
        for image in self.images:
            cpu = AVCSTargetMachine(image)
            cpu.airflow_task()
            cpu.state()
            targets = cpu.targets()
            cpu.write(RAM+0xC9C4, 100, 2)
            cpu.write(RAM+0xC99C, 0xFF, 1)
            cpu.put_float(RAM+0xC8D0, 11)
            cpu.put_float(RAM+0xC8D4, 12)
            cpu.tracking()
            self.assertEqual(cpu.read(RAM+0xC9C4, 2), 0)
            self.assertEqual(cpu.read(RAM+0xC99C, 1), 0xFE)
            self.assertEqual(cpu.array(RAM+0xC9A4, 4), [targets[2], targets[3], 11, 12])


if __name__ == '__main__':
    unittest.main(verbosity=2)
