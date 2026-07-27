#!/usr/bin/env python3
"""Guarded speed-density component for Subaru EZ30R D2WD610H.

The stock periodic airflow task (function pointer at 0x11D20) is replaced by a
wrapper.  The wrapper always runs the complete stock airflow calculation first.
When the calibration switch is exactly 01 and every input/calibration passes its
validity gate, it replaces the final stock mass-airflow value at 0xFFFFB420 with:

    airflow_g_s =
        VE[MAP_abs_mmHg, RPM]
        * MAP_abs_mmHg
        * RPM
        * displacement_litres
        * AIRFLOW_CONSTANT_PER_LITRE_AT_20C
        * IAT_density_correction[IAT_C]
        * global_multiplier

The IAT curve is 293.15 / (IAT_C + 273.15) by default.  This keeps the runtime
stub division-free and makes both the VE surface and density correction visible
in RomRaider.  Invalid inputs, invalid calibration values, RPM below the
configured minimum, or any non-01 enable value retain the stock result.

The canonical stock ROM in the repository root is read only.  The generated
standalone image defaults OFF and is not a flash-ready tune.
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
sys.path.insert(0, str(PATCH_DIR))

from sh2_asm import Asm  # noqa: E402


STOCK = (ROOT / "2005 BLE MT.bin").resolve()
DEFAULT_OUT = HERE / "D2WD610H_speed_density.bin"
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"

# Ghidra-verified stock task and signal path.
AIRFLOW_TASK_PTR = 0x00011D20
STOCK_AIRFLOW_TASK = 0x000172A4
TABLE_2D_LOOKUP = 0x0000209C
TABLE_3D_LOOKUP = 0x00002150

MAP_ADDR = 0xFFFFABC4                 # float, mmHg absolute
RPM_ADDR = 0xFFFFB544                 # float, RPM
IAT_ADDR = 0xFFFFB3B8                 # float, degrees C
FINAL_MASS_AIRFLOW_ADDR = 0xFFFFB420  # float, g/s; stock post-compensation channel

# Free flash starts after the rotational-idle component's reserved ceiling.
FREE_START = 0x0007DD00
COMPONENT_END = 0x0007E3FF
FREE_END = 0x0007FAF7

SD_ENABLE_ADDR = 0x0007DD00           # uint8, exact 01 enables; default 00
GLOBAL_MULTIPLIER_ADDR = 0x0007DD04   # float
DISPLACEMENT_ADDR = 0x0007DD08        # float, litres
MAX_AIRFLOW_ADDR = 0x0007DD0C         # float, g/s
MAP_MIN_ADDR = 0x0007DD10             # float, mmHg absolute
MAP_MAX_ADDR = 0x0007DD14
RPM_MIN_ADDR = 0x0007DD18             # float, RPM
RPM_MAX_ADDR = 0x0007DD1C
IAT_MIN_ADDR = 0x0007DD20             # float, degrees C
IAT_MAX_ADDR = 0x0007DD24
AIRFLOW_CONSTANT_ADDR = 0x0007DD28    # fixed float, per litre at 20 C

VE_DESC_ADDR = 0x0007DD2C             # float 3D descriptor, 20 bytes
IAT_DESC_ADDR = 0x0007DD40            # float 2D descriptor, 12 bytes
MAP_AXIS_ADDR = 0x0007DD4C
RPM_AXIS_ADDR = 0x0007DD80
VE_DATA_ADDR = 0x0007DDC4
IAT_AXIS_ADDR = 0x0007E138
IAT_DATA_ADDR = 0x0007E160
FINITE_FLOAT_MAX_ADDR = 0x0007E188  # fixed IEEE-754 maximum finite float
WRAPPER_ADDR = 0x0007E18C

# The default table covers stock vacuum through substantial positive pressure.
# The supplied 5 psi target is about 1,019 mmHg absolute at a 760 mmHg reference.
MAP_AXIS = (
    150.0, 250.0, 350.0, 450.0, 550.0, 650.0, 760.0,
    850.0, 950.0, 1050.0, 1150.0, 1300.0, 1500.0,
)
RPM_AXIS = (
    0.0, 500.0, 800.0, 1200.0, 1600.0, 2000.0, 2500.0, 3000.0, 3500.0,
    4000.0, 4500.0, 5000.0, 5500.0, 6000.0, 6500.0, 7000.0, 7500.0,
)

# Conservative commissioning surface.  It intentionally overestimates charge
# around high load/early AVLS operation; it is not a measured EZ30R VE map.
RPM_VE_BASE = (
    0.55, 0.64, 0.69, 0.74, 0.80, 0.87, 0.94, 1.00, 1.04,
    1.05, 1.04, 1.02, 1.00, 0.98, 0.96, 0.93, 0.89,
)
MAP_VE_FACTOR = (
    0.76, 0.80, 0.84, 0.88, 0.92, 0.96, 1.00,
    1.02, 1.04, 1.055, 1.065, 1.075, 1.085,
)
VE_TABLE = tuple(
    min(1.15, rpm_ve * map_factor)
    for rpm_ve in RPM_VE_BASE
    for map_factor in MAP_VE_FACTOR
)

IAT_AXIS = (-50.0, -30.0, -10.0, 10.0, 20.0, 40.0, 60.0, 80.0, 110.0, 150.0)
REFERENCE_AIR_TEMPERATURE_K = 293.15
IAT_DENSITY_CORRECTION = tuple(
    REFERENCE_AIR_TEMPERATURE_K / (temperature_c + 273.15)
    for temperature_c in IAT_AXIS
)

GLOBAL_MULTIPLIER = 1.0
DISPLACEMENT_LITRES = 2.999
MAX_AIRFLOW_G_S = 500.0
MAP_MIN_MMHG = 100.0
MAP_MAX_MMHG = 1600.0
RPM_MIN = 100.0
RPM_MAX = 7500.0
IAT_MIN_C = -50.0
IAT_MAX_C = 150.0

# From P*V/(R*T), four-stroke RPM/120, Pa/mmHg, m^3/litre, and kg->g:
#   (133.3223684 * 0.001 * 1000) / (120 * 287.05 * 293.15)
AIRFLOW_CONSTANT_PER_LITRE_AT_20C = (
    133.3223684 / (120.0 * 287.05 * REFERENCE_AIR_TEMPERATURE_K)
)

assert len(MAP_AXIS) == len(MAP_VE_FACTOR) == 13
assert len(RPM_AXIS) == len(RPM_VE_BASE) == 17
assert len(VE_TABLE) == len(MAP_AXIS) * len(RPM_AXIS)
assert len(IAT_AXIS) == len(IAT_DENSITY_CORRECTION) == 10
assert IAT_AXIS_ADDR == VE_DATA_ADDR + len(VE_TABLE) * 4
assert IAT_DATA_ADDR == IAT_AXIS_ADDR + len(IAT_AXIS) * 4
assert FINITE_FLOAT_MAX_ADDR == IAT_DATA_ADDR + len(IAT_DENSITY_CORRECTION) * 4
assert WRAPPER_ADDR == FINITE_FLOAT_MAX_ADDR + 4


def be32(value: int) -> bytes:
    return struct.pack(">I", value & 0xFFFFFFFF)


def f32(value: float) -> bytes:
    return struct.pack(">f", value)


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
        + be32(0x00000000)
    )
    assert len(descriptor) == 0x14
    return descriptor


def desc_2d_float(count: int, axis_addr: int, data_addr: int) -> bytes:
    descriptor = struct.pack(">HBB", count, 0x00, 0x00) + be32(axis_addr) + be32(data_addr)
    assert len(descriptor) == 0x0C
    return descriptor


def emit_float_range_gate(
    assembler: Asm,
    value_addr: int,
    minimum_addr: int,
    maximum_addr: int,
    value_fr: int,
    exit_label: str,
) -> None:
    # A finite value inside finite bounds is required.  Rejecting -infinity on
    # the minimum and +infinity on the maximum is sufficient because the
    # ordinary range comparisons reject the opposite infinities.
    assembler.movl_pool(1, value_addr).fmov_load(value_fr, 1)
    assembler.fcmpeq(value_fr, value_fr).bf(exit_label)
    assembler.movl_pool(1, minimum_addr).fmov_load(3, 1)
    assembler.fcmpeq(3, 3).bf(exit_label)
    assembler.movl_pool(1, FINITE_FLOAT_MAX_ADDR).fmov_load(2, 1).fneg(2)
    assembler.fcmpgt(3, 2).bt(exit_label)  # -FLT_MAX > minimum
    assembler.fcmpgt(value_fr, 3).bt(exit_label)  # threshold > value
    assembler.movl_pool(1, maximum_addr).fmov_load(3, 1)
    assembler.fcmpeq(3, 3).bf(exit_label)
    assembler.movl_pool(1, FINITE_FLOAT_MAX_ADDR).fmov_load(2, 1)
    assembler.fcmpgt(2, 3).bt(exit_label)  # maximum > FLT_MAX
    assembler.fcmpgt(3, value_fr).bt(exit_label)  # value > threshold


def emit_positive_finite_value_gate(
    assembler: Asm,
    value_fr: int,
    exit_label: str,
) -> None:
    assembler.fcmpeq(value_fr, value_fr).bf(exit_label)
    assembler.fldi0(3)
    assembler.fcmpgt(3, value_fr).bf(exit_label)  # require value > 0
    assembler.movl_pool(1, FINITE_FLOAT_MAX_ADDR).fmov_load(3, 1)
    assembler.fcmpgt(3, value_fr).bt(exit_label)  # reject +infinity


def emit_positive_calibration_gate(
    assembler: Asm,
    value_addr: int,
    value_fr: int,
    exit_label: str,
) -> None:
    assembler.movl_pool(1, value_addr).fmov_load(value_fr, 1)
    emit_positive_finite_value_gate(assembler, value_fr, exit_label)


def build_wrapper() -> bytes:
    """Run stock first, then conditionally replace final mass airflow."""
    a = Asm(WRAPPER_ADDR)
    a.stsl_pr()
    a.movl_pool(2, STOCK_AIRFLOW_TASK).jsr(2).nop()

    a.movl_pool(1, SD_ENABLE_ADDR).movb_at(0, 1).cmp_eq_imm(0x01)
    a.bf("invalid_inputs")

    emit_float_range_gate(a, MAP_ADDR, MAP_MIN_ADDR, MAP_MAX_ADDR, 4, "invalid_inputs")
    emit_float_range_gate(a, RPM_ADDR, RPM_MIN_ADDR, RPM_MAX_ADDR, 5, "invalid_inputs")
    emit_float_range_gate(a, IAT_ADDR, IAT_MIN_ADDR, IAT_MAX_ADDR, 4, "invalid_inputs")
    emit_positive_calibration_gate(a, GLOBAL_MULTIPLIER_ADDR, 2, "invalid_inputs")
    emit_positive_calibration_gate(a, DISPLACEMENT_ADDR, 2, "invalid_inputs")
    emit_positive_calibration_gate(a, MAX_AIRFLOW_ADDR, 2, "invalid_inputs")
    a.bra("inputs_valid").nop()
    a.label("invalid_inputs")
    a.bra("done").nop()
    a.label("inputs_valid")

    # VE = VE[MAP, RPM].
    a.movl_pool(1, MAP_ADDR).fmov_load(4, 1)
    a.movl_pool(1, RPM_ADDR).fmov_load(5, 1)
    a.movl_pool(4, VE_DESC_ADDR)
    a.movl_pool(2, TABLE_3D_LOOKUP).jsr(2).nop()
    emit_positive_finite_value_gate(a, 0, "done")

    # Base mass flow at 20 C.
    a.movl_pool(1, MAP_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, RPM_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, DISPLACEMENT_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, AIRFLOW_CONSTANT_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, GLOBAL_MULTIPLIER_ADDR).fmov_load(2, 1).fmul(2, 0)

    # Preserve base flow while the stock 2D helper evaluates IAT correction.
    a.fpush(0)
    a.movl_pool(1, IAT_ADDR).fmov_load(4, 1)
    a.movl_pool(4, IAT_DESC_ADDR)
    a.movl_pool(2, TABLE_2D_LOOKUP).jsr(2).nop()
    emit_positive_finite_value_gate(a, 0, "drop_and_done")
    a.fpop(1).fmul(1, 0)

    # Reject an invalid product and cap the modeled airflow.
    emit_positive_finite_value_gate(a, 0, "done")
    a.movl_pool(1, MAX_AIRFLOW_ADDR).fmov_load(2, 1)
    a.fcmpgt(2, 0).bf("store")
    a.fmov(2, 0)
    a.label("store")
    a.movl_pool(1, FINAL_MASS_AIRFLOW_ADDR).fmov_store(0, 1)
    a.bra("done").nop()

    a.label("drop_and_done")
    a.fpop(1)
    a.label("done")
    a.ldsl_pr().rts().nop()
    return a.assemble()


def build_blobs() -> list[tuple[str, int, bytes]]:
    calibrations = b"".join(
        f32(value)
        for value in (
            GLOBAL_MULTIPLIER,
            DISPLACEMENT_LITRES,
            MAX_AIRFLOW_G_S,
            MAP_MIN_MMHG,
            MAP_MAX_MMHG,
            RPM_MIN,
            RPM_MAX,
            IAT_MIN_C,
            IAT_MAX_C,
            AIRFLOW_CONSTANT_PER_LITRE_AT_20C,
        )
    )
    return [
        ("speed_density_enable", SD_ENABLE_ADDR, b"\x00"),
        ("speed_density_calibrations", GLOBAL_MULTIPLIER_ADDR, calibrations),
        (
            "speed_density_ve_descriptor",
            VE_DESC_ADDR,
            desc_3d_float(
                len(MAP_AXIS),
                len(RPM_AXIS),
                MAP_AXIS_ADDR,
                RPM_AXIS_ADDR,
                VE_DATA_ADDR,
            ),
        ),
        (
            "speed_density_iat_descriptor",
            IAT_DESC_ADDR,
            desc_2d_float(len(IAT_AXIS), IAT_AXIS_ADDR, IAT_DATA_ADDR),
        ),
        ("speed_density_map_axis", MAP_AXIS_ADDR, b"".join(f32(value) for value in MAP_AXIS)),
        ("speed_density_rpm_axis", RPM_AXIS_ADDR, b"".join(f32(value) for value in RPM_AXIS)),
        ("speed_density_ve_table", VE_DATA_ADDR, b"".join(f32(value) for value in VE_TABLE)),
        ("speed_density_iat_axis", IAT_AXIS_ADDR, b"".join(f32(value) for value in IAT_AXIS)),
        (
            "speed_density_iat_correction",
            IAT_DATA_ADDR,
            b"".join(f32(value) for value in IAT_DENSITY_CORRECTION),
        ),
        ("speed_density_finite_float_max", FINITE_FLOAT_MAX_ADDR, be32(0x7F7FFFFF)),
        ("speed_density_airflow_wrapper", WRAPPER_ADDR, build_wrapper()),
    ]


def checked_write(
    rom: bytearray,
    address: int,
    expected: bytes,
    replacement: bytes,
    label: str,
) -> None:
    current = bytes(rom[address : address + len(expected)])
    if current != expected:
        raise SystemExit(
            "REFUSING: %s @0x%05X is %s (expected %s)"
            % (label, address, current.hex(), expected.hex())
        )
    rom[address : address + len(replacement)] = replacement


def merge_ranges(addresses: list[int]) -> list[tuple[int, int]]:
    if not addresses:
        return []
    result: list[tuple[int, int]] = []
    start = previous = addresses[0]
    for address in addresses[1:]:
        if address != previous + 1:
            result.append((start, previous))
            start = address
        previous = address
    result.append((start, previous))
    return result


def apply_to_rom(rom: bytearray) -> list[tuple[str, int, bytes]]:
    """Apply this component to a mutable, stock-derived 512 KiB image."""
    if len(rom) != 0x80000:
        raise SystemExit("REFUSING: expected a 512 KiB ROM, got %d bytes" % len(rom))

    blobs = build_blobs()
    previous_end = FREE_START
    for name, address, data in sorted(blobs, key=lambda item: item[1]):
        end = address + len(data)
        if address < previous_end or end - 1 > COMPONENT_END:
            raise SystemExit(
                "layout error: %s @0x%05X..0x%05X overlaps or exceeds component"
                % (name, address, end - 1)
            )
        if not (FREE_START <= address and end - 1 <= FREE_END):
            raise SystemExit("layout error: %s is outside verified free flash" % name)
        if any(byte != 0xFF for byte in rom[address:end]):
            raise SystemExit(
                "REFUSING: %s @0x%05X..0x%05X is not 0xFF-free"
                % (name, address, end - 1)
            )
        previous_end = end

    checked_write(
        rom,
        AIRFLOW_TASK_PTR,
        be32(STOCK_AIRFLOW_TASK),
        be32(WRAPPER_ADDR),
        "stock airflow periodic-task pointer",
    )
    for _, address, data in blobs:
        rom[address : address + len(data)] = data
    return blobs


def resolve_output(argv: list[str]) -> Path:
    if len(argv) > 2:
        raise SystemExit("usage: python3 patch_speed_density.py [out.bin]")
    return Path(argv[1]).resolve() if len(argv) == 2 else DEFAULT_OUT.resolve()


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv if argv is None else argv
    output = resolve_output(argv)
    if os.path.realpath(output) == os.path.realpath(STOCK):
        raise SystemExit("REFUSING: output aliases canonical stock ROM: %s" % STOCK)
    if output.exists() and os.path.samefile(output, STOCK):
        raise SystemExit("REFUSING: output is the canonical stock ROM or a hard link")

    stock_bytes = STOCK.read_bytes()
    stock_hash = hashlib.sha256(stock_bytes).hexdigest()
    if stock_hash != STOCK_SHA256:
        raise SystemExit(
            "REFUSING: canonical stock SHA-256 is %s (expected %s)"
            % (stock_hash, STOCK_SHA256)
        )

    rom = bytearray(stock_bytes)
    blobs = apply_to_rom(rom)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)

    if STOCK.read_bytes() != stock_bytes:
        raise RuntimeError("canonical root stock ROM changed during patch build")

    changed = [index for index, pair in enumerate(zip(stock_bytes, rom)) if pair[0] != pair[1]]
    print("Speed-density component written: %s" % output)
    print("  stock source   : %s (UNCHANGED, SHA-256 %s)" % (STOCK, stock_hash))
    print("  output SHA-256 : %s" % hashlib.sha256(rom).hexdigest())
    print(
        "  task hook      : 0x%05X 0x%08X -> 0x%08X"
        % (AIRFLOW_TASK_PTR, STOCK_AIRFLOW_TASK, WRAPPER_ADDR)
    )
    print("  runtime switch : 0x%05X=00 (OFF by default)" % SD_ENABLE_ADDR)
    print("  modeled output : 0x%08X mass airflow, maximum %.1f g/s" %
          (FINAL_MASS_AIRFLOW_ADDR, MAX_AIRFLOW_G_S))
    print("  changed bytes  : %d" % len(changed))
    print(
        "  changed ranges : %s"
        % ", ".join("0x%05X..0x%05X" % pair for pair in merge_ranges(changed))
    )
    for name, address, data in blobs:
        print("  %-34s @0x%05X : %d bytes" % (name, address, len(data)))
    print("\n*** STATIC DEVELOPMENT COMPONENT: verify checksum and dyno-calibrate before enabling. ***")


if __name__ == "__main__":
    main()
