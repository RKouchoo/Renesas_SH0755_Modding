#!/usr/bin/env python3
"""Execute retained throttle-link packet and receive-status logic offline.

Native code builds/validates forty-byte frames, filters received status bits,
and selects fault overrides. Transport hardware, the remote endpoint, learned
values and raw diagnostic producers are explicit boundaries. No ECU I/O or
firmware writes occur here; these fixtures do not reconstruct a vehicle log.
"""
from io import StringIO
from pathlib import Path
import random
import unittest

from test_idle_air_override_execution import OverrideMachine, FAULT_WRITES
from test_primary_fueling_execution import signed
from test_wideband_fuel_guard_execution import WIDEBAND_OUTPUTS

ROOT = Path(__file__).resolve().parent.parent
IMAGE = None
TX, RX = 0xFFFFC714, 0xFFFFC73C
PREREQUISITE_WRITES = {(a, 1) for a in (0xFFFFC6FE, 0xFFFFC6FF, 0xFFFFC700)}
TX_WRITES = {(TX + a, 2) for a in range(0, 0x18, 2)} | {
    (TX + a, 1) for a in range(0x18, 0x1E)} | {
    (TX + a, 2) for a in range(0x1E, 0x28, 2)}
RX_WRITES = {(a, 4) for a in range(0xFFFFC6D0, 0xFFFFC6E4, 4)} | {
    (a, 2) for a in range(0xFFFFC702, 0xFFFFC70A, 2)} | {
    (a, 1) for a in range(0xFFFFC6F7, 0xFFFFC6FE)} | {
    (a, 1) for a in range(0xFFFFC768, 0xFFFFC770)} | {
    (a, 1) for a in range(0xFFFFC6E8, 0xFFFFC6ED)} | {
    (0xFFFFC713, 1), (0xFFFFC6CC, 1), (0xFFFFC6CD, 1), (0xFFFFC6CE, 1)}
LOCAL_GETTERS = {0x1C0F4, 0x1C324, 0x1C2E8, 0x1C082, 0x1C2C8, 0x1C280,
                 0x1BFD4, 0x1BFE4, 0x1BFF2, 0x1C014, 0x1C022}
TX_GETTERS = {0x3B430, 0x15AD8, 0x2F9A0, 0x15A52, 0x2F636, 0x376EC,
              0x2F64A, 0x2F936}


class LinkMachine(OverrideMachine):
    # The prerequisite builder visits several native callback lists per call.
    INSTRUCTION_LIMIT = 8000

    def __init__(self, image):
        super().__init__(image)
        self.clear_fault_fixtures()
        for a in (0xFFFFCAAA, 0xFFFFCC00, 0xFFFFC64C, 0xFFFFD364,
                  0xFFFFC6F6, 0xFFFFC700, 0xFFFFC712,
                  0xFFFFC6CC, 0xFFFFC6CD, 0xFFFFC6CE):
            self.write(a, 0, 1)
        # Byte positions 19/1D are assembled by read-modify-write bit operations.
        for a in range(TX, TX + 40):
            self.write(a, 0xA5, 1)
        for a in range(0xFFFFC768, 0xFFFFC770):
            self.write(a, 0, 1)
        for a, value in ((0xC2B4, 6), (0xC2BC, -1), (0xB410, 13.5),
                         (0x80F0, 2), (0x80F8, 3), (0x8080, 4),
                         (0xC2C8, 5), (0x8110, 1.5)):
            self.put_float(0xFFFF0000 | a, value)
        self.write(0xFFFFAB08, 8000, 2)
        for a, value in ((0xC70A, 0x1234), (0xC70C, 0x5678),
                         (0xC70E, 0x9ABC), (0xC710, 0xDEF0)):
            self.write(0xFFFF0000 | a, value, 2)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF0FF == 0x0023:  # braf Rn, with a delay slot.
            assert not in_delay
            target = (pc + 4 + self.r[n]) & 0xFFFFFFFF
            self.pc += 2
            self.step(in_delay=True)
            self.pc = target
        elif op & 0xF0FF == 0x4008:  # shll2 Rn, T unchanged.
            self.r[n] = (self.r[n] << 2) & 0xFFFFFFFF
            self.pc += 2
        elif op & 0xF00F == 0x6007:  # not Rm,Rn.
            self.r[n] = (~self.r[m]) & 0xFFFFFFFF
            self.pc += 2
        elif op & 0xF00F == 0x200A:  # xor Rm,Rn.
            self.r[n] ^= self.r[m]
            self.pc += 2
        elif op & 0xF00F in (0x600E, 0x600F):  # exts.b/w Rm,Rn.
            self.r[n] = signed(self.r[m], 8 if op & 15 == 14 else 16) & 0xFFFFFFFF
            self.pc += 2
        else:
            return super().step(in_delay)
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def call_lookup(self, target):
        if target in LOCAL_GETTERS | TX_GETTERS | {
                0x3824C, 0x4711E, 0x56E64, 0x56F0C, 0x5742C,
                0x254C, 0x257C, 0x25BC, 0x30790, 0x30A2A, 0x2088, 0x2098}:
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def transmit(self):
        self.invoke(0x30328, TX_WRITES)
        return bytes(self.read(TX + i, 1) for i in range(40))

    def receive(self, frame):
        assert len(frame) == 40
        for i, value in enumerate(frame):
            self.write(RX + i, value, 1)
        self.invoke(0x30718, RX_WRITES)


