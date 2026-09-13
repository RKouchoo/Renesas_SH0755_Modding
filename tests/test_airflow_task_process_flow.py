#!/usr/bin/env python3
"""Execute the full native airflow task around the SD hook and its resets.

Native tables, wrapper, upstream flags and downstream load conditioning run
from each image. Sensor/engine states and separate task invocations are
explicit inputs; there is no model of crank deadlines or physical airflow.
"""
import _test_paths
from itertools import product
import math
import unittest

from test_dbw_arbitration_process_flow import DBWArbitrationMachine
from test_primary_fueling_execution import signed
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT, RAM = _test_paths.ROOT, 0xFFFF0000
FLOW_FLOATS = {*range(0xB414, 0xB444, 4), 0xB448, 0xB44C, 0xB450, 0xB458, 0xB45C}
FLOW_WRITES = {(RAM+a, 4) for a in FLOW_FLOATS} | {(RAM+0xB444, 1)}
WRAPPER_WRITES = {(RAM+a, 4) for a in (0xB420, 0xB448, 0xB458, 0xB45C)}


class AirflowTaskMachine(DBWArbitrationMachine):
    LOOKUPS = DBWArbitrationMachine.LOOKUPS | {
        0x24AF2, 0x27088, 0x7E18C, 0x2684, 0x1C972, 0x20E0,
        0x2088, 0x2098, 0x80FE,
    }

    def __init__(self, image, rpm=2800, map_mmhg=820, iat=37, coolant=67):
        super().__init__(image, rpm=rpm)
        self.sr = 0x20
        for a in FLOW_FLOATS:
            self.put_float(RAM+a, 0)
        for a in (0xB444, 0xB454, 0xB52C, 0xB748):
            self.write(RAM+a, 0, 1)
        for a, value in ((0xABC4, map_mmhg), (0xB2A0, map_mmhg),
                         (0xB3B8, iat), (0xB3AC, coolant), (0xB550, rpm),
                         (0xB314, 60), (0xB318, 60), (0xB2C8, 60),
                         (0xB2CC, 0), (0xB878, 0), (0xB6D8, 0)):
            self.put_float(RAM+a, value)
        self.write(RAM+0xB688, 3000, 2)
        self.execute(0x1780A, FLOW_WRITES)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x0005:  # MOV.W Rm,@(R0,Rn).
            self.write((self.r[n]+self.r[0]) & 0xFFFFFFFF, self.r[m], 2, record=True)
        elif op & 0xF00F == 0x000D:  # MOV.W @(R0,Rm),Rn.
            self.r[n] = signed(self.load((self.r[0]+self.r[m]) & 0xFFFFFFFF, 2), 16) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x0002:  # STC SR,Rn.
            self.r[n] = (self.sr & ~1) | int(self.t)
        elif op & 0xF0FF == 0x400E:  # LDC Rn,SR.
            self.sr = self.r[n]
            self.t = bool(self.sr & 1)
        elif op & 0xF0FF == 0x4021:  # SHAR Rn.
            self.t = bool(self.r[n] & 1)
            self.r[n] = (signed(self.r[n], 32) >> 1) & 0xFFFFFFFF
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1

    def airflow_task(self):
        self.execute(0x172A4, FLOW_WRITES)
        return tuple(self.get_float(RAM+a) for a in (0xB420, 0xB428, 0xB438))


class AirflowTaskProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x172A4, 0x173FC), (0x17400, 0x1743C),
                         (0x17440, 0x17914), (0x73960, 0x739B0),
                         (0x737CE, 0x737D1), (0x5E9B4, 0x5E9FC),
                         (0x5EB6C, 0x5EBC0), (0x24AF2, 0x24B1C),
                         (0x1C920, 0x1CA38), (0x1A16E, 0x1A1FC),
                         (0x19F9C, 0x1A02C), (0x1A082, 0x1A0A8),
                         (0x76AE0, 0x76AF8), (0x76648, 0x76658),
                         (0x2088, 0x209C), (0x80FE, 0x8104),
                         (0x81E8, 0x81EC)):
                assert image[a:b] == stock[a:b], hex(a)
            assert image[0x173FC:0x17400] == bytes.fromhex('00027088')
            assert image[0x1743C:0x17440] == bytes.fromhex('0007e18c')

    def test_complete_task_publishes_current_sd_and_filters_load_in_each_lift_mode(self):
        for image, mode, rpm, pressure in product(self.images, (1, 3),
                                                (800, 2800, 3200, 3500), (150, 820)):
            cpu = AirflowTaskMachine(image, rpm, pressure)
            cpu.write(RAM+0xCD86, mode, 1)
            previous = cpu.get_float(RAM+0xB42C)
            for _ in range(4):
                airflow, raw, load = cpu.airflow_task()
                self.assertGreater(airflow, 0)
                self.assertAlmostEqual(raw, min(airflow*60/rpm, 4), delta=.000001)
                self.assertAlmostEqual(cpu.get_float(RAM+0xB42C),
                                       raw+(previous-raw)*.94, delta=.000001)
                self.assertEqual(cpu.get_float(RAM+0xB434), 1)
                self.assertAlmostEqual(load, cpu.get_float(RAM+0xB42C), delta=.000001)
                self.assertEqual(cpu.read(RAM+0xB444, 1) & 0xA0, 0)
                for a in (0xB448, 0xB458, 0xB45C):
                    self.assertEqual(cpu.get_float(RAM+a), airflow)
                previous = cpu.get_float(RAM+0xB42C)

    def test_obsolete_maf_histories_and_fault_do_not_override_final_sd_or_rearm_load_latch(self):
        for image in self.images:
            reference = AirflowTaskMachine(image).airflow_task()
            for stale, flags, fault in product((0, 500), (0, 0x20, 0x40, 0x80, 0xFF), (0, 0x40)):
                cpu = AirflowTaskMachine(image)
                for a in (0xABE4, 0xB448, 0xB458, 0xB45C):
                    cpu.put_float(RAM+a, stale)
                cpu.write(RAM+0xB444, flags, 1)
                cpu.write(RAM+0xD26F, fault, 1)
                actual = cpu.airflow_task()
                self.assertEqual(actual, reference)
                self.assertEqual(cpu.read(RAM+0xB444, 1) & 0xA0, 0)
                self.assertEqual(cpu.read(RAM+0xB444, 1) & 31, flags & 31)
                self.assertNotIn(0x65168, cpu.entered)
                self.assertNotIn(0x17726, cpu.entered)

    def test_native_history_snapshot_precedes_wrapper_and_slow_filter_is_separate(self):
        for image in self.images:
            cpu = AirflowTaskMachine(image)
            cpu.put_float(RAM+0xB448, 31)
            cpu.put_float(RAM+0xB458, 20)
            cpu.put_float(RAM+0xB45C, 40)
            airflow, _, _ = cpu.airflow_task()
            self.assertEqual(cpu.array(RAM+0xB414, 3), [20, 40, 30])
            cpu.airflow_task()
            self.assertEqual(cpu.array(RAM+0xB414, 3), [airflow]*3)
            old = cpu.get_float(RAM+0xB424)
            alpha = cpu.get_float(0x73964)
            cpu.execute(0x177BE, {(RAM+0xB424, 4)})
            self.assertAlmostEqual(cpu.get_float(RAM+0xB424),
                                   old+(airflow-old)*alpha, delta=.000001)
            self.assertNotEqual(alpha, cpu.get_float(0x73968))
            cpu.write(RAM+0xB444, 128, 1)
            cpu.execute(0x177DC, {(RAM+0xB454, 1)})
            self.assertEqual(cpu.read(RAM+0xB454, 1), 0)
            cpu.write(RAM+0xB444, 0, 1)
            cpu.execute(0x177DC, {(RAM+0xB454, 1)})
            self.assertEqual(cpu.read(RAM+0xB454, 1), 1)

    def test_stop_and_crank_selectors_retain_native_load_initialization(self):
        for image in self.images:
            cpu = AirflowTaskMachine(image)
            initial_load = cpu.get_float(RAM+0xB438)
            initial_airflow = cpu.get_float(RAM+0xB420)
            cpu.airflow_task()
            current = cpu.get_float(RAM+0xB420)
            cpu.write(RAM+0xB52C, 128, 1)  # Explicit engine-timeout boundary.
            cpu.execute(0x1785C, FLOW_WRITES)
            self.assertEqual(cpu.get_float(RAM+0xB420), initial_airflow)
            self.assertEqual(cpu.get_float(RAM+0xB438), initial_load)
            # Stopped reset does not rewrite the three synthetic input/history
            # publications; the next complete SD task owns them again.
            self.assertEqual(cpu.get_float(RAM+0xB448), current)
            cpu.write(RAM+0xB52C, 0, 1)
            cpu.write(RAM+0xB748, 128, 1)  # Native crank selector.
            self.assertEqual(cpu.airflow_task()[2], initial_load)
            cpu.write(RAM+0xB748, 0, 1)
            self.assertGreater(cpu.airflow_task()[2], initial_load)
            old_raw = cpu.get_float(RAM+0xB428)
            cpu.put_float(RAM+0xB544, 0)
            airflow, raw, _ = cpu.airflow_task()
            self.assertEqual((airflow, raw), (0, old_raw))

    def test_full_task_fault_fallback_and_nonfinite_obsolete_histories(self):
        # Native temperature/old-airflow lookups run before the SD hook. Run
        # through them instead of testing only the wrapper's validity checks.
        # This value model does not model FPSCR sticky flags or FPU latency.
        for index, image in enumerate(self.images):
            expected = 500 if index == 0 else 12
            for a, values in ((0xABC4, (0, 1601, math.nan, math.inf)),
                              (0xB3B8, (-51, 151, math.nan, math.inf))):
                for value in values:
                    cpu = AirflowTaskMachine(image)
                    cpu.put_float(RAM+a, value)
                    airflow, raw, load = cpu.airflow_task()
                    self.assertEqual(airflow, expected)
                    self.assertAlmostEqual(raw, min(expected*60/2800, 4), delta=.000001)
                    self.assertTrue(math.isfinite(load))
            reference = AirflowTaskMachine(image).airflow_task()
            for a, value in product((0xB448, 0xB458, 0xB45C),
                                     (math.nan, math.inf, -math.inf)):
                cpu = AirflowTaskMachine(image)
                cpu.put_float(RAM+a, value)
                self.assertEqual(cpu.airflow_task(), reference)

    def test_native_crank_producer_phase_hysteresis_and_event_delay(self):
        writes = {(RAM+a, 4) for a in (0xB784, 0xB788)} | {
            (RAM+a, 1) for a in (0xB796, 0xB797, 0xB748)}
        for image in self.images:
            cpu = AirflowTaskMachine(image)
            cpu.write(RAM+0xC0AC, 0, 4)
            cpu.write(RAM+0xB797, 1, 1)
            cpu.write(RAM+0xB748, 0xC5, 1)
            for phase in range(24):
                cpu.original_r[4] = phase
                cpu.execute(0x1C920, writes)
                self.assertEqual(cpu.read(RAM+0xB748, 1), 5)
                self.assertEqual(bool(set(cpu.writes) & writes), phase % 4 == 0)
            self.assertEqual(cpu.get_float(RAM+0xB784), 500)
            self.assertEqual(cpu.get_float(RAM+0xB788), 300)
            self.assertEqual(cpu.read(RAM+0xB796, 1), 0)
            # Enter below 301, hold in the band, leave strictly above 500.
            for rpm, state in ((300, 1), (301, 1), (500, 1), (501, 0),
                               (500, 0), (301, 0), (300, 1), (2800, 0), (3500, 0)):
                cpu.put_float(RAM+0xB544, rpm)
                cpu.execute(0x1C972, writes)
                self.assertEqual(cpu.read(RAM+0xB748, 1), 5 | (state << 7))
            cpu.put_float(RAM+0xB3AC, 20)
            for events, state in ((0, 1), (9, 1), (10, 0)):
                cpu.write(RAM+0xC0AC, events, 4)
                cpu.execute(0x1C972, writes)
                self.assertEqual(cpu.read(RAM+0xB796, 1), 10)
                self.assertEqual(cpu.read(RAM+0xB748, 1), 5 | (state << 7))

    def test_engine_timeout_and_crank_event_publishers_preserve_other_state_bits(self):
        # AC0C is the native event-timeout result, an explicit hardware-facing
        # boundary here. Execute both publishers and their protected sections.
        for image in self.images:
            cpu = AirflowTaskMachine(image)
            reset_target = cpu.read(0x81E8, 4)
            for timeout, original in product((0, 1), (0, 0x40, 0x7F, 0xFF)):
                cpu.write(RAM+0xAC0C, timeout, 1)
                cpu.write(RAM+0xB52C, original, 1)
                cpu.write(reset_target, 7, 1)
                cpu.execute(0x1A16E, {(RAM+0xB52C, 1), (reset_target, 1)})
                expected = (original & 0x3F) | 0x80 if timeout else original & 0x7F
                self.assertEqual(cpu.read(RAM+0xB52C, 1), expected)
                self.assertEqual(cpu.read(reset_target, 1), 0 if timeout else 7)
                self.assertEqual(cpu.sr & 0xF0, 0x20)
            for phase in range(24):
                cpu.write(RAM+0xB52C, 0xFF, 1)
                cpu.write(RAM+0xAC04, 4000, 4)
                cpu.original_r[4] = phase
                cpu.execute(0x19F9C, {(RAM+0xB52C, 1), (RAM+0xB528, 1),
                                      (RAM+0xB529, 1), (RAM+0xB530, 4)})
                self.assertEqual(cpu.read(RAM+0xB52C, 1), 0x7F)
                self.assertEqual(cpu.read(RAM+0xB528, 1), phase)
                self.assertEqual(cpu.read(RAM+0xB529, 1), phase % 4)
                self.assertEqual(cpu.get_float(RAM+0xB530), 1000)
                self.assertEqual(cpu.sr & 0xF0, 0x20)


if __name__ == '__main__':
    unittest.main(verbosity=2)
