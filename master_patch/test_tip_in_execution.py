#!/usr/bin/env python3
"""Execute retained throttle-tip-in eligibility and supplemental pulse request.

23BAE and 14D1E execute ROM instructions. Table interpolation and C700 event
delivery are explicit boundaries; this verifies a requested supplemental pulse,
not injector hardware delivery. Sub-sample throttle/MAP and flag states are
fixtures. The normal scheduled pulse logged as E60 is a separate path.
"""
from io import StringIO
from pathlib import Path
import struct
import unittest

from test_opening_timing_execution import OpeningTimingMachine

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
DESCRIPTORS = (0x5F484, 0x5F978, 0x5F98C, 0x5F45C, 0x5F470, 0x5F9A0)
WRITES = {(a, 4) for a in (0xFFFFBF00, 0xFFFFBF04, 0xFFFFBF14,
                          0xFFFFBEF0, 0xFFFFBEFC, 0xFFFFBF10)} | {
    (a, 1) for a in (0xFFFFBF08, 0xFFFFBF09, 0xFFFFBF1A)}


class TipInMachine(OpeningTimingMachine):
    def __init__(self, image, delta=20, rpm=1350, coolant=45, map_mmhg=330, baro=712):
        super().__init__(image, rpm=rpm, coolant=coolant)
        self.events = []
        for address in (0xFFFFBF08, 0xFFFFBF09, 0xFFFFBF1A, 0xFFFFCCBB, 0xFFFFC2DE):
            self.write(address, 0, 1)
        for address in (0xFFFFBF00, 0xFFFFBF04, 0xFFFFBF14, 0xFFFFBEF0,
                        0xFFFFBEFC, 0xFFFFBF10):
            self.put_float(address, 0)
        self.put_float(0xFFFFBEF8, 1)  # Supplied retained ECT/history compensation.
        self.put_float(0xFFFFC0D8, 650)  # Supplied injector latency, microseconds.
        self.put_float(0xFFFFB2CC, delta)
        self.put_float(0xFFFFCFBC, baro)
        self.put_float(0xFFFFB2A0, map_mmhg)

    def table(self, target, descriptor, x, y):
        if descriptor not in DESCRIPTORS:
            return super().table(target, descriptor, x, y)
        assert target == 0x209C
        n, kind, axis, data, scale, bias = struct.unpack_from('>HHIIff', self.image, descriptor)
        assert kind in (0x400, 0x800)
        size = kind >> 10
        values = [self.read(data+i*size, size)*scale+bias for i in range(n)]
        return self.interpolate(self.array(axis, n), values, x)

    def call_lookup(self, target):
        if target in (0x2AF28, 0x3AF4, 0x3B08):
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        elif target == 0xC700:
            assert self.r[4:7] == [0, 4, 0xFFFFBEFC]
            # C700 indexes FB88[0] -> FD04, slot 4 -> callback 11EF4 with
            # one float payload. Preserve that ABI; do not emulate actuation.
            assert self.read(0xFB88, 4) == 0xFD04
            assert self.image[0xFD24:0xFD2C] == bytes.fromhex('ffff000100011ef4')
            self.events.append((self.get_float(0xFFFFBEFC), self.get_float(0xFFFFBF10)))
            self.poison_scratch()
            self.r[0] = 0
        else:
            super().call_lookup(target)

    def request(self, delta=None, map_mmhg=None):
        if delta is not None:
            self.put_float(0xFFFFB2CC, delta)
        if map_mmhg is not None:
            self.put_float(0xFFFFB2A0, map_mmhg)
        self.events.clear()
        self.table_calls.clear()
        self.invoke(0x23BAE, WRITES)
        return bool(self.read(0xFFFFBF09, 1) & 0x80)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x6002:  # mov.l @Rm,Rn (no postincrement)
            self.r[n] = self.load(self.r[m], 4)
        elif op & 0xF00F == 0xF00B and n != 15:  # fmov.s FRm,@-Rn
            self.r[n] = (self.r[n]-4) & 0xFFFFFFFF
            self.write(self.r[n], self.fr[m], 4, record=True)
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT


class TipInTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes()
        cls.stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x23BAE, 0x23EE8), (0x14CE6, 0x14D52),
                           (0x14D8C, 0x14DBE), (0x2AF28, 0x2AF44),
                           (0x15192, 0x151A6), (0x1ADD8, 0x1ADEC),
                           (0x2534, 0x2560), (0x3AF4, 0x3B1C),
                           (0xFD24, 0xFD2C), (0x76AA8, 0x76AD0)):
            assert cls.image[start:end] == cls.stock[start:end], hex(start)

    def test_native_tip_in_history_uses_two_throttle_updates(self):
        cpu = TipInMachine(self.image)
        for address in range(0xFFFFB2D0, 0xFFFFB2F4, 4):
            cpu.put_float(address, 5)
        cpu.put_float(0xFFFFB2C8, 10)
        writes = {(a, 4) for a in range(0xFFFFB2D0, 0xFFFFB2F4, 4)} | {(0xFFFFB2CC, 4)}
        values = []
        for _ in range(3):
            cpu.invoke(0x14D1E, writes)
            values.append(cpu.get_float(0xFFFFB2CC))
            self.assertGreater(cpu.reads[0xFFFFB2C8], 0)
            self.assertEqual(cpu.reads[0xFFFFB46C], 0)
        self.assertEqual(values, [5, 5, 0])

    def test_positive_delta_requests_a_separate_pulse_in_vacuum(self):
        cpu = TipInMachine(self.image)
        self.assertTrue(cpu.request())
        self.assertEqual(len(cpu.events), 1)
        net, total = cpu.events[0]
        expected = 1548 * (1.0389404296875+1)/2
        self.assertAlmostEqual(net, expected, places=3)
        self.assertAlmostEqual(total, expected+650, places=3)
        self.assertEqual(cpu.get_float(0xFFFFBF14), 382)

    def test_pressure_multiplier_zeroes_tip_in_near_atmospheric_pressure(self):
        for image in (self.stock, self.image):
            for pressure in (562, 650, 712, 760):
                cpu = TipInMachine(image, map_mmhg=pressure)
                self.assertFalse(cpu.request())
                self.assertEqual(cpu.get_float(0xFFFFBEF0), 0)
                self.assertEqual(cpu.events, [])
                self.assertIn((0x209C, 0x5F470, 712-pressure),
                              [call[:3] for call in cpu.table_calls])

    def test_more_base_tip_in_cannot_overcome_zero_pressure_multiplier(self):
        changed = bytearray(self.image)
        for data in (0x7739C, 0x773BC):
            for i in range(5):
                value = struct.unpack_from('>H', changed, data+2*i)[0]
                struct.pack_into('>H', changed, data+2*i, value*2)
        cpu = TipInMachine(changed, map_mmhg=712)
        self.assertFalse(cpu.request())
        self.assertEqual(cpu.get_float(0xFFFFBEF0), 0)
        # In-memory sensitivity only, not a proposed or written calibration.
        changed = bytearray(self.image)
        changed[0x76AC8:0x76ACA] = bytes([128, 128])
        cpu = TipInMachine(changed, map_mmhg=712)
        self.assertTrue(cpu.request())
        self.assertGreater(cpu.events[0][0], 1500)

    def test_retained_flags_and_limits_still_block_ineligible_requests(self):
        for address, value, size in ((0xFFFFB2BC, 2, 1), (0xFFFFB748, 128, 1),
                                     (0xFFFFCCBB, 4, 1), (0xFFFFBF08, 20, 1)):
            cpu = TipInMachine(self.image)
            cpu.write(address, value, size)
            self.assertFalse(cpu.request())
            self.assertEqual(cpu.events, [])
        cpu = TipInMachine(self.image)
        cpu.put_float(0xFFFFBF04, 45)
        self.assertFalse(cpu.request())
        cpu = TipInMachine(self.image, delta=1.4)
        self.assertFalse(cpu.request())
        self.assertTrue(cpu.request(delta=1.5))

    def test_release_and_elapsed_count_reset_history_but_last_value_can_stay(self):
        cpu = TipInMachine(self.image)
        self.assertTrue(cpu.request())
        last = cpu.get_float(0xFFFFBEF0)
        self.assertFalse(cpu.request(delta=-1))
        self.assertEqual(cpu.read(0xFFFFBF08, 1), 0)
        self.assertEqual(cpu.get_float(0xFFFFBF04), 0)
        self.assertEqual(cpu.get_float(0xFFFFBEF0), last)
        cpu.write(0xFFFFBF08, 20, 1)
        cpu.put_float(0xFFFFBF04, 45)
        cpu.write(0xFFFFBF1A, 29, 1)
        self.assertTrue(cpu.request(delta=20))

    def test_minimum_threshold_is_already_in_microseconds(self):
        for calculated, expected in ((185.9, False), (186, True)):
            cpu = TipInMachine(self.image, delta=2, coolant=80)
            cpu.tables = {0x5F978: calculated, 0x5F98C: calculated}
            self.assertEqual(cpu.request(), expected)
        from importlib.util import module_from_spec, spec_from_file_location
        spec = spec_from_file_location('tip_in_master_definition', ROOT / 'master_patch/build_definition.py')
        definition = module_from_spec(spec)
        spec.loader.exec_module(definition)
        tree = definition.build_tree()
        parent = tree.getroot().find('rom')
        scaling = definition.table_by_name(parent, 'Minimum Tip-in Enrichment Activation').find('scaling')
        self.assertEqual(scaling.get('expression'), 'x*.001')
        self.assertEqual(scaling.get('to_byte'), 'x/.001')
        threshold = struct.unpack_from('>f', self.image, 0x763E0)[0]
        self.assertAlmostEqual(threshold*.001, .185967575, places=8)


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TipInTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Throttle tip-in: {result.testsRun} execution test groups passed')
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
