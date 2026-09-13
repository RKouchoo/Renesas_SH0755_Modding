#!/usr/bin/env python3
"""Execute native feedback/learning arbitration and its load/lift histories.

Knock events, cam eligibility and sampled physical inputs are explicit. The
native filter, permission gates, feedback correction and history workers run
ROM instructions. These checks do not reconstruct the loaded car's unlogged
knock sensor or cam state, nor establish real task execution time.
"""
import _test_paths
from itertools import product
import unittest

from test_knock_learning_process_flow import KnockLearningMachine
from test_knock_retained_process_flow import RAM, ROOT, GRID
from test_runtime_rom_checksum_execution import before_pump_scaling

FEEDBACK_WRITES = {(RAM+a, 4) for a in (0xCCFC, 0xCD00, 0xCD14, 0xCD18, 0xCD1C)} | {
    (RAM+a, 1) for a in (0xCD06, 0xCD22, 0xCD2C, 0xCD2D, 0xCD38)} | {
    (RAM+a, 2) for a in (0xCD20, 0xCD24, 0xCD26, 0xCD28, 0xCD2A)}


class KnockFeedbackMachine(KnockLearningMachine):
    LOOKUPS = KnockLearningMachine.LOOKUPS | {
        0x65168, 0x650A2, 0x65208, 0x12C26, 0x3413A, 0x3414E,
        0x349DC, 0x3BB26, 0x14902, 0x3D50A, 0x3E008, 0x3E096,
        0x3F194, 0x3E082, 0x3E942, 0x3E9A6, 0x3E904, 0x1A256,
    }

    def __init__(self, image, rpm=2800, load=2, coolant=90):
        super().__init__(image)
        for a in (0xB151, 0xB28C, 0xC894, 0xC0E3, 0xCCBB,
                  0xD26D, 0xD26E, 0xD26F, 0xB460):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xB52A, 1, 1)
        self.write(RAM+0xCD86, 1, 1)
        self.write(RAM+0xCD2C, 1, 1)
        self.write(RAM+0xCD2D, 0, 1)
        self.write(RAM+0x8274, 1, 1)
        self.write(RAM+0xCD06, 4, 1)
        self.write(RAM+0xCD3A, 1, 1)
        for a, value in ((0xB544, rpm), (0xB438, load), (0xB3AC, coolant),
                         (0xBE48, 0), (0xCA18, 0), (0xCD18, load),
                         (0xCD1C, 0), (0xC134, 1), (0xCD14, 0),
                         (0xCD00, 0), (0xCCFC, 0)):
            self.put_float(RAM+a, value)
        for a in range(0xC0EC, 0xC104, 4):
            self.put_float(RAM+a, 16)
        self.write(RAM+0xCD24, 14, 2)
        self.write(RAM+0xCD26, 126, 2)
        self.write(RAM+0xCD28, 126, 2)

    def permission(self):
        self.execute(0x3E45C, FEEDBACK_WRITES)
        self.execute(0x3E760, FEEDBACK_WRITES)
        return self.read(RAM+0xCD22, 1)

    def feedback(self, knock=False):
        self.write(RAM+0xB460, 0x80 if knock else 0, 1)
        self.execute(0x3E20E, FEEDBACK_WRITES)
        return self.read(RAM+0xCD22, 1), self.get_float(RAM+0xCD14)

    def parent_prefix(self, knock=False):
        for pointer in (0x11DA8, 0x11DAC, 0x11DB0):
            self.execute(self.read(pointer, 4), FEEDBACK_WRITES)
        return self.feedback(knock)


class KnockFeedbackProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x3E008, 0x3E044), (0x3E082, 0x3E20E),
                         (0x3E20E, 0x3E9FC), (0x11DA8, 0x11DB8),
                         (0x77FA0, 0x77FD8), (0x78030, 0x78038)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_stable_loaded_inputs_do_not_create_retard_without_a_knock_event(self):
        for image, rpm, coolant in product(self.images.values(), (2500, 2800, 3250, 3500), (67, 90)):
            cpu = KnockFeedbackMachine(image, rpm=rpm, coolant=coolant)
            retained = cpu.read(GRID, 64*8+17)
            for _ in range(8):
                flags, correction = cpu.parent_prefix()
                self.assertEqual(correction, 0)
                self.assertEqual(bool(flags & 1), coolant < 70)
            self.assertEqual(cpu.read(GRID, 64*8+17), retained)

    def test_feedback_knock_is_bounded_and_clean_recovery_requires_125_event_calls(self):
        for image in self.images.values():
            cpu = KnockFeedbackMachine(image, coolant=67)
            self.assertAlmostEqual(cpu.parent_prefix(True)[1], -1.05, places=5)
            for _ in range(10):
                cpu.parent_prefix(True)
            self.assertEqual(cpu.get_float(RAM+0xCD14), -7)
            cpu.write(RAM+0xB460, 0, 1)
            for _ in range(124):
                cpu.execute(0x3E80A, FEEDBACK_WRITES)
            self.assertEqual(cpu.parent_prefix()[1], -7)
            cpu.execute(0x3E80A, FEEDBACK_WRITES)
            self.assertAlmostEqual(cpu.parent_prefix()[1], -6.65, places=5)
            self.assertEqual(cpu.read(RAM+0xCD20, 2), 0)

    def test_load_filter_routes_transitions_to_feedback_then_releases_without_a_latch(self):
        for image, target in product(self.images.values(), (1, 3)):
            cpu = KnockFeedbackMachine(image)
            self.assertEqual(cpu.parent_prefix(), (0, 0))
            cpu.put_float(RAM+0xB438, target)
            flags, correction = cpu.parent_prefix()
            self.assertEqual(flags & 7, 7)
            self.assertEqual(correction, 0)
            self.assertAlmostEqual(cpu.get_float(RAM+0xCD18), 2+(target-2)*.0312, places=6)
            releases = []
            for call in range(2, 81):
                flags, correction = cpu.parent_prefix()
                self.assertEqual(correction, 0)
                if not flags & 1:
                    releases.append(call)
            self.assertTrue(releases)
            self.assertGreater(releases[0], 70)
            self.assertLessEqual(releases[0], 80)
            self.assertLess(abs(cpu.get_float(RAM+0xCD1C)), .1)

    def test_feedback_handoff_preserves_retard_for_the_next_fine_publication(self):
        for image in self.images.values():
            cpu = KnockFeedbackMachine(image, coolant=67)
            for i in range(64):
                cpu.put_retained(GRID+8*i, 0)
            self.assertAlmostEqual(cpu.parent_prefix(True)[1], -1.05, places=5)
            cpu.put_float(RAM+0xB3AC, 90)
            self.assertEqual(cpu.parent_prefix(), (0, 0))
            self.assertAlmostEqual(cpu.get_float(RAM+0xCD00), -1.05, places=5)
            cpu.select()
            self.assertAlmostEqual(cpu.get_float(RAM+0xCCFC), -1.05, places=5)
            # Native 3DB90 precedes the entry handoff in 3DC02.
            self.assertEqual(cpu.get_float(RAM+0xCCF8), 0)
            cpu.select()
            self.assertAlmostEqual(cpu.get_float(RAM+0xCCF8), -1.05, places=5)
            self.assertTrue(all(cpu.get_float(GRID+8*i) == 0 for i in range(64)))

    def test_all_six_final_timing_slots_affect_only_the_low_rpm_permission_gate(self):
        for image, cylinder in product(self.images.values(), range(1, 7)):
            cpu = KnockFeedbackMachine(image, rpm=1250)
            cpu.write(RAM+0xB52A, cylinder, 1)
            self.assertEqual(cpu.permission() & 2, 2)
            selected = RAM+0xC0EC+4*(cylinder-1)
            cpu.put_float(selected, -30)
            cpu.execute(0x3E45C, FEEDBACK_WRITES)
            self.assertIn(selected, cpu.reads)
            self.assertEqual(cpu.read(RAM+0xCD22, 1) & 2, 0)
            cpu.put_float(selected, -20)
            self.assertEqual(cpu.permission() & 2, 2)
            cpu.put_float(RAM+0xB544, 2800)
            self.assertEqual(cpu.permission() & 2, 0)
        for image, cylinder in product(self.images.values(), (0, 7, 255)):
            cpu = KnockFeedbackMachine(image, rpm=1250)
            cpu.write(RAM+0xB52A, cylinder, 1)
            self.assertEqual(cpu.permission() & 2, 2)

    def test_lift_transition_and_activity_history_hold_then_release_learning(self):
        for image in self.images.values():
            cpu = KnockFeedbackMachine(image)
            self.assertEqual(cpu.permission() & 2, 0)
            cpu.write(RAM+0xCD86, 3, 1)
            cpu.execute(0x3E83C, FEEDBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xCD28, 2), 0)
            self.assertEqual(cpu.permission() & 2, 2)
            for _ in range(125):
                cpu.execute(0x3E83C, FEEDBACK_WRITES)
            self.assertEqual(cpu.permission() & 2, 2)
            cpu.execute(0x3E83C, FEEDBACK_WRITES)
            self.assertEqual(cpu.permission() & 2, 0)
            cpu.write(RAM+0xCD2A, 4, 2)  # Explicit nondefault activity input.
            cpu.execute(0x3E83C, FEEDBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xCD26, 2), 0)
            self.assertEqual(cpu.read(RAM+0xCD2A, 2), 0)
            self.assertEqual(cpu.permission() & 2, 2)
            for _ in range(126):
                cpu.execute(0x3E83C, FEEDBACK_WRITES)
            self.assertEqual(cpu.permission() & 2, 0)

    def test_native_fault_cam_and_transient_gates_select_feedback_without_grid_writes(self):
        gates = ((0xD26F, 0x40), (0xD26F, 1), (0xD26E, 4),
                 (0xC894, 4), (0xC894, 8), (0x8274, 0))
        for image, (address, value) in product(self.images.values(), gates):
            cpu = KnockFeedbackMachine(image)
            cpu.write(RAM+address, value, 1)
            retained = cpu.read(GRID, 64*8+17)
            self.assertEqual(cpu.permission() & 2, 2)
            self.assertEqual(cpu.feedback()[0] & 1, 1)
            self.assertEqual(cpu.read(GRID, 64*8+17), retained)
        for image in self.images.values():
            cpu = KnockFeedbackMachine(image)
            cpu.put_float(RAM+0xBE48, .01)
            self.assertEqual(cpu.permission() & 2, 2)
            cpu.put_float(RAM+0xBE48, 0)
            self.assertEqual(cpu.permission() & 2, 0)
            cpu.write(RAM+0xD26D, 4, 1)
            self.assertEqual(cpu.feedback(), (1, -5))

    def test_clean_event_and_permission_counters_saturate_and_clear_from_native_getters(self):
        for image in self.images.values():
            cpu = KnockFeedbackMachine(image)
            cpu.write(RAM+0xCD20, 65534, 2)
            for _ in range(2):
                cpu.execute(0x3E80A, FEEDBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xCD20, 2), 65535)
            cpu.write(RAM+0xB460, 0x80, 1)
            cpu.execute(0x3E80A, FEEDBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xCD20, 2), 0)
            cpu.write(RAM+0xB151, 0x80, 1)
            cpu.write(RAM+0xCD24, 65534, 2)
            for _ in range(2):
                cpu.execute(0x3E72E, FEEDBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xCD24, 2), 65535)
            cpu.write(RAM+0xB151, 0, 1)
            cpu.execute(0x3E72E, FEEDBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xCD24, 2), 0)

    def test_native_initializer_seeds_mode_timers_and_resets_filter_only_when_requested(self):
        for image, request in product(self.images.values(), (0, 0x80)):
            cpu = KnockFeedbackMachine(image)
            self.assertEqual(cpu.read(0x102B4, 4), 0x3E1B0)
            cpu.write(RAM+0xB52C, request, 1)
            cpu.put_float(RAM+0xCD14, -3)
            cpu.put_float(RAM+0xCD18, 1)
            cpu.put_float(RAM+0xCD1C, 1)
            cpu.execute(0x3E1B0, FEEDBACK_WRITES)
            self.assertEqual(cpu.read(RAM+0xCD26, 2), 65535)
            self.assertEqual(cpu.read(RAM+0xCD28, 2), 65535)
            self.assertEqual(cpu.read(RAM+0xCD2A, 2), 0)
            self.assertEqual(cpu.read(RAM+0xCD2C, 1), 1)
            self.assertEqual(tuple(cpu.get_float(RAM+a) for a in (0xCD14, 0xCD18, 0xCD1C)),
                             (0, 2, 0) if request else (-3, 1, 1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
