#!/usr/bin/env python3
"""Execute dormant reservations and the main-only rotational timing wrapper.

Enable/calibration changes are private in-memory controls. No saved image or
feature is enabled. The actual stock final-timing routine executes before the
wrapper, with explicit native correction inputs. Physical spark and task
timing are covered only by the separately documented boundaries.
"""
import _test_paths
from itertools import product
import struct
import unittest

import patch_rotational_idle as rot
from test_opening_timing_execution import OpeningTimingMachine, FINAL_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_actuator_retirement import verify_actual_fan_preserved

ROOT, RAM = _test_paths.ROOT, 0xFFFF0000


class DormantPatchMachine(OpeningTimingMachine):
    def __init__(self, image, rpm=800, coolant=90, throttle=.5, speed=0, pressure=300):
        super().__init__(image, rpm=rpm, coolant=coolant)
        self.put_float(RAM+0xC130, 20)
        for a, value in ((0xB314, throttle), (0xB538, speed), (0xABC4, pressure)):
            self.put_float(RAM+a, value)

    def call_lookup(self, target):
        if target == 0x279CC:
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        if op & 0xF0FF == 0x4010:  # DT Rn.
            n = (op >> 8) & 15
            self.r[n] = (self.r[n]-1) & 0xFFFFFFFF
            self.t = self.r[n] == 0
            self.pc += 2
            self.instructions += 1
        else:
            return super().step(in_delay)

    def run_timing(self):
        self.invoke(self.read(0x11E30, 4), FINAL_WRITES)
        return tuple(self.get_float(RAM+0xC0EC+4*i) for i in range(6))


def modified(image, enable=1, floats=()):
    result = bytearray(image)
    result[rot.ROT_IDLE_ENABLE_ADDR] = enable
    for address, value in floats:
        struct.pack_into('>f', result, address, value)
    return bytes(result)


class DormantPatchProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        assert main[0x7DB40] == 0
        assert int.from_bytes(main[0x11E30:0x11E34], 'big') == 0x7DB90
        for name, image in cls.images.items():
            assert image[0x279CC:0x27D68] == cls.stock[0x279CC:0x27D68]
            verify_actual_fan_preserved(image, cls.stock)
            if name != 'main':
                assert int.from_bytes(image[0x11E30:0x11E34], 'big') == 0x279CC
                assert image[0x7DB40:0x7DD00] == b'\xff'*0x1C0

    def test_saved_images_execute_native_timing_without_retard_across_idle_and_loaded_inputs(self):
        for name, image in self.images.items():
            for rpm, throttle, speed in ((800, .5, 0), (2800, 70, 45), (3500, 90, 54)):
                cpu = DormantPatchMachine(image, rpm=rpm, throttle=throttle, speed=speed)
                self.assertEqual(cpu.run_timing(), (20,)*6)
                if name == 'main':
                    self.assertEqual(cpu.entered.count(0x279CC), 1)
                    self.assertNotIn(0x7DB6C, cpu.reads)
                self.assertFalse(any(a < RAM+0xC0EC or a > RAM+0xC12C
                                     for a, _ in cpu.writes if a >= cpu.STACK))

    def test_private_enabled_control_runs_native_first_and_restores_each_cylinder_next_call(self):
        cpu = DormantPatchMachine(modified(self.images['main']))
        for _ in range(3):
            self.assertEqual(cpu.run_timing(), (14, 20, 14, 20, 14, 20))
            self.assertEqual(cpu.entered.count(0x279CC), 1)
        cpu.put_float(RAM+0xB544, 1100)
        self.assertEqual(cpu.run_timing(), (20,)*6)
        cpu.put_float(RAM+0xB544, 800)
        self.assertEqual(cpu.run_timing(), (14, 20, 14, 20, 14, 20))

    def test_each_gate_exits_outside_window_and_accepts_its_native_float_boundary(self):
        image = modified(self.images['main'])
        for field, bound, outside in (
            ('coolant', 80, 79.99), ('coolant', 105, 105.01),
            ('rpm', 600, 599.99), ('rpm', 1050, 1050.01),
            ('throttle', 1.68, 1.69), ('speed', 1, 1.01),
            ('pressure', 150, 149.99), ('pressure', 550, 550.01),
        ):
            self.assertEqual(DormantPatchMachine(image, **{field: bound}).run_timing(),
                             (14, 20, 14, 20, 14, 20), field)
            self.assertEqual(DormantPatchMachine(image, **{field: outside}).run_timing(),
                             (20,)*6, field)
        for field in ('coolant', 'rpm', 'throttle', 'speed', 'pressure'):
            self.assertEqual(DormantPatchMachine(image, **{field: float('nan')}).run_timing(),
                             (20,)*6)

    def test_non_one_switch_and_malformed_calibration_preserve_native_result(self):
        main = self.images['main']
        for enable in (0, 2, 255):
            self.assertEqual(DormantPatchMachine(modified(main, enable)).run_timing(), (20,)*6)
        for address in (*range(0x7DB44, 0x7DB6C, 4),):
            image = modified(main, floats=((address, float('nan')),))
            self.assertEqual(DormantPatchMachine(image).run_timing(), (20,)*6, hex(address))
        image = modified(main, floats=tuple((0x7DB6C+4*i, float('nan')) for i in range(6)))
        self.assertEqual(DormantPatchMachine(image).run_timing(), (20,)*6)

    def test_retard_limits_and_original_angle_ceiling_hold_after_native_composition(self):
        main = self.images['main']
        for offsets, maximum, floor, expected in (
            ((20,)*6, 8, 5, (20,)*6),
            ((-20,)*6, 2, 0, (18,)*6),
            ((-20,)*6, -2, 0, (20,)*6),
            ((-20,)*6, 30, 5, (5,)*6),
            ((-20,)*6, 30, 25, (20,)*6),
        ):
            values = [(0x7DB6C+4*i, value) for i, value in enumerate(offsets)]
            values += [(0x7DB64, maximum), (0x7DB68, floor)]
            cpu = DormantPatchMachine(modified(main, floats=values))
            self.assertEqual(cpu.run_timing(), expected)

    def test_retired_entry_calls_do_not_read_state_or_write_outputs_for_any_old_switch(self):
        for image, enable, entry in product(self.images.values(), (0, 1, 255), (0x7D810, 0x7E560)):
            altered = bytearray(image)
            altered[0x7D80C] = enable
            cpu = DormantPatchMachine(bytes(altered))
            registers, floating = cpu.original_r.copy(), cpu.original_fr.copy()
            cpu.invoke(entry, set())
            self.assertEqual(cpu.instructions, 2)
            self.assertEqual(cpu.r, registers)
            self.assertEqual(cpu.fr, floating)
            self.assertEqual(cpu.writes, [])
            self.assertFalse(cpu.reads)
            self.assertEqual(cpu.entered, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
