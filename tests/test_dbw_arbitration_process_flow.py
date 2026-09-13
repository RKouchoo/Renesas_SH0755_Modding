#!/usr/bin/env python3
"""Execute driver maps, native torque arbitration and final throttle selection.

Digital/received states, prior histories and learned offsets are explicit
fixtures. Native lookup and scalar helpers execute opcodes. This does not
recover unlogged vehicle states, model actuator motion or certify deadlines.
"""
import _test_paths
from itertools import product
import unittest

from test_iat_process_flow import IATProcessMachine
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_idle_air_request_execution import SUM_WRITES, REQUEST_WRITES
from test_idle_air_override_execution import (RECEIVE_GETTERS, OFF_WRITES,
                                             TIMER_WRITES, STOP_WRITES)

ROOT = _test_paths.ROOT
ARB_WRITES = {(0xFFFFC3E0, 1)} | {
    (a, 4) for a in (0xFFFFC3D4, 0xFFFFC3E4, 0xFFFFC3E8, 0xFFFFC3EC)
} | {(a, 1) for a in range(0xFFFFC3F0, 0xFFFFC3F6)}
RECEIVE_RESET_WRITES = {(0xFFFF0000+a, 4) for a in
                        (0xB214, 0xB218, 0xB210, 0xB238, 0xB20C, 0xB240)} | {
    (0xFFFF0000+a, 1) for a in (0xB234, 0xB235, 0xB236, 0xB23C)
}
CAN_RECEIVE_WRITES = RECEIVE_RESET_WRITES | {
    (0xFFFF0000+a, 1) for a in (*range(0xB21C, 0xB234), 0xB200,
                               *range(0xB244, 0xB24A), 0xB23D)
} | {(0xFFFFB208, 2), (0xFFFFB20A, 2), (0xFFFFE40E, 2)}


