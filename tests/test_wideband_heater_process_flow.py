#!/usr/bin/env python3
"""Follow WB readiness and retained impedance through native heater outputs.

Executes qualification, both controller banks, PWM initialization/activation
and Q16 compare writes. Native impedance initialization is the 16384 input
boundary; no physical heater, output polarity or sensor temperature is modeled.
"""
import _test_paths
import unittest

from test_wideband_feedback_process_flow import WidebandFeedbackMachine, RAM, ROOT
from test_primary_fueling_execution import signed
from test_runtime_rom_checksum_execution import before_pump_scaling

PWM_WORDS = (0xF58E, 0xF586, 0xF596, 0xF59E,
             0xF58C, 0xF584, 0xF594, 0xF59C, 0xAB88, 0xAB8A)
HARDWARE_WRITES = {(RAM+a, 2) for a in PWM_WORDS} | {
    (RAM+a, 1) for a in (0xAE5C, 0xAE5D, 0xF400)} | {
    (RAM+0xAE54, 4), (RAM+0xAE58, 4)}
HEATER_WRITES = {(RAM+a, 4) for a in (
    0xB174, 0xB178, 0xB17C, 0xB180, 0xB184, 0xB188, 0xB18C,
    0xB190, 0xB194, 0xB1A0, 0xB1A4, 0xB1A8, 0xB1AC, 0xB1B0, 0xB1B4)} | {
    (RAM+a, 2) for a in (0xB198, 0xB19A, 0xB1B8, 0xB1BA, 0xB1BC)} | {
    (RAM+a, 1) for a in (0x807C, 0xB19C, 0xB1BE, 0xB1BF, 0xB1C0)} | {
    (RAM+0xAE54, 4), (RAM+0xAE58, 4), (RAM+0xF594, 2), (RAM+0xF596, 2)}


class WidebandHeaterMachine(WidebandFeedbackMachine):
    LOOKUPS = WidebandFeedbackMachine.LOOKUPS | {
        0x1D23C, 0x64F90, 0x470F4, 0x13014, 0xB2C4, 0x2390, 0x2088, 0x2098}

    def __init__(self, image, activate=True):
        super().__init__(image)
        for a in range(0xB174, 0xB1C1):
            self.write(RAM+a, 0, 1)
        for a in (0x807C, 0xD26C, 0x8FA0):
            self.write(RAM+a, 0, 1)
        for a, value in ((0xAE78, 16384), (0xAE7C, 16384),
                         (0xB6C0, 67), (0xB430, 2)):
            self.put_float(RAM+a, value)
        self.write(RAM+0xF400, 0x19, 1)
        for a in PWM_WORDS:
            self.write(RAM+a, 0, 2)
        self.execute(0xB1E8, HARDWARE_WRITES)
        if activate:
            self.execute(0xB366, HARDWARE_WRITES)
            self.execute(0xB366, HARDWARE_WRITES)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x0006:  # MOV.L Rm,@(R0,Rn).
            self.write((self.r[n]+self.r[0]) & 0xFFFFFFFF, self.r[m], 4, record=True)
        elif op & 0xF0FF == 0xF00D:  # FSTS FPUL,FRn, bit-preserving transfer.
            self.fr[n] = self.fpul
        elif op & 0xF00F == 0x300D:  # DMULS.L.
            value = signed(self.r[n], 32)*signed(self.r[m], 32)
            self.mach, self.macl = (value >> 32) & 0xFFFFFFFF, value & 0xFFFFFFFF
        elif op & 0xF0FF == 0x000A:  # STS MACH,Rn.
            self.r[n] = self.mach
        elif op & 0xF0FF == 0x400A:  # LDS Rn,MACH.
            self.mach = self.r[n]
        elif op & 0xF0FF == 0x401A:  # LDS Rn,MACL.
            self.macl = self.r[n]
        elif op & 0xF0FF == 0x4021:  # SHAR.
            self.t = bool(self.r[n] & 1)
            self.r[n] = (signed(self.r[n], 32) >> 1) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x4025:  # ROTCR including carry transfer.
            value, old_t = self.r[n], int(self.t)
            self.r[n], self.t = (value >> 1) | (old_t << 31), bool(value & 1)
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def heater(self, raw):
        self.update_wideband(raw)
        self.execute(0x12C8C, HEATER_WRITES)
        self.execute(0x12F10, HEATER_WRITES)
        return tuple(self.get_float(RAM+a) for a in (0xB174, 0xB178))


class WidebandHeaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x12C8C, 0x13360), (0xB1E8, 0xB45C),
                         (0x2088, 0x209C), (0x2390, 0x240C),
                         (0x72ABC, 0x72B04), (0x4AF0C, 0x4AF44)):
                assert image[a:b] == stock[a:b], hex(a)
            # Native raw-impedance seed and indexed store, distinct from WB
            # readiness. Whole ADC/retained-record initialization is separate.
            assert image[0xB560:0xB564] == bytes.fromhex('46800000')
            assert image[0xB4DC:0xB4E0] == bytes.fromhex('d025fce7')
            assert image[0xB574:0xB578] == bytes.fromhex('ffffae78')

    def test_native_pwm_initialization_and_independent_bank_activation(self):
        for image in self.images:
            cpu = WidebandHeaterMachine(image, activate=False)
            self.assertEqual(cpu.read(RAM+0xF400, 1), 0xD9)
            self.assertEqual((cpu.read(RAM+0xAE5C, 1), cpu.read(RAM+0xAE5D, 1)), (0, 0))
            for a in PWM_WORDS[:-2]:
                self.assertEqual(cpu.read(RAM+a, 2), 1)
            duty = cpu.heater(26000)
            self.assertGreater(duty[0], 0)
            self.assertEqual(cpu.read(RAM+0xF596, 2), 1)  # Buffered until activation.
            self.assertEqual(cpu.read(RAM+0xF594, 2), 1)
            cpu.execute(0xB366, HARDWARE_WRITES)
            self.assertEqual((cpu.read(RAM+0xAE5C, 1), cpu.read(RAM+0xAE5D, 1)), (1, 0))
            self.assertEqual(cpu.read(RAM+0xAB8A, 2), 32000)
            cpu.execute(0xB366, HARDWARE_WRITES)
            self.assertEqual(cpu.read(RAM+0xAE5D, 1), 1)
            self.assertEqual(cpu.read(RAM+0xAB88, 2), 32000)
            cpu.execute(0xB280, HARDWARE_WRITES)
            for period, output, fraction in ((0xAB8A, 0xF596, 0xAE54),
                                              (0xAB88, 0xF594, 0xAE58)):
                p = cpu.read(RAM+period, 2)
                expected = p - (p*cpu.read(RAM+fraction, 4) >> 16)
                self.assertEqual(cpu.read(RAM+output, 2), expected)
            self.assertEqual(cpu.read(RAM+0xF400, 1), 0xD9)

    def test_valid_external_wb_keeps_cold_impedance_heater_branch_invalid_stops_output(self):
        for image in self.images:
            cpu = WidebandHeaterMachine(image)
            for _ in range(100):
                first, second = cpu.heater(26000)
            self.assertEqual(cpu.read(RAM+0xB19C, 1) & 128, 128)
            self.assertEqual(first, second)
            self.assertAlmostEqual(first, 7.000732421875, delta=.00001)
            for a in (0xB1BF, 0xB1C0):
                self.assertEqual(cpu.read(RAM+a, 1) & 0xC0, 0xC0)
            for a in (0xAE78, 0xAE7C):
                self.assertEqual(cpu.get_float(RAM+a), 16384)
            self.assertEqual(cpu.heater(0), (0, 0))
            self.assertEqual(cpu.read(RAM+0xB19C, 1) & 128, 0)
            for a in (0xF594, 0xF596):
                self.assertEqual(cpu.read(RAM+a, 2), 32000)
            # Raw-impedance flags retain their separate meaning after rejection.
            self.assertEqual(cpu.read(RAM+0xB1BF, 1) & 0xC0, 0xC0)

    def test_raw_impedance_and_common_heater_enable_are_separate_from_external_readiness(self):
        for image in self.images:
            duties = []
            for impedance in (16384, 49, 30):
                cpu = WidebandHeaterMachine(image)
                for a in (0xAE78, 0xAE7C):
                    cpu.put_float(RAM+a, impedance)  # Explicit native-state control.
                for _ in range(100):
                    first, second = cpu.heater(26000)
                self.assertEqual(first, second)
                self.assertEqual(cpu.get_float(RAM+0xAE70), 50)
                duties.append(first)
            self.assertAlmostEqual(duties[0], 7.000732421875, delta=.00001)
            self.assertAlmostEqual(duties[1], 67.0013427734375, delta=.00001)
            self.assertEqual(duties[2], 0)
            cpu.write(RAM+0xB748, 128, 1)
            self.assertEqual(cpu.heater(26000), (0, 0))
            self.assertEqual(cpu.read(RAM+0xB19C, 1) & 128, 0)


if __name__ == '__main__':
    unittest.main()
