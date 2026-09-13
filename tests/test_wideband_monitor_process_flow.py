#!/usr/bin/env python3
"""Execute the retained native current-span monitor with external WB state.

The external publisher supplies zero synthetic current on both valid and
invalid inputs. Monitor prerequisites and task calls below are explicit
fixtures; this is not a physical misfire or sensor acquisition simulation.
"""
import _test_paths
import struct
import unittest

from test_transient_fuel_execution import TransientFuelMachine
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT = _test_paths.ROOT
WRITES = {(a, 4) for a in range(0xFFFFD7EC, 0xFFFFD7FC, 4)} | {
    (0xFFFFD944, 1), (0xFFFFD94F, 1)}


class CurrentSpanMachine(TransientFuelMachine):
    def __init__(self, image, enrichment=.3):
        super().__init__(image)
        self.put_float(0xFFFFBDF8, enrichment)
        for address in (0xFFFFAE68, 0xFFFFAE6C):
            self.put_float(address, 0)
        for address, size in WRITES | {(0xFFFFD852, 1)}:
            self.write(address, 0, size)  # Normal startup DMA boundary.

    def table(self, target, descriptor, x, y):
        if descriptor == 0x5EF8C:
            assert target == 0x209C
            n, kind, axis, data, scale, bias = struct.unpack_from('>HHIIff', self.image, descriptor)
            assert kind == 0x800
            return self.interpolate(self.array(axis, n),
                                    [self.read(data+2*i, 2)*scale+bias for i in range(n)], x)
        return super().table(target, descriptor, x, y)

    def sample(self, bank1=0, bank2=0):
        self.put_float(0xFFFFAE68, bank1)
        self.put_float(0xFFFFAE6C, bank2)
        self.invoke(0x6DE50, WRITES)
        return self.read(0xFFFFD94F, 1) & 4


class WidebandMonitorFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        cls.images = {
            'main': (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes(),
            'v2': (ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes(),
        }
        cls.images['captured'] = before_pump_scaling(cls.images['v2'])
        for image in cls.images.values():
            for a, b in ((0x6DE50, 0x6DF70), (0x5EF8C, 0x5EFA0),
                         (0x75644, 0x75662), (0x74CF3, 0x74CF4),
                         (0x74E44, 0x74E48)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_zero_synthetic_current_never_sets_span_flag_across_two_monitor_windows(self):
        for name, image in self.images.items():
            for enrichment in (.249, .25, .3, .5, 1):
                cpu = CurrentSpanMachine(image, enrichment)
                for call in range(365):
                    self.assertEqual(cpu.sample(), 0, (name, enrichment, call))

    def test_imposed_current_span_sets_latches_then_native_window_reset_clears(self):
        for name, image in self.images.items():
            for bank in (1, 2):
                cpu = CurrentSpanMachine(image)
                cpu.write(0xFFFFD852, 1, 1)
                self.assertEqual(cpu.sample(), 0)  # Execute the real monitor reset.
                cpu.write(0xFFFFD852, 0, 1)
                self.assertEqual(cpu.sample(), 0)
                self.assertEqual(cpu.sample(8 if bank == 1 else 0, 8 if bank == 2 else 0), 0)
                # The comparison uses the span saved at function entry; the
                # new extremes become observable on the following invocation.
                self.assertEqual(cpu.sample(), 4, (name, bank))
                while cpu.read(0xFFFFD944, 1) < image[0x74CF3]:
                    self.assertEqual(cpu.sample(), 4)
                self.assertEqual(cpu.sample(), 0)
                self.assertEqual(cpu.read(0xFFFFD944, 1), 0)
                self.assertEqual(cpu.sample(), 0)

    def test_prerequisite_loss_clears_only_span_bit_and_resets_extrema(self):
        for image in self.images.values():
            for reason in ('disabled', 'below_enrichment'):
                cpu = CurrentSpanMachine(image)
                cpu.write(0xFFFFD94F, 0xA7, 1)
                cpu.write(0xFFFFD944, 20, 1)
                if reason == 'disabled':
                    cpu.write(0xFFFFD852, 1, 1)
                else:
                    cpu.put_float(0xFFFFBDF8, .249)
                self.assertEqual(cpu.sample(), 0)
                self.assertEqual(cpu.read(0xFFFFD94F, 1), 0xA3)
                self.assertEqual(cpu.read(0xFFFFD944, 1), 0)
                self.assertEqual([cpu.get_float(a) for a in range(0xFFFFD7EC, 0xFFFFD7FC, 4)],
                                 [-2, -2, 2, 2])


if __name__ == '__main__':
    unittest.main(verbosity=2)
