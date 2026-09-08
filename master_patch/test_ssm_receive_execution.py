#!/usr/bin/env python3
"""Execute stock SSM byte reception to establish its request-size boundary.

32CA4 and its 2534 saturating-add helper execute ROM instructions. UART input
is a byte fixture; 474AE supplies normal diagnostic mode. Accepted-command
decode 32FEC and transmit setup 32F74 are recorded boundaries, not UART I/O.
"""
from io import StringIO
from pathlib import Path
import sys
import unittest

from test_injector_scheduler_execution import SchedulerMachine, ROOT
import logger_profiles as profiles

IMAGE = None
RECEIVER = 0x32CA4
RX_BYTE = 0xFFFFC7A4
RX_INDEX = 0xFFFFC7A9
RX_SUM = 0xFFFFC7AA
RX_BUFFER = 0xFFFFC7B4
FLAGS = 0xFFFFC846
WRITES = {(a, 1) for a in (RX_INDEX, RX_SUM, 0xFFFFC7AC, FLAGS + 1,
                           0xFFFFC840, *range(RX_BUFFER, RX_BUFFER + 138))}


def request(count):
    # Distinct read addresses keep this packet independent of host deduplication.
    data = b''.join((0xFFB000 + i).to_bytes(3, 'big') for i in range(count))
    packet = bytes((0x80, 0x10, 0xF0, 2 + len(data), 0xA8, 1)) + data
    return packet + bytes((sum(packet) & 255,))


class ReceiveMachine(SchedulerMachine):
    def __init__(self, image):
        super().__init__(image)
        self.accepted = []
        self.transmit_setups = 0
        for a in range(0xFFFFC7A4, FLAGS + 2):
            self.write(a, 0, 1)

    def call_lookup(self, target):
        if target == 0x2534:
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        elif target in (0x474AE, 0x32FEC, 0x32F74):
            if target == 0x32FEC:
                length = self.read(RX_BUFFER + 3, 1)
                self.accepted.append(bytes(self.read(RX_BUFFER + i, 1)
                                           for i in range(length + 4)))
            elif target == 0x32F74:
                self.transmit_setups += 1
            self.poison_scratch()
            self.r[0] = 0
        else:
            super().call_lookup(target)

    def feed(self, packet):
        for byte in packet:
            self.write(RX_BYTE, byte, 1)
            self.invoke(RECEIVER, WRITES)


class SSMReceiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (ROOT / 'master_patch/D2WD610H_master_patch.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x2534, 0x254C), (0x32CA4, 0x32ECC)):
            assert cls.image[start:end] == stock[start:end]
        assert cls.image[0x32D90:0x32D92] == b'\x00\x89'

    def test_native_receiver_accepts_requests_through_43_addresses(self):
        for count in (1, 21, 40, 42, 43):
            cpu = ReceiveMachine(self.image)
            packet = request(count)
            cpu.feed(packet)
            self.assertEqual(cpu.accepted, [packet[:-1]])
            self.assertEqual(cpu.transmit_setups, 1)
            self.assertEqual(cpu.read(RX_INDEX, 1), 0)

    def test_native_receiver_cannot_reach_oversized_request_checksum(self):
        for count in (44, 79, 81, 83, 84):
            cpu = ReceiveMachine(self.image)
            cpu.feed(request(count))
            self.assertEqual(cpu.accepted, [])
            self.assertEqual(cpu.transmit_setups, 0)
            self.assertEqual(cpu.read(RX_INDEX, 1), 137)
            with self.assertRaisesRegex(ValueError, 'native receive index stops at 137'):
                profiles.request_sizes(count)

    def test_bad_checksum_or_destination_is_rejected(self):
        for wrong_header in (False, True):
            packet = bytearray(request(43))
            if wrong_header:
                packet[1] = 0x11
                packet[-1] = sum(packet[:-1]) & 255
            else:
                packet[-1] ^= 1
            cpu = ReceiveMachine(self.image)
            cpu.feed(packet)
            self.assertEqual(cpu.accepted, [])


def verify_execution(image):
    global IMAGE
    previous, IMAGE = IMAGE, image
    try:
        report = StringIO()
        result = unittest.TextTestRunner(stream=report).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SSMReceiveTests))
        if not result.wasSuccessful():
            raise SystemExit(report.getvalue())
        print(f'  SSM receive: {result.testsRun} execution test groups passed')
    finally:
        IMAGE = previous


if __name__ == '__main__':
    if len(sys.argv) > 1:
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
