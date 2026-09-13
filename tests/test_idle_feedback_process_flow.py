#!/usr/bin/env python3
"""Connect native idle feedback eligibility, pressure output and air bounds.

Sampled pressures, shaped RPM, digital inputs and retained air terms are
explicit. This extends the older idle tests with native table helpers,
timing-air compensation and the captured image. Task invocation order is
preserved; elapsed time and physical throttle response are not simulated.
"""
import _test_paths
from itertools import product
import unittest

from test_timing_feedback_process_flow import (
    TimingFeedbackMachine, RAM, ROOT, IDLE_COMPENSATION_WRITES,
)
from test_idle_air_execution import (
    GATE_WRITES, PEDAL_WRITES, OUTPUT_WRITES, LIMIT_WRITES,
    DEMAND_WRITES, PRESSURE_WRITES,
)
from test_runtime_rom_checksum_execution import before_pump_scaling


class IdleFeedbackMachine(TimingFeedbackMachine):
    LOOKUPS = TimingFeedbackMachine.LOOKUPS | {
        0x2D1FC, 0x36986, 0x14774, 0x14778, 0x18B14,
        0x19EC4, 0x652D0, 0x64FBC, 0x64F7C, 0x2458,
    }

    def __init__(self, image, rpm=800, speed=0, target=800, pedal=0, retard=0):
        super().__init__(image, rpm=rpm, speed=speed, correction=retard)
        self.air_path_inputs(pedal)
        for a, _ in IDLE_COMPENSATION_WRITES:
            self.put_float(a, 0)
        for a in (0xBF20, 0xD26C, 0xD272, 0xB748, 0xB52C, 0xC778,
                  0xC51C, 0xC51D, 0xC51E, 0xC4D9, 0xC4DA, 0xCA64,
                  0xB151, 0xB483, 0xB51D):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xB51A, 0x80, 1)
        self.write(RAM+0xB51E, 0x10, 1)
        self.write(RAM+0xB51C, 0, 1)
        for a in (0xC510, 0xC4FC, 0xB4CC, 0xC508, 0xC50A, 0xC50C,
                  0xC50E, 0xC4D4):
            self.write(RAM+a, 0, 2)
        self.write(RAM+0xC4D6, 8, 2)
        self.write(RAM+0xB688, 1000, 2)
        for a, value in ((0xC468, target), (0xC4BC, rpm), (0xC48C, rpm),
                         (0xC490, rpm), (0xC47C, 300), (0xB548, rpm),
                         (0xB67C, rpm), (0xB290, 300), (0xC480, 300),
                         (0xC4AC, .5), (0xC45C, .5), (0xC448, 1)):
            self.put_float(RAM+a, value)
        for a in (0xC4EC, 0xC4F0, 0xC4F4, 0xC4B4, 0xC4B0,
                  0xC49C, 0xC4C8, 0xC4CC, 0xC4F8, 0xC498,
                  0xC4A4, 0xC4A0, 0xC4A8):
            self.put_float(RAM+a, 0)

    def eligibility(self, pedal):
        self.put_float(RAM+0xB46C, pedal)
        self.put_float(RAM+0xB470, pedal)
        self.execute(0x18B14, PEDAL_WRITES)
        self.execute(0x2C760, GATE_WRITES)
        return self.read(RAM+0xC4D9, 1) & 8

    def pressure_output(self):
        self.execute(0x2CE50, DEMAND_WRITES)
        self.execute(0x2CF9C, PRESSURE_WRITES)
        self.execute(0x2D0AC, OUTPUT_WRITES)
        return self.get_float(RAM+0xC45C)

    def cycle(self, pedal):
        # Native order: gate11054 -> pressure11064/68/80 -> compensation
        # 110A0 -> final-air110EC/F0/F4. Other task producers stay explicit.
        self.eligibility(pedal)
        correction = self.pressure_output()
        self.idle_compensation()
        self.air_path()
        return correction, self.final_step()


class IdleFeedbackProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x2C760, 0x2CB60), (0x2CE50, 0x2D834),
                         (0x7952A, 0x7955C), (0x79654, 0x79670),
                         (0x796F0, 0x7972C), (0x60304, 0x6032C),
                         (0x60774, 0x60780), (0x79B2C, 0x79BF4),
                         (0x7A4C4, 0x7A514), (0x604D0, 0x604E4),
                         (0x60828, 0x60860), (0x7ADE4, 0x7AED2),
                         (0x18B14, 0x18C38), (0x18C80, 0x18C94),
                         (0x36986, 0x3699E), (0x2450, 0x2484)):
                assert image[a:b] == stock[a:b], hex(a)
            # Check real instruction/pointer pairs, not just table ordering.
            for pc, pool, target in (
                    (0x10E10, 0x11054, 0x2C760),
                    (0x10E28, 0x11064, 0x2CE50),
                    (0x10E2E, 0x11068, 0x2CF9C),
                    (0x10E52, 0x11080, 0x2D0AC),
                    (0x10E82, 0x110A0, 0x2E8CC),
                    (0x10EF4, 0x110EC, 0x2B570)):
                op = int.from_bytes(image[pc:pc+2], 'big')
                assert op >> 12 == 0xD
                assert ((pc+4) & ~3)+(op & 255)*4 == pool
                assert int.from_bytes(image[pool:pool+4], 'big') == target
                assert int.from_bytes(image[pc+2:pc+4], 'big') == 0x400B | ((op >> 8) & 15) << 8

    def test_loaded_pedal_release_gate_clears_old_feedback_from_every_cycle_position(self):
        for image, phase, rpm, old in product(self.images.values(), range(1, 9),
                                              (2500, 2800, 3250, 3500), (-5, 5)):
            cpu = IdleFeedbackMachine(image, rpm=rpm, speed=44, pedal=70, retard=5)
            cpu.write(RAM+0xC4D6, phase, 2)
            cpu.write(RAM+0xC4D9, 9, 1)  # Explicit prior enabled controller.
            cpu.put_float(RAM+0xC45C, old)
            cpu.put_float(RAM+0xC4AC, old)
            for _ in range(8):
                correction, final = cpu.cycle(70)
                self.assertEqual(cpu.read(RAM+0xB484, 1) & 128, 0)
                self.assertGreater(final, 40)
            self.assertEqual(correction, 0)
            self.assertEqual(cpu.get_float(RAM+0xC4AC), 0)
            self.assertEqual(cpu.read(RAM+0xC4D9, 1) & 8, 0)

    def test_timing_compensation_enters_native_lower_and_upper_headroom_bounds(self):
        for image, retard, (low, high, requested, limited) in product(
                self.images.values(), (0, 5), ((0, 8, 10, True),
                                             (8, 100, -10, True), (0, 100, 2, False))):
            cpu = IdleFeedbackMachine(image, retard=retard)
            compensation = cpu.idle_compensation()
            cpu.air_path()  # Establish prior-cycle base before bounds consume it.
            cpu.write(RAM+0xC4D9, 8, 1)
            cpu.put_float(RAM+0xC4EC, requested)
            cpu.put_float(RAM+0xC2E0, low)
            cpu.put_float(RAM+0xC2E4, high)
            cpu.execute(0x2D1FC, LIMIT_WRITES)
            base = cpu.get_float(RAM+0xC2E8)
            self.assertAlmostEqual(cpu.get_float(RAM+0xC4F0), low-base-compensation, delta=.00002)
            self.assertAlmostEqual(cpu.get_float(RAM+0xC4F4), high-base-compensation, delta=.00002)
            self.assertAlmostEqual(cpu.get_float(RAM+0xC45C),
                                   5-2*compensation if limited else requested, places=5)
            self.assertIn(RAM+0xC5B8, cpu.reads)

    def test_parent_and_limit_hold_output_outside_permission_or_eighth_call(self):
        for image, phase, enabled in product(self.images.values(), range(1, 9), (False, True)):
            if phase == 8 and enabled:
                continue
            cpu = IdleFeedbackMachine(image)
            cpu.write(RAM+0xC4D6, phase, 2)
            cpu.write(RAM+0xC4D9, 8 if enabled else 0, 1)
            cpu.put_float(RAM+0xC45C, 1.25)
            cpu.put_float(RAM+0xC4AC, 2.5)
            cpu.put_float(RAM+0xC4EC, 3.75)
            cpu.execute(0x2D0AC, OUTPUT_WRITES)
            self.assertEqual(cpu.get_float(RAM+0xC45C), 1.25)
            self.assertEqual(cpu.get_float(RAM+0xC4AC), 2.5)
            self.assertEqual(cpu.get_float(RAM+0xC4EC), 3.75)
            self.assertNotIn(RAM+0xC5B8, cpu.reads)

    def test_underspeed_chain_qualifies_and_opening_clears_feedback_with_native_tables(self):
        for image in self.images.values():
            cpu = IdleFeedbackMachine(image, rpm=558, target=1000, retard=5)
            cpu.write(RAM+0xB484, 0, 1)  # Pedal-release qualification starts here.
            for count in range(1, 49):
                value, final = cpu.cycle(0)
                self.assertEqual(bool(cpu.read(RAM+0xC4D9, 1) & 8), count >= 40)
                self.assertGreaterEqual(value, 0)
                self.assertGreaterEqual(final, 0)
            self.assertGreater(value, 0)
            self.assertGreater(cpu.get_float(RAM+0xC4AC), 0)
            self.assertGreater(cpu.get_float(RAM+0xC498), 300)
            for _ in range(8):
                value, final = cpu.cycle(35)
            self.assertEqual(value, 0)
            self.assertEqual(cpu.get_float(RAM+0xC4AC), 0)
            self.assertEqual(cpu.read(RAM+0xC4D9, 1) & 8, 0)
            self.assertGreater(final, 10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
