#!/usr/bin/env python3
"""Execute fine knock learning, selected-record writes and rough-mode reentry.

Knock events, prior learned contents and upstream feedback permission are
explicit inputs. Native load/row selection, event histories, protected writes
and cross-mode resets execute from each image. There is no sensor or physical
combustion model and no claim about event counts in the driving ECU.
"""
import _test_paths
from itertools import product
import unittest

from test_knock_retained_process_flow import (
    KnockRetainedMachine, RAM, ROOT, GRID, IAM, STEP, STATUS, GRID_WRITES,
)
from test_runtime_rom_checksum_execution import before_pump_scaling

FINE_WRITES = GRID_WRITES | {(STATUS, 1), (RAM+0xCD04, 2)} | {
    (RAM+a, 1) for a in (0xCD06, 0xCD0C, 0xCD0D, 0xCD0E, 0xCD0F,
                         0xCD10, 0xCD11, 0xCD38)} | {
    (RAM+a, 4) for a in (0xCCF8, 0xCCFC, 0xCD00, 0xCD08, 0xCD30,
                         0xCD34, 0xCD44)}


class KnockLearningMachine(KnockRetainedMachine):
    LOOKUPS = KnockRetainedMachine.LOOKUPS | {
        0x3E0B0, 0x3E0A0, 0x3F194, 0x3E078, 0x15192,
    }

    def __init__(self, image):
        super().__init__(image)
        self.write(STATUS, 0xD5, 1)  # Native fine-learning mode, upper canary.
        self.write(RAM+0xCD06, 0xA0, 1)
        self.write(RAM+0xCD11, 0xA0, 1)
        self.write(RAM+0xCD0F, 255, 1)
        self.put_float(RAM+0xCCFC, 0)
        self.put_float(RAM+0xCD00, 0)
        self.write(RAM+0xB51D, 0, 1)
        self.write(RAM+0xB2BC, 0, 1)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        if op & 0xF0FF == 0x4008:  # SHLL2; T is unchanged.
            n = (op >> 8) & 15
            self.r[n] = self.r[n] << 2 & 0xFFFFFFFF
            self.trace.append((pc, op))
            self.pc += 2
            self.instructions += 1
        else:
            return super().step(in_delay)

    def event(self, knock=False):
        self.write(RAM+0xB460, 0x80 if knock else 0, 1)
        self.execute(0x3DFD6, {(RAM+0xCD04, 2)})

    def select(self, rpm=2800, load=2):
        self.put_float(RAM+0xB544, rpm)
        self.put_float(RAM+0xB438, load)
        for entry in (0x3DEF0, 0x3DAA6, 0x3DB90, 0x3DBC6, 0x3DC02):
            self.execute(entry, FINE_WRITES)
        return self.read(RAM+0xCD0E, 1)

    def learn(self, knock=False):
        self.write(RAM+0xB460, 0x80 if knock else 0, 1)
        self.execute(0x3DC9C, FINE_WRITES)
        return self.get_float(GRID+8*self.read(RAM+0xCD0E, 1))


class KnockLearningProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x3D9B4, 0x3E1A4), (0x3EF74, 0x3F254),
                         (0x3F386, 0x3F3E4), (0x77D5A, 0x77D5C)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_selected_record_decrements_on_event_with_no_adjacent_or_iam_write(self):
        for image in self.images.values():
            for rpm, load in ((2800, 1.5), (3000, 2), (4000, 1.8)):
                cpu = KnockLearningMachine(image)
                cell = cpu.select(rpm, load)
                previous = [cpu.read(GRID+8*i, 8) for i in range(64)]
                old = cpu.get_float(GRID+8*cell)
                value = cpu.learn(knock=True)
                self.assertLess(value, old)
                self.assertGreaterEqual(value, -5)
                self.assertEqual(cpu.get_float(IAM), .75)
                self.assertEqual(cpu.read(STATUS, 1), 0xD5)
                self.assertEqual(cpu.get_float(STEP), .125)
                for i in range(64):
                    if i != cell:
                        self.assertEqual(cpu.read(GRID+8*i, 8), previous[i])
                self.assertEqual(cpu.valid(0x3D9E8), 0)

    def test_recovery_waits_for_same_cell_and_125_clean_event_calls(self):
        for image in self.images.values():
            cpu = KnockLearningMachine(image)
            cell = cpu.select()
            old = cpu.get_float(GRID+8*cell)
            cpu.learn()  # Establish same-cell history, zero event counter.
            for _ in range(124):
                cpu.event()
                self.assertEqual(cpu.learn(), old)
            cpu.event()
            self.assertAlmostEqual(cpu.learn(), old+.35, places=6)
            self.assertEqual(cpu.read(RAM+0xCD04, 2), 0)
            self.assertEqual(cpu.get_float(IAM), .75)
            # Moving to a different load/RPM cell consumes history and restarts
            # qualification even if the separate event counter was saturated.
            cpu.write(RAM+0xCD04, 65535, 2)
            other = cpu.select(4000, 1.5)
            self.assertNotEqual(cell, other)
            before = cpu.get_float(GRID+8*other)
            self.assertEqual(cpu.learn(), before)
            self.assertEqual(cpu.read(RAM+0xCD04, 2), 0)

    def test_event_timer_saturates_and_knock_resets_it_before_learning(self):
        for image in self.images.values():
            cpu = KnockLearningMachine(image)
            cpu.write(RAM+0xCD04, 65534, 2)
            cpu.event()
            self.assertEqual(cpu.read(RAM+0xCD04, 2), 65535)
            cpu.event()
            self.assertEqual(cpu.read(RAM+0xCD04, 2), 65535)
            cpu.event(knock=True)
            self.assertEqual(cpu.read(RAM+0xCD04, 2), 0)

    def test_shared_offset_recovers_before_the_selected_protected_cell(self):
        for image in self.images.values():
            cpu = KnockLearningMachine(image)
            cell = cpu.select()
            cpu.learn()
            cpu.put_float(RAM+0xCCFC, -.7)
            old = cpu.get_float(GRID+8*cell)
            for _ in range(125):
                cpu.event()
            self.assertEqual(cpu.learn(), old)
            self.assertAlmostEqual(cpu.get_float(RAM+0xCCFC), -.35, places=6)
            self.assertAlmostEqual(cpu.get_float(RAM+0xCD00), -.35, places=6)
            self.assertEqual(cpu.read(RAM+0xCD06, 1) & 2, 0)

    def test_feedback_rough_mode_and_load_gates_hold_records_during_knock(self):
        for image, gate in product(self.images.values(), ('feedback', 'rough', 'load', 'diagnostic')):
            cpu = KnockLearningMachine(image)
            cpu.select(load=.1 if gate == 'load' else 2)
            if gate == 'feedback':
                cpu.write(RAM+0xCD22, 1, 1)
            elif gate == 'rough':
                cpu.write(STATUS, 0xDA, 1)
            elif gate == 'diagnostic':
                cpu.write(RAM+0xD26D, 4, 1)
            before = [cpu.read(GRID+8*i, 8) for i in range(64)]
            cpu.learn(knock=True)
            self.assertEqual([cpu.read(GRID+8*i, 8) for i in range(64)], before)
            self.assertEqual(cpu.get_float(IAM), .75)

    def test_new_learning_reaches_composition_on_the_next_native_publication(self):
        for image in self.images.values():
            cpu = KnockLearningMachine(image)
            cell = cpu.select()
            cpu.put_retained(GRID+8*cell, -2)
            cpu.put_float(RAM+0xCD14, 1)
            cpu.execute(0x3EBCC, FINE_WRITES)
            cpu.select()
            self.assertEqual(cpu.get_float(RAM+0xCCF8), -2)
            cpu.learn(knock=True)
            cpu.execute(0x3F386, FINE_WRITES)
            self.assertEqual(cpu.get_float(RAM+0xCD44), 2.75)
            # The actual parent calls 3DB90 before 3DC9C. The new learned
            # record and shared offset enter CCF8 at its next publication.
            cpu.select()
            cpu.execute(0x3F386, FINE_WRITES)
            self.assertAlmostEqual(cpu.get_float(RAM+0xCD44), 1.7, places=5)
            self.assertEqual(cpu.get_float(IAM), .75)

    def test_large_fine_correction_reenters_rough_mode_then_native_parent_resets_grid(self):
        for name, image in self.images.items():
            for correction in (-3, -4):
                cpu = KnockLearningMachine(image)
                cell = cpu.select()
                cpu.put_retained(GRID+8*cell, correction)
                cpu.execute(0x3DB90, FINE_WRITES)
                cpu.write(RAM+0xCD3A, 1, 1)  # Native rough load window remains eligible.
                updated = cpu.learn(knock=True)
                cpu.execute(0x3EF74, FINE_WRITES)
                self.assertEqual(cpu.read(STATUS, 1), 0xDA if correction == -4 else 0xD5)
                cpu.qualify_reset()
                self.assertEqual(cpu.get_float(GRID+8*cell), 0 if correction == -4 else updated)
                expected_iam = (.5 if name == 'main' else 1) if correction == -4 else .75
                self.assertEqual(cpu.get_float(IAM), expected_iam)
                self.assertEqual(cpu.valid(0x29570), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
