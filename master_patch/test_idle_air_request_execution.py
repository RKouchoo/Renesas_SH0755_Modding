#!/usr/bin/env python3
"""Execute stock base-air summation through the combined plate request.

Digital producers, learning and actuator motion are explicit fixture boundaries.
Table interpolation is mathematical. Native request instructions and helpers
run unchanged from the candidate; this does not reconstruct unlogged states.
"""
from io import StringIO
from pathlib import Path
import unittest

from test_idle_air_handover_execution import HandoverMachine

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
BASE_WRITES = {(0xFFFFC420, 1), (0xFFFFC40C, 1),
               (0xFFFFC2E8, 4), (0xFFFFC2EC, 4), (0xFFFFC410, 4)}
AIR_WRITES = {(a, 4) for a in (0xFFFFC404, 0xFFFFC3FC,
                              0xFFFFC408, 0xFFFFC400)}
PLATE_WRITES = {(0xFFFFC41C, 4), (0xFFFFC3F8, 4)}
SUM_WRITES = {(a, 4) for a in range(0xFFFFC300, 0xFFFFC3CC, 4)} | {
    (0xFFFFC2F4, 4), (0xFFFFC2C4, 4), (0xFFFFC2DE, 1), (0xFFFFC2DD, 1)}
REQUEST_WRITES = {(a, 4) for a in (0xFFFFC2D0, 0xFFFFC2B8,
                                  0xFFFFC2BC, 0xFFFFC2FC)}
COOLANT_WRITES = {(0xFFFFC428, 4), (0xFFFFC430, 2)}
BASE_UPDATE_WRITES = {(0xFFFFC434, 2), (0xFFFFC42C, 4),
                     (0xFFFFC436, 1), (0xFFFFC432, 2), (0xFFFFC424, 4)}


class RequestMachine(HandoverMachine):
    def __init__(self, image, rpm=558, coolant=40):
        super().__init__(image, rpm)
        for a in (0xFFFFC420, 0xFFFFC2DE, 0xFFFFC2DD, 0xFFFFC2DC,
                  0xFFFFC5E0, 0xFFFFB385, 0xFFFFC436, 0xFFFFC40C,
                  0xFFFFC640, 0xFFFFC618):
            self.write(a, 0, 1)
        self.write(0xFFFF0000 | self.read(0x653D0, 2), 0, 1)
        self.write(0xFFFFC4D8, 4, 1)  # Explicit coolant-table mode, not logged.
        for a in (0xFFFFC430, 0xFFFFC432, 0xFFFFC434):
            self.write(a, 0, 2)
        self.write(0xFFFFAC08, 40000, 4)  # History timing input, inactive selection.
        self.put_float(0xFFFFB3AC, coolant)
        self.put_float(0xFFFFB3B0, coolant)
        self.put_float(0xFFFFB3B8, 26)
        self.put_float(0xFFFFCFBC, 760)  # Effective barometric input; unlogged.
        for a in (0xFFFFB46C, 0xFFFFB730, 0xFFFFD10C, 0xFFFFCA78, 0xFFFFC3FC,
                  0xFFFFC400, 0xFFFFC2EC, 0xFFFFC3D0,
                  0xFFFFC2C8, 0xFFFFC2C0, 0xFFFFC2D8, 0xFFFFC2B4,
                  0xFFFFC2FC, 0xFFFFC5DC, 0xFFFFC428, 0xFFFFC42C,
                  0xFFFF80F0):
            self.put_float(a, 0)
        for a in range(0xFFFFC300, 0xFFFFC3CC, 4):
            self.put_float(a, 0)
        # Execute the native limit/barometric producers once with fixed inputs.
        self.invoke(0x2B728, {(0xFFFFC2F0, 4)})
        self.invoke(0x2B73C, {(0xFFFFC414, 4), (0xFFFFC418, 4)})
        self.invoke(0x2B762, {(0xFFFFC2E0, 4), (0xFFFFC2E4, 4)})
        self.put_float(0xFFFF80D8, 84)  # Explicit learned actuator bound.

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0xF00B and n != 15:  # fmov.s FRm,@-Rn.
            self.r[n] = (self.r[n] - 4) & 0xFFFFFFFF
            self.write(self.r[n], self.fr[m], 4, record=True)
        elif op & 0xF0FF == 0x4000:  # shll Rn; shifted-out bit goes to T.
            self.t = bool(self.r[n] & 0x80000000)
            self.r[n] = (self.r[n] << 1) & 0xFFFFFFFF
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def call_lookup(self, target):
        if target in (0x18D08, 0x1629A, 0x2B8AC, 0x2B908, 0x653BA):
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def table(self, target, descriptor, x, y):
        if descriptor not in (0x602DC, 0x6075C, 0x603B8, 0x603CC,
                              0x603E0, 0x603F4, 0x603A4, 0x60340,
                              0x60354, 0x60368, 0x6037C, 0x60390):
            return super().table(target, descriptor, x, y)
        assert target == 0x209C
        n, kind = self.read(descriptor, 2), self.read(descriptor + 2, 2)
        axis = self.array(self.read(descriptor + 4, 4), n)
        data = self.read(descriptor + 8, 4)
        if kind == 0:
            values = self.array(data, n)
        else:
            assert kind in (0x400, 0x800)
            size = kind >> 10
            scale, bias = self.get_float(descriptor + 12), self.get_float(descriptor + 16)
            values = [self.read(data + i*size, size)*scale + bias for i in range(n)]
        return self.interpolate(axis, values, x)

    def coolant_base(self):
        self.invoke(0x2B7E8, COOLANT_WRITES)
        self.invoke(0x2B846, BASE_UPDATE_WRITES)
        return self.get_float(0xFFFFC424)

    def plate_request(self):
        # Execute this dependency chain; actual task scheduling/learning is
        # outside this fixture and is checked separately from data propagation.
        for entry, writes in ((0x2B570, BASE_WRITES), (0x2B432, AIR_WRITES),
                              (0x2B408, PLATE_WRITES), (0x2AC16, SUM_WRITES),
                              (0x2AB06, REQUEST_WRITES)):
            self.invoke(entry, writes)
        return self.get_float(0xFFFFC2B8) / .84


class RequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch/candidates/D2WD610H_idle_recovery_candidate.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for a, b in ((0x2AAAC, 0x2AD6C), (0x2AE5E, 0x2AE60),
                     (0x2B408, 0x2B7E8), (0x2B7E8, 0x2B9C8),
                     (0x1629A, 0x162AE), (0x162C4, 0x162C6),
                     (0x18D08, 0x18D1C), (0x18D90, 0x18D92),
                     (0x602DC, 0x602F0), (0x60340, 0x60408),
                     (0x6075C, 0x60768), (0x79524, 0x79628),
                     (0x75E0E, 0x75E0F), (0x79B10, 0x79B1A),
                     (0x79990, 0x799D0), (0x79C18, 0x79D1C),
                     (0x7A344, 0x7A47C), (0xC688, 0xC6F0),
                     (0x2FDDE, 0x2FE0C), (0x2FEFC, 0x2FF14),
                     (0x7B270, 0x7B278), (0x10EF4, 0x10F42),
                     (0x110EC, 0x11120), (0x653BA, 0x653D2)):
            assert cls.image[a:b] == stock[a:b], hex(a)

    def test_feedback_survives_native_air_to_plate_chain(self):
        # Retained producer pointers in task 9, in this same relative order.
        for pc, pool, target in ((0x10EF4, 0x110EC, 0x2B570),
                                 (0x10EFA, 0x110F0, 0x2B432),
                                 (0x10F00, 0x110F4, 0x2B408),
                                 (0x10F2A, 0x11110, 0x2AC16),
                                 (0x10F3C, 0x1111C, 0x2AB06)):
            op = int.from_bytes(self.image[pc:pc + 2], 'big')
            self.assertEqual(op >> 12, 0xD)
            self.assertEqual(((pc + 4) & ~3) + (op & 255)*4, pool)
            self.assertEqual(int.from_bytes(self.image[pool:pool + 4], 'big'), target)
        outputs = []
        for correction in (0, 2, 6):
            cpu = RequestMachine(self.image)
            cpu.put_float(0xFFFFC424, 7)
            cpu.put_float(0xFFFFC438, .666)
            cpu.put_float(0xFFFFC45C, correction)
            outputs.append(cpu.plate_request())
            self.assertAlmostEqual(cpu.get_float(0xFFFFC3FC), 7.666 + correction, places=5)
            self.assertEqual(cpu.get_float(0xFFFFC2C4), cpu.get_float(0xFFFFC3F8))
            self.assertEqual(cpu.get_float(0xFFFFC2B8), cpu.get_float(0xFFFFC3F8))
        self.assertTrue(0 < outputs[0] < outputs[1] < outputs[2] < 100)

    def test_coolant_table_selection_executes_native_lookup(self):
        for mode, expected in ((1, 8.500671), (2, 8.500671), (3, 8.500671),
                                (4, 7.000732), (5, 7.000732), (6, 7.000732)):
            cpu = RequestMachine(self.image)
            cpu.write(0xFFFFC4D8, mode, 1)
            cpu.invoke(0x2B7E8, COOLANT_WRITES)
            self.assertAlmostEqual(cpu.get_float(0xFFFFC428), expected, places=5)

    def test_cold_base_air_initialization_and_slew(self):
        cpu = RequestMachine(self.image)
        cpu.write(0xFFFFB748, 0x80, 1)  # Native startup getter.
        initial = cpu.coolant_base()
        self.assertAlmostEqual(initial, 7.000732421875)
        cpu.write(0xFFFFB748, 0, 1)
        cpu.put_float(0xFFFFB3AC, 50)
        self.assertAlmostEqual(cpu.coolant_base(), initial - .01, places=6)
        cpu.put_float(0xFFFFB3AC, 30)
        self.assertAlmostEqual(cpu.coolant_base(), initial, places=6)

    def test_request_bounds_and_alternate_selection_are_distinct(self):
        cpu = RequestMachine(self.image)
        cpu.put_float(0xFFFFC424, 7)
        cpu.put_float(0xFFFFC45C, 6)
        normal = cpu.plate_request()
        # This alternate native request selection ignores the idle plate term.
        # Its mode producer is unlogged; this is not an observed vehicle mode.
        cpu.write(0xFFFFC2DC, 1, 1)
        cpu.put_float(0xFFFFC2C0, 2)
        self.assertAlmostEqual(cpu.plate_request(), 2 / .84)
        self.assertGreater(normal, 2 / .84)
        # Restore normal mode and independently impose insufficient air headroom.
        cpu.write(0xFFFFC2DC, 0, 1)
        cpu.put_float(0xFFFFC2E4, 7)
        limited = cpu.plate_request()
        self.assertLess(limited, normal)
        self.assertEqual(cpu.get_float(0xFFFFC3FC), 7)

    def test_native_adc_fault_helper_does_not_read_repurposed_maf_channel(self):
        cpu = RequestMachine(self.image)
        # C688 is called by the raw 8138/813C diagnostic producers. These
        # RAM bounds are copied from the pinned native 2FDDC calibration inputs.
        for ram, cal in ((0xFFFFC684, 0x7B270), (0xFFFFC686, 0x7B272),
                         (0xFFFFC688, 0x7B274), (0xFFFFC68A, 0x7B276)):
            cpu.write(ram, cpu.read(cal, 2), 2)
        for channel in (0, 1):
            cpu.original_r[4] = channel
            for raw, expected in ((0, 2), (1311, 0), (32768, 0),
                                   (64224, 0), (64225, 1), (65535, 1)):
                for maf_raw in (0, 65535):
                    cpu.write(0xFFFFAB08 + channel*2, raw, 2)
                    cpu.write(0xFFFFAB06, maf_raw, 2)
                    self.assertEqual(cpu.invoke(0xC688, set()), expected)
                    self.assertNotIn(0xFFFFAB06, cpu.reads)

    def test_final_request_adds_learning_and_honors_separate_overrides(self):
        cpu = RequestMachine(self.image)
        cpu.put_float(0xFFFFC424, 7)
        cpu.put_float(0xFFFFC45C, 6)
        cpu.plate_request()
        cpu.put_float(0xFFFF80F0, 2)  # Explicit learned offset, not from the log.
        writes = {(0xFFFFC2B4, 4)}
        cpu.invoke(0x2AAAC, writes)
        self.assertAlmostEqual(cpu.get_float(0xFFFFC2B4),
                               cpu.get_float(0xFFFFC2B8) + 2, places=6)
        cpu.write(0xFFFFC640, 1, 1)
        cpu.put_float(0xFFFFC63C, 1)
        cpu.invoke(0x2AAAC, writes)
        self.assertEqual(cpu.get_float(0xFFFFC2B4), 3)
        cpu.write(0xFFFFC640, 0, 1)
        cpu.write(0xFFFFC618, 1, 1)
        cpu.put_float(0xFFFFC610, 4)
        cpu.invoke(0x2AAAC, writes)
        self.assertEqual(cpu.get_float(0xFFFFC2B4), 4)
        cpu.write(0xFFFFC618, 0, 1)
        cpu.write(0xFFFF0000 | cpu.read(0x653D0, 2), 0x40, 1)
        cpu.put_float(0xFFFFC2D4, 1.5)
        cpu.invoke(0x2AAAC, writes)
        self.assertEqual(cpu.get_float(0xFFFFC2B4), 3.5)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(RequestTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Idle request: {result.testsRun} execution test groups passed')
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
