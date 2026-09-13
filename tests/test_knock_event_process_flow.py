#!/usr/bin/env python3
"""Native knock-sample processing and publication; physical samples explicit.

The AN24 sample, AN30 reference, phase callbacks and timer progress are
supplied inputs. Native histories and event publication execute ROM instructions.
This does not synthesize a knock waveform or infer the car's sensor state.
"""
import _test_paths
from itertools import product
import unittest

from test_knock_feedback_process_flow import (
    KnockFeedbackMachine, RAM, ROOT, FEEDBACK_WRITES,
)
from test_sync_transition_process_flow import SIGNAL_WORK_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling

EVENT_WRITES = {(RAM+0xAD94, 1), (RAM+0xAE4B, 1)} | {
    (RAM+0xAE45+i, 1) for i in range(6)} | {
    (RAM+a, 4) for a in (0xAE24, 0xADA0, 0xAD9C, 0xADD4, 0xADF8,
                         0xADD8, 0xADDC, 0xADFC, 0xAE00, 0xAE04,
                         *range(0xADBC, 0xADD4, 4), *range(0xADE0, 0xADF8, 4),
                         *range(0xADA4, 0xADBC, 4), *range(0xAE0C, 0xAE24, 4))}
BACKGROUND_WRITES = {(RAM+a, 2) for a in (0xAE32, 0xAE30, 0xAE2E, 0xAE2C)} | {
    (RAM+0xAE08, 4), (RAM+0xAE28, 4), (RAM+0xAE3E, 1)}
SERIAL_WRITES = {(RAM+a, 1) for a in range(0xF000, 0xF007)} | {
    (RAM+0xF72C, 2), (RAM+0xF764, 2)}
WINDOW_WRITES = SERIAL_WRITES | {(RAM+0xAB50, 1)} | {
    (RAM+a, 2) for a in (0xF610, 0xF620, 0xF65C, 0xF66A, 0xF66C)}
PHASE_WRITES = WINDOW_WRITES | EVENT_WRITES | {
    (RAM+a, 1) for a in (*range(0xAE34, 0xAE3E), *range(0xAE3F, 0xAE45),
                        0xF858, 0xF859)} | {(RAM+0xAD98, 2)}


class KnockEventMachine(KnockFeedbackMachine):
    LOOKUPS = KnockFeedbackMachine.LOOKUPS | {
        0xADD8, 0xAEEC, 0x7748, 0x77AA, 0x4BC8, 0x4C20,
        0xD744, 0xA7EA, 0x740C,
    }

    def __init__(self, image, cylinder=0, reference=0, captured=0):
        super().__init__(image)
        # Normal startup DMA clears this work bank. The actual initializer
        # then assigns its defaults; retained offsets are explicit zero here.
        for a in range(0xAD90, 0xAE60):
            self.write(RAM+a, 0, 1)
        for i in range(12):
            self.write(RAM+0xC68C+i, image[0x7B250+i], 1)
        self.execute(0xA76C, SIGNAL_WORK_WRITES)
        self.write(RAM+0xAE3C, cylinder, 1)
        self.write(RAM+0xAE2C, reference, 2)
        self.write(RAM+0xAD98, captured, 2)
        self.put_float(RAM+0xAC00, 2800)
        self.write(RAM+0xB688, 250, 2)
        for a in (0xAB50, 0xAB51, *range(0xF000, 0xF007), 0xF858):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xF859, 15, 1)
        self.write(RAM+0xF840, captured, 2)
        self.an24 = captured
        for a, value in ((0xF600, 1000), (0xF610, 0), (0xF620, 0),
                         (0xF65C, 0), (0xF666, 0), (0xF66A, 0xE55A),
                         (0xF66C, 0xA55A), (0xF72C, 0x1234), (0xF764, 0xAA54)):
            self.write(RAM+a, value, 2)
        self.write(RAM+0xAC08, 1536, 4)
        self.write(RAM+0xAC1C, 16000, 4)

    def write(self, address, value, size=4, record=False):
        if record and address == RAM+0xF858:
            # ADF cannot be set by the CPU. Completion is supplied below.
            value = (value & 127) | (value & self.read(address, 1) & 128)
        if record and address == RAM+0xF66A:
            # TSR8 status: writing one preserves the bit; zero clears it.
            value &= self.read(address, 2)
        super().write(address, value, size, record)
        if (record and address == RAM+0xF859 and value & 32
                and self.read(RAM+0xF858, 1) & 127 == 0x18):
            # Explicit immediate one-off AN24 completion, not conversion time.
            assert self.an24 & 63 == 0 and 0 <= self.an24 <= 65472
            self.write(RAM+0xF840, self.an24, 2)
            self.write(RAM+0xF858, self.read(RAM+0xF858, 1) | 128, 1)
            self.write(RAM+0xF859, value & ~32, 1)

    def step(self, in_delay=False):
        if self.pc == 0x77DE:
            # Explicit SCI0 receive/transmit completion at the native poll.
            self.write(RAM+0xF004, self.read(RAM+0xF004, 1) | 0xC0, 1)
            self.write(RAM+0xF005, 0x5A, 1)
        op = self.read(self.pc, 2)
        if op & 0xF0FF == 0xF00D:  # FSTS FPUL,FRn: raw bits, not FLOAT.
            self.fr[(op >> 8) & 15] = self.fpul
            self.trace.append((self.pc, op))
            self.pc += 2
            self.instructions += 1
            return
        return super().step(in_delay)

    def sample_event(self):
        self.execute(0xAA50, EVENT_WRITES)
        return self.read(RAM+0xAD94, 1)

    def publish_event(self):
        self.execute(0x17914, {(RAM+0xB460, 1)})
        return self.read(RAM+0xB460, 1) & 0x80

    def phase(self, code):
        self.original_r[4] = code
        self.execute(0xA8F0, PHASE_WRITES)


class KnockEventProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0xA76C, 0xB0AC), (0x740C, 0x74BA),
                         (0x7536, 0x7550), (0x7748, 0x7840),
                         (0x4BC8, 0x4C4C), (0x17914, 0x17980),
                         (0x17980, 0x17984), (0x77D50, 0x77D52),
                         (0x5CD8, 0x5CE4), (0x5D70, 0x5D78),
                         (0x2FCC, 0x2FD0),
                         (0xD744, 0xD77C), (0xFB74, 0xFB86),
                         (0x608E4, 0x60980), (0x7B250, 0x7B280),
                         (0x7B2B4, 0x7B2DC),
                         (0x7B8D0, 0x7BAF0)):
                assert image[a:b] == stock[a:b], hex(a)
            assert int.from_bytes(image[0x11D24:0x11D28], 'big') == 0x17914
            assert int.from_bytes(image[0x10C88:0x10C8C], 'big') == 0x17942

    def test_unrecognized_phase_bytes_do_not_enter_or_write_sample_state(self):
        for image in self.images.values():
            valid = set(image[0xFB7A:0xFB86])
            cpu = KnockEventMachine(image, cylinder=255)
            for code in set(range(256))-valid:
                cpu.phase(code)
                self.assertFalse(cpu.entered)
                self.assertTrue(all(cpu.min_sp <= a < cpu.STACK for a, _ in cpu.writes))
                self.assertEqual(cpu.read(RAM+0xAE3C, 1), 255)

    def test_native_phase_handoff_bounds_all_six_arrays_and_skips_startup_sentinel(self):
        for image in self.images.values():
            cpu = KnockEventMachine(image, cylinder=255, reference=60000, captured=1024)
            protected = {a: 0xA5A00000+i for i, a in enumerate(
                (*cpu.wideband_outputs, cpu.lean_counter_ram, cpu.lean_state_ram))}
            for a, value in protected.items():
                cpu.write(a, value, 4)
            for lap in range(3):
                for cylinder in range(6):
                    previous = cpu.read(RAM+0xAE3C, 1)
                    cpu.phase(image[0xFB7A+cylinder])
                    self.assertEqual(cpu.read(RAM+0xAE3B, 1), cylinder)
                    self.assertEqual(any(pc == 0xAA50 for pc, _ in cpu.trace), previous != 255)
                    self.assertTrue(previous in range(6) or previous == 255)
                    cpu.write(RAM+0xF666, 0x4000, 2)  # Supplied active window.
                    old_ready = cpu.read(RAM+0xAE3D, 1)
                    cpu.phase(image[0xFB80+(cylinder+1) % 6])
                    self.assertEqual(cpu.read(RAM+0xAE3D, 1), 1)
                    self.assertEqual(cpu.read(RAM+0xAE3C, 1), cylinder if old_ready else previous)
                    self.assertEqual(cpu.read(RAM+0xAD98, 2), 1024)
                    self.assertIn(0x740C, cpu.entered)
                    self.assertEqual(cpu.read(RAM+0xF003, 1),
                                     cpu.read(RAM+0xAB50, 1) | cpu.read(RAM+0xAB51, 1))
                    for a, value in protected.items():
                        self.assertEqual(cpu.read(a, 4), value, hex(a))

    def test_sample_subtraction_gain_and_adaptive_threshold_are_bounded_per_cylinder(self):
        for image, cylinder, reference, captured, gain in product(
                self.images.values(), range(6), (0, 32768, 65472),
                (0, 16384, 65472), (0, 2, 4, 5, 6)):
            cpu = KnockEventMachine(image, cylinder, reference, captured)
            cpu.write(RAM+0xAE35+cylinder, gain, 1)
            cpu.write(RAM+0xAE3F+cylinder, cpu.read(RAM+0xAE45+cylinder, 1), 1)
            unselected = {(base, i): cpu.read(RAM+base+4*i, 4)
                          for base in (0xADA4, 0xADBC, 0xADE0, 0xAE0C)
                          for i in range(6) if i != cylinder}
            event = cpu.sample_event()
            self.assertAlmostEqual(cpu.get_float(RAM+0xAE24), max(0, reference-captured)*5/65536)
            strength, threshold = (cpu.get_float(RAM+a) for a in (0xADA0, 0xAE04))
            self.assertGreaterEqual(strength, 0)
            self.assertLessEqual(strength, 288)
            self.assertGreaterEqual(threshold, 32)
            self.assertLessEqual(threshold, 276)
            self.assertEqual(event, int(strength >= threshold))
            for (base, i), value in unselected.items():
                self.assertEqual(cpu.read(RAM+base+4*i, 4), value)

    def test_reference_filter_updates_only_between_500_and_2000_rpm(self):
        for image, rpm in product(self.images.values(), (0, 499, 500, 1999, 2000, 2800, 3500)):
            cpu = KnockEventMachine(image, reference=10000)
            cpu.put_float(RAM+0xAE28, 10000)
            cpu.write(RAM+0xAB3C, 30016, 2)  # Native AN30 normal-scan handoff.
            cpu.put_float(RAM+0xAC00, rpm)
            cpu.execute(0xA9A8, BACKGROUND_WRITES)
            self.assertEqual(cpu.read(RAM+0xAE2E, 2), 30016)
            expected = 10000 + (30016-10000)*cpu.get_float(0x7287C) if 500 <= rpm < 2000 else 10000
            self.assertAlmostEqual(cpu.get_float(RAM+0xAE28), expected, delta=.002)
            self.assertEqual(cpu.read(RAM+0xAE2C, 2), int(expected))
            self.assertNotIn(RAM+0xAB06, cpu.reads)
            self.assertEqual(cpu.read(RAM+0xAE3E, 1), 0)

    def test_window_timing_handles_future_late_and_wrap_without_other_channel_writes(self):
        fixtures = ((1000, 16000, 512, (1064, 1160)),
                    (1080, 16000, 512, (1083, 1160)),
                    (1200, 16000, 512, (1203, 1203)),
                    (65534, 0xFFFE0, 0, (1, 94)))
        for image, (counter, timestamp, lead, expected) in product(self.images.values(), fixtures):
            cpu = KnockEventMachine(image)
            cpu.write(RAM+0xF600, counter, 2)
            cpu.write(RAM+0xAC1C, timestamp, 4)
            cpu.write(RAM+0xAE32, lead, 2)
            cpu.write(RAM+0xAE30, 768, 2)
            others = (*range(0xF640, 0xF65C, 2), 0xF65E, 0xF622,
                      *range(0xF444, 0xF454, 2), *range(0xF604, 0xF610, 2),
                      *range(0xF614, 0xF620, 2), 0xF666)
            protected = {RAM+a: 0xA500+i for i, a in enumerate(others)}
            for a, value in protected.items():
                cpu.write(a, value, 2)
            cpu.execute(0xADD8, WINDOW_WRITES)
            self.assertEqual(tuple(cpu.read(RAM+a, 2) for a in (0xF620, 0xF610)), expected)
            self.assertEqual(cpu.read(RAM+0xF65C, 2), 65535)
            self.assertEqual(cpu.read(RAM+0xF66A, 2), 0xA55A)
            self.assertEqual(cpu.read(RAM+0xF66C, 2), 0xE55A)
            self.assertEqual(cpu.read(RAM+0xF72C, 2), 0xD234)
            self.assertEqual(cpu.read(RAM+0xF764, 2), 0xAA55)
            for a, value in protected.items():
                self.assertEqual(cpu.read(a, 2), value, hex(a))

    def test_publication_qualifies_runtime_exact_event_and_native_reset(self):
        for image, runtime, event in product(self.images.values(), (0, 249, 250, 65535), (0, 1, 2, 255)):
            cpu = KnockEventMachine(image)
            cpu.write(RAM+0xB688, runtime, 2)
            cpu.write(RAM+0xAD94, event, 1)
            cpu.write(RAM+0xB460, 0xD5, 1)
            self.assertEqual(cpu.publish_event(), 128 if runtime >= 250 and event == 1 else 0)
            self.assertEqual(cpu.read(RAM+0xB460, 1) & 127, 0x55)
            for reset in (0, 128):
                old = cpu.read(RAM+0xB460, 1)
                cpu.write(RAM+0xB52C, reset, 1)
                cpu.execute(0x17942, {(RAM+0xB460, 1)})
                self.assertEqual(cpu.read(RAM+0xB460, 1), old & 127 if reset else old)

    def test_real_sample_event_reaches_feedback_without_an_inserted_knock_flag(self):
        for image, reference in product(self.images.values(), (0, 65472)):
            cpu = KnockEventMachine(image, reference=reference)
            cpu.put_float(RAM+0xB3AC, 67)
            event = cpu.sample_event()
            self.assertEqual(event, int(reference != 0))
            self.assertEqual(cpu.publish_event(), 128*event)
            for pointer in (0x11DA8, 0x11DAC, 0x11DB0, 0x11DB4):
                cpu.execute(cpu.read(pointer, 4), FEEDBACK_WRITES)
            self.assertAlmostEqual(cpu.get_float(RAM+0xCD14), -1.05 if event else 0, places=5)

    def test_completion_callback_captures_an24_and_clears_only_its_interrupt_bit(self):
        for image, sample in product(self.images.values(), (0, 16384, 65472)):
            cpu = KnockEventMachine(image, captured=sample)
            cpu.write(RAM+0xAB06, 40000, 2)
            cpu.write(RAM+0xF806, 40000, 2)
            cpu.write(RAM+0xF66C, 0xE55A, 2)
            cpu.execute(cpu.read(0x2FCC, 4), PHASE_WRITES)
            self.assertEqual(cpu.read(RAM+0xAD98, 2), sample)
            self.assertIn(0x740C, cpu.entered)
            self.assertEqual(cpu.read(RAM+0xF66A, 2), 0xA55A)
            self.assertEqual(cpu.read(RAM+0xF66C, 2), 0xA55A)
            self.assertNotIn(RAM+0xAB06, cpu.reads)
            self.assertEqual(cpu.read(RAM+0xF806, 2), 40000)
            self.assertEqual(cpu.read(RAM+0xAB06, 2), 40000)

    def test_gain_selection_and_resync_keep_history_inside_its_native_bank(self):
        levels = ((0, 6, 0x20), (64, 5, 0x18), (96, 4, 0x10),
                  (128, 2, 8), (192, 0, 0), (300, 0, 0))
        for image, cylinder, (threshold, gain, command) in product(self.images.values(), range(6), levels):
            cpu = KnockEventMachine(image, reference=65472)
            cpu.write(RAM+0xAE3B, cylinder, 1)
            following = (cylinder+1) % 6
            cpu.put_float(RAM+0xAE0C+4*following, threshold)
            cpu.execute(0xAEEC, PHASE_WRITES)
            self.assertEqual(cpu.read(RAM+0xAE35+following, 1), gain)
            self.assertEqual(cpu.read(RAM+0xAB50, 1) & 0x38, command)
            self.assertEqual(cpu.read(RAM+0xAE3F+following, 1), image[0x7B250+following])
            # The already traced sync callback invokes this native initializer.
            # It clears event/threshold histories but retains accumulated offsets.
            cpu.put_float(RAM+0xADBC+4*cylinder, 12.5)
            cpu.sample_event()
            offsets = cpu.read(RAM+0xADBC, 24)
            cpu.execute(0xA76C, SIGNAL_WORK_WRITES)
            self.assertEqual(cpu.read(RAM+0xADBC, 24), offsets)
            self.assertEqual(cpu.read(RAM+0xAD94, 1), 0)
            self.assertEqual(cpu.read(RAM+0xAE3C, 1), 255)
            self.assertEqual(cpu.read(RAM+0xAE3D, 1), 0)
            self.assertEqual(cpu.publish_event(), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
