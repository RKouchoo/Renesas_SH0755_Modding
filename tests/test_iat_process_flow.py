#!/usr/bin/env python3
"""Execute IAT ADC filter/lookup, runtime substitution and retained qualifiers.

Raw ADC samples and diagnostic/start flags are explicit fixtures. Native
lookup helpers execute opcodes; this does not calibrate the installed sensor
or emulate ADC conversion timing, task preemption or physical temperature.
"""
import _test_paths
from itertools import product
import unittest

from audit_map_sources import MapSourceMachine
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_primary_fueling_execution import signed

ROOT = _test_paths.ROOT
ADC_WRITES = {(0xFFFFABB0, 2), (0xFFFFABAC, 4)}
IAT_WRITES = {(a, 4) for a in (0xFFFFB3B8, 0xFFFFB3BC, 0xFFFFB3C0, 0xFFFFB3C4)}


class IATProcessMachine(MapSourceMachine):
    LOOKUPS = MapSourceMachine.LOOKUPS | {
        0x25CC, 0x257C, 0x27F0, 0x64FA8, 0x2534, 0x4714E, 0x258C,
    }

    def __init__(self, image, raw=32768):
        super().__init__(image)
        self.write(0xFFFFAB3A, raw, 2)
        self.write(0xFFFFABB0, raw, 2)
        self.put_float(0xFFFFABAC, 30)
        for a in (0xFFFFB3B8, 0xFFFFB3BC, 0xFFFFB3C0, 0xFFFFB3C4):
            self.put_float(a, 0)

    def convert(self):
        self.execute(0x786C, ADC_WRITES)
        return self.get_float(0xFFFFABAC)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x3007:  # CMP/GT signed, byte-result upper clamp.
            self.t = signed(self.r[n], 32) > signed(self.r[m], 32)
        elif op & 0xF0FF == 0x4011:  # CMP/PZ.
            self.t = signed(self.r[n], 32) >= 0
        else:
            return super().step(in_delay)
        self.trace.append((self.pc, op))
        self.pc += 2
        self.instructions += 1

    def update(self):
        self.execute(0x16D1C, IAT_WRITES)
        return self.get_float(0xFFFFB3B8)


class IATProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/f).read_bytes() for f in
                      ('master_patch/D2WD610H_master_patch.bin',
                       'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x786C, 0x78AC), (0x78D8, 0x78FC), (0x72878, 0x7287A),
                         (0x609B8, 0x609C4), (0x16D1C, 0x16E04),
                         (0x209C, 0x20D8), (0x25CC, 0x27D0), (0x27F0, 0x2830),
                         (0x257C, 0x25BC), (0x64FA8, 0x64FBC), (0x650C8, 0x650CA),
                         (0x672E4, 0x67428), (0x4F1E0, 0x4F1FA),
                         (0x4F2B4, 0x4F2C0), (0x4714E, 0x4715C), (0x47234, 0x47238)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_native_adc_filter_and_temperature_lookup_cover_sensor_range(self):
        for image in self.images:
            for raw in (0, 1024, 8192, 16384, 24576, 32768, 49152, 60000, 65535):
                cpu = IATProcessMachine(image, raw)
                temperature = cpu.convert()
                axis = cpu.array(0x72960, 30)
                values = cpu.array(0x729D8, 30)
                expected = cpu.interpolate(axis, values, raw*5/65536)
                self.assertAlmostEqual(temperature, expected, delta=.00005)
                self.assertEqual(cpu.read(0xFFFFABB0, 2), raw)
            cpu = IATProcessMachine(image, 16384)
            cpu.write(0xFFFFAB3A, 49152, 2)
            cpu.convert()
            self.assertEqual(cpu.read(0xFFFFABB0, 2), 24576)

    def test_temperature_and_two_voltage_histories_share_adc_but_differ_units(self):
        for image in self.images:
            cpu = IATProcessMachine(image, 16384)
            cpu.convert()
            cpu.execute(0x16DA8, IAT_WRITES)
            self.assertEqual(cpu.get_float(0xFFFFB3C0), 1.25)
            self.assertEqual(cpu.get_float(0xFFFFB3C4), 1.25)
            cpu.write(0xFFFFAB3A, 49152, 2)
            temperature = cpu.convert()
            self.assertEqual(cpu.update(), temperature)
            self.assertEqual(cpu.get_float(0xFFFFB3C4), 1.875)
            self.assertEqual(cpu.get_float(0xFFFFB3C0), 1.2890625)

    def test_fault_substitution_start_capture_and_raw_export_remain_distinct(self):
        for image, cranking, fault in product(self.images, (0, 128), (0, 32)):
            cpu = IATProcessMachine(image)
            cpu.put_float(0xFFFFABAC, 100)
            cpu.put_float(0xFFFFB3BC, 40)
            cpu.write(0xFFFFB748, cranking, 1)
            cpu.write(0xFFFFD26C, fault, 1)
            expected = 20 if fault else 100
            self.assertEqual(cpu.update(), expected)
            self.assertEqual(cpu.get_float(0xFFFFB3BC), expected if cranking else 40)
            cpu.execute(0x4F1E0, {(0xFFFFDA5A, 1)})
            self.assertEqual(cpu.read(0xFFFFDA5A, 1), 140)  # Raw ABAC+40.

    def test_iat_gate_controls_retained_purge_inhibit_countdown(self):
        for image in self.images:
            cpu = IATProcessMachine(image)
            for a, value in ((0xB3AC, 85), (0xB3B8, 30), (0xB544, 3000),
                             (0xB438, 2), (0xD29C, 0), (0xD2AC, 0),
                             (0xD2B8, 0), (0xD2A0, 0)):
                cpu.put_float(0xFFFF0000+a, value)
            cpu.write(0xFFFFDB27, 1, 1)
            cpu.write(0xFFFFD2CA, 0, 1)
            cpu.write(0xFFFFD2A4, 0, 2)
            allowed = {(0xFFFFD2CA, 1), (0xFFFFD2A4, 2)}
            for _ in range(40):
                cpu.execute(0x672E4, allowed)
            self.assertEqual(cpu.read(0xFFFFD2CA, 1), 39)
            self.assertEqual(cpu.read(0xFFFFD2A4, 2), 703)
            cpu.put_float(0xFFFFB3B8, 70)
            cpu.execute(0x672E4, allowed)
            self.assertEqual(cpu.read(0xFFFFD2CA, 1), 0)
            self.assertEqual(cpu.read(0xFFFFD2A4, 2), 702)


if __name__ == '__main__':
    unittest.main(verbosity=2)
