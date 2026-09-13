#!/usr/bin/env python3
"""Execute the native startup capture-inhibit latch and periodic release.

Retained validation flags and measured/requested throttle values are explicit
inputs. No physical throttle, retained-memory validity, task cadence or time
deadline is inferred. The real latch, getters, ratio test, delay counter and
decoder request/loss-message path execute on all three pinned images.
"""
import _test_paths
from itertools import product
import unittest

from test_crank_decoder_process_flow import CrankDecoderMachine, DECODER_WRITES
from test_sync_transition_process_flow import ROOT, RAM
from test_runtime_rom_checksum_execution import before_pump_scaling

LATCH_WRITES = {(RAM+0xB542, 1), (RAM+0xB540, 2)}


class CaptureInhibitMachine(CrankDecoderMachine):
    LOOKUPS = CrankDecoderMachine.LOOKUPS | {
        0x16270, 0x2F64A, 0x37704, 0x65366, 0x653BA, 0x24FC,
    }

    def __init__(self, image):
        super().__init__(image)
        for a, value in ((0x80D4, 1), (0x829C, 1), (0x82A0, 0),
                         (0xC618, 0), (0xD36C, 0), (0xD273, 0),
                         (0xD274, 0), (0xB542, 0xFF), (0xB525, 0x7F)):
            self.write(RAM+a, value, 1)
        self.write(RAM+0xB540, 0, 2)
        self.put_float(RAM+0xC2B4, 20)
        self.put_float(RAM+0xABD4, 16)

    def startup(self):
        self.execute(0x1A428, LATCH_WRITES)

    def release(self):
        self.execute(0x1A368, LATCH_WRITES)


class CaptureInhibitProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x1A368, 0x1A4A4), (0x16270, 0x1627E),
                         (0x162C8, 0x162CA), (0x2F64A, 0x2F658),
                         (0x2F680, 0x2F682), (0x37704, 0x3771A),
                         (0x65366, 0x6537A), (0x653BA, 0x653D2),
                         (0x24FC, 0x2540), (0x73806, 0x73808),
                         (0x73B90, 0x73B94), (0xFF68, 0xFF6E),
                         (0x1018C, 0x10190), (0x10CBC, 0x10CC0)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_startup_sets_only_the_high_bit_from_retained_validation_inputs(self):
        for image, valid, reset, learned, prior in product(
                self.images.values(), (0, 1), (0, 1, 2), (0, 1, 2), (0x35, 0xB5)):
            cpu = CaptureInhibitMachine(image)
            cpu.write(RAM+0x80D4, 0xFE | valid, 1)
            cpu.write(RAM+0x82A0, reset, 1)
            cpu.write(RAM+0x829C, learned, 1)
            cpu.write(RAM+0xB542, prior, 1)
            cpu.startup()
            inhibit = (not valid) or reset == 1 or learned == 0
            self.assertEqual(cpu.read(RAM+0xB542, 1), 0x35 | (0x80 if inhibit else 0))
            self.assertEqual(cpu.read(RAM+0xB540, 2), 25)

    def test_release_requires_native_ratio_and_all_four_gates_or_a_selected_fault(self):
        for image, valid, other, monitor, learned in product(
                self.images.values(), (0, 1), (0, 1), (0, 0x80), (0, 1, 2)):
            cpu = CaptureInhibitMachine(image)
            cpu.write(RAM+0x80D4, valid, 1)
            cpu.write(RAM+0xC618, other, 1)
            cpu.write(RAM+0xD36C, monitor, 1)
            cpu.write(RAM+0x829C, learned, 1)
            cpu.release()
            released = valid == 1 and other == 0 and monitor == 0 and learned == 1
            self.assertEqual(cpu.read(RAM+0xB542, 1), 0x7F if released else 0xFF)
        for image, actual in product(self.images.values(), (15.99, 16, 16.01)):
            cpu = CaptureInhibitMachine(image)
            cpu.put_float(RAM+0xC2B4, 20)
            cpu.put_float(RAM+0xABD4, actual)
            cpu.release()
            self.assertEqual(cpu.read(RAM+0xB542, 1), 0x7F if actual >= 16 else 0xFF)
        for image, fault_a, fault_b in product(self.images.values(), (0, 4), (0, 0x40)):
            cpu = CaptureInhibitMachine(image)
            cpu.write(RAM+0x80D4, 0, 1)
            cpu.write(RAM+0xD273, fault_a, 1)
            cpu.write(RAM+0xD274, fault_b, 1)
            cpu.put_float(RAM+0xC2B4, 0)
            cpu.release()
            self.assertEqual(cpu.read(RAM+0xB542, 1), 0x7F if fault_a or fault_b else 0xFF)

    def test_near_zero_request_holds_latch_but_counter_decrements_without_rearming(self):
        for image, request in product(self.images.values(), (0, .001, -.001)):
            cpu = CaptureInhibitMachine(image)
            cpu.write(RAM+0x80D4, 0, 1)
            cpu.startup()
            cpu.write(RAM+0x80D4, 1, 1)
            cpu.put_float(RAM+0xC2B4, request)
            for tick in range(30):
                cpu.release()
                self.assertEqual(cpu.read(RAM+0xB540, 2), max(0, 24-tick))
                self.assertEqual(cpu.read(RAM+0xB542, 1), 0xFF)
            cpu.put_float(RAM+0xC2B4, 20)
            cpu.release()
            self.assertEqual(cpu.read(RAM+0xB542, 1), 0x7F)
            # Every input that would prevent release is now made unfavorable.
            # The periodic service still has no setting path, at any RPM.
            for a, value in ((0x80D4, 0), (0x82A0, 1), (0x829C, 0),
                             (0xC618, 1), (0xD36C, 0x80)):
                cpu.write(RAM+a, value, 1)
            cpu.put_float(RAM+0xABD4, 0)
            for rpm in (0, 1000, 2500, 2800, 3000, 3500, 4144):
                cpu.put_float(RAM+0xB544, rpm)
                cpu.release()
                self.assertEqual(cpu.read(RAM+0xB542, 1), 0x7F)
                self.assertEqual(cpu.read(RAM+0xB540, 2), 0)

    def test_latch_propagates_to_decoder_loss_once_then_releases_capture(self):
        for image in self.images.values():
            cpu = CaptureInhibitMachine(image)
            cpu.write(RAM+0x80D4, 0, 1)
            cpu.startup()
            cpu.write(RAM+0xAC16, 1, 1)
            cpu.write(RAM+0xAC3C, 1, 1)
            count = cpu.read(RAM+0x9306, 1)
            writes = DECODER_WRITES | {(RAM+0xB52B, 1)}
            cpu.execute(0x1A0BA, writes)
            self.assertEqual(cpu.read(RAM+0xAC22, 1), 1)
            self.assertEqual(cpu.read(RAM+0xAC16, 1), 0)
            self.assertEqual(cpu.read(RAM+0x9306, 1), count+1)
            cpu.execute(0x1A0BA, writes)
            self.assertEqual(cpu.read(RAM+0x9306, 1), count+1)
            cpu.write(RAM+0x80D4, 1, 1)
            cpu.release()
            cpu.execute(0x1A0BA, writes)
            self.assertEqual(cpu.read(RAM+0xAC22, 1), 0)
            self.assertEqual(cpu.read(RAM+0x9306, 1), count+1)
            cpu.waveform()
            self.assertEqual(cpu.read(RAM+0xAC16, 1), 1)
            self.assertEqual(cpu.read(RAM+0x9306, 1), count+2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
