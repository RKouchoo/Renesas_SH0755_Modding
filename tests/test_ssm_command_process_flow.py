#!/usr/bin/env python3
"""Execute SSM receive, command dispatch, getters/writers and response frames.

SCI1 receive/completion and matching transmit echoes are supplied events.
All CPU callees execute native instructions, including signed division,
standard parameter getters, reset writers and continuous-read reentry. This
does not model baud timing, interrupt arrival or the host's electrical link.
"""
import _test_paths
from itertools import product
import unittest
import struct
import xml.etree.ElementTree as ET

import logger_profiles as profiles
from test_retained_reset_process_flow import RetainedResetMachine, ROOT, RAM, HEADER
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_primary_fueling_execution import signed

FLAGS, RX_INDEX = RAM+0xC846, RAM+0xC7A9
SCR, TDR, SSR, RDR = (RAM+a for a in (0xF012, 0xF013, 0xF014, 0xF015))
# Protocol workspace only; the two special-decoder bytes are explicitly
# separate from the adjacent CFA0 injector inhibit byte.
PROTOCOL_WRITES = {(a, n) for a in range(RAM+0xC790, RAM+0xC850)
                   for n in (1, 2, 4) if a+n <= RAM+0xC850} | {
    (RAM+0xCFAC, 1), (RAM+0xCFB1, 1), (SCR, 1), (TDR, 1), (SSR, 1)}
EXPLICIT_RESET_WRITES = {(HEADER, 2), (RAM+0x8262, 1), (RAM+0xEC0A, 2)}


def packet(command, data):
    payload = bytes((command,))+data
    frame = bytes((0x80, 0x10, 0xF0, len(payload)))+payload
    return frame+bytes((sum(frame) & 255,))


def read_packet(addresses, continuous=1):
    return packet(0xA8, bytes((continuous,))+b''.join(
        a.to_bytes(3, 'big') for a in addresses))


def saved_queries(path):
    selected = {p.get('id') for p in ET.parse(path).getroot().findall('./parameters/parameter')
                if any(p.get(v) == 'selected' for v in ('livedata', 'dash', 'graph'))}
    assert selected == profiles.PROFILE_SELECTIONS[path]
    root = ET.parse(profiles.LOGGER_DEFINITION).getroot()
    definitions = {p.get('id'): p for q in ('./protocols/protocol/parameters/parameter',
                    './protocols/protocol/ecuparams/ecuparam') for p in root.findall(q)}
    queries = set()
    for key in selected:
        definition = definitions[key]
        query = []
        for a in definition.findall('./address') or definition.findall(
                './ecu[@id="3C5A387116"]/address'):
            start = int(a.text, 0)
            query.extend(range(start, start+int(a.get('length', '1'))))
        assert query
        queries.add(tuple(query))
    return [a for q in sorted(queries) for a in q]


class SSMCommandMachine(RetainedResetMachine):
    def __init__(self, image):
        self.wire = []
        super().__init__(image)
        for a in range(0xF010, 0xF017):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xEC0A, 0xA55A, 2)
        self.visited.clear()
        self.native_targets.clear()

    def write(self, address, value, size=4, record=False):
        if record and address == SSR and size == 1:
            old = self.read(address, 1)
            # CPU writes of one preserve existing status; they do not create
            # framing/overrun events. TEND is supplied with completion below.
            value = (value & old & 0xF8) | (old & 4) | (value & 3)
        super().write(address, value, size, record)
        if record and address == TDR and size == 1:
            self.wire.append(value & 255)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        # Renesas SH-1/SH-2/SH-DSP Software Manual, 6.1.17/19, pp159-163:
        # https://www.renesas.com/en/document/mah/sh-1sh-2sh-dsp-software-manual
        if op & 0xF00F == 0x2007:  # DIV0S Rm,Rn.
            q, flag_m = bool(self.r[n] & 0x80000000), bool(self.r[m] & 0x80000000)
            self.sr = (self.sr & ~0x300) | (int(q) << 8) | (int(flag_m) << 9)
            self.t = q != flag_m
        elif op & 0xF0FF == 0x4024:  # ROTCL Rn.
            value = self.r[n]
            self.r[n] = ((value << 1) | int(self.t)) & 0xFFFFFFFF
            self.t = bool(value & 0x80000000)
        elif op & 0xF00F == 0x3004:  # DIV1 Rm,Rn.
            old_q, flag_m = bool(self.sr & 0x100), bool(self.sr & 0x200)
            sign = bool(self.r[n] & 0x80000000)
            value = ((self.r[n] << 1) | int(self.t)) & 0xFFFFFFFF
            if old_q == flag_m:
                self.r[n] = (value-self.r[m]) & 0xFFFFFFFF
                carry = self.r[n] > value
            else:
                self.r[n] = (value+self.r[m]) & 0xFFFFFFFF
                carry = self.r[n] < value
            q = carry ^ sign ^ flag_m
            self.sr = (self.sr & ~0x100) | (int(q) << 8)
            self.t = q == flag_m
        elif op & 0xF00F == 0x300A:  # SUBC Rm,Rn.
            value = self.r[n]-self.r[m]-int(self.t)
            self.r[n], self.t = value & 0xFFFFFFFF, value < 0
        elif op & 0xF00F == 0x300E:  # ADDC Rm,Rn.
            value = self.r[n]+self.r[m]+int(self.t)
            self.r[n], self.t = value & 0xFFFFFFFF, value > 0xFFFFFFFF
        else:
            return super().step(in_delay)
        self.visited.add(pc)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def receive(self, value, extra=frozenset()):
        self.write(RDR, value, 1)
        self.write(SSR, 0xC4, 1)  # Explicit clean receive/transmit completion.
        self.execute(0x32BB4, PROTOCOL_WRITES | extra)

    def feed(self, frame):
        for value in frame:
            self.receive(value)

    def response(self, data_count, extra=frozenset()):
        start = len(self.wire)
        # Native 32B24 sends the staged first byte on its third tick.
        for _ in range(3):
            self.execute(0x32B24, PROTOCOL_WRITES | extra)
        assert len(self.wire) == start+1
        for _ in range(data_count+5):
            previous = len(self.wire)
            self.receive(self.wire[-1], extra)
            assert len(self.wire) == previous+1
        frame = bytes(self.wire[start:])
        self.receive(self.wire[-1], extra)  # Ack checksum; execute reentry/exit.
        assert len(self.wire) == start+data_count+6
        return frame


class SSMCommandProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        main = (ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2 = (ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images = {'main': main, 'v2': v2, 'captured': before_pump_scaling(v2)}
        for image in cls.images.values():
            for a, b in ((0x4280, 0x4334), (0x32894, 0x328AE),
                         (0x319E2, 0x319EC), (0x32B24, 0x337A8),
                         (0x474AE, 0x47720), (0x47A08, 0x47B0C),
                         (0x4B6FC, 0x4C37C)):
                assert image[a:b] == stock[a:b], hex(a)
            assert int.from_bytes(image[0x4B87C:0x4B880], 'big') == 0x319E2
            assert int.from_bytes(image[0x4BEBC:0x4BEC0], 'big') == 0x32894
            for a, b in ((0x3192A, 0x3198E), (0x319F2, 0x31A18),
                         (0xDFB4, 0xDFBE), (0xDFE4, 0xDFE8), (0x258C, 0x25BC)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_native_signed_division_used_for_request_counts_matches_integer_quotients(self):
        cpu = SSMCommandMachine(self.images['v2'])
        for dividend, divisor in product(range(-132, 133), (-7, -3, -1, 1, 3, 7)):
            cpu.original_r[0], cpu.original_r[1] = divisor & 0xFFFFFFFF, dividend & 0xFFFFFFFF
            cpu.execute(0x4280, set())
            expected = abs(dividend)//abs(divisor)
            if (dividend < 0) != (divisor < 0):
                expected = -expected
            self.assertEqual(signed(cpu.r[0], 32), expected)

    def test_all_saved_profiles_run_native_read_and_two_complete_continuous_responses(self):
        for image, path in product(self.images.values(), profiles.PROFILE_SELECTIONS):
            cpu = SSMCommandMachine(image)
            addresses = saved_queries(path)
            self.assertEqual(len(addresses), 43)
            retained = cpu.protected_bytes()
            raw_values = {a: cpu.read(0xFF000000+a, 1) for a in addresses if a & 0x800000}
            cpu.feed(read_packet(addresses))
            for _ in range(2):
                frame = cpu.response(len(addresses))
                self.assertEqual(frame[:5], bytes((0x80, 0xF0, 0x10, 44, 0xE8)))
                self.assertEqual(sum(frame[:-1]) & 255, frame[-1])
                for i, address in enumerate(addresses):
                    if address in raw_values:
                        self.assertEqual(frame[5+i], raw_values[address], hex(address))
                    elif address < 0x190:
                        self.assertIn(cpu.read(0x4B6FC+4*address, 4), cpu.visited)
            self.assertEqual(cpu.protected_bytes(), retained)
            self.assertFalse({0x336E6, 0x32894, 0xF5F6} & cpu.visited)
            self.assertTrue({0x32BB4, 0x32CA4, 0x474AE, 0x47A08, 0x32FEC,
                             0x32B24, 0x32DE8, 0x3322C, 0x33668, 0x4280} <= cpu.visited)

    def test_avcs_callbacks_and_profile_separate_upstream_demand_from_normal_output(self):
        for image in self.images.values():
            cpu = SSMCommandMachine(image)
            capability = cpu.read(0x4C458+14*4, 4)
            self.assertEqual(capability, 0x7BDB3)
            self.assertEqual(cpu.read(capability, 1) & 0xFC, 0xFC)
            for values, expected in (
                    ((12, 28, 40, 60, .32, .64), (62, 78, 102, 153, 10, 20)),
                    ((-50, 205, -10, 110, 0, 8.16), (0, 255, 0, 255, 0, 255))):
                for a, value in zip((0xC8C8, 0xC8CC, 0xC914, 0xC918, 0xB098, 0xB09C), values):
                    cpu.put_float(RAM+a, value)
                for index, entry, value in zip(range(0x3C, 0x42),
                        (0x3192A, 0x31938, 0x31946, 0x31954, 0x31962, 0x31978), expected):
                    self.assertEqual(cpu.read(0x4B6FC+4*index, 4), entry)
                    cpu.execute(entry, set())
                    self.assertEqual(cpu.r[0], value)
            # Deliberately disagree with the earlier C914/C918 demand: the
            # new channels must read the repaired 34BE4 output publications.
            cpu.put_float(RAM+0xC91C, 25)
            cpu.put_float(RAM+0xC920, 75)
            addresses = saved_queries(profiles.AVCS_PROFILE)
            self.assertEqual(len(addresses), 43)
            self.assertFalse({0x3E, 0x3F} & set(addresses))
            retained = cpu.protected_bytes()
            cpu.feed(read_packet(addresses))
            for _ in range(2):
                frame = cpu.response(len(addresses))
                self.assertEqual(sum(frame[:-1]) & 255, frame[-1])
                for base, expected in ((0xFFC91C, 25), (0xFFC920, 75)):
                    raw = bytes(frame[5+addresses.index(base+i)] for i in range(4))
                    self.assertEqual(struct.unpack('>f', raw)[0], expected)
            self.assertEqual(cpu.protected_bytes(), retained)
            self.assertFalse({0x336E6, 0x32894, 0xF5F6} & cpu.visited)

    def test_reading_reset_parameter_uses_getter_and_leaves_retained_bytes_unchanged(self):
        for image in self.images.values():
            cpu = SSMCommandMachine(image)
            cpu.write(RAM+0x8262, 0x4055, 2)
            before = cpu.protected_bytes()
            addresses = (0x60, 0xFF8000, 0xFF8001, 0xFF8262, 0xFF8263)
            cpu.feed(read_packet(addresses, continuous=0))
            frame = cpu.response(len(addresses))
            self.assertEqual(frame[5:-1], bytes.fromhex('40 aa 55 40 55'))
            self.assertEqual(cpu.protected_bytes(), before)
            self.assertIn(0x319E2, cpu.visited)
            self.assertNotIn(0x32894, cpu.visited)
            self.assertEqual(cpu.read(FLAGS, 1) & 0x60, 0)

    def test_explicit_b8_parameter_write_reaches_reset_handler_and_checks_complete_word(self):
        for image, low, value in product(self.images.values(), (0, 0x55), (0, 0x40, 0xAA, 0xFF)):
            cpu = SSMCommandMachine(image)
            cpu.write(RAM+0x8262, 0x4000 | low, 2)
            before = cpu.protected_bytes()
            cpu.feed(packet(0xB8, bytes((0, 0, 0x60, value))))
            frame = cpu.response(1, EXPLICIT_RESET_WRITES)
            result = value << 8 | low
            self.assertEqual(cpu.read(RAM+0x8262, 2), result)
            self.assertEqual(cpu.read(HEADER, 2), 0xAA55 if result == 0xAA55 else 0x55AA)
            self.assertEqual(frame[4:-1], bytes((0xF8, value)))
            self.assertTrue({0x336E6, 0x32894} <= cpu.visited)
            self.assertEqual(0xF5F6 in cpu.visited, result != 0xAA55)
            after = cpu.protected_bytes()
            self.assertTrue(all(before[i] == after[i] for i in range(len(before))
                                if i not in (0, 1, 0x262)))
            self.assertEqual(cpu.read(RAM+0xEC0A, 2), 0xA55A)

    def test_raw_b0_writes_to_retained_header_or_reset_word_are_blocked_by_native_address_check(self):
        for image, address in product(self.images.values(), (0xFF8000, 0xFF8262)):
            cpu = SSMCommandMachine(image)
            cpu.write(RAM+0x8262, 0x4055, 2)
            before = cpu.protected_bytes()
            cpu.feed(packet(0xB0, address.to_bytes(3, 'big')+b'\xAA'))
            frame = cpu.response(1, {(RAM+0xEC0A, 2)})
            self.assertEqual(frame[4], 0xF0)
            self.assertEqual(cpu.protected_bytes(), before)
            self.assertIn(0x336E6, cpu.visited)
            self.assertNotIn(0x32894, cpu.visited)

    def test_bad_request_checksum_and_unreachable_44_address_checksum_never_dispatch(self):
        for image, oversized in product(self.images.values(), (False, True)):
            cpu = SSMCommandMachine(image)
            before = cpu.protected_bytes()
            frame = bytearray(read_packet(range(0xFFB000, 0xFFB000+(44 if oversized else 43))))
            if not oversized:
                frame[-1] ^= 1
            cpu.feed(frame)
            self.assertFalse({0x32FEC, 0x3322C, 0x32894, 0xF5F6} & cpu.visited)
            self.assertEqual(cpu.wire, [])
            self.assertEqual(cpu.protected_bytes(), before)
            if oversized:
                self.assertEqual(cpu.read(RX_INDEX, 1), 137)


if __name__ == '__main__':
    unittest.main(verbosity=2)
