#!/usr/bin/env python3
"""Execute native spark permission and shutdown gates with explicit fixtures.

This does not simulate coil current, physical spark, crank synchronization or
the full ignition scheduler. Fault bits are imposed, not recovered from a log.
The raw-u16 dwell lookup is a descriptor/interpolation boundary; its caller and
the cached-count getter execute ROM instructions. No firmware is written.
"""

import _test_paths
from itertools import product
from pathlib import Path
import struct
import sys
import unittest

from test_injector_scheduler_execution import SchedulerMachine
from test_primary_fueling_execution import number

ROOT = _test_paths.ROOT
IMAGE = None
SPARK_WORD = 0xFFFFC0DC
SPARK_WRITES = {(SPARK_WORD, 2)}
MODE_WRITES = {(0xFFFFC0E1, 1), (0xFFFFC0E3, 1),
               (0xFFFFC0E4, 4), (0xFFFFC0E8, 4), (0xFFFF8224, 2)}
NATIVE = {0x27090, 0x46F66, 0x46F7A, 0x46F8E, 0x46F9C, 0x46FB0,
          0x46FC4, 0x1D250, 0x4244, 0x19C04, 0x449FE, 0x44A0C,
          0x148B2, 0x2534, 0x24DC}


class IgnitionMachine(SchedulerMachine):
    def __init__(self, image):
        super().__init__(image)
        for address in (0xCD50, 0xCE28, 0xD94D, 0xC0E0, 0xC0E3,
                        0xB529, 0x81B0, 0x8546, 0xCE54):
            self.write(0xFFFF0000 | address, 0, 1)
        self.write(0xFFFFB51E, 0x10, 1)
        self.write(0xFFFFB289, 0x80, 1)  # Configuration 737C8 bit 0 is set.
        self.write(0xFFFFC0E1, 2, 1)
        self.write(0xFFFF8224, 0x00FF, 2)
        self.write(0xFFFFCD52, 0, 2)
        self.write(0xFFFFC290, 0, 2)
        self.write(SPARK_WORD, 0, 2)
        self.put_float(0xFFFFB3AC, 70)

    def call_lookup(self, target):
        if target in NATIVE:
            self.entered.append(target)
            return_pc = self.pr
            self.pc = target
            while self.pc != return_pc:
                self.step()
        elif target == 0x21B0:
            # Stock 21B0 truncates the interpolated raw value to unsigned u16.
            descriptor = self.r[4]
            assert descriptor == 0x60998
            nx, ny, ax, ay, data = struct.unpack_from('>HHIII', self.image, descriptor)
            assert (nx, ny) == (15, 5)
            x, y = number(self.fr[4]), number(self.fr[5])
            rows = [self.interpolate(self.array(ax, nx),
                    [self.read(data + (j * nx + i) * 2, 2) for i in range(nx)], x)
                    for j in range(ny)]
            result = int(self.interpolate(self.array(ay, ny), rows, y))
            self.poison_scratch()
            self.r[0] = result
        else:
            super().call_lookup(target)

    def step(self, in_delay=False):
        op = self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x6008:  # SWAP.B, used by native protected-bit getter.
            value = self.r[m]
            self.r[n] = (value & 0xFFFF0000) | ((value & 255) << 8) | ((value >> 8) & 255)
        elif op & 0xF0FF == 0x4010:  # DT; modulo-32 decrement and equality flag.
            self.r[n] = (self.r[n] - 1) & 0xFFFFFFFF
            self.t = self.r[n] == 0
        elif op & 0xF0FF == 0x4001:  # SHLR, logical with shifted-out bit in T.
            self.t = bool(self.r[n] & 1)
            self.r[n] >>= 1
        else:
            return super().step(in_delay)
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT


class IgnitionPermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE if IMAGE is not None else (
            ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        stock = (ROOT / '2005 BLE MT.bin').read_bytes()
        for start, end in ((0x27090, 0x27480), (0x29794, 0x2A44C),
                           (0x46F66, 0x46FE0), (0x3F5F0, 0x3F650),
                           (0x41698, 0x416F8), (0x449FE, 0x44A3C),
                           (0x44ACC, 0x44ADC), (0x19C04, 0x19C18),
                           (0x148B2, 0x148C6), (0x148DC, 0x148DE),
                           (0x1D250, 0x1D266), (0x1D28E, 0x1D290),
                           (0x1D29C, 0x1D2A0), (0x4244, 0x427E),
                           (0x9FEC, 0xA034), (0x60998, 0x609A8),
                           (0x7BBE0, 0x7BCC6), (0x77D68, 0x77D7C)):
            assert cls.image[start:end] == stock[start:end], hex(start)

    def test_spark_status_bits_are_separate_from_injector_status_bits(self):
        for mask in range(64):
            cpu = IgnitionMachine(self.image)
            cpu.write(0xFFFFD94C, (mask & 3) << 6 | 0x3F, 1)
            cpu.write(0xFFFFD94D, mask >> 2, 1)
            cpu.invoke(0x27090, SPARK_WRITES)
            self.assertEqual(cpu.read(SPARK_WORD, 2), mask | (mask << 6))

    def test_global_spark_inhibit_does_not_publish_injector_inhibit(self):
        for address, mask in ((0xFFFFCD50, 0x80), (0xFFFFCE28, 1)):
            cpu = IgnitionMachine(self.image)
            cpu.write(address, mask, 1)
            cpu.invoke(0x27090, SPARK_WRITES)
            self.assertEqual(cpu.read(SPARK_WORD, 2), 0xFFFF)
            self.assertEqual(cpu.read(0xFFFFB744, 2), 0)

    def test_warm_running_rpm_releases_startup_spark_gate(self):
        for coolant, rpm, previous in product((65, 70, 74.99, 75, 76),
                (2500, 2800, 2999, 3000, 3200, 3500, 4144), (0, 1, 2)):
            cpu = IgnitionMachine(self.image)
            cpu.put_float(0xFFFFB3AC, coolant)
            cpu.put_float(0xFFFFB544, rpm)
            cpu.write(0xFFFFC0E1, previous, 1)
            cpu.write(0xFFFFC0E3, 0x40, 1)  # Start with the gate latched.
            cpu.invoke(0x2716C, MODE_WRITES)
            self.assertEqual(cpu.read(0xFFFFC0E1, 1), 2)
            self.assertEqual(cpu.read(0xFFFFC0E3, 1) & 0x40, 0)
            self.assertEqual(cpu.get_float(0xFFFFC0E8), 500 if coolant < 75 else 120)

    def test_ignition_switch_on_clears_shutdown_cut_in_either_test_state(self):
        for connected in (False, True):
            cpu = IgnitionMachine(self.image)
            cpu.write(0xFFFFB51E, 0x90 if connected else 0x10, 1)
            cpu.write(0xFFFFCD50, 0x80, 1)
            cpu.write(0xFFFFCD52, 65535, 2)
            cpu.invoke(0x3F5F0, SPARK_WRITES | {(0xFFFFCD50, 1), (0xFFFFCD52, 2)})
            self.assertEqual(cpu.read(SPARK_WORD, 2), 0)
            self.assertEqual(cpu.read(0xFFFFCD52, 2), 0)
        cpu = IgnitionMachine(self.image)
        cpu.write(0xFFFFB51E, 0, 1)
        cpu.write(0xFFFFCD52, cpu.read(0x77D2E, 2), 2)
        cpu.invoke(0x3F5F0, SPARK_WRITES | {(0xFFFFCD50, 1), (0xFFFFCD52, 2)})
        self.assertEqual(cpu.read(SPARK_WORD, 2), 0xFFFF)

    def test_configured_status_path_requires_its_actual_qualifiers(self):
        for configured, status, flags in product((0, 0x80), (0, 1), (0, 2, 4)):
            cpu = IgnitionMachine(self.image)
            cpu.write(0xFFFFB289, configured, 1)
            cpu.write(0xFFFF8546, status, 1)
            cpu.write(0xFFFFCE54, flags, 1)
            cpu.invoke(0x41698, SPARK_WRITES | {(0xFFFFCE28, 1)})
            self.assertEqual(cpu.read(SPARK_WORD, 2),
                             0xFFFF if configured and (status or flags) else 0)

    def test_effective_mask_combines_permission_and_auxiliary_bits(self):
        for mode, word, aux in product((0, 1, 2), (0, 0x41, 0xFFF), (0, 0xFC0)):
            cpu = IgnitionMachine(self.image)
            cpu.write(0xFFFFC0E1, mode, 1)
            cpu.write(SPARK_WORD, word, 2)
            cpu.write(0xFFFFC290, aux, 2)
            result = cpu.invoke(0x2A262, set()) & 0xFFFF
            self.assertEqual(result, (word if mode else 0xFFFF) | aux)

    def test_stock_dwell_caller_preserves_nonzero_counts_across_failure_rpm(self):
        for rpm, expected in ((2500, 752), (2800, 713), (3000, 688), (3500, 624)):
            cpu = IgnitionMachine(self.image)
            cpu.put_float(0xFFFFAC00, rpm)
            cpu.put_float(0xFFFFABB4, 14)
            cpu.invoke(0x9FEC, {(0xFFFFAD5C, 2)})
            self.assertEqual(cpu.read(0xFFFFAD5C, 2), expected)
            self.assertEqual(cpu.invoke(0x2A3C0, set()), expected * 16)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        IMAGE = Path(sys.argv.pop()).read_bytes()
    unittest.main(verbosity=2)