class DBWArbitrationMachine(IATProcessMachine):
    INSTRUCTION_LIMIT = 20000
    LOOKUPS = IATProcessMachine.LOOKUPS | RECEIVE_GETTERS | {
        0x2150, 0x26B0, 0x2858, 0x24FC, 0x19EC4, 0x18CF4, 0x18D1C, 0x18D78,
        0x651BA, 0x19D96, 0x19C68, 0x653BA, 0x2B8AC, 0x2B908, 0x1629A,
        0x1BFD4, 0x251C, 0x19C04, 0x2FB08, 0x30AC2, 0x1628C,
        0x1C082, 0x19CB8, 0x15AC4, 0x15AB0, 0x15A3A, 0x16270,
        0x1627E, 0x312E0, 0x4244, 0x36972, 0x2484, 0x18D30,
        0x1C074, 0x2450, 0x1A256,
    }

    def __init__(self, image, rpm=2800, pedal=70, speed=25, gear=2):
        super().__init__(image)
        # Explicit zero histories; no claim that a running capture had these.
        for a in range(0xFFFFC2B4, 0xFFFFC3F8):
            self.write(a, 0, 1)
        for a, value in ((0xB544, rpm), (0xB46C, pedal), (0xB470, pedal),
                         (0xB3AC, 85), (0xB538, speed), (0xB314, 60),
                         (0x80D8, 84), (0x80F0, 0), (0xC3F8, 4), (0xB47C, 0)):
            self.put_float(0xFFFF0000+a, value)
        for a in (0xB484, 0xB51A, 0xB51C, 0xB51E, 0xB385,
                  0xD26F, 0xD274, 0xC640, 0xC618, 0xC5E0, 0xC4D9):
            self.write(0xFFFF0000+a, 0, 1)
        self.write(0xFFFFCD48, gear, 1)
        self.write(0xFFFFAC08, round(4_000_000*20/rpm), 4)
        self.execute(0x142FA, RECEIVE_RESET_WRITES)
        self.execute(0x2B37E, ARB_WRITES)
        for a in range(0xFFFFC610, 0xFFFFC652):
            self.write(a, 0, 1)
        for a in (0x80D4, 0x80D5, 0x80D6, 0x8134, 0x814C,
                  0xB358, 0x80B0, 0x825C, 0xD25C):
            self.write(0xFFFF0000+a, 0, 1)
        self.write(0xFFFFB354, 0, 2)
        self.write(0xFFFFB51E, 0x10, 1)  # Native ignition-on qualifier.
        for a in range(0xFFFFC6F7, 0xFFFFC700):
            self.write(a, 0, 1)
        self.write(0xFFFFC6F7, 2, 1)
        self.write(0xFFFFC650, 0x80, 1)
        for a, value in ((0xABB4, 13.5), (0x8108, 40), (0x8080, 4),
                         (0xC6D0, 0), (0xC6E0, 0)):
            self.put_float(0xFFFF0000+a, value)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x000C:  # MOV.B @(R0,Rm),Rn; sign extend.
            value = self.load((self.r[0]+self.r[m]) & 0xFFFFFFFF, 1)
            self.r[n] = (value if value < 128 else value-256) & 0xFFFFFFFF
        elif op & 0xF00F == 0x6004:  # MOV.B @Rm+,Rn; sign extend.
            address = self.r[m]
            value = self.load(address, 1)
            self.r[n] = (value if value < 128 else value-256) & 0xFFFFFFFF
            if n != m:
                self.r[m] = (address+1) & 0xFFFFFFFF
        elif op & 0xF00F == 0x6002:  # MOV.L @Rm,Rn.
            self.r[n] = self.load(self.r[m], 4)
        elif op & 0xF000 == 0x1000:  # MOV.L Rm,@(disp,Rn).
            self.write(self.r[n]+(op & 15)*4, self.r[m], 4, record=True)
        elif op & 0xF0FF == 0x4001:  # SHLR Rn.
            self.t = bool(self.r[n] & 1)
            self.r[n] >>= 1
        elif op & 0xF0FF == 0x4010:  # DT Rn.
            self.r[n] = (self.r[n]-1) & 0xFFFFFFFF
            self.t = self.r[n] == 0
        elif op & 0xF00F == 0x6008:  # SWAP.B Rm,Rn; high word unchanged.
            value = self.r[m]
            self.r[n] = (value & 0xFFFF0000) | ((value & 255) << 8) | ((value >> 8) & 255)
        elif op & 0xF0FF == 0x4019:  # SHLR8 Rn; T unchanged.
            self.r[n] >>= 8
        elif op & 0xF0FF == 0x4018:  # SHLL8 Rn; T unchanged.
            self.r[n] = (self.r[n] << 8) & 0xFFFFFFFF
        elif op & 0xFF00 == 0xCA00:  # XOR #imm,R0.
            self.r[0] ^= op & 255
        elif op & 0xF00F == 0xF00B and n != 15:
            self.r[n] = (self.r[n]-4) & 0xFFFFFFFF
            self.write(self.r[n], self.fr[m], 4, record=True)
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1

    def driver_step(self):
        for entry, writes in ((0x2B35A, {(0xFFFFC3DC, 4)}),
                              (0x2B350, {(0xFFFFC3D8, 4)}),
                              (0x2AF74, ARB_WRITES),
                              (0x2AF5C, {(0xFFFFC3D0, 4)})):
            self.execute(entry, writes)
        return self.get_float(0xFFFFC3D0)

    def final_step(self):
        self.driver_step()
        for entry, writes in ((0x2ADEC, {(0xFFFFC2CC, 4)}),
                              (0x2AD6C, {(0xFFFFC2C8, 4)}),
                              (0x2AC16, SUM_WRITES),
                              (0x2ADF6, {(0xFFFFC2D4, 4), (0xFFFFC2F8, 2),
                                         (0xFFFFC3CC, 1)}),
                              (0x2ADCA, {(0xFFFFC2DE, 1)}),
                              (0x2AB06, REQUEST_WRITES),
                              (0x2F684, OFF_WRITES),
                              (0x2F8C0, {(0xFFFFC642, 2)}),
                              (0x2F914, {(0xFFFFC640, 1)}),
                              (0x2EFB8, TIMER_WRITES),
                              (0x2F03C, STOP_WRITES),
                              (0x2F390, {(0xFFFFC638, 1), (0xFFFFC610, 4),
                                         (0xFFFFC61A, 2), (0xFFFFC61C, 2)}),
                              (0x2F500, {(a, 4) for a in range(0xFFFFC620, 0xFFFFC638, 4)}
                                         | {(0xFFFFC616, 2)}),
                              (0x2F5E2, {(0xFFFFC618, 1)}),
                              (0x2F968, {(0xFFFFC64C, 1)}),
                              (0x2AAAC, {(0xFFFFC2B4, 4)})):
            self.execute(entry, writes)
        return self.get_float(0xFFFFC2B4)


