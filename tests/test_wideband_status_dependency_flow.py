#!/usr/bin/env python3
"""Trace replaced WB status helpers through native aggregate and output state.

Other diagnostic sources, permission state, ignition and hardware port words
are supplied fixtures. This proves consumers beyond stored DTC enables; it
does not identify those states or electrical outputs in the loaded-drive log.
"""
import _test_paths
from itertools import product
import unittest

from test_dbw_arbitration_process_flow import DBWArbitrationMachine
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT, RAM = _test_paths.ROOT, 0xFFFF0000
GETTERS = {
    0x3BB8A, 0x3BB9E, 0x1C044, 0x64F7C, 0x64F90, 0x64FBC, 0x64FD0,
    0x64FE4, 0x64FF8, 0x6500C, 0x65024, 0x65038, 0x65060, 0x65074,
    0x650BA, 0x650D4, 0x650E8, 0x65168, 0x6517C, 0x65182, 0x6518E,
    0x652D0, 0x651CE, 0x6519A, 0x651A0, 0x651BA, 0x47198, 0x47178,
    0x1C064, 0x1C054, 0x3BBEE,
}
PERMISSION_WRITES = {(RAM+a, 1) for a in (0xCAA8, 0xCAA9, 0xCAAC)}
OUTPUT_WRITES = {(RAM+a, 1) for a in (0xCC44, 0xCC48)} | {
    (RAM+a, 2) for a in (0xCC46, 0xCC4A, 0xF754)}


class WidebandStatusMachine(DBWArbitrationMachine):
    LOOKUPS = DBWArbitrationMachine.LOOKUPS | GETTERS | {0x2088, 0x2098, 0x4BC8}

    def __init__(self, image):
        super().__init__(image)
        # Explicitly clear each native getter's fault/configuration source.
        for a in (*range(0xD26C, 0xD275), 0xDB2A, 0xDAA4, 0x8140,
                  0x8144, 0x8148, 0xCC4E, 0xCEC4, 0xCF2C, 0xCF2D,
                  0xCBFE, 0xCF28, 0xCAA8, 0xC778, 0xB748, 0xCC00):
            self.write(RAM+a, 0, 1)
        self.write(RAM+0xCAA9, 3, 1)  # Supplied active permission state.
        # Native feature setter, also referenced by startup at104BA/10658.
        self.execute(0x3BA68, {(RAM+0xCC4E, 1)})
        self.write(RAM+0xCAAA, 1, 1)
        self.write(RAM+0xCAAC, 128, 1)  # Hold rather than toggling user input.
        for a in (0xCC44, 0xCC48):
            self.write(RAM+a, 0, 1)
        for a in (0xCC46, 0xCC4A):
            self.write(RAM+a, 0, 2)
        self.write(RAM+0xF754, 0xA5A5, 2)
        self.write(RAM+0xB744, 0x15, 1)

    def aggregate_and_permission(self, raw):
        self.update_wideband(raw)
        self.execute(0x44B14, {(RAM+0xCEC4, 1)})
        self.execute(0x37B32, PERMISSION_WRITES)
        return tuple(self.read(RAM+a, 1) for a in (0xCEC4, 0xCAA8, 0xCAA9))


class WidebandStatusDependencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x44B14, 0x44E08), (0x45908, 0x45C8C),
                         (0x45D1C, 0x45D20), (0x37B32, 0x37CA4),
                         (0x3B760, 0x3B994), (0x3BB8A, 0x3BC56),
                         (0x3BA68, 0x3BA72), (0x3BB00, 0x3BB02),
                         (0x1C044, 0x1C074), (0x47178, 0x471AC),
                         (0x47240, 0x47250), (0x7CAEA, 0x7CAEE),
                         (0x4BC8, 0x4BE0)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_invalid_wb_reaches_native_permission_state_despite_disabled_o2_dtcs(self):
        for image, raw in product(self.images, (0, 7000, 18000, 58000, 65535)):
            cpu = WidebandStatusMachine(image)
            invalid = raw in (0, 65535)
            flags, summary, permission = cpu.aggregate_and_permission(raw)
            self.assertEqual(flags & 128, 128 if invalid else 0)
            self.assertEqual(summary & 64, 64 if invalid else 0)
            self.assertEqual(permission & 2, 0 if invalid else 2)
            self.assertEqual(cpu.read(RAM+0xB744, 1), 0x15)
            # Removing the fault clears the aggregate, but the supplied hold
            # state retains its summary and previously revoked permission.
            if invalid:
                flags, summary, permission = cpu.aggregate_and_permission(18000)
                self.assertEqual((flags & 128, summary & 64, permission & 2), (0, 64, 0))

    def test_other_snapshot_consumer_retains_its_bit_until_caller_clears_workspace(self):
        for image in self.images:
            cpu = WidebandStatusMachine(image)
            cpu.update_wideband(0)
            outputs = {(RAM+0xCF2C, 1), (RAM+0xCF2D, 1)}
            cpu.execute(0x45908, outputs)
            self.assertEqual(cpu.read(RAM+0xCF2D, 1) & 128, 128)
            cpu.update_wideband(18000)
            cpu.execute(0x45908, outputs)
            self.assertEqual(cpu.read(RAM+0xCF2D, 1) & 128, 128)
            cpu.write(RAM+0xCF2D, 0, 1)  # Explicit parent workspace-clear boundary.
            cpu.execute(0x45908, outputs)
            self.assertEqual(cpu.read(RAM+0xCF2D, 1) & 128, 0)
            cpu.write(RAM+0xDB2A, 1, 1)
            flags, summary, _ = cpu.aggregate_and_permission(0)
            self.assertEqual((flags & 128, summary & 64), (0, 0))

    def test_native_status_output_toggles_assigned_port_bit_without_writing_injector_mask(self):
        for image in self.images:
            cpu = WidebandStatusMachine(image)
            cpu.aggregate_and_permission(0)
            states = []
            for _ in range(251):
                cpu.execute(0x3B760, OUTPUT_WRITES)
                states.append(cpu.read(RAM+0xCC44, 1) & 64)
                self.assertEqual(cpu.read(RAM+0xF754, 2) & ~12, 0xA5A5 & ~12)
                self.assertEqual(bool(cpu.read(RAM+0xF754, 2) & 4), not bool(states[-1]))
                self.assertEqual(cpu.read(RAM+0xB744, 1), 0x15)
            self.assertEqual((states[0], states[124], states[125], states[249], states[250]),
                             (64, 64, 0, 0, 64))
            cpu.write(RAM+0xC778, 1, 1)
            cpu.execute(0x3B760, OUTPUT_WRITES)
            self.assertEqual(cpu.read(RAM+0xCC44, 1) & 0xC0, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
