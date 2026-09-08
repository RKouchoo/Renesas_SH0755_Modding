#!/usr/bin/env python3
"""Check stock DBW maps and the separate idle request with released pedal.

Native lookup callers/filter/request composition execute from ROM. Lookup
interpolation is mathematical; the intervening torque arbitration, learned
state and physical actuator remain explicit boundaries. No BIN is written.
"""
from io import StringIO
from pathlib import Path
import struct
import unittest

from test_idle_air_request_execution import RequestMachine
from test_idle_air_handover_execution import HandoverMachine

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None


class DBWMachine(RequestMachine):
    def __init__(self, image, rpm=558):
        super().__init__(image, rpm)
        self.put_float(0xFFFFB47C, 0)
        for a in (0xFFFFC3DC, 0xFFFFC3D4, 0xFFFFC2CC):
            self.put_float(a, 0)

    def table(self, target, descriptor, x, y):
        if descriptor not in (0x607D4, 0x607F0):
            return super().table(target, descriptor, x, y)
        assert target == 0x2150
        nx, ny = self.read(descriptor, 2), self.read(descriptor + 2, 2)
        xs = self.array(self.read(descriptor + 4, 4), nx)
        ys = self.array(self.read(descriptor + 8, 4), ny)
        data = self.read(descriptor + 12, 4)
        assert self.read(descriptor + 16, 4) == 0x08000000
        scale, bias = self.get_float(descriptor + 20), self.get_float(descriptor + 24)
        rows = [self.interpolate(xs, [self.read(data + 2*(row*nx + i), 2)*scale + bias
                                      for i in range(nx)], x) for row in range(ny)]
        return self.interpolate(ys, rows, y)


class DBWTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch/candidates/D2WD610H_idle_recovery_candidate.bin').read_bytes()

    def test_visible_dbw_maps_axes_and_traced_constants_are_stock_identical(self):
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for a, b in ((0x2AAAC, 0x2F390), (0x607D4, 0x6080C),
                     (0x7A6AC, 0x7AD24), (0x79524, 0x797D8)):
            self.assertEqual(self.image[a:b], stock[a:b], hex(a))
        cpu = DBWMachine(self.image)
        self.assertEqual((cpu.read(0x607F0, 2), cpu.read(0x607F2, 2)), (19, 20))
        self.assertEqual(cpu.read(0x607FC, 4), 0x7AA2C)
        self.assertEqual((cpu.read(0x607D4, 2), cpu.read(0x607D6, 2)), (15, 20))
        self.assertEqual(cpu.read(0x607E0, 4), 0x7A738)

    def test_native_lookup_callers_keep_zero_request_zero_and_respond_to_pedal(self):
        for rpm in (558, 600, 800, 1000, 1200, 2000, 2500):
            cpu = DBWMachine(self.image, rpm)
            for pedal in (0, 1, 4, 20, 100):
                cpu.put_float(0xFFFFB46C, pedal)
                cpu.invoke(0x2B35A, {(0xFFFFC3DC, 4)})
                torque = cpu.get_float(0xFFFFC3DC)
                self.assertEqual(torque == 0, pedal == 0)
                self.assertLessEqual(torque, 320)
                # Explicit normal-driver fixture. Native 2AF74 can arbitrate
                # C3DC into C3D4 with other requests/limits; it is not run here.
                cpu.put_float(0xFFFFC3D4, torque)
                cpu.invoke(0x2AF5C, {(0xFFFFC3D0, 4)})
                target = cpu.get_float(0xFFFFC3D0)
                self.assertEqual(target == 0, pedal == 0)
                self.assertGreaterEqual(target, 0)
                self.assertLessEqual(target, 84)

    def test_released_driver_request_does_not_zero_separate_idle_air(self):
        requests = []
        for correction in (0, 2, 6):
            cpu = DBWMachine(self.image)
            cpu.put_float(0xFFFFB46C, 0)
            cpu.invoke(0x2B35A, {(0xFFFFC3DC, 4)})
            self.assertEqual(cpu.get_float(0xFFFFC3DC), 0)
            cpu.put_float(0xFFFFC3D4, 0)  # Other torque requests inactive.
            cpu.invoke(0x2AF5C, {(0xFFFFC3D0, 4)})
            cpu.invoke(0x2ADEC, {(0xFFFFC2CC, 4)})
            cpu.put_float(0xFFFFC2C8, 20)  # Stale opening before pedal release.
            cpu.invoke(0x2AD6C, {(0xFFFFC2C8, 4)})
            self.assertEqual(cpu.get_float(0xFFFFC2C8), 0)
            cpu.put_float(0xFFFFC424, 7)
            cpu.put_float(0xFFFFC438, .666)
            cpu.put_float(0xFFFFC45C, correction)
            request = cpu.plate_request()
            requests.append(request)
            self.assertAlmostEqual(cpu.get_float(0xFFFFC2B8), cpu.get_float(0xFFFFC3F8))
        self.assertTrue(0 < requests[0] < requests[1] < requests[2])
        for actual, expected in zip(requests, (4.479, 5.611, 7.606)):
            self.assertAlmostEqual(actual, expected, delta=.001)

    def test_dashpot_hold_threshold_is_shared_but_decay_has_separate_control(self):
        # Sensitivity only: held RPM/MAP/gain state does not model an engine.
        # Each alternate calibration exists only in this local bytearray.
        variants = ((None, b'', (40, 40, 48)),
                    (0x79538, (76).to_bytes(2, 'big'), (78, 78, 86)),
                    (0x7963C, struct.pack('>f', .1), (40, 40, 88)))
        for address, data, expected in variants:
            image = bytearray(self.image)
            if address is not None:
                image[address:address + len(data)] = data
            cpu = HandoverMachine(bytes(image), rpm=558)
            for _ in range(16):
                cpu.release_step(20)
            samples = []
            for count in range(1, 105):
                air, flags = cpu.release_step(0)
                samples.append((count, air, bool(flags & 8)))
            observed = (next(k for k, air, on in samples if on),
                        next(k for k, air, on in samples if air < .665),
                        next(k for k, air, on in samples if air == 0))
            self.assertEqual(observed, expected, address)

    def test_raised_zero_request_table_cells_do_not_bypass_pedal_limit(self):
        # Reproduce the six cells in the separately supplied slight-dashpot
        # file in memory. Do not require or rewrite that external artifact.
        variant = bytearray(self.image)
        for row, raw in ((2, 220), (3, 528), (4, 881), (5, 1101), (6, 1321), (7, 1541)):
            address = 0x7A738 + 2*row*15
            variant[address:address+2] = raw.to_bytes(2, 'big')
        for rpm in (1000, 1200, 1400, 1600, 1800, 2000):
            outputs = []
            for image in (self.image, bytes(variant)):
                cpu = DBWMachine(image, rpm)
                cpu.put_float(0xFFFFB46C, 0)
                cpu.put_float(0xFFFFC3D4, 0)  # Other torque requests inactive.
                cpu.invoke(0x2AF5C, {(0xFFFFC3D0, 4)})
                mapped = cpu.get_float(0xFFFFC3D0)
                cpu.invoke(0x2ADEC, {(0xFFFFC2CC, 4)})
                cpu.put_float(0xFFFFC2C8, 20)
                cpu.invoke(0x2AD6C, {(0xFFFFC2C8, 4)})
                self.assertEqual(cpu.get_float(0xFFFFC2C8), 0)
                cpu.put_float(0xFFFFC424, 7)
                cpu.put_float(0xFFFFC438, .666)
                cpu.put_float(0xFFFFC45C, 2)
                outputs.append((mapped, cpu.plate_request()))
            self.assertEqual(outputs[0][0], 0)
            self.assertGreater(outputs[1][0], 0)  # The modified map is actually read.
            self.assertEqual(outputs[0][1], outputs[1][1])


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(DBWTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  DBW tables: {result.testsRun} execution test groups passed')
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