class DBWReceiveMachine(DBWArbitrationMachine):
    """HCAN receive-complete is W1C; supplied mailbox data stays fixed.

    No CAN bus, reception timing or interrupt emulation. The CPU's descriptor
    copy, unsigned conversion, status validation and timeout code are native.
    RXPR semantics: SH7055S hardware manual section 16.2.9, page 537.
    """
    LOOKUPS = DBWArbitrationMachine.LOOKUPS | {
        0x19D88, 0x2078, 0x24DC, 0x13E08, 0xC9AA, 0xCC14, 0x25BC, 0x142FA,
        0xCA9C, 0xCA84,
    }

    def __init__(self, image):
        super().__init__(image)
        for a in range(0xFFFFB200, 0xFFFFB24A):
            self.write(a, 0, 1)
        self.write(0xFFFFB208, 0x00FF, 2)
        self.write(0xFFFFB20A, 0x00FF, 2)
        self.write(0xFFFFB1FC, 2, 1)
        self.write(0xFFFFB1FE, 0x00FF, 2)
        self.write(0xFFFFC778, 0, 1)
        self.write(0xFFFF0000 | self.read(0xCAEC, 2), 0, 1)
        self.write(0xFFFFDAE4, 0, 1)
        self.write(0xFFFFE40E, 0, 2)
        for a in (0xFFFFE4D8, 0xFFFFE500, 0xFFFFE4F0):
            for i in range(8):
                self.write(a+i, 0, 1)
        self.execute(0x142FA, RECEIVE_RESET_WRITES)

    def write(self, address, value, size=4, record=False):
        if record and address == 0xFFFFE40E:
            assert size == 2
            value = self.read(address, 2) & ~(value & 0xFFFF)
        return super().write(address, value, size, record)

    def receive(self, value=None):
        if value is not None:
            assert 0 <= value <= 255
            self.write(0xFFFFE500, value, 1)  # ID 421 descriptor, first byte.
            self.write(0xFFFFE40E, 4, 2)
        self.execute(0x13FE0, CAN_RECEIVE_WRITES)
        return self.get_float(0xFFFFB214)


class DBWArbitrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = [(ROOT/f).read_bytes() for f in
                      ('master_patch/D2WD610H_master_patch.bin',
                       'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        for image in cls.images:
            for a, b in ((0x2AAAC, 0x2B408), (0x142FA, 0x14374),
                         (0x2EFB8, 0x2F9B8), (0x79524, 0x7952A),
                         (0x795C4, 0x795F0), (0x10F06, 0x10F7E),
                         (0x110F8, 0x11148), (0x13E08, 0x14374),
                         (0xC9AA, 0xCAB2), (0xCAEC, 0xCAEE),
                         (0xCC14, 0xCC3E), (0x72CD8, 0x72CE8),
                         (0x4AFA4, 0x4AFC0), (0x4AFEC, 0x4B008),
                         (0x4B01C, 0x4B038)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_connected_normal_driver_has_no_rpm_window_cut(self):
        for image, rpm, pedal in product(self.images,
                                         (2500, 2800, 3000, 3200, 3500, 4144),
                                         (0, 10, 35, 70, 100)):
            cpu = DBWArbitrationMachine(image, rpm, pedal)
            for _ in range(8):
                angle = cpu.driver_step()
            self.assertTrue(0 <= angle <= 84, (rpm, pedal, angle))
            self.assertEqual(angle == 0, pedal == 0)
            self.assertAlmostEqual(cpu.get_float(0xFFFFC3DC),
                                   cpu.get_float(0xFFFFC3D4), delta=.0001)

    def test_native_final_composition_keeps_idle_term_and_releases_driver(self):
        for image in self.images:
            cpu = DBWArbitrationMachine(image)
            for _ in range(20):
                opening = cpu.final_step()
            self.assertGreater(opening, 40)
            cpu.put_float(0xFFFFB46C, 0)
            cpu.put_float(0xFFFFB470, 0)
            self.assertEqual(cpu.final_step(), 4)
            self.assertEqual(cpu.get_float(0xFFFFC2C8), 0)

    def test_received_limit_has_floor_fault_bypass_and_native_reset(self):
        for image, limit in product(self.images, (0, 20, 40, 80, 160, 240, 510)):
            cpu = DBWArbitrationMachine(image)
            cpu.put_float(0xFFFFB214, limit)
            for _ in range(8):
                angle = cpu.driver_step()
            requested = cpu.get_float(0xFFFFC3DC)
            self.assertAlmostEqual(cpu.get_float(0xFFFFC3D4),
                                   min(requested, max(40, limit)), delta=.0001)
            if limit <= 40:
                self.assertLess(angle, 10)
            cpu.write(0xFFFFD26F, 8, 1)  # Native 651BA returns 2.
            cpu.driver_step()
            self.assertAlmostEqual(cpu.get_float(0xFFFFC3D4), requested, delta=.0001)
            cpu.write(0xFFFFD26F, 0, 1)
            cpu.execute(0x142FA, RECEIVE_RESET_WRITES)
            self.assertEqual(cpu.get_float(0xFFFFB214), 510)
            cpu.driver_step()
            self.assertAlmostEqual(cpu.get_float(0xFFFFC3D4), requested, delta=.0001)

    def test_native_can_mailbox_limit_publication_unsigned_byte_and_timeout(self):
        for image, value in product(self.images, (0, 20, 40, 80, 120, 128, 200, 255)):
            cpu = DBWReceiveMachine(image)
            self.assertEqual(cpu.receive(value), 2*value)
            self.assertEqual(cpu.read(0xFFFFE40E, 2), 0)
            self.assertEqual(cpu.read(0xFFFFB224, 1), value)
            cpu.driver_step()
            self.assertAlmostEqual(cpu.get_float(0xFFFFC3D4),
                                   min(cpu.get_float(0xFFFFC3DC), max(40, 2*value)),
                                   delta=.0001)
            for _ in range(63):
                cpu.receive()
            self.assertEqual(cpu.get_float(0xFFFFB214), 510)
            cpu.driver_step()
            self.assertAlmostEqual(cpu.get_float(0xFFFFC3D4),
                                   cpu.get_float(0xFFFFC3DC), delta=.0001)

    def test_can_monitor_enable_fresh_data_and_latched_timeout_are_distinct(self):
        writes = {(0xFFFFB1FC, 1), (0xFFFFB1FE, 2), (0xFFFFB202, 2),
                  (0xFFFFB204, 1), (0xFFFFB206, 2)}
        for image in self.images:
            cpu = DBWReceiveMachine(image)
            cpu.write(0xFFFFB1FC, 0, 1)
            cpu.write(0xFFFFB202, 998, 2)
            cpu.execute(0x13E30, writes)
            self.assertEqual(cpu.read(0xFFFFB1FC, 1) & 2, 0)
            cpu.execute(0x13E30, writes)
            self.assertEqual(cpu.read(0xFFFFB1FC, 1) & 2, 2)
            # All three mailboxes remain fresh; the counter byte is held.
            for _ in range(70):
                cpu.write(0xFFFFE500, 20, 1)
                cpu.write(0xFFFFE40E, 0x2005, 2)
                cpu.execute(0x13FE0, CAN_RECEIVE_WRITES)
            self.assertEqual(cpu.get_float(0xFFFFB214), 40)
            self.assertEqual(cpu.read(0xFFFFB208, 2), 0x00FF)
            self.assertEqual(cpu.read(0xFFFFB20A, 2), 0x01FE)
            # Missing-message timeout resets the limit, but its status latches.
            for _ in range(63):
                cpu.receive()
            self.assertEqual(cpu.get_float(0xFFFFB214), 510)
            self.assertEqual(cpu.read(0xFFFFB208, 2), 0x01FE)
            # One new mailbox cannot defeat the other two expired counters.
            self.assertEqual(cpu.receive(120), 510)
            cpu.write(0xFFFFE40E, 0x2005, 2)
            cpu.execute(0x13FE0, CAN_RECEIVE_WRITES)
            self.assertEqual(cpu.get_float(0xFFFFB214), 240)
            self.assertEqual(cpu.read(0xFFFFB208, 2), 0x01FE)
            cpu.put_float(0xFFFFABB4, 10)
            cpu.execute(0x13E30, writes)
            self.assertEqual(cpu.read(0xFFFFB1FC, 1) & 2, 0)
            self.assertEqual(cpu.read(0xFFFFB202, 2), 0)

    def test_qualified_rate_latch_ramps_recovers_and_does_not_hold_release(self):
        for image, gear in product(self.images, (1, 2, 3, 4)):
            cpu = DBWArbitrationMachine(image, pedal=10, gear=gear)
            cpu.write(0xFFFFB51C, 1, 1)  # Explicit native digital qualifier.
            cpu.put_float(0xFFFFB314, 0)  # Explicit prior processed throttle.
            for _ in range(8):
                cpu.driver_step()
            self.assertEqual(cpu.read(0xFFFFC3E0, 1) & 1, 1)
            previous = cpu.get_float(0xFFFFC3D4)
            cpu.put_float(0xFFFFB46C, 70)
            cpu.put_float(0xFFFFB470, 70)
            cpu.driver_step()
            self.assertGreater(cpu.get_float(0xFFFFC3D4), previous)
            self.assertLess(cpu.get_float(0xFFFFC3D4), cpu.get_float(0xFFFFC3DC))
            for _ in range(80):
                current = cpu.get_float(0xFFFFC3D4)
                cpu.driver_step()
                self.assertGreaterEqual(cpu.get_float(0xFFFFC3D4), current)
            self.assertEqual(cpu.read(0xFFFFC3E0, 1) & 1, 0)
            self.assertAlmostEqual(cpu.get_float(0xFFFFC3D4),
                                   cpu.get_float(0xFFFFC3DC), delta=.0001)
            cpu.put_float(0xFFFFB46C, 0)
            cpu.put_float(0xFFFFB470, 0)
            self.assertEqual(cpu.driver_step(), 0)

    def test_native_override_order_clears_stale_shutdown_and_stop_requests(self):
        for image, rpm in product(self.images, (2500, 2800, 3000, 3200, 3500, 4144)):
            cpu = DBWArbitrationMachine(image, rpm)
            for _ in range(20):
                normal = cpu.final_step()
            cpu.write(0xFFFFC640, 1, 1)
            cpu.write(0xFFFFC618, 9, 1)
            cpu.put_float(0xFFFFC63C, 0)
            cpu.put_float(0xFFFFC610, 0)
            self.assertAlmostEqual(cpu.final_step(), normal, delta=.0001)
            self.assertEqual(cpu.read(0xFFFFC640, 1) & 1, 0)
            self.assertEqual(cpu.read(0xFFFFC618, 1) & 1, 0)
            # The separate tracking fault must still affect the final result.
            cpu.write(0xFFFFD274, 0x40, 1)
            self.assertLessEqual(cpu.final_step(), 4)
            cpu.write(0xFFFFD274, 0, 1)
            self.assertGreater(cpu.final_step(), 40)


if __name__ == '__main__':
    unittest.main(verbosity=2)
