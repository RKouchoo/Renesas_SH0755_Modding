#!/usr/bin/env python3
"""Join native tip-in calculation, immediate C700 callback and injector device.

23BAE's table interpolation and the supplied sensor/history states remain
explicit fixtures. C700, its callback, six-channel inhibit gate, and actual
timer writes execute the unchanged ROM. Peripherals remain inert snapshots.
"""
import _test_paths
from itertools import product
import unittest

from test_tip_in_execution import TipInMachine, WRITES
from test_injector_device_process_flow import (
    InjectorDeviceMachine, DEVICE_WRITES, NATIVE, ROOT, HARDWARE,
)
from test_injector_scheduler_execution import NATIVE_CALLS
from test_runtime_rom_checksum_execution import before_pump_scaling

CALLBACK_NATIVE = NATIVE | NATIVE_CALLS | {
    0xC700, 0x11EF4, 0x2689C, 0x268E8, 0x90BA,
}
ALL_WRITES = WRITES | DEVICE_WRITES | {(0xFFFFC0B0, 1)}


class TipInDeviceMachine(TipInMachine, InjectorDeviceMachine):
    def __init__(self, image, **inputs):
        super().__init__(image, **inputs)
        rpm = inputs.get('rpm', 1350)
        self.write(0xFFFFAC04, round(4_000_000*5/rpm))
        self.write(0xFFFFAC08, round(4_000_000*20/rpm))
        self.put_float(0xFFFFC0D8, self.read(0xFFFFAC7C, 4)/4)

    def call_lookup(self, target):
        if target in CALLBACK_NATIVE:
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        if op & 0xF00F == 0x0006:  # MOV.L Rm,@(R0,Rn), C700 payload copy.
            n, m = (op >> 8) & 15, (op >> 4) & 15
            self.write((self.r[0]+self.r[n]) & 0xFFFFFFFF,
                       self.r[m], 4, record=True)
            self.pc += 2
            self.instructions += 1
            assert self.instructions < self.INSTRUCTION_LIMIT
        else:
            super().step(in_delay)

    def request_to_device(self, delta=None):
        if delta is not None:
            self.put_float(0xFFFFB2CC, delta)
        self.entered.clear()
        self.invoke(0x23BAE, ALL_WRITES)


class TipInDeviceFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = {
            'main': (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes(),
            'v2': (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes(),
        }
        cls.images['captured'] = before_pump_scaling(cls.images['v2'])
        for image in cls.images.values():
            for a, b in ((0xC700, 0xC76E), (0xC818, 0xC824), (0xFB88, 0xFB8C),
                         (0xFD24, 0xFD2C), (0x11EF4, 0x11F00), (0x11F94, 0x11F98),
                         (0x2689C, 0x268C2), (0x268E8, 0x269F8),
                         (0x4B64C, 0x4B658), (0x4B6A8, 0x4B6B4),
                         (0x90BA, 0x90BE), (0x96FC, 0x98CC)):
                assert image[a:b] == cls.stock[a:b], hex(a)

    def test_changed_pressure_gate_reaches_all_six_timer_registers(self):
        for name, image in self.images.items():
            cpu = TipInDeviceMachine(image, rpm=3000, coolant=85,
                                     map_mmhg=820, baro=712)
            cpu.request_to_device()
            if name == 'main':
                self.assertNotIn(0xC700, cpu.entered)
                self.assertEqual(cpu.read(0xFFFFF640, 2), 0)
                continue
            self.assertIn(0xC700, cpu.entered)
            self.assertEqual(cpu.entered.count(0x90BA), 6)
            self.assertIn(0x96FC, cpu.visited)  # Reached by the native BRA thunk.
            net = cpu.get_float(0xFFFFBEFC)
            expected = (int(net*4)+2736)//16
            self.assertGreater(expected, 0)
            self.assertEqual([cpu.read(0xFFFFF640+2*i, 2) for i in range(6)],
                             [expected]*6)
            self.assertEqual(cpu.read(0xFFFFC0B0, 1), 1)
            self.assertAlmostEqual(cpu.get_float(0xFFFFBF10), net+684)

    def test_immediate_callback_obeys_every_inhibit_mask(self):
        for image, mask in product(self.images.values(), range(64)):
            cpu = TipInDeviceMachine(image, rpm=3000, coolant=85,
                                     map_mmhg=330, baro=712)
            cpu.write(0xFFFFB744, mask, 2)
            cpu.request_to_device()
            for channel in range(6):
                self.assertEqual(cpu.read(0xFFFFF640+2*channel, 2) > 0,
                                 not bool(mask & (1 << channel)))

    def test_existing_pulse_is_extended_without_second_latency(self):
        for image in self.images.values():
            cpu = TipInDeviceMachine(image, rpm=3000, coolant=85,
                                     map_mmhg=330, baro=712)
            cpu.write(0xFFFFF666, 63, 2)
            for channel in range(6):
                cpu.write(0xFFFFF640+2*channel, 1000, 2)
            cpu.request_to_device()
            extra = int(cpu.get_float(0xFFFFBEFC)*4)//16
            self.assertEqual([cpu.read(0xFFFFF640+2*i, 2) for i in range(6)],
                             [1000+extra]*6)
            # A settled throttle delta must not reapply the previous request.
            cpu.request_to_device(delta=0)
            self.assertNotIn(0xC700, cpu.entered)
            self.assertEqual([cpu.read(0xFFFFF640+2*i, 2) for i in range(6)],
                             [1000+extra]*6)


if __name__ == '__main__':
    unittest.main(verbosity=2)
