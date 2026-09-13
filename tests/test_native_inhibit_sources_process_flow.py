#!/usr/bin/env python3
"""Execute retained inhibit producers, qualification, recovery and B744.

This closes actual source routines beyond forcing the final cut flags. Digital,
diagnostic and remote states remain explicit inputs. Logged speed/RPM/load/ECT
are applied as sampled values; unobserved intervals and task timing are not
reconstructed. No peripheral state or vehicle cure is inferred.
"""
import _test_paths
import csv
import hashlib
from itertools import product
import unittest

from test_throttle_tracking_process_flow import ThrottleTrackingMachine
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_runtime_switch_process_flow import (RuntimeSwitchMachine,
                                             SAMPLE_WRITES, PUBLISH_WRITES)
from test_wideband_fuel_guard_execution import INHIBIT_GETTERS

ROOT, RAM = _test_paths.ROOT, 0xFFFF0000
CUT = {(RAM+0xB744, 2)}
STOP_WRITES = CUT | {(RAM+0xBF70, 1), (RAM+0xBF72, 2)}
STATIONARY_WRITES = CUT | {(RAM+0xBF74, 1)} | {
    (RAM+a, 2) for a in (0xBF76, 0xBF80, 0xBF82, 0xBF84, 0xBF86, 0xBF88)} | {
    (RAM+a, 4) for a in (0xBF78, 0xBF7C)}
SPEED_WRITES = CUT | {(RAM+a, 1) for a in (0xBF8C, 0xBF8D, 0xBF8E)}
LIFT_WRITES = CUT | {(RAM+a, 1) for a in (0xCF24, 0xCF25)}
TORQUE_WRITES = CUT | {(RAM+a, 1) for a in (0xBF9C, 0xBF9D, 0xBF9E, 0xBFB0)} | {
    (RAM+a, 4) for a in (0xBF94, 0xBFA0, 0xBFA4)}


class NativeInhibitMachine(ThrottleTrackingMachine):
    LOOKUPS = ThrottleTrackingMachine.LOOKUPS | {
        0x19C18, 0x1C5D4, 0x65244, 0x64F7C, 0x18CF4, 0x2484,
        0x65208, 0x449FE, 0x44A0C, 0x148B2, 0x3C652, 0x35DEE,
        0x24C0, 0x25F8E, 0x470F4,
    }

    def __init__(self, image):
        super().__init__(image)
        for a in range(0xBF70, 0xBFA8):
            self.write(RAM+a, 0, 1)
        for a, value in ((0xB51D, 0x40), (0xB51C, 0), (0xB484, 0),
                         (0xCC71, 0), (0xB289, 0), (0x8546, 0),
                         (0xCE54, 0), (0xCF24, 0), (0xCF25, 0),
                         (0xCD86, 1), (0xD270, 0), (0xCCBB, 0), (0xBFB0, 0),
                         (0x8FA0, 0)):
            self.write(RAM+a, value, 1)
        self.put_float(RAM+0xB438, 2)
        self.put_float(RAM+0xCA18, 0)
        self.write(RAM+0xBF9A, 0, 1)

    def stationary(self, rpm, speed, load=2, ect=67):
        for a, value in ((0xB544, rpm), (0xB538, speed),
                         (0xB438, load), (0xB3AC, ect)):
            self.put_float(RAM+a, value)
        self.execute(0x24CB0, STATIONARY_WRITES)
        self.execute(0x24E0C, STATIONARY_WRITES)
        return self.read(RAM+0xBF74, 1), self.read(RAM+0xB744, 2)


class DigitalInhibitMachine(RuntimeSwitchMachine):
    LOOKUPS = RuntimeSwitchMachine.LOOKUPS | {0x19C18, 0x1C5D4, *INHIBIT_GETTERS}

    def __init__(self, image):
        super().__init__(image)
        self.write(RAM+0xBF70, 0, 1)
        self.write(RAM+0xBF72, 0, 2)
        self.write(RAM+0xF74E, 1, 2)
        self.execute(0x6B08, SAMPLE_WRITES)
        self.execute(0x193D0, PUBLISH_WRITES)

    def sample(self, port_f):
        self.write(RAM+0xF74E, port_f, 2)
        self.execute(0x6BB4, SAMPLE_WRITES)
        self.execute(0x193D0, PUBLISH_WRITES)
        self.execute(0x24C34, STOP_WRITES)
        return self.read(RAM+0xB51D, 1) & 0x40, self.read(RAM+0xB744, 2)


class NativeInhibitSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x24C34, 0x253A8), (0x25AC0, 0x2600C),
                         (0x4162C, 0x41698), (0x4551C, 0x455C8),
                         (0x472E4, 0x47324), (0x3C388, 0x3C3C8),
                         (0x7645C, 0x764A8), (0x764F0, 0x764FC),
                         (0x75FBA, 0x75FC6), (0x75E38, 0x75E3A),
                         (0x35DEE, 0x35DF2)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_native_digital_loss_needs_two_calls_and_healthy_input_releases(self):
        for image in self.images.values():
            cpu = NativeInhibitMachine(image)
            cpu.write(RAM+0xBF70, 0x35, 1)
            cpu.write(RAM+0xB51D, 0, 1)
            for count, cut in ((1, 0), (2, 0xFFFF), (3, 0xFFFF)):
                cpu.execute(0x24C34, STOP_WRITES)
                self.assertEqual(cpu.read(RAM+0xBF72, 2), count)
                self.assertEqual(cpu.read(RAM+0xB744, 2), cut)
                self.assertEqual(cpu.read(RAM+0xBF70, 1) & 0x7F, 0x35)
            cpu.write(RAM+0xB51D, 0x40, 1)
            cpu.execute(0x24C34, STOP_WRITES)
            self.assertEqual(cpu.read(RAM+0xB744, 2), 0)
            self.assertEqual(cpu.read(RAM+0xBF72, 2), 0)

    def test_port_f_zero_bit_debounce_reaches_digital_cut_without_a_port_e_alias(self):
        for image in self.images.values():
            cpu = DigitalInhibitMachine(image)
            self.assertEqual(cpu.sample(1), (0x40, 0))
            for port_e in (0, 4, 8, 12, 0x4000, 0x8000, 0xC00C):
                cpu.write(RAM+0xF754, port_e, 2)
                self.assertEqual(cpu.sample(1), (0x40, 0))
                self.assertEqual(cpu.sample(1), (0x40, 0))
            # One bad sample is filtered. The second updates the shared
            # digital flag; two qualified cut-service calls then inhibit.
            self.assertEqual(cpu.sample(0), (0x40, 0))
            self.assertEqual(cpu.sample(0), (0, 0))
            self.assertEqual(cpu.sample(0), (0, 0xFFFF))
            self.assertEqual(cpu.sample(1), (0, 0xFFFF))
            self.assertEqual(cpu.sample(1), (0x40, 0))

    def test_stationary_timer_reaches_cut_and_moving_resets_even_with_saturated_history(self):
        for image in self.images.values():
            cpu = NativeInhibitMachine(image)
            # Native qualification: ECT>=60, speed<1, selected faults clear.
            # 4000-RPM branch requires1094 consecutive qualified calls.
            for _ in range(1093):
                flags, cut = cpu.stationary(4000, 0)
                self.assertEqual(cut, 0)
            flags, cut = cpu.stationary(4000, 0)
            self.assertEqual(flags & 0xE0, 0xE0)
            self.assertEqual(cut, 0xFFFF)
            for rpm, speed in product((2500, 2800, 3000, 3500, 4144), (1, 40, 50, 54)):
                cpu.write(RAM+0xBF74, 0xFF, 1)
                for a in (0xBF76, 0xBF80, 0xBF82, 0xBF84, 0xBF86, 0xBF88):
                    cpu.write(RAM+a, 65535, 2)
                flags, cut = cpu.stationary(rpm, speed)
                self.assertEqual(flags & 0xF0, 0)
                self.assertEqual(cut, 0)
                self.assertEqual([cpu.read(RAM+a, 2) for a in
                                  (0xBF76, 0xBF80, 0xBF82, 0xBF84, 0xBF86)], [0]*5)

    def test_logged_loaded_rows_clear_stationary_cut_with_stale_latches(self):
        path = ROOT/'logs/romraiderlog_adjustedvedrive_20260912_144204.csv'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         '347d10ce5e5c70d64f478e4bb6d124453697af07b1e074271ecbe1830d7efb33')
        with path.open() as f:
            rows = [r for r in csv.DictReader(f)
                    if 71000 <= float(r['Time (msec)']) <= 86000
                    or 130000 <= float(r['Time (msec)']) <= 132000]
        self.assertGreater(len(rows), 150)
        for image in self.images.values():
            cpu = NativeInhibitMachine(image)
            for row in rows:
                self.assertGreaterEqual(float(row['Vehicle Speed (km/h)']), 1)
                cpu.write(RAM+0xBF74, 0xFF, 1)
                flags, cut = cpu.stationary(float(row['Engine Speed (rpm)']),
                    float(row['Vehicle Speed (km/h)']),
                    float(row['Engine Load (4-Byte)* (g/rev)']),
                    float(row['Coolant Temperature (C)']))
                self.assertEqual(flags & 0xF0, 0)
                self.assertEqual(cut, 0)

    def test_low_lift_limit_is_4600_on_and_below_4400_off_in_both_software_modes(self):
        for image, mode, fault in product(self.images.values(), (1, 3), (0, 4)):
            cpu = NativeInhibitMachine(image)
            cpu.write(RAM+0xCD86, mode, 1)
            cpu.write(RAM+0xD26E, fault, 1)
            for rpm, held in ((3500, 0), (4144, 0), (4599, 0), (4600, 1),
                              (4500, 1), (4400, 1), (4399, 0), (3500, 0)):
                cpu.put_float(RAM+0xB544, rpm)
                cpu.execute(0x4551C, LIFT_WRITES)
                self.assertEqual(bool(cpu.read(RAM+0xCF25, 1) & 0x80), bool(held))
                self.assertEqual(cpu.read(RAM+0xB744, 2),
                                 0xFFFF if held and (mode == 1 or fault) else 0)

    def test_speed_limit_needs_262_kmh_and_5400_rpm_and_recovers_below_260(self):
        for image in self.images.values():
            cpu = NativeInhibitMachine(image)
            for rpm, speed in product((2500, 2800, 3000, 3500, 4144), (0, 40, 54, 262)):
                cpu.put_float(RAM+0xB544, rpm)
                cpu.put_float(RAM+0xB538, speed)
                for _ in range(17): cpu.execute(0x2513C, SPEED_WRITES)
                self.assertEqual(cpu.read(RAM+0xB744, 2), 0)
            cpu.put_float(RAM+0xB544, 5400)
            cpu.put_float(RAM+0xB538, 262)
            for _ in range(18): cpu.execute(0x2513C, SPEED_WRITES)
            self.assertEqual(cpu.read(RAM+0xB744, 2), 63)
            cpu.put_float(RAM+0xB538, 259)
            for _ in range(18): cpu.execute(0x2513C, SPEED_WRITES)
            self.assertEqual(cpu.read(RAM+0xB744, 2), 0)

    def test_installed_zero_permission_resets_received_torque_pattern_to_twelve(self):
        for image, rpm, received in product(self.images.values(),
                (2500, 2800, 3000, 3500, 4144), (0, 40, 510)):
            cpu = NativeInhibitMachine(image)
            cpu.put_float(RAM+0xB544, rpm)
            cpu.put_float(RAM+0xB210, received)
            cpu.put_float(RAM+0xBF94, 3)
            cpu.write(RAM+0xBF9C, 0xFF, 1)
            cpu.write(RAM+0xBF9D, 0xFF, 1)
            cpu.execute(0x25AC0, TORQUE_WRITES)
            cpu.execute(0x25B58, TORQUE_WRITES)
            cpu.execute(0x25D42, TORQUE_WRITES)
            self.assertEqual(cpu.get_float(RAM+0xBF94), 12)
            self.assertEqual(cpu.read(RAM+0xBF9E, 1), 12)
            self.assertEqual(cpu.read(RAM+0xBF9C, 1) & 3, 0)
            cpu.execute(0x1C5D4, CUT)
            self.assertEqual(cpu.read(RAM+0xB744, 2), 0)

    def test_security_and_combined_digital_request_publish_and_release_independently(self):
        for image, enabled, record, status in product(self.images.values(),
                (0, 0x80), (0, 1, 2), (0, 2, 4)):
            cpu = NativeInhibitMachine(image)
            cpu.write(RAM+0xB289, enabled, 1)
            cpu.write(RAM+0x8546, record, 1)
            cpu.write(RAM+0xCE54, status, 1)
            cpu.execute(0x4162C, CUT | {(RAM+0xCE24, 1)})
            self.assertEqual(cpu.read(RAM+0xB744, 2),
                             0xFFFF if enabled and (record == 1 or status) else 0)
            cpu.write(RAM+0xB289, 0, 1)
            cpu.execute(0x4162C, CUT | {(RAM+0xCE24, 1)})
            self.assertEqual(cpu.read(RAM+0xB744, 2), 0)
        for image, source in product(self.images.values(), (0, 8, 16, 24)):
            cpu = NativeInhibitMachine(image)
            cpu.write(RAM+0xCC71, source, 1)
            cpu.execute(0x3C388, {(RAM+0xCC71, 1)})
            cpu.execute(0x472E4, CUT | {(RAM+0xCFA0, 1)})
            self.assertEqual(cpu.read(RAM+0xB744, 2), 0xFFFF if source == 24 else 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
