#!/usr/bin/env python3
"""Check the installed patch's signal identities with independent pedal inputs.

Injected code executes native opcodes. SD table interpolation is modeled;
the pressure wrapper's stock target and rotational idle's stock final timing
are explicit fixtures. Other engine inputs stay fixed while pedal changes.
This isolates added decisions, not the engine's physical response to pedal.
"""
from io import StringIO
from pathlib import Path
import struct
import unittest

import build_master_patch as master
import test_hook_execution as sd_test
from test_idle_air_execution import IdleAirMachine
from test_wideband_fuel_guard_execution import GuardMachine, safety

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
PEDAL_START, PEDAL_END = 0xFFFFB46C, 0xFFFFB4D0
PEDAL = 0xFFFFB46C
roti = master.rotational_idle


def seed_pedal(cpu, value):
    for address in range(PEDAL_START, PEDAL_END):
        cpu.write(address, 0xA5, 1)
    cpu.put_float(PEDAL, value)


def pedal_accesses(cpu):
    return ([a for a in cpu.reads if PEDAL_START <= a < PEDAL_END],
            [(a, n) for a, n in cpu.writes if a < PEDAL_END and a+n > PEDAL_START])


def substitute_literal(image, start, size, old, new):
    before, after = struct.pack('>I', old), struct.pack('>I', new)
    region = image[start:start+size]
    assert region.count(before) == 1
    altered = bytearray(image)
    offset = start + region.index(before)
    altered[offset:offset+4] = after
    return bytes(altered)  # Negative control in memory; no BIN write.


class RotationalFixture(IdleAirMachine):
    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        if op & 0xF0FF == 0x4010:  # dt Rn: decrement, then test for zero.
            n = (op >> 8) & 15
            self.r[n] = (self.r[n] - 1) & 0xFFFFFFFF
            self.t = self.r[n] == 0
            self.pc += 2
            self.instructions += 1
            assert self.instructions < 2000
        else:
            super().step(in_delay)

    def call_lookup(self, target):
        if target == roti.STOCK_FINAL_TIMING_TASK:
            self.entered.append(target)
            for address in range(roti.FINAL_TIMING_ARRAY, roti.FINAL_TIMING_ARRAY+24, 4):
                self.write(address, sd_test.bits(20), record=True)
            self.poison_scratch()
        else:
            super().call_lookup(target)


class PedalDependencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes()
        cls.stock, _, cls.blobs, _ = master.build_image()

    def test_pedal_producers_and_dbw_calibration_remain_stock(self):
        # Real pedal producer/qualifiers, DBW/idle code and calibration.
        for start, end in ((0x17984, 0x18DAC), (0x2AAAC, 0x2F390),
                           (0x79500, 0x7B000), (0x73A2C, 0x73B54)):
            self.assertEqual(self.image[start:end], self.stock[start:end], hex(start))
        # Emitted literal inventory complements execution below; not a general
        # proof against every possible computed address or stock callee input.
        for component, blobs in self.blobs.items():
            for name, address, data in blobs:
                installed = self.image[address:address+len(data)]
                literals = [int.from_bytes(installed[i:i+4], 'big')
                            for i in range(len(installed)-3)]
                self.assertFalse(any(PEDAL_START <= n < PEDAL_END for n in literals),
                                 (component, name))
        # Existing AVLS modification intentionally makes pedal engagement
        # unreachable below the RPM override; it does not command 110% pedal.
        for address, count in ((0x7D67C, 7), (0x7D6B4, 7), (0x7D4B0, 2)):
            values = struct.unpack_from('>'+'f'*count, self.image, address)
            self.assertTrue(all(v > 100 for v in values))

    def test_standard_pedal_and_vehicle_speed_channels_are_distinct(self):
        cpu = IdleAirMachine(self.image)
        self.assertEqual(cpu.read(0x4B6FC + 4*0x29, 4), 0x3184E)
        self.assertEqual(cpu.read(0x4B6FC + 4*0x10, 4), 0x31678)
        for pedal, encoded_pedal in ((0, 0), (20, 51), (100, 255)):
            cpu.put_float(PEDAL, pedal)
            cpu.put_float(0xFFFFB53C, 73)  # P9 source, before B538 validity selection.
            self.assertEqual(cpu.invoke(0x3184E, set()), encoded_pedal)
            self.assertEqual(cpu.invoke(0x31678, set()), 73)

    def test_sd_airflow_ignores_pedal_and_detects_substituted_map_address(self):
        previous = sd_test.IMAGE
        try:
            sd_test.IMAGE = self.image
            outputs = []
            for pedal in (0, 20, 100):
                cpu = sd_test.Machine(rpm=1000, map_mmhg=315, iat=25, mode=1)
                seed_pedal(cpu, pedal)
                outputs.append(cpu.run())
                self.assertEqual(pedal_accesses(cpu), ([], []))
            self.assertEqual(outputs, [outputs[0]] * 3)
            sd_test.IMAGE = substitute_literal(
                self.image, master.speed_density.WRAPPER_ADDR,
                len(master.speed_density.build_wrapper()), 0xFFFFABC4, PEDAL)
            cpu = sd_test.Machine(rpm=1000, map_mmhg=315, iat=25, mode=1)
            seed_pedal(cpu, 20)
            self.assertNotEqual(cpu.run(), outputs[0])
            self.assertIn(PEDAL, cpu.reads)
        finally:
            sd_test.IMAGE = previous

    def test_wideband_and_added_pressure_cut_decisions_ignore_pedal(self):
        results = []
        for pedal in (0, 20, 100):
            outcomes = []
            for pressure in (315, 800, 1200):
                cpu = GuardMachine(self.image)
                seed_pedal(cpu, pedal)
                cpu.put_float(safety.MAP_PRESSURE, pressure)
                for raw in (0, 30000):
                    outcomes.append(cpu.update_wideband(raw))
                    self.assertEqual(pedal_accesses(cpu), ([], []))
                cpu.invoke(cpu.read(safety.PRIMARY_OL_TASK_PTR, 4),
                           {(safety.CL_OL_STATE_FLAGS, 1)})
                outcomes.append(cpu.read(safety.CL_OL_STATE_FLAGS, 1))
                self.assertEqual(pedal_accesses(cpu), ([], []))
                # Covers vacuum, delayed/confirmed lean and immediate hard cut.
                for _ in range(60):
                    state = cpu.cut_step()
                    self.assertEqual(pedal_accesses(cpu), ([], []))
                outcomes.append(state)
            results.append(outcomes)
        self.assertEqual(results, [results[0]] * 3)
        self.assertFalse(results[0][3][2])
        self.assertTrue(results[0][7][2])
        self.assertTrue(results[0][11][2])

    def test_rotational_idle_uses_vehicle_speed_not_pedal(self):
        def run(image, pedal, speed):
            cpu = RotationalFixture(image, rpm=800)
            seed_pedal(cpu, pedal)
            for address, value in ((roti.ECT_ADDR, 90), (roti.THROTTLE_ADDR, 0),
                                   (roti.VEHICLE_SPEED_ADDR, speed), (roti.MAP_ADDR, 300)):
                cpu.put_float(address, value)
            addresses = range(roti.FINAL_TIMING_ARRAY, roti.FINAL_TIMING_ARRAY+24, 4)
            cpu.invoke(roti.ROT_IDLE_WRAPPER_ADDR, {(a, 4) for a in addresses})
            return tuple(cpu.get_float(a) for a in addresses), pedal_accesses(cpu)

        self.assertEqual(self.image[roti.ROT_IDLE_ENABLE_ADDR], 0)
        self.assertEqual(run(self.image, 100, 0)[0], (20,) * 6)
        enabled = bytearray(self.image)
        enabled[roti.ROT_IDLE_ENABLE_ADDR] = 1  # In-memory coverage of dormant code.
        for pedal in (0, 100):
            self.assertEqual(run(enabled, pedal, 0), ((14, 20, 14, 20, 14, 20), ([], [])))
            self.assertEqual(run(enabled, pedal, 73), ((20,) * 6, ([], [])))
        altered = substitute_literal(enabled, roti.ROT_IDLE_WRAPPER_ADDR,
                                     len(roti.build_wrapper()), roti.VEHICLE_SPEED_ADDR, PEDAL)
        self.assertNotEqual(run(altered, 0, 0)[0], run(altered, 100, 0)[0])


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(PedalDependencyTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Pedal dependencies: {result.testsRun} execution/integrity groups passed')
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