def frame_with_status(status, header=0x5AA5):
    frame = bytearray(40)
    frame[:2] = header.to_bytes(2, 'big')
    frame[0x12:0x19] = status
    checksum = sum(int.from_bytes(frame[i:i+2], 'big') for i in range(0, 38, 2))
    frame[38:40] = (checksum & 65535).to_bytes(2, 'big')
    return frame


class LinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for a, b in ((0x2FFE4, 0x30A84), (0x254C, 0x258A), (0x25BC, 0x25CA),
                     (0x2088, 0x209C), (0x4711E, 0x47138),
                     (0x56E64, 0x56E96), (0x56EFC, 0x57430),
                     (0x579FC, 0x57C10), (0x75E02, 0x75E03),
                     (0xBECE, 0xC20C)):
            assert cls.image[a:b] == stock[a:b], hex(a)

    def test_transmit_layout_scaling_and_checksum(self):
        cpu = LinkMachine(self.image)
        cpu.write(0xFFFFB51E, 0x10, 1)
        packet = cpu.transmit()
        words = [int.from_bytes(packet[i:i+2], 'big') for i in range(0, 40, 2)]
        self.assertEqual(words[:12], [0xA55A, 197, 197, 0xFFE0, 44237,
                                     66, 98, 8000, 0x1234, 0x5678, 0x9ABC, 0xDEF0])
        self.assertEqual(packet[0x18:0x1E], bytes([0, 3, 0, 0, 0, 0]))
        self.assertEqual(words[15:19], [131, 164, 384, 2857])
        self.assertEqual(words[-1], sum(words[:-1]) & 65535)

    def test_transmit_does_not_read_repurposed_sensors_with_requests_fixed(self):
        cpu = LinkMachine(self.image)
        baseline = cpu.transmit()
        # Explicitly keep throttle/learning/fault inputs fixed. This tests the
        # serializer's dependencies, not independence of physical engine torque.
        sensor_ranges = ((0xAB06, 2, (0, 65535)), (0xB420, 4, (0, 500)),
                         (0xB428, 4, (0, 4)), (0xB438, 4, (0, 4)),
                         (0xB448, 4, (0, 500)), (0xB458, 4, (0, 500)),
                         (0xB45C, 4, (0, 500)), (0xABCC, 4, (0, 5)),
                         (0xABD0, 4, (0, 5))) + tuple(
            (a & 65535, 4, (0, 2)) for a in WIDEBAND_OUTPUTS)
        for a, size, values in sensor_ranges:
            for value in values:
                address = 0xFFFF0000 | a
                if size == 4:
                    cpu.put_float(address, value)
                else:
                    cpu.write(address, value, size)
                self.assertEqual(cpu.transmit(), baseline, (a, value))
                self.assertNotIn(address, cpu.reads)
        # Positive controls prevent an inert packet fixture passing this test.
        for address, size, value, offsets in (
                (0xC2B4, 4, 20, {2, 3, 4, 5, 38, 39}),
                (0xB544, 4, 2000, {36, 37, 38, 39}),
                (0xAB08, 2, 16000, {14, 15, 38, 39})):
            cpu = LinkMachine(self.image)
            before = cpu.transmit()
            if size == 4:
                cpu.put_float(0xFFFF0000 | address, value)
            else:
                cpu.write(0xFFFF0000 | address, value, size)
            after = cpu.transmit()
            changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
            self.assertTrue(changed)
            self.assertLessEqual(changed, offsets)

    def test_diagnostic_prerequisites_forward_faults_and_preserve_other_bits(self):
        cpu = LinkMachine(self.image)
        cpu.write(0xFFFFCAAA, 1, 1)
        for a in (0xFFFFC6FE, 0xFFFFC6FF, 0xFFFFC700):
            cpu.write(a, 255, 1)
        cpu.invoke(0x2FFE4, PREREQUISITE_WRITES)
        self.assertEqual(tuple(cpu.read(a, 1) for a in (0xFFFFC6FE, 0xFFFFC6FF, 0xFFFFC700)),
                         (0x0C, 0x08, 0xF8))
        cpu.write(0xFFFF8150, 1, 1)  # Raw local diagnostic, producer not simulated.
        cpu.invoke(0x301EE, {(0xFFFFC712, 1)})
        self.assertEqual(cpu.read(0xFFFFC712, 1), 3)
        cpu.invoke(0x2FFE4, PREREQUISITE_WRITES)
        packet = cpu.transmit()
        self.assertEqual(packet[0x18], 3)
        self.assertEqual(packet[0x1A:0x1D], bytes([0xCD, 0x08, 0xFC]))
        cpu.write(0xFFFF8150, 0, 1)
        cpu.invoke(0x301EE, {(0xFFFFC712, 1)})
        self.assertEqual(cpu.read(0xFFFFC712, 1), 0)

    def test_prerequisite_callbacks_read_enumerated_status_inputs(self):
        cpu = LinkMachine(self.image)
        cpu.write(0xFFFFCAAA, 1, 1)
        # Healthy status takes every applicable callback through its sentinel;
        # active faults return earlier. Assert the actual complete read set so
        # a new sensor dependency cannot hide behind unchanged output values.
        cpu.invoke(0x2FFE4, PREREQUISITE_WRITES)
        expected = {0x8134, 0x8138, 0x813C, 0x814C, 0x8150, 0x8194,
                    0x81A0, 0x81A8, 0x81AC, 0xC700, 0xCAAA} | set(range(0xC6F7, 0xC700))
        reads = {a for a in cpu.reads if a >= 0xFFFF0000 and not cpu.min_sp <= a < cpu.STACK}
        self.assertEqual(reads, {0xFFFF0000 | a for a in expected})
        # Local pedal-pair disagreement remains a separate prerequisite input.
        # It changes only C700 bit 2 in this no-other-fault fixture.
        cpu.write(0xFFFF8134, 1, 1)
        cpu.invoke(0x2FFE4, PREREQUISITE_WRITES)
        self.assertEqual(tuple(cpu.read(a, 1) for a in (0xFFFFC6FE, 0xFFFFC6FF, 0xFFFFC700)),
                         (0, 0, 4))

    def test_validated_status_needs_two_matching_accepted_frames_per_bit(self):
        cpu = LinkMachine(self.image)
        cpu.write(0xFFFFCAAA, 1, 1)  # Avoid separate C6FD mode-bit override.
        previous, latched = bytes(7), bytes(7)
        rng = random.Random(30790)
        for _ in range(24):
            new = bytes(rng.randrange(256) for _ in range(7))
            for _ in range(2):
                expected = bytes(((old & (value ^ prev)) | (prev & ~(value ^ prev))) & 255
                                 for value, prev, old in zip(new, previous, latched))
                cpu.receive(frame_with_status(new))
                latched = bytes(cpu.read(0xFFFFC6F7 + i, 1) for i in range(7))
                self.assertEqual(latched, expected)
                self.assertEqual(bytes(cpu.read(0xFFFFC768 + i, 1) for i in range(7)), new)
                self.assertEqual(cpu.read(0xFFFFC6CE, 1), 1)
                previous = new
            self.assertEqual(latched, new)

    def test_bad_header_or_checksum_cannot_update_receive_history(self):
        cpu = LinkMachine(self.image)
        cpu.write(0xFFFFCAAA, 1, 1)
        active = frame_with_status(bytes([8, 0, 0, 0, 0, 0, 0]))
        cpu.receive(active)
        bad_header = frame_with_status(bytes(7), header=0xA55A)
        bad_checksum = frame_with_status(bytes(7))
        bad_checksum[-1] ^= 1
        for frame, flags in ((bad_header, (0, 1)), (bad_checksum, (1, 0))):
            cpu.write(0xFFFFC6CE, 0, 1)  # Consumer-acknowledged fixture.
            cpu.receive(frame)
            self.assertEqual((cpu.read(0xFFFFC6CC, 1), cpu.read(0xFFFFC6CD, 1)), flags)
            self.assertEqual(cpu.read(0xFFFFC768, 1), 8)
            self.assertEqual(cpu.read(0xFFFFC6F7, 1), 0)
            self.assertEqual(cpu.read(0xFFFFC6CE, 1), 0)
        cpu.receive(active)
        self.assertEqual(cpu.read(0xFFFFC6F7, 1), 8)
        self.assertEqual(cpu.read(0xFFFFC6CE, 1), 1)
        cpu.receive(bad_checksum)
        self.assertEqual(cpu.read(0xFFFFC6CE, 1), 1)  # Validator does not clear an old acknowledgment.

    def test_received_faults_select_and_release_final_override(self):
        for offset, bit in ((0, 8), (2, 16), (2, 64), (3, 1), (3, 8), (4, 4), (5, 1)):
            cpu = LinkMachine(self.image)
            cpu.put_float(0xFFFFC2B8, 6)
            cpu.put_float(0xFFFFC2D4, 1.5)
            status = bytearray(7)
            status[offset] = bit
            for values, expected in ((status, 8), (status, 3.5), (bytes(7), 3.5), (bytes(7), 8)):
                cpu.receive(frame_with_status(values))
                cpu.invoke(0x64874, FAULT_WRITES)
                cpu.invoke(0x2AAAC, {(0xFFFFC2B4, 4)})
                self.assertEqual(cpu.get_float(0xFFFFC2B4), expected, (offset, bit, values))


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(LinkTests))
        if not result.wasSuccessful():
            raise AssertionError(report.getvalue())
        print(f'  Throttle link: {result.testsRun} execution test groups passed')
        return result.testsRun
    finally:
        IMAGE = previous


if __name__ == '__main__':
    unittest.main()
