#!/usr/bin/env python3
"""Execute preserved fan duty/output paths and classify retired references.

Fan mode, coolant, IAT and timer period are explicit native-state inputs.
Mode branches, lookup instructions and PWM conversion execute ROM bytes.
Descriptor poisoning affects only in-memory retired data. Fan motion,
electrical polarity and hardware timer progression are not simulated.
"""
import _test_paths
from itertools import product
import unittest

from test_avcs_actuator_process_flow import AVCSActuatorMachine, RAM, ROOT
from test_runtime_rom_checksum_execution import before_pump_scaling

FAN_WRITES = {(RAM+a, 4) for a in (0xCD54, 0xCD58, 0xCD5C, 0xB0F0)} | {
    (RAM+0xCD81, 1), (RAM+0xF590, 2)}
PARENT_WRITES = FAN_WRITES | {(RAM+a, 4) for a in (0xCD60, 0xCD64, 0xCD68, 0xCD6C)} | {
    (RAM+a, 2) for a in (0xCD70, 0xCD72, 0xCD7A)} | {
    (RAM+a, 1) for a in (*range(0xCD74, 0xCD7A), *range(0xCD7C, 0xCD82))}
RETIRED = ((0x7D790, 0x7D80D), (0x7D810, 0x7D8C0), (0x7E560, 0x7E640))


class FanRetiredMachine(AVCSActuatorMachine):
    LOOKUPS = AVCSActuatorMachine.LOOKUPS | {
        0xE8C4, 0x64F7C, 0x1C0AC, 0x2A480, 0x19C54, 0x35ED2,
        0x1B006, 0x3C62A, 0x12C12, 0x18CF4,
    }

    def __init__(self, image, mode=0, coolant=100, iat=30):
        super().__init__(image)
        for a in range(0xCD60, 0xCD82):
            self.write(RAM+a, 0, 1)
        for a in (0xCD54, 0xCD58, 0xCD5C):
            self.put_float(RAM+a, 0)
        self.write(RAM+0xCD81, 0, 1)
        self.write(RAM+0xCD77, mode, 1)
        self.write(RAM+0xAB84, 10000, 2)
        self.put_float(RAM+0xB3AC, coolant)
        self.put_float(RAM+0xB3B8, iat)
        # Canaries for other PWM channels and patch-owned learned state.
        for a in (0xF510, 0xF512, 0xF590+2, 0xAE9C):
            self.write(RAM+a, 0xA55A, 2)
        self.write(RAM+0xAEA0, 0xA5, 1)

    def parents(self):
        # Exact five consecutive fan calls in the slow dispatcher. The
        # preceding 3F5F0 is a separate, previously tested spark-inhibit path.
        for pointer in (0x11768, 0x1176C, 0x11770, 0x11774, 0x11778):
            self.execute(self.read(pointer, 4), PARENT_WRITES)
        return self.read(RAM+0xCD77, 1), self.get_float(RAM+0xCD54)

    def healthy_parent_inputs(self):
        for a in (0xD268, 0xC294, 0xB6C8, 0xCC54, 0xB151,
                  0xB484, 0xCA10, 0xC778, 0xD26C, 0xD26D, 0xB51D):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xB51E, 0x10, 1)
        self.write(RAM+0xB688, 3000, 2)

    def output(self):
        self.execute(0x3FC0A, FAN_WRITES)
        return self.get_float(RAM+0xCD54), self.read(RAM+0xF590, 2)


class FanRetiredProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x3F650, 0x3FD9C), (0xE8B4, 0xE918),
                         (0x609C4, 0x609EC), (0x4C778, 0x4C808),
                         (0x7BCC8, 0x7BD9C),
                         (0x4FB8C, 0x4FCDC)):
                assert image[a:b] == stock[a:b], hex(a)
            assert int.from_bytes(image[0x11774:0x11778], 'big') == 0x3FC0A

    def test_all_native_mode_branches_publish_only_fan_pwm_and_preserve_shared_channels(self):
        expected = ((0, 10000), (70, 3001), (100, 0), (50, 5000),
                    (0, 10000), (100, 0), (70, 3001), (70, 3001))
        for image, mode in product(self.images.values(), range(8)):
            cpu = FanRetiredMachine(image, mode)
            self.assertEqual(cpu.output(), expected[mode])
            self.assertIn(0xE8C4, {pc for pc, _ in cpu.trace})  # Native tail jump.
            for a in (0xF510, 0xF512, 0xF592, 0xAE9C):
                self.assertEqual(cpu.read(RAM+a, 2), 0xA55A)
            self.assertEqual(cpu.read(RAM+0xAEA0, 1), 0xA5)
            self.assertFalse(any(lo <= a < hi for a in cpu.reads for lo, hi in RETIRED))

    def test_poisoned_retired_descriptors_switches_and_data_do_not_change_native_fan_paths(self):
        for image in self.images.values():
            poisoned = bytearray(image)
            for lo, hi in RETIRED:
                if lo in (0x7D810, 0x7E560):
                    continue  # Preserve the already-tested return-only entries.
                poisoned[lo:hi] = b'\xA5'*(hi-lo)
            for mode, coolant, iat in product(range(8), (60, 90, 100, 120), (0, 60)):
                baseline = FanRetiredMachine(image, mode, coolant, iat)
                expected = baseline.output()
                cpu = FanRetiredMachine(bytes(poisoned), mode, coolant, iat)
                self.assertEqual(cpu.output(), expected)
                self.assertEqual(cpu.writes, baseline.writes)
                self.assertEqual(cpu.entered, baseline.entered)

    def test_only_external_retired_address_literal_is_the_exclusive_checksum_boundary(self):
        for image in self.images.values():
            external = []
            internal = []
            for address in range(0, len(image)-3, 2):
                target = int.from_bytes(image[address:address+4], 'big')
                if not any(lo <= target < hi for lo, hi in RETIRED):
                    continue
                (internal if any(lo <= address < hi for lo, hi in RETIRED)
                 else external).append((address, target))
            self.assertEqual(external, [(0x4FC30, 0x7D790)])
            self.assertEqual(internal, [(0x7D794, 0x7D7A4), (0x7D798, 0x7D7C4),
                                       (0x7D7D0, 0x7D7A4), (0x7D7D4, 0x7D7E0)])
            # The corresponding native CMP/HS + exit branches are pinned.
            # Their full accumulator execution is in the checksum suite.
            self.assertEqual(image[0x4FBAE:0x4FBB6], bytes.fromhex('634233228d41eb00'))

    def test_native_parent_temperature_transitions_reach_output_with_hysteresis(self):
        for image in self.images.values():
            cpu = FanRetiredMachine(image)
            cpu.healthy_parent_inputs()
            for temperature, expected in ((60, (0, 0)), (90, (0, 0)), (100, (1, 70)),
                                          (110, (2, 100)), (120, (2, 100)),
                                          (100, (2, 100)), (80, (0, 0))):
                cpu.put_float(RAM+0xB3AC, temperature)
                self.assertEqual(cpu.parents(), expected)
                self.assertEqual(cpu.read(RAM+0xAE9C, 2), 0xA55A)
                self.assertEqual(cpu.read(RAM+0xAEA0, 1), 0xA5)

    def test_all_36_computed_mode_entries_stay_in_native_byte_data(self):
        for image in self.images.values():
            table = [int.from_bytes(image[0x4C778+4*i:0x4C77C+4*i], 'big') for i in range(36)]
            self.assertEqual(table, list(range(0x7BCC8, 0x7BCEC)))
            seen = set()
            for speed_class, temperature_class, digital in product(range(4), range(3), range(3)):
                cpu = FanRetiredMachine(image)
                cpu.healthy_parent_inputs()
                cpu.write(RAM+0xCD80, speed_class, 1)
                cpu.write(RAM+0xCD7F, temperature_class, 1)
                cpu.write(RAM+0xB51D, 0x80 if digital else 0, 1)
                cpu.write(RAM+0xCA10, 0x80 if digital == 2 else 0, 1)
                cpu.execute(0x3F650, PARENT_WRITES)
                index = 9*speed_class+temperature_class+3*digital
                self.assertIn(0x4C778+4*index, cpu.reads)
                self.assertIn(table[index], cpu.reads)
                self.assertEqual(cpu.read(RAM+0xCD77, 1), image[table[index]])
                seen.add(index)
            self.assertEqual(seen, set(range(36)))

    def test_native_period_reload_and_writer_use_fan_channel_only(self):
        for image in self.images.values():
            cpu = FanRetiredMachine(image, mode=2)
            cpu.execute(0xE8B4, {(RAM+0xF588, 2), (RAM+0xAB84, 2)})
            self.assertEqual(cpu.read(RAM+0xF588, 2), 8000)
            self.assertEqual(cpu.read(RAM+0xAB84, 2), 8000)
            self.assertEqual(cpu.output(), (100, 0))
            cpu.write(RAM+0xCD77, 0, 1)
            self.assertEqual(cpu.output(), (0, 8000))
            self.assertEqual(cpu.read(RAM+0xF592, 2), 0xA55A)


if __name__ == '__main__':
    unittest.main(verbosity=2)
