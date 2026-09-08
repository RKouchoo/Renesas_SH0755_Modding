#!/usr/bin/env python3
"""Execute retained final-throttle override producers with explicit inputs.

Native instructions decide the overrides. Digital inputs, receive state and
learning are fixtures, not recovered from the vehicle's non-atomic capture.
No firmware image is changed or written by this module.
"""
from io import StringIO
from pathlib import Path
import unittest

from test_idle_air_request_execution import RequestMachine
from test_primary_fueling_execution import signed

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
TIMER_WRITES = {(0xFFFFC614, 2), (0xFFFFC618, 1)}
STOP_WRITES = {(0xFFFFC618, 1), (0xFFFFC638, 1)}
OFF_WRITES = {(0xFFFFC640, 1), (0xFFFFC648, 1), (0xFFFFC63C, 4),
              (0xFFFFC644, 2), (0xFFFFC646, 2)}
FAULT_WRITES = {(a, 1) for a in range(0xFFFFD271, 0xFFFFD275)}
PAIR_WRITES = {(0xFFFFD1F8, 2), (0xFFFFD1FA, 2),
               (0xFFFFD200, 1), (0xFFFF8134, 1)}
ADC_WRITES = {(0xFFFFAF80, 4), (0xFFFFAF84, 4), (0xFFFFAF88, 2),
              (0xFFFFAF8A, 2), (0xFFFFAF8C, 1), (0xFFFFAF8D, 1)}
RECEIVE_GETTERS = {
    0x30C3E, 0x30C7A, 0x30D00, 0x30CA2, 0x30CCA, 0x30AFE,
    0x30B3A, 0x30B5C, 0x30BA6, 0x30BCE, 0x30BF6, 0x30AEA,
    0x30C30, 0x30C66, 0x30CEC, 0x30D28, 0x30D4A, 0x30D86,
    0x30DB8, 0x30E02, 0x30E2A, 0x30D72,
}


class OverrideMachine(RequestMachine):
    def __init__(self, image, rpm=558):
        super().__init__(image, rpm)
        for a in (0xFFFF80D4, 0xFFFF80D5, 0xFFFF80D6, 0xFFFF814C,
                  0xFFFFB358, 0xFFFFC638, 0xFFFFC648, 0xFFFF80B0,
                  0xFFFF825C):
            self.write(a, 0, 1)
        for a in (0xFFFFB354, 0xFFFFC614, 0xFFFFC644, 0xFFFFC646):
            self.write(a, 0, 2)
        self.put_float(0xFFFFABB4, 13.5)
        self.put_float(0xFFFF8108, 40)
        self.put_float(0xFFFFC6D0, 0)
        self.put_float(0xFFFFC63C, 0)
        # Deliberately permit the downstream conditions so the RPM/switch
        # exclusions cannot pass merely because a different gate was closed.
        self.write(0xFFFFC650, 0x80, 1)
        self.write(0xFFFFC6F7, 2, 1)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF0FF == 0x4001:  # shlr Rn.
            self.t = bool(self.r[n] & 1)
            self.r[n] >>= 1
        elif op & 0xF00F == 0x6008:  # swap.b Rm,Rn; retain the high word.
            value = self.r[m]
            self.r[n] = (value & 0xFFFF0000) | ((value & 255) << 8) | ((value >> 8) & 255)
        elif op & 0xF0FF == 0x4010:  # dt Rn.
            self.r[n] = (self.r[n] - 1) & 0xFFFFFFFF
            self.t = self.r[n] == 0
        elif op & 0xF00F == 0x6005:  # mov.w @Rm+,Rn.
            value = signed(self.load(self.r[m], 2), 16) & 0xFFFFFFFF
            if n != m:
                self.r[m] = (self.r[m] + 2) & 0xFFFFFFFF
            self.r[n] = value
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def call_lookup(self, target):
        if target in RECEIVE_GETTERS | {
                0x19C04, 0x2FB08, 0x30AC2, 0x1628C, 0x1C082,
                0x19CB8, 0x15AC4, 0x15AB0, 0x15A3A, 0x16270,
                0x1627E, 0x312E0, 0x4244, 0x36972, 0x2484, 0x18D30}:
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def clear_fault_fixtures(self):
        # Enumerated diagnostic inputs, not a zero-initialized whole ECU RAM.
        for a in (0x8134, 0x8138, 0x813C, 0x8150, 0x8194,
                  0x81AC, 0x81A8, 0x814C, 0x8198, 0x81A0):
            self.write(0xFFFF0000 | a, 0, 1)
        for a in range(0xFFFFC6F7, 0xFFFFC700):
            self.write(a, 0, 1)
        for a in range(0xFFFFD271, 0xFFFFD275):
            self.write(a, 0, 1)


class OverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for a, b in ((0x2EFB8, 0x2F390), (0x2F684, 0x2F8C0),
                     (0x2FB08, 0x2FB20), (0x19C04, 0x19C18),
                     (0x19D40, 0x19D58), (0x31AE4, 0x31BBC),
                     (0x31CA4, 0x31CB8), (0x4B884, 0x4B888),
                     (0x4244, 0x427E), (0x30A9A, 0x30E60),
                     (0x18D30, 0x18D48), (0x18D92, 0x18DAC),
                     (0x61A08, 0x61B98), (0x74DC0, 0x74DC4),
                     (0x74FBC, 0x74FE4),
                     (0xC5C8, 0xC700), (0x727D8, 0x727E1),
                     (0x7B270, 0x7B278), (0x7B2A4, 0x7B2AC),
                     (0x64874, 0x64F7C), (0x79531, 0x79534),
                     (0x79582, 0x7958E), (0x79934, 0x79990),
                     (0x10F42, 0x10F7E), (0x11120, 0x11148)):
            assert cls.image[a:b] == stock[a:b], hex(a)

    def test_ignition_getter_is_the_native_ssm_62_bit_3_input(self):
        self.assertEqual(int.from_bytes(self.image[0x4B884:0x4B888], 'big'), 0x31AE4)
        for ignition in (0, 0x10):
            cpu = OverrideMachine(self.image)
            cpu.write(0xFFFFB51E, ignition, 1)
            # The complete stock SSM getter composes all five reported bits.
            value = cpu.invoke(0x31AE4, set())
            self.assertEqual(bool(value & 8), bool(ignition))

    def test_running_rpm_clears_stopped_engine_override_even_if_latched(self):
        cpu = OverrideMachine(self.image, rpm=100)
        cpu.write(0xFFFFC618, 8, 1)
        cpu.write(0xFFFFC614, 6, 2)
        cpu.invoke(0x2F03C, STOP_WRITES)
        self.assertEqual(cpu.read(0xFFFFC618, 1) & 1, 1)  # Positive control.
        for rpm, expected in ((199, 1), (200, 1), (299, 1), (300, 0),
                               (558, 0), (673, 0), (1000, 0), (200, 0), (199, 1)):
            cpu.put_float(0xFFFFB544, rpm)
            cpu.invoke(0x2F03C, STOP_WRITES)
            self.assertEqual(cpu.read(0xFFFFC618, 1) & 1, expected, rpm)

    def test_ignition_on_clears_shutdown_override_before_final_selection(self):
        for rpm in (558, 673, 1000, 2500):
            cpu = OverrideMachine(self.image, rpm)
            cpu.write(0xFFFFC640, 1, 1)  # Deliberately stale override.
            cpu.write(0xFFFFB51E, 0x10, 1)
            cpu.put_float(0xFFFFC2B8, 6)
            cpu.put_float(0xFFFF80F0, 2)
            for raw in (0, 65535):
                cpu.write(0xFFFFAB06, raw, 2)
                cpu.invoke(0x2F684, OFF_WRITES)
                self.assertEqual(cpu.read(0xFFFFC640, 1) & 1, 0)
                self.assertNotIn(0xFFFFAB06, cpu.reads)
                cpu.invoke(0x2AAAC, {(0xFFFFC2B4, 4)})
                self.assertEqual(cpu.get_float(0xFFFFC2B4), 8)

    def test_shutdown_timer_resets_on_ignition_and_expires_without_wrap(self):
        cpu = OverrideMachine(self.image)
        cpu.write(0xFFFFB51E, 0x10, 1)
        cpu.write(0xFFFFC614, 1000, 2)
        cpu.invoke(0x2EFB8, TIMER_WRITES)
        self.assertEqual(cpu.read(0xFFFFC614, 2), 0)
        cpu.write(0xFFFFB51E, 0, 1)
        # Native task order runs 2F684 before 2EFB8; use the real order at
        # the final permitted count rather than inventing a timer convention.
        cpu.write(0xFFFFC614, 374, 2)
        cpu.invoke(0x2F684, OFF_WRITES)
        self.assertEqual(cpu.read(0xFFFFC640, 1) & 1, 1)
        self.assertEqual(cpu.get_float(0xFFFFC63C), 3)
        cpu.invoke(0x2EFB8, TIMER_WRITES)
        self.assertEqual(cpu.read(0xFFFFC614, 2), 375)
        cpu.invoke(0x2F684, OFF_WRITES)
        self.assertEqual(cpu.read(0xFFFFC640, 1) & 1, 0)
        cpu.write(0xFFFFC614, 65535, 2)
        cpu.invoke(0x2EFB8, TIMER_WRITES)
        self.assertEqual(cpu.read(0xFFFFC614, 2), 65535)

    def test_fault_override_aggregates_seven_receive_bits_and_pair_monitor(self):
        # Follow the register overwrite at 64B8E: r13 is 8134 bit 0 here,
        # not its earlier C6FB/8 value. Exercise unrelated bits as controls.
        sources = {0xC6F7: 0x08, 0xC6F9: 0x50, 0xC6FA: 0x09,
                   0xC6FB: 0x04, 0xC6FC: 0x01, 0x8134: 0x01}
        cpu = OverrideMachine(self.image)
        for a, mask in sources.items():
            for bit in (1, 2, 4, 8, 16, 32, 64, 128):
                cpu.clear_fault_fixtures()
                cpu.write(0xFFFF0000 | a, bit, 1)
                cpu.invoke(0x64874, FAULT_WRITES)
                expected = bool(bit & mask)
                self.assertEqual(bool(cpu.read(0xFFFFD273, 1) & 0x10), expected, (a, bit))
                self.assertEqual(bool(cpu.read(0xFFFFD274, 1) & 0x40), expected, (a, bit))
                cpu.clear_fault_fixtures()
                cpu.invoke(0x64874, FAULT_WRITES)
                self.assertEqual(cpu.read(0xFFFFD274, 1) & 0x40, 0)

    def test_native_pedal_pair_monitor_can_select_fault_request(self):
        for maf_raw in (0, 65535):
            cpu = OverrideMachine(self.image)
            cpu.clear_fault_fixtures()
            cpu.write(0xFFFFAB06, maf_raw, 2)
            cpu.write(0xFFFF8128, 0, 1)  # Normal diagnostic selection.
            cpu.write(0xFFFFD200, 1, 1)  # Explicitly enabled raw monitor.
            for a in (0xFFFFD1F8, 0xFFFFD1FA):
                cpu.write(a, 0, 2)
            for a in (0xFFFFB464, 0xFFFFB468, 0xFFFFD1FC):
                cpu.put_float(a, 0)
            for _ in range(29):
                cpu.invoke(0x61A08, PAIR_WRITES)
            self.assertEqual(cpu.read(0xFFFF8134, 1) & 1, 0)
            cpu.put_float(0xFFFFB464, 12)  # Deliberate sensor disagreement.
            for count in range(1, 30):
                cpu.invoke(0x61A08, PAIR_WRITES)
                self.assertEqual(cpu.read(0xFFFF8134, 1) & 1, int(count == 29))
                self.assertNotIn(0xFFFFAB06, cpu.reads)
            cpu.invoke(0x64874, FAULT_WRITES)
            self.assertEqual(cpu.read(0xFFFFD274, 1) & 0x40, 0x40)
            cpu.put_float(0xFFFFC2B8, 6)
            cpu.put_float(0xFFFFC2D4, 1.5)  # Separate unlogged fault request.
            cpu.put_float(0xFFFF80F0, 2)
            cpu.invoke(0x2AAAC, {(0xFFFFC2B4, 4)})
            self.assertEqual(cpu.get_float(0xFFFFC2B4), 3.5)

    def test_pedal_adc_pair_producer_keeps_channels_separate_from_maf(self):
        cpu = OverrideMachine(self.image)
        # Values copied by native 2FDDC. ADC update and scaling execute here;
        # electrical signals and later offset learning are fixture boundaries.
        for ram, cal, size in ((0xC67C, 0x7B2A4, 4), (0xC680, 0x7B2A8, 4),
                               (0xC684, 0x7B270, 2), (0xC686, 0x7B272, 2),
                               (0xC688, 0x7B274, 2), (0xC68A, 0x7B276, 2)):
            cpu.write(0xFFFF0000 | ram, cpu.read(cal, size), size)
        for a, size in ((0xFFFFAF88, 2), (0xFFFFAF8A, 2),
                         (0xFFFFAF8C, 1), (0xFFFFAF8D, 1)):
            cpu.write(a, 0, size)
        cpu.write(0xFFFFAB08, 8000, 2)
        cpu.write(0xFFFFAB0A, 16000, 2)
        outputs = []
        for maf_raw in (0, 65535):
            cpu.write(0xFFFFAB06, maf_raw, 2)
            cpu.invoke(0xC5C8, ADC_WRITES)
            outputs.append((cpu.get_float(0xFFFFAF80), cpu.get_float(0xFFFFAF84)))
            self.assertNotIn(0xFFFFAB06, cpu.reads)
        self.assertEqual(outputs[0], outputs[1])
        self.assertAlmostEqual(outputs[0][0], 4.0283203125, delta=1e-6)
        self.assertAlmostEqual(outputs[0][1], 8.056640625, delta=1e-6)
        cpu.write(0xFFFFAB08, 16000, 2)
        cpu.invoke(0xC5C8, ADC_WRITES)
        self.assertEqual(cpu.get_float(0xFFFFAF80), outputs[0][1])
        self.assertEqual(cpu.get_float(0xFFFFAF84), outputs[0][1])


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(OverrideTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Idle overrides: {result.testsRun} execution test groups passed')
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
