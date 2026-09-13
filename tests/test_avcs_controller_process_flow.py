#!/usr/bin/env python3
"""Connect bank cam observations to the periodic AVCS controller and OCV loop.

Cam observations, retained learning state and invocation order are explicit
boundaries. Native instructions perform the descriptor-indexed conversion,
error histories, qualification, duty arbitration and output. No hydraulic
response or wall-clock scheduler is simulated.
"""
import _test_paths
import unittest

from test_avcs_actuator_process_flow import (
    AVCSActuatorMachine, RAM, ROOT, DUTY_WRITES, DEVICE_WRITES,
    CURRENT_WRITES, FEEDBACK_WRITES, INIT_WRITES, safety,
)
from test_avcs_target_process_flow import STATE_WRITES, TARGET_WRITES, TRACK_WRITES

OBSERVATION_WRITES = {(RAM+a, 4) for a in range(0xC8A0, 0xC908, 4)}
CONTROLLER_WRITES = (STATE_WRITES | TARGET_WRITES | TRACK_WRITES |
    DUTY_WRITES | FEEDBACK_WRITES | {
        (RAM+a, 4) for a in (*range(0xC92C, 0xC948, 4),
                             *range(0xC94C, 0xC970, 4),
                             *range(0xC9C8, 0xC9E8, 4),
                             *range(0xC9EC, 0xC9FC, 4),
                             0x8264, 0x826C)} | {
        (RAM+a, 1) for a in (0x8274, 0xC908, 0xC90E, 0xC90F,
                             0xC910, 0xC911, 0xC912, 0xC948, 0xC970, 0xC9E8)} | {
        (RAM+a, 2) for a in (0xC90A, 0xC90C, 0xC924, 0xC926,
                             0x8268, 0x826A, 0x8270, 0x8272)})


class AVCSControllerMachine(AVCSActuatorMachine):
    LOOKUPS = AVCSActuatorMachine.LOOKUPS | {
        0x1D228, 0x12C26, 0x36986, 0x49530, 0x4963A,
        0x34BAC, 0x34D50, 0x34D6A, 0x33B92, 0x34CD2, 0x353B0,
        0x3475C, 0x345F4, 0x34880, 0x34920, 0x34F40,
        0x35BE8, 0x35A3C, 0x35CAA, 0x35B34, 0x35750, 0x34A1E,
        0x34208, 0x34304, 0x3438E, 0x3496E,
        0x35246, 0x35304, 0x35346, 0x352E0,
    }

    def __init__(self, image, rpm=2800):
        super().__init__(image, rpm)
        for a in range(0xC9D0, 0xC9FC):
            self.write(RAM+a, 0, 1)
        for a in (0xB151, 0xCA64, 0xCD77, 0x8274):
            self.write(RAM+a, 0, 1)
        self.put_float(RAM+0xB3B0, 85)
        self.put_float(RAM+0xB3BC, 30)
        self.execute(0x344A8, CONTROLLER_WRITES)
        self.execute(self.read(safety.LEAN_STATE_INIT_TASK_PTR, 4), INIT_WRITES)

    def observe(self, bank, raw_angle):
        self.put_float(RAM+0xB0B0+4*bank, raw_angle)
        self.original_r[4] = bank
        self.execute(0x34194, OBSERVATION_WRITES)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x0007:  # MUL.L Rm,Rn -> low 32-bit MACL.
            self.macl = self.r[n]*self.r[m] & 0xFFFFFFFF
        elif op & 0xF0FF == 0x001A:  # STS MACL,Rn.
            self.r[n] = self.macl
        elif op & 0xF00F == 0x000E:  # MOV.L @(R0,Rm),Rn.
            self.r[n] = self.load((self.r[0]+self.r[m]) & 0xFFFFFFFF, 4)
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1

    def periodic_controller(self):
        # Exact consecutive native AVCS subsequence in parent 11270; the
        # parent's other subsystems are covered separately, not stubbed here.
        for pointer in range(0x11444, 0x11498, 4):
            self.execute(self.read(pointer, 4), CONTROLLER_WRITES)
        return tuple(self.read(RAM+a, 2) for a in (0xF510, 0xF512))


class AVCSControllerProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        for image in cls.images:
            for a, b in ((0x34194, 0x353B0), (0x35734, 0x35D44),
                         (0x4C618, 0x4C690), (0x7BE2E, 0x7BFA8)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_bank_observation_descriptor_publishes_actual_angle_and_target_error(self):
        for image in self.images:
            cpu = AVCSControllerMachine(image)
            self.assertEqual(cpu.array(RAM+0x8264, 1), [40])
            self.assertEqual(cpu.get_float(RAM+0x826C), 40)
            for bank in (0, 1):
                cpu.put_float(RAM+0xC974+4*bank, 20+5*bank)
                for _ in range(50):
                    cpu.observe(bank, 50+5*bank)
                angle = cpu.get_float(RAM+0xC8C8+4*bank)
                error = cpu.get_float(RAM+0xC8E8+4*bank)
                self.assertAlmostEqual(angle, 10+5*bank, delta=.001)
                self.assertAlmostEqual(error, 20+5*bank-angle, delta=.00001)

    def test_complete_periodic_chain_uses_learned_permission_and_produces_pwm(self):
        for image in self.images:
            for learned in (False, True):
                cpu = AVCSControllerMachine(image)
                # This retained bit is an explicit fixture; learning itself
                # is exercised separately below rather than inferred.
                cpu.write(RAM+0x8274, 1 if learned else 2, 1)
                for _ in range(20):
                    cpu.airflow_task()
                    for bank in (0, 1):
                        cpu.observe(bank, 40)
                    cpu.execute(0xE0D0, CURRENT_WRITES)
                    output = cpu.periodic_controller()
                self.assertTrue(all(v > 0 for v in output))
                self.assertEqual(bool(cpu.read(RAM+0xC948, 1) & 1), learned)
                self.assertEqual(cpu.read(RAM+0xC929, 1), 5 if learned else 6)
                self.assertEqual(cpu.read(RAM+0xC894, 1) & 0x10, 0x10)

    def test_native_rest_learning_qualifies_then_enables_loaded_controller(self):
        for image in self.images:
            cpu = AVCSControllerMachine(image, rpm=1000)
            for bank in (0, 1):
                for _ in range(50):
                    cpu.observe(bank, 40)
            # Explicit entry to the native rest-learning operating state;
            # the 33B92 state selector is covered by the target suite.
            cpu.write(RAM+0xC894, 4, 1)
            for tick in range(1, 128):
                for entry in (0x3475C, 0x345F4, 0x34880, 0x34920):
                    cpu.execute(entry, CONTROLLER_WRITES)
                if tick == 63:
                    self.assertEqual(cpu.read(RAM+0xC908, 1), 0)
                if tick == 64:
                    self.assertEqual(cpu.read(RAM+0xC908, 1), 3)
                if tick < 127:
                    self.assertEqual(cpu.read(RAM+0x8274, 1), 2)
            self.assertEqual(cpu.read(RAM+0x8274, 1), 1)
            self.assertEqual(cpu.read(RAM+0xC908, 1), 7)
            # Native protected-record validation must accept both learned
            # float values and their duplicated checksum halfwords.
            for address in (0x8264, 0x826C):
                cpu.original_r[4] = RAM+address
                cpu.execute(0x4963A, CONTROLLER_WRITES)
                self.assertEqual(cpu.r[0], 0)
            cpu.put_float(RAM+0xB544, 3200)
            cpu.airflow_task()
            output = cpu.periodic_controller()
            self.assertEqual(cpu.read(RAM+0xC929, 1), 5)
            self.assertTrue(all(v > 0 for v in output))


if __name__ == '__main__':
    unittest.main(verbosity=2)
