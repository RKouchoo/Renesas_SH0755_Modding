#!/usr/bin/env python3
"""Execute AVCS duty feedback and its native timer publication.

Raw OCV-current ADC values, controller enable states and timer cycle matches
are supplied boundaries. No cam motion, oil pressure or engine torque is
simulated. The old image's removed tasks are exercised through its pointers.
"""
import _test_paths
import unittest

from test_avcs_target_process_flow import AVCSTargetMachine, RAM, ROOT
from test_primary_fueling_execution import signed
from test_runtime_rom_checksum_execution import before_pump_scaling
import fueling_safety_component as safety
import wideband_component as wideband

CURRENT_WRITES = {(RAM+0xB094, 2), (RAM+0xB096, 2),
                  (RAM+0xB098, 4), (RAM+0xB09C, 4)}
FEEDBACK_WRITES = {(RAM+a, 4) for a in range(0xC85C, 0xC894, 4)}
OUTPUT_WRITES = {(RAM+a, 4) for a in (0xC91C, 0xC920, 0xB0A0, 0xB0A4)} | {
    (RAM+0xF510, 2), (RAM+0xF512, 2)}
DEVICE_WRITES = OUTPUT_WRITES | CURRENT_WRITES | {
    (RAM+a, 1) for a in range(0xB0A8, 0xB0B0)} | {(RAM+0xF400, 1)} | {
    (RAM+a, 2) for a in (0xAB8C, 0xAB8E, 0xF508, 0xF50A,
                         0xF500, 0xF502, 0xF518, 0xF51A)}
DUTY_WRITES = DEVICE_WRITES | {(RAM+a, 4) for a in (0xC914, 0xC918)} | {
    (RAM+a, 1) for a in (0xC929, 0xC92A, 0xC92B, 0xC928, 0xC895)}
INIT_WRITES = {(RAM+a, 4) for a in (0xC85C, 0xC860)} | {
    (safety.LEAN_STATE_RAM, 4), (safety.LEAN_COUNTER_RAM, 4)}


class AVCSActuatorMachine(AVCSTargetMachine):
    LOOKUPS = AVCSTargetMachine.LOOKUPS | {
        0x19C18, 0x650D4, 0x64F90, 0x65244, 0xDF00, 0xE290, 0x2390,
        0x651A6, 0xDF1E, 0xDF6E, 0xDFAC, 0x33FE8, 0x33FF2, 0xDFB4,
        0x33B12, 0x33AAC, 0x33970, 0x34BE4, 0x66C2, 0xE0D0, 0xE174,
        0x33964,
        0xB5AC, 0x49486,
    }

    def __init__(self, image, rpm=2800):
        super().__init__(image, rpm)
        for a in range(0xC85C, 0xC894):
            self.write(RAM+a, 0, 1)
        for a in range(0xB094, 0xB0B0):
            self.write(RAM+a, 0, 1)
        for a in (0xB51C, 0xB51E, 0xD26C, 0xD26D, 0xD272):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xB51D, 0x40, 1)
        self.write(RAM+0xAB20, 20000, 2)
        self.write(RAM+0xAB0C, 21000, 2)
        self.write(RAM+0xF400, 0x90, 1)
        self.execute(0xDFE8, DEVICE_WRITES)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x300D:
            value = signed(self.r[n], 32)*signed(self.r[m], 32)
            self.mach, self.macl = (value >> 32) & 0xFFFFFFFF, value & 0xFFFFFFFF
        elif op & 0xF0FF == 0x000A:
            self.r[n] = self.mach
        elif op & 0xF0FF == 0x400A:
            self.mach = self.r[n]
        elif op & 0xF0FF == 0x401A:
            self.macl = self.r[n]
        elif op & 0xF0FF == 0x4025:
            value, old_t = self.r[n], int(self.t)
            self.r[n], self.t = (value >> 1) | (old_t << 31), bool(value & 1)
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1

    def output(self):
        self.execute(self.read(0x11494, 4), OUTPUT_WRITES)
        return self.read(RAM+0xF510, 2), self.read(RAM+0xF512, 2)

    def cycle_match(self):
        # SH7055S manual 11.2.22--24: cycle compare transfers BFR to DTR.
        for buffer, duty in ((0xF510, 0xF518), (0xF512, 0xF51A)):
            self.write(RAM+duty, self.read(RAM+buffer, 2), 2)


class AVCSActuatorProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.captured = before_pump_scaling(cls.images[1])

    def test_captured_bypass_removes_hardware_command_despite_nonzero_cam_duty(self):
        for image in (self.captured,):
            cpu = AVCSActuatorMachine(image)
            cpu.put_float(RAM+0xC914, 40)
            cpu.put_float(RAM+0xC918, 45)
            self.assertEqual(cpu.output(), (0, 0))
            self.assertNotIn(0xDF00, cpu.entered)
            cpu.cycle_match()
            self.assertEqual((cpu.read(RAM+0xF518, 2), cpu.read(RAM+0xF51A, 2)), (0, 0))
        cpu = AVCSActuatorMachine(self.stock)
        cpu.execute(0x33964, FEEDBACK_WRITES)
        cpu.put_float(RAM+0xC914, 40)
        cpu.put_float(RAM+0xC918, 45)
        result = cpu.output()
        self.assertGreater(result[0], 0)
        self.assertGreater(result[1], result[0])
        self.assertEqual(cpu.entered.count(0xDF00), 2)
        cpu.cycle_match()
        self.assertEqual((cpu.read(RAM+0xF518, 2), cpu.read(RAM+0xF51A, 2)), result)

    def test_rolling_images_preserve_native_init_and_connected_control_output(self):
        for image in self.images:
            for rpm in (2500, 2800, 3000, 3200, 3500, 4144):
                for mode in (1, 3):
                    cpu = AVCSActuatorMachine(image, rpm)
                    cpu.execute(cpu.read(safety.LEAN_STATE_INIT_TASK_PTR, 4), INIT_WRITES)
                    self.assertEqual(cpu.array(RAM+0xC85C, 2), [1, 1])
                    self.assertEqual(cpu.read(safety.LEAN_STATE_RAM, 4), 0)
                    self.assertEqual(cpu.read(safety.LEAN_COUNTER_RAM, 4), 0)
                    cpu.write(RAM+0xCD86, mode, 1)
                    for _ in range(3):
                        cpu.airflow_task()
                    cpu.state()
                    self.assertGreater(cpu.targets()[0], 0)
                    # Hydraulic position/controller eligibility are explicit
                    # supplied boundaries; native duty selection runs below.
                    cpu.write(RAM+0xC948, 1, 1)
                    cpu.execute(0x34A1E, DUTY_WRITES)
                    self.assertEqual(cpu.read(RAM+0xC929, 1), 5)
                    self.assertEqual(cpu.array(RAM+0xC914, 2), [40, 40])
                    current = cpu.array(RAM+0xB098, 2)
                    for _ in range(5):
                        cpu.update_wideband(26000)
                        for pointer in (0x11488, 0x1148C, 0x11490):
                            cpu.execute(cpu.read(pointer, 4), FEEDBACK_WRITES)
                        result = cpu.output()
                        self.assertGreater(result[0], 0)
                        self.assertGreater(result[1], 0)
                        for buffer, fraction, period in ((0xF510, 0xB0A0, 0xAB8C),
                                                          (0xF512, 0xB0A4, 0xAB8E)):
                            q16 = int(cpu.get_float(RAM+fraction)*65536)
                            self.assertEqual(cpu.read(RAM+buffer, 2),
                                             q16*cpu.read(RAM+period, 2) >> 16)
                        self.assertEqual(cpu.array(RAM+0xB098, 2), current)
                        self.assertEqual(cpu.sr & 0xF0, 0x20)

    def test_restoring_only_output_pointer_leaves_zero_integrator_and_broken_output(self):
        partial = bytearray(self.captured)
        partial[0x11494:0x11498] = self.stock[0x11494:0x11498]
        cpu = AVCSActuatorMachine(bytes(partial))
        cpu.execute(0x7EBA0, {(RAM+0xC85C, 4), (RAM+0xC860, 4)})
        cpu.put_float(RAM+0xC914, 40)
        cpu.put_float(RAM+0xC918, 45)
        self.assertEqual(cpu.output(), (0, 0))
        self.assertEqual(cpu.entered.count(0xDF00), 2)

    def test_native_fault_and_enable_gates_zero_output_then_recover(self):
        for image in self.images:
            for address, mask in ((0xB748, 128), (0xB51C, 8),
                                  (0xD26D, 2), (0xD26C, 64), (0xD272, 2),
                                  (0xB51D, 64), (0xCC4C, 64)):
                cpu = AVCSActuatorMachine(image)
                cpu.execute(cpu.read(safety.LEAN_STATE_INIT_TASK_PTR, 4), INIT_WRITES)
                cpu.put_float(RAM+0xC914, 40)
                cpu.put_float(RAM+0xC918, 45)
                expected = cpu.output()
                old = cpu.read(RAM+address, 1)
                cpu.write(RAM+address, old ^ mask, 1)
                self.assertEqual(cpu.output(), (0, 0), hex(address))
                cpu.write(RAM+address, old, 1)
                self.assertEqual(cpu.output(), expected)

    def test_override_defers_normal_commands_and_restores_latest_value_on_release(self):
        for image in self.images:
            cpu = AVCSActuatorMachine(image)
            cpu.execute(cpu.read(safety.LEAN_STATE_INIT_TASK_PTR, 4), INIT_WRITES)
            cpu.put_float(RAM+0xC914, 40)
            cpu.put_float(RAM+0xC918, 45)
            before = cpu.output()
            cpu.original_r[4] = 0
            cpu.execute(0xDF1E, DEVICE_WRITES)
            override = cpu.read(RAM+0xF510, 2)
            self.assertGreater(override, before[0])
            cpu.put_float(RAM+0xC914, 50)
            self.assertEqual(cpu.output()[0], override)
            self.assertEqual(cpu.get_float(RAM+0xB0A0), .5)
            cpu.original_r[4] = 0
            cpu.execute(0xDF6E, DEVICE_WRITES)
            self.assertEqual(cpu.read(RAM+0xF510, 2), cpu.read(RAM+0xAB8C, 2)//2)
            self.assertEqual(cpu.read(RAM+0xB0AE, 1), 0)

    def test_retained_front_initialization_and_adc_handoff_do_not_own_lean_scratch(self):
        from test_adc_handoff_process_flow import ADCHandoffMachine
        init_writes = {(RAM+a, 4) for a in (*range(0xAE60, 0xAE80, 4),
                                           0xAE8C, 0xAE90, 0xAEB4, 0xAEB8)} | {
            (RAM+a, 1) for a in (0xAE80, 0xAE81, 0xAE82, 0xAE83,
                *range(0xAEC8, 0xAED3), 0xF45A, 0xF628)} | {
            (RAM+a, 2) for a in (0xAEBC, 0xAEBE, 0xF462, 0xF632,
                                 0xF464, 0xF630, 0xF66C)}
        for image in self.images:
            cpu = AVCSActuatorMachine(image)
            for a, size in init_writes:
                cpu.write(a, 0, size)
            for a in range(0x803C, 0x804C, 2):
                cpu.write(RAM+a, 0, 2)  # Explicit invalid records -> native zero default.
            cpu.write(safety.LEAN_COUNTER_RAM, 0x12345678, 4)
            cpu.write(safety.LEAN_STATE_RAM, 0x31415926, 4)
            cpu.execute(0xB49A, init_writes)
            self.assertEqual(cpu.read(safety.LEAN_COUNTER_RAM, 4), 0x12345678)
            self.assertEqual(cpu.read(safety.LEAN_STATE_RAM, 4), 0x31415926)
            self.assertEqual(cpu.get_float(wideband.WIDEBAND_LOG_LAMBDA_BANK1), 0)
            # Both banks' active special ADC service survives the O2 patch.
            # Check its complete handoff against the newly reclaimed bytes.
            adc = ADCHandoffMachine(image)
            sentinels = {a: 0xA5A50000+i for i, a in enumerate((
                wideband.WIDEBAND_LOG_LAMBDA_BANK1, wideband.WIDEBAND_LOG_LAMBDA_BANK2,
                safety.LEAN_COUNTER_RAM, safety.LEAN_STATE_RAM))}
            for a, value in sentinels.items():
                adc.write(a, value, 4)
            banks = set()
            for _ in range(130):
                adc.collect_and_start()
                adc.finish_normal_scans()
                if adc.read(RAM+0xAB43, 1):
                    banks.add(adc.read(RAM+0xAECE, 1))
                    adc.finish_front_measurement()
                self.assertEqual({a: adc.read(a, 4) for a in sentinels}, sentinels)
            self.assertEqual(banks, {0, 1})

    def test_native_override_progression_completes_and_restores_both_latest_commands(self):
        for image in self.images:
            cpu = AVCSActuatorMachine(image)
            cpu.execute(cpu.read(safety.LEAN_STATE_INIT_TASK_PTR, 4), INIT_WRITES)
            for bank in (0, 1):
                cpu.original_r[4] = bank
                cpu.execute(0xDF1E, DEVICE_WRITES)
            high = tuple(cpu.read(RAM+a, 2) for a in (0xF510, 0xF512))
            cpu.put_float(RAM+0xC914, 50)
            cpu.put_float(RAM+0xC918, 60)
            self.assertEqual(cpu.output(), high)
            changes = []
            previous = high
            for tick in range(1, 32):
                cpu.execute(0xE174, DEVICE_WRITES)
                output = tuple(cpu.read(RAM+a, 2) for a in (0xF510, 0xF512))
                if output != previous:
                    changes.append((tick, output))
                previous = output
            self.assertEqual([tick for tick, _ in changes], list(range(4, 32, 3)))
            low = tuple(int(cpu.read(RAM+a, 2)*int(9.36/100*65536)/65536)
                        for a in (0xAB8C, 0xAB8E))
            self.assertEqual([value for _, value in changes[:-1]],
                             [low, high, low, high, low, high, low, high, low])
            self.assertEqual(changes[-1][1], (3333, 3999))
            for a in (0xB0AE, 0xB0AF):
                self.assertEqual(cpu.read(RAM+a, 1), 0)
            for a in (0xB0AA, 0xB0AB):
                self.assertEqual(cpu.read(RAM+a, 1), 5)
            cpu.execute(0xE174, DEVICE_WRITES)
            self.assertEqual(tuple(cpu.read(RAM+a, 2) for a in (0xF510, 0xF512)),
                             changes[-1][1])

    def test_current_converter_has_native_ocv_calibration_and_feedback_consumer(self):
        cpu = AVCSActuatorMachine(self.stock)
        for raw in (0, 20000, 65535):
            cpu.write(RAM+0xAB20, raw, 2)
            cpu.write(RAM+0xAB0C, raw, 2)
            cpu.execute(0xE0D0, CURRENT_WRITES)
            expected = max(0, raw*5/65536*.334-.035)
            for a in (0xB098, 0xB09C):
                self.assertAlmostEqual(cpu.get_float(RAM+a), expected, delta=.000001)
            cpu.put_float(RAM+0xC914, 40)
            cpu.put_float(RAM+0xC918, 45)
            cpu.execute(0x33B12, FEEDBACK_WRITES)
            cpu.execute(0x33AAC, FEEDBACK_WRITES)
            for target, measured, error in ((0xC87C, 0xC86C, 0xC874),
                                             (0xC880, 0xC870, 0xC878)):
                self.assertAlmostEqual(cpu.get_float(RAM+error),
                    cpu.get_float(RAM+target)-cpu.get_float(RAM+measured), delta=.000001)


if __name__ == '__main__':
    unittest.main(verbosity=2)
