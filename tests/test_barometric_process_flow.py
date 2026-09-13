#!/usr/bin/env python3
"""Run native barometric eligibility, update, and publication in task order.

ADC pressure, processed MAP, discrete prerequisites, speed and throttle are
explicit fixtures. This checks propagation and reset behavior, not physical
sensor accuracy or the meaning of every upstream discrete-state producer.
"""
import _test_paths
import unittest

from audit_map_sources import MapSourceMachine, BARO_WRITES, BARO, NATIVE_MAP
from test_primary_fueling_execution import signed
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT = _test_paths.ROOT
WRITES = BARO_WRITES | {(BARO, 4)} | {
    (0xFFFFCFC4, 4), (0xFFFFCFC8, 4), (0xFFFFCFCC, 4),
    (0xFFFFCFD0, 1), (0xFFFFCFDC, 1),
    *((a, 2) for a in range(0xFFFFCFD2, 0xFFFFCFDC, 2))}


class BarometerMachine(MapSourceMachine):
    LOOKUPS = MapSourceMachine.LOOKUPS | {
        0x48134, 0x481BC, 0x47EA6, 0x47F84, 0x480B8, 0x4803C, 0x47DCC,
        0x24B06, 0x254C, 0x3C544, 0x312E0, 0x4244, 0x65244,
        0x24FC, 0x2458, 0x2150, 0x27F0, 0x2684, 0x251C, 0x2858,
    }

    def __init__(self, image, rpm=2800, native_kpa=20):
        super().__init__(image, rpm=rpm, native_kpa=native_kpa, baro_mmhg=712)
        for address, size in WRITES - BARO_WRITES - {(BARO, 4)}:
            self.write(address, 0, size)
        for address in (0xFFFFB52C, 0xFFFFBF20, 0xFFFFB2BC,
                        0xFFFFCC6D, 0xFFFFCD48, 0xFFFF825C, 0xFFFFD272):
            self.write(address, 0, 1)
        self.put_float(0xFFFFB3AC, 80)
        self.put_float(0xFFFFB538, 0)
        self.put_float(0xFFFFB2C8, 0)
        self.put_float(0xFFFFB2A0, 150)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x6008:  # SWAP.B: swap low bytes, preserve upper half.
            value = self.r[m]
            self.r[n] = (value & 0xFFFF0000) | ((value & 255) << 8) | ((value >> 8) & 255)
        elif op & 0xF0FF == 0x4001:  # SHLR, outgoing low bit becomes T.
            self.t = bool(self.r[n] & 1)
            self.r[n] >>= 1
        elif op & 0xF00F == 0x3007:  # CMP/GT signed registers.
            self.t = signed(self.r[n], 32) > signed(self.r[m], 32)
        elif op & 0xF0FF == 0x4011:  # CMP/PZ signed register.
            self.t = signed(self.r[n], 32) >= 0
        elif op & 0xF0FF == 0x4010:  # DT: decrement and test for zero.
            self.r[n] = (self.r[n]-1) & 0xFFFFFFFF
            self.t = self.r[n] == 0
        elif op & 0xF00F == 0x6004:  # MOV.B @Rm+,Rn; sign-extended.
            address = self.r[m]
            self.r[n] = signed(self.load(address, 1), 8) & 0xFFFFFFFF
            if n != m:
                self.r[m] = (address+1) & 0xFFFFFFFF
        else:
            return super().step(in_delay)
        self.trace.append((self.pc, op))
        self.pc += 2
        self.instructions += 1

    def update(self):
        before = self.read(NATIVE_MAP, 4)
        self.execute(0x47D92, WRITES)  # Falls through 47DB2 after restoring PR.
        assert self.read(NATIVE_MAP, 4) == before
        return self.get_float(BARO), self.read(0xFFFFCFD0, 1)


class BarometricFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        cls.images = {
            'main': (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes(),
            'v2': (ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes(),
        }
        cls.images['captured'] = before_pump_scaling(cls.images['v2'])
        for image in cls.images.values():
            for a, b in ((0x47D6A, 0x482DC), (0x312E0, 0x312F8),
                         (0x4244, 0x427E), (0x737D9, 0x737DA),
                         (0x73812, 0x7383C), (0x5EBC0, 0x5EBDC)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_running_deep_vacuum_holds_estimate_and_never_clamps_native_map(self):
        for image in self.images.values():
            for rpm in (2800, 3000, 3500):
                cpu = BarometerMachine(image, rpm)
                for _ in range(4):
                    self.assertEqual(cpu.update(), (712, 0))

    def test_rising_packed_state_samples_once_and_clamps_only_baro(self):
        for image in self.images.values():
            for kpa, expected in ((20, 570), (110, 770)):
                cpu = BarometerMachine(image, native_kpa=kpa)
                cpu.write(0xFFFF825C, 0x10, 1)  # Actual field read by 312E0/4244.
                value, flags = cpu.update()
                self.assertEqual(value, expected)
                self.assertEqual(flags & 0x83, 0x83)
                value, flags = cpu.update()
                self.assertEqual(value, expected)
                self.assertEqual(flags & 0x83, 3)
                cpu.write(0xFFFF825C, 0, 1)
                self.assertEqual(cpu.update()[1] & 0x83, 0)

    def test_stopped_counter_sample_and_restart_reset_follow_native_order(self):
        for image in self.images.values():
            cpu = BarometerMachine(image, rpm=0, native_kpa=95)
            cpu.write(0xFFFFB52C, 0x80, 1)
            cpu.write(0xFFFFCFD4, 624, 2)
            self.assertEqual(cpu.update()[1] & 0x80, 0)
            value, flags = cpu.update()
            self.assertTrue(flags & 0x80)
            self.assertAlmostEqual(value, cpu.get_float(NATIVE_MAP), places=5)
            self.assertEqual(cpu.update()[1] & 0x80, 0)
            cpu.write(0xFFFFB52C, 0, 1)
            cpu.put_float(0xFFFFB544, 2800)
            cpu.update()
            self.assertEqual(cpu.read(0xFFFFCFD4, 2), 0)

    def test_map_fault_priority_publishes_760_without_overwriting_sd_input(self):
        for image in self.images.values():
            cpu = BarometerMachine(image, native_kpa=20)
            cpu.write(0xFFFFD26C, 0x10, 1)
            cpu.write(0xFFFF825C, 0x10, 1)
            self.assertEqual(cpu.update()[0], 760)

    def test_running_learning_delay_and_fault_disqualification_reset(self):
        for image in self.images.values():
            cpu = BarometerMachine(image)
            cpu.put_float(0xFFFFB2C8, 90)
            cpu.put_float(0xFFFFB2A0, 700)
            for _ in range(63):
                self.assertEqual(cpu.update()[1] & 0x40, 0)
            value, flags = cpu.update()
            self.assertTrue(flags & 0x40)
            self.assertTrue(570 <= value <= 770)
            cpu.write(0xFFFFD272, 2, 1)
            self.assertEqual(cpu.update()[1] & 0x40, 0)
            self.assertEqual(cpu.read(0xFFFFCFDA, 2), 0)
            cpu.write(0xFFFFD272, 0, 1)
            self.assertEqual(cpu.update()[1] & 0x40, 0)
            self.assertEqual(cpu.read(0xFFFFCFDA, 2), 1)

    def test_distance_increment_is_consumed_once_then_cleared_in_native_order(self):
        for image in self.images.values():
            for qualifier in ('overrun', 'gear_speed'):
                cpu = BarometerMachine(image)
                cpu.put_float(0xFFFFB538, 40)
                cpu.put_float(0xFFFFCFCC, 199.9)
                if qualifier == 'overrun':
                    cpu.write(0xFFFFBF20, 0x40, 1)
                    cpu.write(0xFFFFCFD6, 625, 2)
                    mask = 0x10
                else:
                    cpu.write(0xFFFFB2BC, 2, 1)
                    cpu.write(0xFFFFCD48, 2, 1)
                    cpu.write(0xFFFFCFD8, 188, 2)
                    mask = 8
                value, flags = cpu.update()
                self.assertTrue(flags & mask)
                self.assertTrue(flags & 0x20)
                self.assertEqual(value, 714.5)
                value, flags = cpu.update()
                self.assertEqual(value, 714.5)
                self.assertEqual(flags & 0x20, 0)
                self.assertEqual(cpu.get_float(0xFFFFCFCC), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
