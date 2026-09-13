#!/usr/bin/env python3
"""Execute protected knock records, native reset qualification and IAM recovery.

Stored values and knock-event/fault inputs are explicit fixtures. The native
record writers/validators, load gates, reset workers and IAM updater execute
their instructions. This does not reconstruct unlogged vehicle history or
model the knock sensor, EEPROM transport or task timing.
"""
import _test_paths
from itertools import product
import unittest

from test_avcs_diagnostic_process_flow import AVCSDiagnosticMachine, RAM, ROOT
from test_primary_fueling_execution import bits
from test_runtime_rom_checksum_execution import before_pump_scaling

GRID, IAM, STEP, STATUS = (RAM+a for a in (0x831C, 0x851C, 0x8524, 0x852C))


def records(bases):
    return {(a+offset, width) for a in bases
            for offset, width in ((0, 4), (4, 2), (6, 2))}


GRID_WRITES = records(GRID+8*i for i in range(64))
IAM_WRITES = records((IAM, STEP)) | {(STATUS, 1)}
RESET_WRITES = GRID_WRITES | IAM_WRITES | {
    (RAM+a, 1) for a in (0xCD38, 0xCD39, 0xCD3A, 0xCD40)} | {
    (RAM+a, 4) for a in (0xCCFC, 0xCD00)}
RECOVERY_WRITES = IAM_WRITES | {(RAM+a, 1) for a in range(0xCD3C, 0xCD40)}
UPDATE_WRITES = IAM_WRITES | {(RAM+a, 1) for a in range(0xCD38, 0xCD3C)}
VALIDATION_WRITES = records((RAM+0x8228, *(RAM+0x82EC+8*i for i in range(6)))) \
    | GRID_WRITES | IAM_WRITES


class KnockRetainedMachine(AVCSDiagnosticMachine):
    LOOKUPS = AVCSDiagnosticMachine.LOOKUPS | {
        0x2078, 0x273EC, 0x292FC, 0x3D916, 0x3EA2E, 0x3D9E8,
        0x3E044, 0x3E082, 0x3E08E, 0x3F256,
        0x3BB26, 0x349DC, 0x650D4, 0x6521C, 0x65208,
        0x650BA, 0x17960, 0x3F1C4, 0x3F21E,
    }

    def __init__(self, image):
        super().__init__(image)
        for a in range(0xCD00, 0xCD45):
            self.write(RAM+a, 0, 1)
        self.write(STATUS, 0xDA, 1)  # Unrelated upper bits are canaries.
        self.write(RAM+0x852D, 0xA55AA5, 3)
        for a in (0xD26D, 0xD26E, 0xD270, 0xB460):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0x8274, 1, 1)  # Explicit valid AVCS rest-learning state.
        self.write(RAM+0x8224, 0x00FF, 2)
        self.write(RAM+0x8226, 0x40, 1)
        self.put_retained(RAM+0x8228, 0)
        for i in range(6):
            self.put_retained(RAM+0x82EC+8*i, -i/8)
        for i in range(64):
            self.put_retained(GRID+8*i, -i/16)
        self.put_retained(IAM, .75)
        self.put_retained(STEP, .125)
        self.put_float(RAM+0xCCFC, -2)
        self.put_float(RAM+0xCD00, -3)
        self.put_float(RAM+0xCD30, 5)
        self.write(RAM+0xCD3C, 1, 1)
        self.execute(0x3B9E8, {(RAM+0xCC4C, 1)})

    def put_retained(self, address, value):
        argument, fargument = self.original_r[4], self.original_fr[4]
        self.original_r[4], self.original_fr[4] = address, bits(value)
        self.execute(0x49530, records((address,)))
        self.original_r[4], self.original_fr[4] = argument, fargument

    def valid(self, entry):
        self.execute(entry, VALIDATION_WRITES)
        return self.r[0]

    def recovery(self):
        self.execute(0x3F020, RECOVERY_WRITES)
        return self.get_float(IAM)

    def qualify_reset(self, rpm=2800, load=2):
        self.put_float(RAM+0xB544, rpm)
        self.put_float(RAM+0xB438, load)
        for entry in (0x3EBDC, 0x3EC6C, 0x3ECB6):
            self.execute(entry, RESET_WRITES)
        return self.read(RAM+0xCD3A, 1)

    def update(self, knock=False):
        event_address = RAM | self.read(0x17976, 2)
        self.write(event_address, 0x80 if knock else 0, 1)
        self.execute(0x3ED6C, UPDATE_WRITES)
        return self.get_float(IAM), self.get_float(STEP)


class KnockRetainedProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x29570, 0x295D8), (0x3D916, 0x3DA30),
                         (0x3E044, 0x3E096), (0x3E9FC, 0x3EB38),
                         (0x3EBDC, 0x3F368), (0x49530, 0x4969C),
                         (0x3B9C0, 0x3BC68), (0x349DC, 0x349FC)):
                assert image[a:b] == cls.stock[a:b], hex(a)

    def test_native_initializer_uses_each_images_iam_calibration_and_protects_adjacent_records(self):
        for name, image in self.images.items():
            cpu = KnockRetainedMachine(image)
            last = cpu.read(GRID+63*8, 8)
            cpu.execute(0x3E9FC, IAM_WRITES)
            self.assertEqual(cpu.get_float(IAM), .5 if name == 'main' else 1)
            self.assertEqual(cpu.get_float(STEP), .5)
            self.assertEqual(cpu.read(STATUS, 1), 0xDA)
            self.assertEqual(cpu.valid(0x3EA2E), 0)
            self.assertEqual(cpu.read(GRID+63*8, 8), last)
            self.assertEqual(cpu.read(RAM+0x852D, 3), 0xA55AA5)

    def test_grid_validation_repairs_either_checksum_copy_without_reading_iam(self):
        for image, cell, offset in product(self.images.values(), (0, 31, 63), (4, 6)):
            cpu = KnockRetainedMachine(image)
            a = GRID+8*cell
            correct = cpu.read(a+offset, 2)
            cpu.write(a+offset, correct ^ 1, 2)
            self.assertEqual(cpu.valid(0x3D9E8), 0)
            self.assertEqual(cpu.read(a+4, 2), correct)
            self.assertEqual(cpu.read(a+6, 2), correct)
            self.assertNotIn(IAM, cpu.reads)
            self.assertEqual(cpu.get_float(a), -cell/16)

    def test_bad_grid_record_stops_validation_at_the_first_failure(self):
        for image, cell in product(self.images.values(), (0, 31, 63)):
            cpu = KnockRetainedMachine(image)
            a = GRID+8*cell
            cpu.write(a+4, cpu.read(a+4, 2) ^ 1, 2)
            cpu.write(a+6, cpu.read(a+6, 2) ^ 2, 2)
            self.assertEqual(cpu.valid(0x3D9E8), 1)
            self.assertEqual(cpu.entered.count(0x4963A), cell+1)
            self.assertNotIn(a+8, cpu.reads)
            self.assertEqual(cpu.get_float(IAM), .75)

    def test_ignition_retained_parent_checks_all_groups_and_both_two_bit_status_fields(self):
        for image in self.images.values():
            cpu = KnockRetainedMachine(image)
            self.assertEqual(cpu.valid(0x29570), 0)
            for target in (0x273EC, 0x292FC, 0x3D916, 0x3EA2E, 0x3D9E8):
                self.assertIn(target, cpu.entered)
            for a in (RAM+0x8228, RAM+0x82EC, IAM, STEP, GRID+63*8):
                cpu = KnockRetainedMachine(image)
                cpu.write(a+4, cpu.read(a+4, 2) ^ 1, 2)
                cpu.write(a+6, cpu.read(a+6, 2) ^ 2, 2)
                self.assertEqual(cpu.valid(0x29570), 1, hex(a))
            for low, upper in product(range(4), repeat=2):
                cpu.write(STATUS, 0xD0 | low | upper << 2, 1)
                self.assertEqual(cpu.valid(0x3EA2E),
                                 0 if low in (1, 2) and upper in (1, 2) else 1)

    def test_load_qualified_first_entry_resets_exactly_the_grid_and_iam_once(self):
        for name, image in self.images.items():
            cpu = KnockRetainedMachine(image)
            cpu.qualify_reset()
            self.assertEqual(cpu.get_float(IAM), .5 if name == 'main' else 1)
            self.assertEqual(cpu.get_float(STEP), .5)
            self.assertEqual(cpu.read(STATUS, 1), 0xD6)
            self.assertEqual(cpu.get_float(RAM+0xCCFC), 0)
            self.assertEqual(cpu.get_float(RAM+0xCD00), 0)
            self.assertTrue(all(cpu.get_float(GRID+8*i) == 0 for i in range(64)))
            self.assertEqual(cpu.valid(0x29570), 0)
            cpu.put_retained(GRID+63*8, -2)
            cpu.put_retained(IAM, .75)
            cpu.qualify_reset()
            self.assertEqual(cpu.get_float(IAM), .75)
            self.assertEqual(cpu.get_float(GRID+63*8), -2)
            self.assertEqual(cpu.read(RAM+0x852D, 3), 0xA55AA5)

    def test_reset_parent_respects_load_window_feedback_permission_and_advance_threshold(self):
        for image, rpm, load, advance, feedback, status in product(
                self.images.values(), (1500, 2800, 4500), (.5, 2, 4.5),
                (3.9, 4), (0, 1), (0xDA, 0xD9)):
            cpu = KnockRetainedMachine(image)
            cpu.put_float(RAM+0xCD30, advance)
            cpu.write(RAM+0xCD22, feedback, 1)
            cpu.write(STATUS, status, 1)
            cpu.qualify_reset(rpm, load)
            expected = rpm == 2800 and load == 2 and advance == 4 and feedback == 0 and status == 0xDA
            self.assertEqual(cpu.get_float(GRID+63*8), 0 if expected else -63/16)
            if not expected:
                self.assertEqual(cpu.get_float(IAM), .75)

    def test_feature_and_fault_parents_force_zero_then_restore_calibrated_iam_on_recovery(self):
        for name, image in self.images.items():
            for address, value in ((0x8274, 0), (0x8274, 2), (0xD26D, 2),
                                   (0xD26E, 4), (0xD270, 0x80)):
                cpu = KnockRetainedMachine(image)
                old = cpu.read(RAM+address, 1)
                cpu.write(RAM+address, value, 1)
                self.assertEqual(cpu.recovery(), 0)
                self.assertEqual(cpu.get_float(STEP), .5)
                self.assertEqual(cpu.read(STATUS, 1), 0xDA)
                self.assertEqual(cpu.get_float(GRID+63*8), -63/16)
                cpu.write(RAM+address, old, 1)
                self.assertEqual(cpu.recovery(), .5 if name == 'main' else 1)
                cpu.put_retained(IAM, .625)
                self.assertEqual(cpu.recovery(), .625)  # No edge, no reset.
                self.assertEqual(cpu.valid(0x3EA2E), 0)

    def test_disabled_feature_preserves_iam_but_consumes_recovery_history(self):
        for image in self.images.values():
            cpu = KnockRetainedMachine(image)
            cpu.write(RAM+0xCC4C, cpu.read(RAM+0xCC4C, 1) & ~0x40, 1)
            cpu.write(RAM+0xD26E, 4, 1)
            self.assertEqual(cpu.recovery(), .75)
            self.assertEqual(cpu.read(RAM+0xCD3D, 1), 2)
            cpu.write(RAM+0xD26E, 0, 1)
            self.assertEqual(cpu.recovery(), .75)
            self.assertEqual(cpu.read(RAM+0xCD3D, 1), 0)
            cpu.execute(0x3B9E8, {(RAM+0xCC4C, 1)})
            self.assertEqual(cpu.recovery(), .75)

    def test_changed_upper_load_limit_alters_reset_eligibility_with_native_hysteresis(self):
        for name, image in self.images.items():
            cpu = KnockRetainedMachine(image)
            cpu.qualify_reset(load=3)
            self.assertEqual(cpu.get_float(GRID+63*8), -63/16 if name == 'main' else 0)
            high = 2.2 if name == 'main' else 4
            cpu = KnockRetainedMachine(image)
            cpu.qualify_reset(load=high+.01)
            self.assertEqual(cpu.get_float(GRID+63*8), -63/16)
            cpu.qualify_reset(load=high-.05)
            self.assertEqual(cpu.get_float(GRID+63*8), -63/16)
            cpu.qualify_reset(load=high-.11)
            self.assertEqual(cpu.get_float(GRID+63*8), 0)

    def test_native_iam_learning_waits_for_qualified_events_and_halves_step_on_direction_change(self):
        for image in self.images.values():
            cpu = KnockRetainedMachine(image)
            cpu.write(RAM+0xCD3A, 2, 1)  # Qualified parent; event input is explicit.
            for i in range(255):
                self.assertEqual(cpu.update(), (.75, .125), i)
                self.assertEqual(cpu.read(RAM+0xCD38, 1), i+1)
            self.assertEqual(cpu.read(RAM+0xCD3B, 1), 255)
            self.assertEqual(cpu.update(), (.875, .125))
            self.assertEqual(cpu.read(RAM+0xCD38, 1), 0)
            self.assertEqual(cpu.update(knock=True), (.8125, .0625))
            self.assertEqual(cpu.update(knock=True), (.75, .0625))
            cpu.write(RAM+0xCD38, 255, 1)
            self.assertEqual(cpu.update(), (.78125, .03125))
            self.assertEqual(cpu.valid(0x3EA2E), 0)
            self.assertEqual(cpu.get_float(GRID+63*8), -63/16)
            for diagnostic, qualified in ((4, 2), (0, 0)):
                cpu.write(RAM+0xD26D, diagnostic, 1)
                cpu.write(RAM+0xCD3A, qualified, 1)
                self.assertEqual(cpu.update(knock=True), (.78125, .03125))

    def test_iam_learning_clamps_bounds_and_preserves_the_record_metadata(self):
        for image, value, knock in product(self.images.values(), (0, 1), (False, True)):
            cpu = KnockRetainedMachine(image)
            cpu.put_retained(IAM, value)
            cpu.put_retained(STEP, .5)
            cpu.write(RAM+0xCD3A, 2, 1)
            cpu.write(RAM+0xCD38, 255, 1)
            result, step = cpu.update(knock)
            self.assertEqual(result, max(0, min(1, value+(-.5 if knock else .5))))
            self.assertEqual(step, .5)
            self.assertEqual(cpu.valid(0x3EA2E), 0)
            self.assertEqual(cpu.read(RAM+0x852D, 3), 0xA55AA5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
