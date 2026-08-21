#!/usr/bin/env python3
"""Committed-AVLS-state dual-VE component for D2WD610H speed density.

This component is deliberately layered on top of ``speed_density``.  It keeps
the verified stock airflow/load task and all of the existing sensor/calibration
validity behavior, but replaces the single full-range VE lookup with one of two
physically scoped surfaces:

* low lift:  0 through 3200 RPM;
* high lift: 3000 through 7500 RPM.

The selector reads the Ghidra-verified committed AVLS mode byte at FFFFCD86.
Mode 3 selects high lift; every other value selects the conservative low-lift
surface.  There is no time-based or requested-state blend: AVLS is a binary
hydraulic profile switch, and committed state changes only after the retained
stock control/actuation path accepts the transition.

The canonical stock ROM is read only.  The generated standalone image applies
the base MAFless speed-density component first, this component second, and a
predictable 3200/3000 RPM AVLS calibration last.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PATCH_DIR = ROOT / "patch"
SD_DIR = ROOT / "speed_density"
for directory in (PATCH_DIR, SD_DIR):
    sys.path.insert(0, str(directory))

from sh2_asm import Asm  # noqa: E402
import patch_speed_density as speed_density  # noqa: E402


STOCK = (ROOT / "2005 BLE MT.bin").resolve()
DEFAULT_OUT = HERE / "D2WD610H_avls_dual_ve.bin"
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"
ROM_SIZE = 0x80000

AVLS_COMMITTED_MODE_ADDR = 0xFFFFCD86
AVLS_LOW_MODE = 1
AVLS_HIGH_MODE = 3

# The master wideband/boost prerequisite guard ends at 0x7E63F.  This region
# is verified 0xFF free space in canonical D2WD610H and remains below the
# Subaru checksum end at 0x7FAF7.
FREE_START = 0x0007E640
FREE_END = 0x0007FAF7
LOW_VE_DESC_ADDR = 0x0007E640
HIGH_VE_DESC_ADDR = 0x0007E654
LOW_RPM_AXIS_ADDR = 0x0007E668
HIGH_RPM_AXIS_ADDR = 0x0007E68C
LOW_VE_DATA_ADDR = 0x0007E6B8
HIGH_VE_DATA_ADDR = 0x0007E88C
WRAPPER_ADDR = speed_density.WRAPPER_ADDR

LOW_RPM_AXIS = (0.0, 500.0, 800.0, 1200.0, 1600.0, 2000.0, 2500.0, 3000.0, 3200.0)
HIGH_RPM_AXIS = (3000.0, 3200.0, 3500.0, 4000.0, 4500.0, 5000.0,
                 5500.0, 6000.0, 6500.0, 7000.0, 7500.0)

# Predictable switched-lift calibration.  The stock vehicle-speed conditioner
# is capped at 100 km/h.  A 110 km/h boundary makes high-lift engagement
# unreachable and makes low-lift release unconditional once the hard RPM latch
# clears.  This is applied to both table-driven oil bands and the separate
# fixed/fallback thresholds at 0x7D4B0/0x7D4B4.
AVLS_NORMAL_SPEED_DATA_ADDR = 0x0007D67C
AVLS_HOT_SPEED_DATA_ADDR = 0x0007D6B4
AVLS_SPEED_ROWS = 7
AVLS_SPEED_DISABLED_VALUE = 110.0
AVLS_SPEED_DISABLED = (AVLS_SPEED_DISABLED_VALUE,) * AVLS_SPEED_ROWS
AVLS_FIXED_SPEED_A_ADDR = 0x0007D4B0
AVLS_FIXED_SPEED_B_ADDR = 0x0007D4B4
AVLS_ACTUATION_MIN_RPM_ADDR = 0x0007D4AC
AVLS_RELEASE_RPM_ADDR = 0x0007D4B8
AVLS_ENGAGE_RPM_ADDR = 0x0007D4BC
AVLS_ACTUATION_MIN_RPM = 3000.0
AVLS_RELEASE_RPM = 3000.0
AVLS_ENGAGE_RPM = 3200.0

CHECKSUM_TABLE_ADDR = 0x0007FB80
CHECKSUM_TOTAL = 0x5AA5A55A


def be32(value: int) -> bytes:
    return struct.pack(">I", value & 0xFFFFFFFF)


def f32(value: float) -> bytes:
    return struct.pack(">f", value)


def pack_floats(values: tuple[float, ...]) -> bytes:
    return b"".join(f32(value) for value in values)


def desc_3d_float(
    x_count: int,
    y_count: int,
    x_axis_addr: int,
    y_axis_addr: int,
    data_addr: int,
) -> bytes:
    descriptor = (
        struct.pack(">HH", x_count, y_count)
        + be32(x_axis_addr)
        + be32(y_axis_addr)
        + be32(data_addr)
        + be32(0)
    )
    assert len(descriptor) == 0x14
    return descriptor


def interpolate(values_x: tuple[float, ...], values_y: tuple[float, ...], x: float) -> float:
    if x <= values_x[0]:
        return values_y[0]
    if x >= values_x[-1]:
        return values_y[-1]
    for index in range(len(values_x) - 1):
        x0, x1 = values_x[index], values_x[index + 1]
        if x0 <= x <= x1:
            fraction = (x - x0) / (x1 - x0)
            return values_y[index] + fraction * (values_y[index + 1] - values_y[index])
    raise AssertionError("interpolation range failure")


def seed_table(rpm_axis: tuple[float, ...]) -> tuple[float, ...]:
    """Resample the existing conservative surface without changing its shape."""
    result: list[float] = []
    columns = len(speed_density.MAP_AXIS)
    for rpm in rpm_axis:
        for column in range(columns):
            source_column = tuple(
                speed_density.VE_TABLE[row * columns + column]
                for row in range(len(speed_density.RPM_AXIS))
            )
            result.append(interpolate(speed_density.RPM_AXIS, source_column, rpm))
    return tuple(result)


LOW_VE_TABLE = seed_table(LOW_RPM_AXIS)
HIGH_VE_TABLE = seed_table(HIGH_RPM_AXIS)

assert len(LOW_VE_TABLE) == len(speed_density.MAP_AXIS) * len(LOW_RPM_AXIS)
assert len(HIGH_VE_TABLE) == len(speed_density.MAP_AXIS) * len(HIGH_RPM_AXIS)
assert LOW_VE_DATA_ADDR + len(LOW_VE_TABLE) * 4 == HIGH_VE_DATA_ADDR


def build_wrapper() -> bytes:
    """Calculate airflow with a committed-state-selected VE surface."""
    a = Asm(WRAPPER_ADDR)
    a.stsl_pr()

    a.movl_pool(1, speed_density.RPM_ADDR).fmov_load(5, 1)
    a.fcmpeq(5, 5).bf("early_invalid_rpm")
    a.fldi0(3).fcmpeq(3, 5).bf("rpm_precheck_done")
    a.bra("store_zero").nop()
    a.label("early_invalid_rpm")
    a.bra("failsafe").nop()
    a.bra("failsafe").nop()
    a.label("rpm_precheck_done")

    speed_density.emit_float_range_gate(
        a, speed_density.MAP_ADDR, speed_density.MAP_MIN_ADDR,
        speed_density.MAP_MAX_ADDR, 4, "invalid_inputs"
    )
    speed_density.emit_float_range_gate(
        a, speed_density.RPM_ADDR, speed_density.RPM_MIN_ADDR,
        speed_density.RPM_MAX_ADDR, 5, "invalid_inputs"
    )
    speed_density.emit_float_range_gate(
        a, speed_density.IAT_ADDR, speed_density.IAT_MIN_ADDR,
        speed_density.IAT_MAX_ADDR, 4, "invalid_inputs"
    )
    speed_density.emit_positive_calibration_gate(
        a, speed_density.GLOBAL_MULTIPLIER_ADDR, 2, "invalid_inputs"
    )
    speed_density.emit_positive_calibration_gate(
        a, speed_density.DISPLACEMENT_ADDR, 2, "invalid_inputs"
    )
    speed_density.emit_positive_calibration_gate(
        a, speed_density.MAX_AIRFLOW_ADDR, 2, "invalid_inputs"
    )
    a.bra("inputs_valid").nop()
    a.label("invalid_inputs")
    a.bra("failsafe").nop()
    a.label("inputs_valid")

    # Binary AVLS selection.  Mode 3 is the Ghidra-verified committed high-lift
    # state.  Startup, inhibited, and any unexpected states use low-lift VE.
    a.movl_pool(1, AVLS_COMMITTED_MODE_ADDR).movb_at(0, 1)
    a.cmp_eq_imm(AVLS_HIGH_MODE).bt("high_lift")
    a.movl_pool(4, LOW_VE_DESC_ADDR)
    a.bra("descriptor_selected").nop()
    a.label("high_lift")
    a.movl_pool(4, HIGH_VE_DESC_ADDR)
    a.label("descriptor_selected")

    a.movl_pool(1, speed_density.MAP_ADDR).fmov_load(4, 1)
    a.movl_pool(1, speed_density.RPM_ADDR).fmov_load(5, 1)
    a.movl_pool(2, speed_density.TABLE_3D_LOOKUP).jsr(2).nop()
    speed_density.emit_positive_finite_value_gate(a, 0, "invalid_ve")
    a.bra("ve_valid").nop()
    a.label("invalid_ve")
    a.bra("failsafe").nop()
    a.label("ve_valid")

    a.movl_pool(1, speed_density.MAP_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, speed_density.RPM_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, speed_density.DISPLACEMENT_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, speed_density.AIRFLOW_CONSTANT_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, speed_density.GLOBAL_MULTIPLIER_ADDR).fmov_load(2, 1).fmul(2, 0)

    a.fpush(0)
    a.movl_pool(1, speed_density.IAT_ADDR).fmov_load(4, 1)
    a.movl_pool(4, speed_density.IAT_DESC_ADDR)
    a.movl_pool(2, speed_density.TABLE_2D_LOOKUP).jsr(2).nop()
    speed_density.emit_positive_finite_value_gate(a, 0, "drop_and_failsafe")
    a.fpop(1).fmul(1, 0)

    speed_density.emit_positive_finite_value_gate(a, 0, "invalid_product")
    a.bra("product_valid").nop()
    a.label("invalid_product")
    a.bra("failsafe").nop()
    a.label("product_valid")
    a.movl_pool(1, speed_density.MAX_AIRFLOW_ADDR).fmov_load(2, 1)
    a.fcmpgt(2, 0).bf("store")
    a.fmov(2, 0)
    a.label("store")
    a.bra("store_all").nop()

    a.label("drop_and_failsafe")
    a.fpop(1)
    a.bra("failsafe").nop()

    a.label("store_zero")
    a.fldi0(0)
    a.bra("store_all").nop()

    a.label("failsafe")
    a.movl_pool(1, speed_density.FAILSAFE_AIRFLOW_ADDR).fmov_load(0, 1)

    a.label("store_all")
    for address in (
        speed_density.FINAL_MASS_AIRFLOW_ADDR,
        speed_density.SYNTHETIC_RAW_AIRFLOW_ADDR,
        speed_density.SYNTHETIC_FILTER_A_ADDR,
        speed_density.SYNTHETIC_FILTER_B_ADDR,
    ):
        a.movl_pool(1, address).fmov_store(0, 1)
    a.ldsl_pr().rts().nop()
    return a.assemble()


def build_blobs() -> list[tuple[str, int, bytes]]:
    return [
        (
            "avls_low_lift_ve_descriptor",
            LOW_VE_DESC_ADDR,
            desc_3d_float(
                len(speed_density.MAP_AXIS), len(LOW_RPM_AXIS),
                speed_density.MAP_AXIS_ADDR, LOW_RPM_AXIS_ADDR, LOW_VE_DATA_ADDR,
            ),
        ),
        (
            "avls_high_lift_ve_descriptor",
            HIGH_VE_DESC_ADDR,
            desc_3d_float(
                len(speed_density.MAP_AXIS), len(HIGH_RPM_AXIS),
                speed_density.MAP_AXIS_ADDR, HIGH_RPM_AXIS_ADDR, HIGH_VE_DATA_ADDR,
            ),
        ),
        ("avls_low_lift_rpm_axis", LOW_RPM_AXIS_ADDR, pack_floats(LOW_RPM_AXIS)),
        ("avls_high_lift_rpm_axis", HIGH_RPM_AXIS_ADDR, pack_floats(HIGH_RPM_AXIS)),
        ("avls_low_lift_ve_table", LOW_VE_DATA_ADDR, pack_floats(LOW_VE_TABLE)),
        ("avls_high_lift_ve_table", HIGH_VE_DATA_ADDR, pack_floats(HIGH_VE_TABLE)),
    ]


def checked_write(
    rom: bytearray, address: int, expected: bytes, replacement: bytes, label: str
) -> None:
    actual = bytes(rom[address : address + len(expected)])
    if actual != expected:
        raise SystemExit(
            f"REFUSING: {label} @0x{address:05X} is {actual.hex()} "
            f"(expected {expected.hex()})"
        )
    rom[address : address + len(replacement)] = replacement


def apply_to_rom(rom: bytearray) -> list[tuple[str, int, bytes]]:
    """Layer dual VE onto an image containing the exact speed-density component."""
    if len(rom) != ROM_SIZE:
        raise SystemExit(f"REFUSING: expected 512 KiB ROM, got {len(rom)} bytes")

    old_wrapper = speed_density.build_wrapper()
    new_wrapper = build_wrapper()
    wrapper_span = max(len(old_wrapper), len(new_wrapper))
    if WRAPPER_ADDR + wrapper_span - 1 > speed_density.COMPONENT_END:
        raise SystemExit("dual-VE wrapper exceeds reserved speed-density code space")
    expected = old_wrapper + b"\xFF" * (wrapper_span - len(old_wrapper))
    replacement = new_wrapper + b"\xFF" * (wrapper_span - len(new_wrapper))
    checked_write(rom, WRAPPER_ADDR, expected, replacement, "speed-density airflow wrapper")

    blobs = build_blobs()
    previous_end = FREE_START
    for name, address, data in blobs:
        end = address + len(data)
        if address < previous_end or end - 1 > FREE_END:
            raise SystemExit(f"layout error: {name} @0x{address:05X}..0x{end - 1:05X}")
        if any(byte != 0xFF for byte in rom[address:end]):
            raise SystemExit(f"REFUSING: {name} target is not 0xFF-free")
        previous_end = end
    for _, address, data in blobs:
        rom[address : address + len(data)] = data
    # The wrapper deliberately replaces the speed-density wrapper in its
    # already-declared code allocation.  Only its extension beyond the old
    # allocation is new ownership; returning that tail keeps multi-component
    # audits precise without reporting the expected shared body as overlap.
    extension = new_wrapper[len(old_wrapper) :]
    extension_blob = (
        "avls_dual_ve_wrapper_extension",
        WRAPPER_ADDR + len(old_wrapper),
        extension,
    )
    return [extension_blob, *blobs]


def apply_predictable_avls_calibration(rom: bytearray) -> dict[str, tuple[int, bytes]]:
    """Disable road-speed engagement and retain 3200/3000 RPM hysteresis."""
    writes = {
        "AVLS Vehicle Speed Threshold (Normal Oil Temperature)": (
            AVLS_NORMAL_SPEED_DATA_ADDR, pack_floats(AVLS_SPEED_DISABLED)
        ),
        "AVLS Vehicle Speed Threshold (High Oil Temperature)": (
            AVLS_HOT_SPEED_DATA_ADDR, pack_floats(AVLS_SPEED_DISABLED)
        ),
        "AVLS Actuation Minimum RPM": (
            AVLS_ACTUATION_MIN_RPM_ADDR, f32(AVLS_ACTUATION_MIN_RPM)
        ),
        "AVLS Fixed/Fallback Speed Threshold A": (
            AVLS_FIXED_SPEED_A_ADDR, f32(AVLS_SPEED_DISABLED_VALUE)
        ),
        "AVLS Fixed/Fallback Speed Threshold B": (
            AVLS_FIXED_SPEED_B_ADDR, f32(AVLS_SPEED_DISABLED_VALUE)
        ),
        "AVLS High Cam Release RPM": (AVLS_RELEASE_RPM_ADDR, f32(AVLS_RELEASE_RPM)),
        "AVLS High Cam Engage RPM": (AVLS_ENGAGE_RPM_ADDR, f32(AVLS_ENGAGE_RPM)),
    }
    for _, (address, data) in writes.items():
        rom[address : address + len(data)] = data
    return writes


def checksum_value(image: bytes | bytearray) -> tuple[int, int]:
    start, end, stored = struct.unpack_from(">III", image, CHECKSUM_TABLE_ADDR)
    if (start, end) != (0x2000, 0x7FAF7):
        raise SystemExit("REFUSING: unexpected Subaru checksum range")
    total = sum(
        struct.unpack_from(">I", image, address)[0]
        for address in range(start, end, 4)
    ) & 0xFFFFFFFF
    return stored, (CHECKSUM_TOTAL - total) & 0xFFFFFFFF


def fix_checksum(rom: bytearray) -> None:
    _, calculated = checksum_value(rom)
    rom[CHECKSUM_TABLE_ADDR + 8 : CHECKSUM_TABLE_ADDR + 12] = be32(calculated)
    stored, verify = checksum_value(rom)
    if stored != verify:
        raise AssertionError("Subaru checksum correction failed")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv if argv is None else argv
    if len(argv) > 2:
        raise SystemExit("usage: python3 avls_ve/patch_avls_ve.py [out.bin]")
    output = Path(argv[1]).resolve() if len(argv) == 2 else DEFAULT_OUT.resolve()
    if Path(os.path.realpath(output)) == STOCK or (output.exists() and os.path.samefile(output, STOCK)):
        raise SystemExit("REFUSING: output aliases canonical stock ROM")

    stock = STOCK.read_bytes()
    if len(stock) != ROM_SIZE or hashlib.sha256(stock).hexdigest() != STOCK_SHA256:
        raise SystemExit("REFUSING: canonical stock ROM hash/size mismatch")
    rom = bytearray(stock)
    speed_density.apply_to_rom(rom)
    blobs = apply_to_rom(rom)
    apply_predictable_avls_calibration(rom)
    fix_checksum(rom)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)
    if STOCK.read_bytes() != stock:
        raise RuntimeError("canonical stock ROM changed during build")

    print(f"D2WD610H AVLS dual-VE patch written: {output}")
    print(f"  selector          : committed mode {AVLS_HIGH_MODE}=high; otherwise low")
    print(f"  low-lift VE       : {len(speed_density.MAP_AXIS)}x{len(LOW_RPM_AXIS)}, "
          f"{LOW_RPM_AXIS[0]:.0f}..{LOW_RPM_AXIS[-1]:.0f} RPM")
    print(f"  high-lift VE      : {len(speed_density.MAP_AXIS)}x{len(HIGH_RPM_AXIS)}, "
          f"{HIGH_RPM_AXIS[0]:.0f}..{HIGH_RPM_AXIS[-1]:.0f} RPM")
    print(f"  AVLS switch       : engage {AVLS_ENGAGE_RPM:.0f}, release {AVLS_RELEASE_RPM:.0f} RPM")
    print(f"  free-space blobs  : {len(blobs)}")
    print(f"  output SHA-256    : {hashlib.sha256(rom).hexdigest()}")
    print("\n*** DEVELOPMENT IMAGE: bench/log validation required before load. ***")


if __name__ == "__main__":
    main()
