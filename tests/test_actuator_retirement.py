#!/usr/bin/env python3
"""Independently verify the real fan path survives actuator retirement.

This checks stock scheduler, fan control, PWM writer, and calibration bytes,
plus the two retired allocations. It establishes software ownership and
inert return instructions, not physical fan polarity or measured PWM timing.
Run: python3 tests/test_actuator_retirement.py [master-ROM.bin]
"""

from __future__ import annotations

import _test_paths  # Shared offline-test imports and repository root.

import hashlib
from pathlib import Path
import struct
import sys
import unittest


ROOT = _test_paths.ROOT
STOCK_PATH = ROOT / "2005 BLE MT.bin"
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"
ROM_SIZE = 0x80000
FAN_OUTPUT_LITERAL = 0x3FD8C
FAN_OUTPUT_WRITER = 0xE8C4
RETIRED_ENABLE = 0x7D80C
# Deliberately pinned independently of the patch generators.
RETIRED_ALLOCATIONS = ((0x7D810, 172), (0x7E560, 224))
RETURN_NOP = bytes.fromhex("000b0009")
IMAGE: bytes | None = None

# Ghidra-confirmed function bodies and their adjacent literal pools. The
# contiguous 3F5F0..3FD9B block is the fan timeout/control/mode/state/duty/counter
# group; it ends before the next subsystem. The remaining ranges are only
# fan-owned calibration or literal bytes, not neighboring MAP calibration.
FAN_STOCK_RANGES = (
    ("fan control functions and literal pools", 0x3F5F0, 0x3FD9C),
    ("fan PWM period reload", 0xE8B4, 0xE8C4),
    ("fan PWM output writer", 0xE8C4, 0xE8F0),
    ("fan PWM period register literal", 0xE8F4, 0xE8F6),
    ("fan PWM output register literal", 0xE8F8, 0xE8FA),
    ("fan PWM period calibration pointer", 0xE8FC, 0xE900),
    ("fan PWM multiply helper pointer", 0xE900, 0xE904),
    ("fan PWM period RAM literal", 0xE908, 0xE90C),
    ("fan PWM scaling and request RAM literal", 0xE910, 0xE918),
    ("fan PWM period calibration", 0x72808, 0x7280A),
    ("fan timeout threshold", 0x77D2E, 0x77D30),
    ("fan coolant-to-duty descriptors", 0x609C4, 0x609EC),
    ("fan mode thresholds, axes, and duty data", 0x7BCEC, 0x7BD9C),
)

FAN_SCHEDULER = (
    (0x11754, 0x3F5F0, 0x11556),
    (0x11770, 0x3F650, 0x11580),
    (0x11768, 0x3F878, 0x11574),
    (0x1176C, 0x3F9E4, 0x1157A),
    (0x11774, 0x3FC0A, 0x11586),
    (0x11778, 0x3FD38, 0x1158C),
)

# Independent identity evidence: P92/SSM 2F reads fan percent CD54, whereas
# P38/SSM 32 reads actual CPC ratio B6D4. Keep the instructions and the
# referenced literals pinned, rather than trusting a function's old name.
IDENTITY_BYTES = (
    ("SSM radiator-fan dispatch", 0x4B7B8, "00031878"),
    ("SSM CPC dispatch", 0x4B7C4, "000318e8"),
    ("fan logger instructions", 0x31878, "9308f68dd208f438422bf59d"),
    ("fan logger CD54 source", 0x3188C, "cd54"),
    ("fan logger converter", 0x318A0, "0000258c"),
    ("CPC logger instructions", 0x318E8,
     "fffbf68dc744937df508f438c743f308d243f432422bfff9"),
    ("CPC logger B6D4 source", 0x319EC, "b6d4"),
    ("CPC logger scaling and converter", 0x31A00, "3ec8c8c842c800000000258c"),
    ("fan output pointer", FAN_OUTPUT_LITERAL, "0000e8c4"),
    ("fan PWM hardware register", 0xE8F8, "f590"),
    ("fan PWM period RAM", 0xE908, "ffffab84"),
)


def _expect(image: bytes | bytearray, address: int, expected: bytes, label: str) -> None:
    actual = image[address:address + len(expected)]
    if actual != expected:
        raise AssertionError(f"Actuator retirement: {label} changed at 0x{address:05X}")


def verify_actual_fan_preserved(image: bytes | bytearray, stock: bytes | bytearray) -> None:
    """Reject a fan hijack, changed fan behavior, or executable retired controller."""
    if len(image) != ROM_SIZE or len(stock) != ROM_SIZE:
        raise AssertionError("Actuator retirement requires two 512-KiB ROMs")
    if hashlib.sha256(stock).hexdigest() != STOCK_SHA256:
        raise AssertionError("Actuator retirement requires canonical stock reference")

    for label, address, encoded in IDENTITY_BYTES:
        expected = bytes.fromhex(encoded)
        _expect(stock, address, expected, f"canonical {label}")
        _expect(image, address, expected, label)

    for label, start, end in FAN_STOCK_RANGES:
        _expect(image, start, bytes(stock[start:end]), label)

    for slot, entry, call in FAN_SCHEDULER:
        _expect(stock, slot, struct.pack(">I", entry), "canonical fan task pointer")
        _expect(image, slot, struct.pack(">I", entry), "fan task pointer")
        # The pointer load, JSR, and its delay slot must still execute.
        _expect(image, call - 2, bytes(stock[call - 2:call + 4]), "fan task call")

    for address, size in RETIRED_ALLOCATIONS:
        _expect(image, address, RETURN_NOP, "retired entry RTS/NOP")
        _expect(image, address + 4, b"\xff" * (size - 4), "retired code/literal erasure")


class ActuatorRetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stock = STOCK_PATH.read_bytes()
        if IMAGE is not None:
            cls.image = IMAGE
        else:
            # Exercise the actual component installers without writing a ROM.
            for path in (ROOT / "patches/core", ROOT / "master_patch"):
                if str(path) not in sys.path:
                    sys.path.insert(0, str(path))
            import patch_boost
            import wideband_component

            candidate = bytearray(cls.stock)
            patch_boost.apply_to_rom(candidate)
            wideband_component.apply_to_rom(candidate)
            cls.image = bytes(candidate)

    def reject_byte_change(self, address: int) -> None:
        candidate = bytearray(self.image)
        candidate[address] ^= 1
        with self.assertRaises(AssertionError):
            verify_actual_fan_preserved(candidate, self.stock)

    def test_component_installers_preserve_real_fan(self) -> None:
        verify_actual_fan_preserved(self.image, self.stock)

    def test_both_historical_fan_hijacks_are_rejected(self) -> None:
        for destination, _ in RETIRED_ALLOCATIONS:
            with self.subTest(destination=hex(destination)):
                candidate = bytearray(self.image)
                struct.pack_into(">I", candidate, FAN_OUTPUT_LITERAL, destination)
                with self.assertRaisesRegex(AssertionError, "fan output pointer"):
                    verify_actual_fan_preserved(candidate, self.stock)

    def test_writer_hardware_literals_and_all_fan_ranges_are_guarded(self) -> None:
        for label, start, end in FAN_STOCK_RANGES:
            for address in (start, end - 1):
                with self.subTest(label=label, address=hex(address)):
                    self.reject_byte_change(address)

    def test_both_duty_tables_and_coolant_axis_are_guarded(self) -> None:
        for address in (0x7BD6C, 0x7BD80, 0x7BD88, 0x7BD98):
            with self.subTest(address=hex(address)):
                self.reject_byte_change(address)

    def test_scheduler_pointer_and_call_changes_are_rejected(self) -> None:
        for slot, _, call in FAN_SCHEDULER:
            for address in (slot, call):
                with self.subTest(address=hex(address)):
                    self.reject_byte_change(address)

    def test_fan_and_cpc_identity_changes_are_rejected(self) -> None:
        for label, address, _ in IDENTITY_BYTES:
            with self.subTest(label=label):
                self.reject_byte_change(address)

    def test_retired_entry_delay_slot_and_leftover_code_are_rejected(self) -> None:
        for start, size in RETIRED_ALLOCATIONS:
            for address in (start, start + 2, start + 4, start + size - 1):
                with self.subTest(address=hex(address)):
                    self.reject_byte_change(address)
            candidate = bytearray(self.image)
            struct.pack_into(">I", candidate, start + 8, FAN_OUTPUT_WRITER)
            with self.assertRaisesRegex(AssertionError, "retired code/literal erasure"):
                verify_actual_fan_preserved(candidate, self.stock)

    def test_old_switch_values_cannot_reenable_controller(self) -> None:
        for value in (0, 1, 255):
            with self.subTest(value=value):
                candidate = bytearray(self.image)
                candidate[RETIRED_ENABLE] = value
                verify_actual_fan_preserved(candidate, self.stock)
                # RTS followed by NOP has no data read, store, conditional
                # branch, or hardware call. The switch byte cannot affect it.
                for entry, _ in RETIRED_ALLOCATIONS:
                    self.assertEqual(struct.unpack_from(">HH", candidate, entry), (0x000B, 0x0009))
                self.assertEqual(struct.unpack_from(">I", candidate, FAN_OUTPUT_LITERAL)[0], FAN_OUTPUT_WRITER)

    def test_wideband_refuses_upstream_fan_hijack_before_mutation(self) -> None:
        import wideband_component

        for destination, _ in RETIRED_ALLOCATIONS:
            with self.subTest(destination=hex(destination)):
                candidate = bytearray(self.stock)
                struct.pack_into(">I", candidate, FAN_OUTPUT_LITERAL, destination)
                before = bytes(candidate)
                with self.assertRaisesRegex(SystemExit, "radiator-fan output literal"):
                    wideband_component.apply_to_rom(candidate)
                self.assertEqual(bytes(candidate), before)

    def test_modified_stock_reference_is_rejected(self) -> None:
        altered = bytearray(self.stock)
        altered[0x7BD80] ^= 1
        with self.assertRaisesRegex(AssertionError, "canonical stock"):
            verify_actual_fan_preserved(self.image, altered)


if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        IMAGE = Path(sys.argv.pop(1)).read_bytes()
    unittest.main()
