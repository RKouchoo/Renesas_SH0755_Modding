#!/usr/bin/env python3
"""Execute native timing-retard feedback and its downstream publications.

Temperature, digital inputs, runtime and prior final angles are explicit
fixtures. Native table lookup, six-cylinder minimum gating and final spark
composition execute ROM instructions. Physical timing and interrupt latency
are not simulated.
"""
import _test_paths
from itertools import product
import struct
import unittest

from test_knock_feedback_process_flow import KnockFeedbackMachine, RAM, ROOT
from test_opening_timing_execution import FINAL_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling

TIMING_FEEDBACK_WRITES = {(RAM+a, 4) for a in (0xC1B4, 0xC1B8, 0xC1BC)} | {
    (RAM+0xC1C4, 2), (RAM+0xC1C6, 1)}
IDLE_COMPENSATION_WRITES = {(RAM+a, 4) for a in (0xC5B8, 0xC5BC, 0xC5C0, 0xC5C4, 0xC5C8)}


class TimingFeedbackMachine(KnockFeedbackMachine):
    LOOKUPS = KnockFeedbackMachine.LOOKUPS | {
        0x1ADD8, 0x19C68, 0x18CF4, 0x19BE2, 0x1D228,
        0x6504C, 0x12C12, 0x35ED2, 0x1487E, 0x27088, 0x279CC, 0x19D6C, 0x18D08,
    }

    def __init__(self, image, rpm=800, speed=0, coolant=67, correction=5):
        super().__init__(image, rpm=rpm, coolant=coolant)
        for a, value in ((0xB538, speed), (0xB3B0, coolant), (0xC468, 800),
                         (0xB54C, 0), (0xC1BC, correction)):
            self.put_float(RAM+a, value)
        for a, value in ((0xB6B8, 0), (0xB51C, 0x80), (0xB484, 0x80),
                         (0xB51E, 0), (0xB748, 0), (0xC1C6, 0)):
            self.write(RAM+a, value, 1)
        self.write(RAM+0xB688, 0, 2)
        self.write(RAM+0xC1C4, 65535, 2)

    def correction(self):
        self.execute(0x28C38, TIMING_FEEDBACK_WRITES)
        return self.get_float(RAM+0xC1BC)

    def final_inputs(self):
        # Match the ordinary-running native composition fixture, keeping
        # this suite's C1BC producer state and explicit speed/RPM inputs.
        for a, value in ((0xB2BC, 0), (0xB151, 0), (0xB289, 0), (0xCA10, 0),
                         (0xD141, 0), (0xC120, 3), (0xC121, 0),
                         (0xC12B, 0), (0xC12C, 0), (0xC12D, 0), (0xC12E, 0)):
            self.write(RAM+a, value, 1)
        for a in (0xB2F8, 0xB834, 0xB89C, 0xC118, 0xC1A0, 0xC1A4,
                  0xC1A8, 0xC1C8, 0xC1D0, 0xC1D4, 0xC1E0, 0xC1E4,
                  0xCA18, 0xCD44, 0xD0F8, 0xD12C, 0xD11C,
                  *range(0xCCC8, 0xCCE0, 4)):
            self.put_float(RAM+a, 0)
        for a, value in ((0xB314, 100), (0xC104, 90), (0xC108, 90),
                         (0xC124, 0), (0xC130, 20), (0xC134, 1),
                         (0xC138, 15.1953125), (0xC13C, 15.1953125)):
            self.put_float(RAM+a, value)

    def final(self):
        self.execute(self.read(0x11E30, 4), FINAL_WRITES)
        return tuple(self.get_float(RAM+0xC0EC+4*i) for i in range(6))

    def idle_compensation(self):
        self.execute(0x2E8CC, IDLE_COMPENSATION_WRITES)
        return self.get_float(RAM+0xC5B8)

    def air_path_inputs(self, pedal=0):
        for a in (0xC438, 0xC524, 0xC534, 0xC568, 0xC5B4, 0xC5CC,
                  0xC588, 0xC58C, 0xC45C, 0xCFA4, 0x8E10, 0xD10C,
                  0xD14C, 0xD164, 0xC2E8, 0xC2EC, 0xC2E0,
                  0xC3FC, 0xC3F8, 0xC404, 0xC400, 0xC408,
                  0xCA78, 0xC410, 0xC41C, 0xB730):
            self.put_float(RAM+a, 0)
        for a, value in ((0xC424, 3), (0xC2E4, 100), (0xC2F0, 1),
                         (0xC414, 0), (0xC418, 100), (0xB3B8, 30),
                         (0xB46C, pedal), (0xB470, pedal)):
            self.put_float(RAM+a, value)
        self.write(RAM+0xC40C, 0, 1)
        self.write(RAM+0xC420, 0, 1)

    def air_path(self):
        assert tuple(self.read(0x110EC+4*i, 4) for i in range(3)) == (0x2B570, 0x2B432, 0x2B408)
        for entry, writes in (
            (0x2B570, {(RAM+a, 4) for a in (0xC2E8, 0xC2EC, 0xC410)} |
                       {(RAM+0xC40C, 1), (RAM+0xC420, 1)}),
            (0x2B432, {(RAM+a, 4) for a in (0xC404, 0xC3FC, 0xC408, 0xC400)}),
            (0x2B408, {(RAM+0xC41C, 4), (RAM+0xC3F8, 4)}),
        ):
            self.execute(entry, writes)
        return self.get_float(RAM+0xC3F8)


class TimingFeedbackProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x28A82, 0x29024), (0x5FCCC, 0x5FD08),
                         (0x60004, 0x60010), (0x77E78, 0x77EBC),
                         (0x2B408, 0x2B7C8), (0x2E8CC, 0x2E9E0),
                         (0x16B04, 0x16C4A), (0x6BB30, 0x6BDF4),
                         (0x5EE24, 0x5EE9C), (0x7510C, 0x7514C),
                         (0x753C0, 0x75480)):
                assert image[a:b] == stock[a:b], hex(a)
            assert image[0x7952A] == 0
            monitor_curves = []
            for address in (0x5EE24, 0x5EE38, 0x5EE4C, 0x5EE60, 0x5EE74, 0x5EE88):
                n, kind, axis, data, scale, bias = struct.unpack_from('>HHIIff', image, address)
                assert (n, kind, axis, scale, bias) == (16, 0x800, 0x7510C, 1/8192, 0)
                monitor_curves.append(image[data:data+2*n])
            assert len(set(monitor_curves)) == 1

    def test_logged_moving_speeds_release_retard_across_temperature_and_rpm_inputs(self):
        for image, rpm, temperature in product(self.images.values(), (2500, 2800, 3250, 3500), (0, 30, 67, 90)):
            cpu = TimingFeedbackMachine(image, rpm=rpm, speed=44, coolant=temperature, correction=5)
            previous = 5
            for _ in range(20):
                current = cpu.correction()
                self.assertGreaterEqual(current, 0)
                self.assertLessEqual(current, previous)
                previous = current
            self.assertEqual(current, 0)

    def test_any_of_six_low_final_angles_stops_growth_at_the_native_floor(self):
        for image, cylinder in product(self.images.values(), range(6)):
            cpu = TimingFeedbackMachine(image)
            selected = RAM+0xC0EC+4*cylinder
            cpu.put_float(selected, -20)
            self.assertEqual(cpu.correction(), 5)
            self.assertEqual(cpu.read(RAM+0xC1C6, 1) & 8, 8)
            cpu.put_float(selected, -19.99)
            self.assertGreater(cpu.correction(), 5)
            self.assertEqual(cpu.read(RAM+0xC1C6, 1) & 8, 0)

    def test_native_zero_reset_and_completion_latch_have_explicit_rearm(self):
        for image in self.images.values():
            for address in (0xB6B8, 0xB51E):
                cpu = TimingFeedbackMachine(image)
                cpu.write(RAM+address, 0x80, 1)
                self.assertEqual(cpu.correction(), 0)
            cpu = TimingFeedbackMachine(image, correction=0)
            cpu.write(RAM+0xB688, 600, 2)
            cpu.correction()  # Publishes native temperature-dependent period.
            self.assertEqual(cpu.correction(), 0)
            self.assertEqual(cpu.read(RAM+0xC1C6, 1) & 1, 1)
            cpu.write(RAM+0xB688, 0, 2)
            self.assertEqual(cpu.correction(), 0)  # Latch holds.
            cpu.write(RAM+0xB748, 0x80, 1)
            self.assertGreater(cpu.correction(), 0)
            self.assertEqual(cpu.read(RAM+0xC1C6, 1) & 1, 0)

    def test_correction_is_subtracted_once_in_each_saved_images_native_final_path(self):
        for image in self.images.values():
            cpu = TimingFeedbackMachine(image, rpm=2800, speed=44)
            cpu.final_inputs()
            self.assertEqual(cpu.final(), (15,)*6)
            self.assertEqual(cpu.final(), (15,)*6)
            self.assertEqual(cpu.correction(), 4.5)
            self.assertEqual(cpu.final(), (15.5,)*6)
            for _ in range(9):
                cpu.correction()
            self.assertEqual(cpu.final(), (20,)*6)

    def test_repeated_stationary_updates_obey_the_native_dynamic_limit(self):
        for image, initial in product(self.images.values(), (0, 5, 20)):
            cpu = TimingFeedbackMachine(image, correction=initial)
            for _ in range(200):
                value = cpu.correction()
                limit = cpu.get_float(RAM+0xC1B4)*cpu.get_float(RAM+0xC1B8)*.01
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, limit+1e-6)
            self.assertAlmostEqual(value, 7.03125, places=5)

    def test_retard_air_compensation_rises_immediately_and_uses_both_native_decay_rates(self):
        for image, accelerated in product(self.images.values(), (False, True)):
            cpu = TimingFeedbackMachine(image)
            for address, _ in IDLE_COMPENSATION_WRITES:
                cpu.put_float(address, 0)
            raised = cpu.idle_compensation()
            self.assertAlmostEqual(raised, .3620190918445587, places=6)
            self.assertEqual(raised, cpu.get_float(RAM+0xC5BC))
            cpu.put_float(RAM+0xC1BC, 0)
            cpu.write(RAM+0xB6B8, 0x80 if accelerated else 0, 1)
            decayed = cpu.idle_compensation()
            self.assertEqual(cpu.get_float(RAM+0xC5BC), 0)
            self.assertAlmostEqual(decayed, raised*(.0625 if accelerated else .5), places=6)
            self.assertGreaterEqual(decayed, 0)

    def test_native_idle_chain_includes_compensation_once_and_does_not_reduce_driver_request(self):
        for image, pedal in product(self.images.values(), (0, 70)):
            results = []
            for retard in (0, 5):
                cpu = TimingFeedbackMachine(image, rpm=2800, speed=44, correction=retard)
                for address, _ in IDLE_COMPENSATION_WRITES:
                    cpu.put_float(address, 0)
                cpu.air_path_inputs(pedal)
                compensation = cpu.idle_compensation()
                idle_request = cpu.air_path()
                self.assertAlmostEqual(cpu.get_float(RAM+0xC2E8), 3+compensation, places=6)
                self.assertEqual(cpu.get_float(RAM+0xC408), cpu.get_float(RAM+0xC2E8))
                # Explicit ordinary key-on and digital states from the
                # existing connected DBW fixture, after the timing fixture.
                cpu.write(RAM+0xB51E, 0x10, 1)
                cpu.write(RAM+0xB484, 0, 1)
                cpu.write(RAM+0xB51C, 0, 1)
                final = cpu.final_step()
                self.assertGreaterEqual(final, idle_request)
                results.append((idle_request, final))
            self.assertGreater(results[1][0], results[0][0])
            self.assertGreater(results[1][1], results[0][1])
            if pedal:
                self.assertGreater(results[0][1], 40)

    def test_native_temperature_sample_holds_independently_of_live_coolant(self):
        writes = {(RAM+a, 4) for a in (0xB3B0, 0xB3AC, 0x8100)} | {
            (RAM+a, 1) for a in range(0xB3B4, 0xB3B8)} | {
            (RAM+0x8104, 2), (RAM+0x8106, 2)}
        for image in self.images.values():
            cpu = TimingFeedbackMachine(image)
            for a in range(0xB3B4, 0xB3B8):
                cpu.write(RAM+a, 0, 1)
            cpu.write(RAM+0xB51E, 0x10, 1)
            cpu.write(RAM+0xB52C, 0, 1)
            cpu.put_float(RAM+0xB3B0, 10)
            for converted, trigger, fault, live, held in (
                (40, 0, 0, 40, 10), (50, 8, 0, 50, 50),
                (90, 8, 0, 90, 50), (90, 0, 0, 90, 50),
                (90, 8, 0, 90, 90), (90, 0, 64, 70, 90), (90, 8, 64, 70, 70)):
                cpu.put_float(RAM+0xABBC, converted)
                cpu.write(RAM+0xB51C, trigger, 1)
                cpu.write(RAM+0xD26C, fault, 1)
                cpu.execute(0x16B04, writes)
                self.assertEqual(cpu.get_float(RAM+0xB3AC), live)
                self.assertEqual(cpu.get_float(RAM+0xB3B0), held)

    def test_native_monitor_threshold_branches_leave_actuator_words_untouched(self):
        for image, temperature, selector, mode in product(self.images.values(), (0, 67, 90), (0, 8), (0, 16)):
            results = []
            for retard in (0, 5):
                cpu = TimingFeedbackMachine(image, correction=retard, coolant=temperature)
                cpu.put_float(RAM+0xC1C8, 0)
                cpu.put_float(RAM+0xD96C, 2800)  # Explicit diagnostic RPM sample.
                cpu.write(RAM+0xD81E, 0, 2)
                cpu.write(RAM+0xD952, selector, 1)
                cpu.write(RAM+0xD94A, mode, 1)
                cpu.write(RAM+0xB744, 0xA55A, 2)
                cpu.write(RAM+0xC0DC, 0x5AA5, 2)
                for a in range(0xD3D8, 0xD418, 4):
                    cpu.put_float(RAM+a, 0)
                cpu.execute(0x6BB30, {(RAM+a, 4) for a in (0xD40C, 0xD410, 0xD414)})
                cpu.execute(0x6BBA2, {(RAM+a, 4) for a in range(0xD3D8, 0xD40C, 4)})
                results.append(tuple(cpu.get_float(RAM+a) for a in (0xD3D8, 0xD3E4, 0xD3F0, 0xD3FC)))
                self.assertEqual(cpu.read(RAM+0xB744, 2), 0xA55A)
                self.assertEqual(cpu.read(RAM+0xC0DC, 2), 0x5AA5)
            # Native alternative gain tables produce the same results in
            # these fixtures; this does not close later monitor consumers.
            self.assertEqual(results[0], results[1])

    def test_other_idle_timing_consumer_clears_its_correction_at_loaded_rpm(self):
        writes = {(RAM+a, 1) for a in (0xC1B1, 0xC1B2)} | {
            (RAM+a, 4) for a in (0xC1A8, 0xC1AC)}
        for image, rpm, retard in product(self.images.values(), (2000, 2800, 3500), (0, 5)):
            cpu = TimingFeedbackMachine(image, rpm=rpm, correction=retard)
            for a, value in ((0xB854, 0), (0xB548, 1000), (0xC468, 1000),
                             (0xC1A8, -5), (0xC1AC, 99)):
                cpu.put_float(RAM+a, value)
            for a in (0xC1B0, 0xC1B1, 0xC1B2):
                cpu.write(RAM+a, 0, 1)
            cpu.execute(0x28A82, writes)
            self.assertEqual(cpu.get_float(RAM+0xC1A8), 0)
            self.assertEqual(cpu.get_float(RAM+0xC1AC), 99)
            self.assertNotIn(RAM+0xC1BC, cpu.reads)


if __name__ == '__main__':
    unittest.main(verbosity=2)
