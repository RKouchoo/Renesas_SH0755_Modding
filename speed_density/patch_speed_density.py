#!/usr/bin/env python3
"""MAFless committed-AVLS dual-VE component for Subaru EZ30R D2WD610H.

The stock periodic airflow/load task remains scheduled at function pointer
0x11D20 so its downstream load, filtering, and state channels keep updating.
Its final-airflow helper pointer at 0x1743C is replaced by an always-on
speed-density calculation before the task stores 0xFFFFB420.  Both raw MAF
conversion calls in the sensor-processing tasks are disabled.  The scheduled
raw-MAF limit/filter update, MAF-input diagnostic task, and both scheduled calls
to a mixed temperature/MAF diagnostic condition are bypassed, and the two
D2WD610H MAF input DTC switches are cleared.

When every input/calibration passes its validity gate, the replacement writes
the final stock mass-airflow value at 0xFFFFB420 as:

    airflow_g_s =
        VE[committed_AVLS_state, MAP_abs_mmHg, RPM]
        * MAP_abs_mmHg
        * RPM
        * displacement_litres
        * AIRFLOW_CONSTANT_PER_LITRE_AT_20C
        * IAT_density_correction[IAT_C]
        * global_multiplier

The IAT curve is 293.15 / (IAT_C + 273.15) by default.  This keeps the runtime
stub division-free and makes both the VE surface and density correction visible
in RomRaider.  The retained stock task then calculates raw engine load as
airflow_g_s * 60 / RPM, limits it to 4.0 g/rev, and conditions it for the stock
g/rev table consumers.  Exact zero RPM writes zero airflow.  Any other invalid
sensor, calibration, lookup, or arithmetic state writes a fixed 500 g/s
rich/high-load fail-safe; it never falls back to MAF or a stale MAF-derived
value.

Committed AVLS mode 3 selects the high-lift VE surface; every other value uses
the low-lift surface.  The same patch fixes AVLS to a predictable 3200 RPM
engage / 3000 RPM release policy.  The canonical stock ROM in the repository
root is read only.  The generated standalone image is always MAFless and is not
a vehicle-tested tune.
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
STOCK_MAF_AIRFLOW_TASK = 0x000172A4
FINAL_AIRFLOW_CALL_SEQUENCE_ADDR = 0x00017398
FINAL_AIRFLOW_CALL_SEQUENCE_STOCK = bytes.fromhex(
    "420bf42c932cf30a"
)  # jsr @r2; fmov fr2,fr4; load B420; fmov.s fr0,@r3
FINAL_AIRFLOW_HELPER_PTR = 0x0001743C
STOCK_FINAL_AIRFLOW_HELPER = 0x000024B0
STOCK_ENGINE_LOAD_CALC_ADDR = 0x0001753C
STOCK_ENGINE_LOAD_CALC_SEQUENCE = bytes.fromhex(
    "9b5eff358f0d0009c735f2089359f138f122f41cf4f3f44cc732d333430bf508fb0a"
)  # B420 * 60 / RPM, limited by 4.0, stored to B428
ENGINE_LOAD_SCALE_ADDR = 0x0001761C
ENGINE_LOAD_LIMIT_ADDR = 0x00017620
MAF_CONVERSION_CALL_ADDRS = (0x0000639C, 0x000066D8)
MAF_CONVERSION_CALL_STOCK = bytes.fromhex("430b")  # jsr @r3; target loaded as 0x00007C30
MAF_CONVERSION_CALL_PATCHED = bytes.fromhex("0009")  # nop
MAF_LIMIT_UPDATE_CALL_ADDR = 0x000107F8
MAF_LIMIT_UPDATE_CALL_STOCK = bytes.fromhex("420b")  # jsr @r2; target 0x00017726
MAF_INPUT_DIAGNOSTIC_TASK_PTR = 0x00011804
STOCK_MAF_INPUT_DIAGNOSTIC_TASK = 0x00061328
TEMPERATURE_MAF_CONDITION_TASK_PTRS = (0x0001062C, 0x0001185C)
STOCK_TEMPERATURE_MAF_CONDITION_TASK = 0x0007266C
NOOP_TASK = 0x000066C2  # sensor_processing_return_stub: rts; nop
P0102_SWITCH_ADDR = 0x0005BD57
P0103_SWITCH_ADDR = 0x0005BD58
TABLE_2D_LOOKUP = 0x0000209C
TABLE_3D_LOOKUP = 0x00002150

MAP_ADDR = 0xFFFFABC4                 # float, mmHg absolute
RPM_ADDR = 0xFFFFB544                 # float, RPM
IAT_ADDR = 0xFFFFB3B8                 # float, degrees C
FINAL_MASS_AIRFLOW_ADDR = 0xFFFFB420  # float, g/s; stock post-compensation channel
RAW_ENGINE_LOAD_ADDR = 0xFFFFB428     # float, g/rev before retained conditioning
ENGINE_LOAD_ADDR = 0xFFFFB438         # float, conditioned g/rev table input
SYNTHETIC_RAW_AIRFLOW_ADDR = 0xFFFFB448
SYNTHETIC_FILTER_A_ADDR = 0xFFFFB458
SYNTHETIC_FILTER_B_ADDR = 0xFFFFB45C

# Free flash starts after the integrated rotational-idle component's ceiling.
FREE_START = 0x0007DD00
COMPONENT_END = 0x0007E3FF
FREE_END = 0x0007FAF7

FAILSAFE_AIRFLOW_ADDR = 0x0007DD00     # fixed float, g/s; not exposed for tuning
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

# The dual-VE calibration is part of this component but sits after the master
# wideband/boost guard allocation.  Keeping these exact proven addresses makes
# standalone speed density and master use one identical firmware component.
DUAL_VE_START = 0x0007E640
DUAL_VE_END = 0x0007EAC7
LOW_VE_DESC_ADDR = 0x0007E640
HIGH_VE_DESC_ADDR = 0x0007E654
LOW_RPM_AXIS_ADDR = 0x0007E668
HIGH_RPM_AXIS_ADDR = 0x0007E68C
LOW_VE_DATA_ADDR = 0x0007E6B8
HIGH_VE_DATA_ADDR = 0x0007E88C

AVLS_COMMITTED_MODE_ADDR = 0xFFFFCD86
AVLS_HIGH_MODE = 3
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

LOW_RPM_AXIS = (0.0, 500.0, 800.0, 1200.0, 1600.0, 2000.0, 2500.0, 3000.0, 3200.0)
HIGH_RPM_AXIS = (3000.0, 3200.0, 3500.0, 4000.0, 4500.0, 5000.0,
                 5500.0, 6000.0, 6500.0, 7000.0, 7500.0)


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


def seed_ve_table(rpm_axis: tuple[float, ...]) -> tuple[float, ...]:
    """Resample the conservative base surface without changing its shape."""
    result: list[float] = []
    columns = len(MAP_AXIS)
    for rpm in rpm_axis:
        for column in range(columns):
            source_column = tuple(
                VE_TABLE[row * columns + column] for row in range(len(RPM_AXIS))
            )
            result.append(interpolate(RPM_AXIS, source_column, rpm))
    return tuple(result)


LOW_VE_TABLE = seed_ve_table(LOW_RPM_AXIS)
HIGH_VE_TABLE = seed_ve_table(HIGH_RPM_AXIS)

IAT_AXIS = (-50.0, -30.0, -10.0, 10.0, 20.0, 40.0, 60.0, 80.0, 110.0, 150.0)
REFERENCE_AIR_TEMPERATURE_K = 293.15
IAT_DENSITY_CORRECTION = tuple(
    REFERENCE_AIR_TEMPERATURE_K / (temperature_c + 273.15)
    for temperature_c in IAT_AXIS
)

GLOBAL_MULTIPLIER = 1.0
DISPLACEMENT_LITRES = 2.999
MAX_AIRFLOW_G_S = 500.0
FAILSAFE_AIRFLOW_G_S = 500.0
MAP_MIN_MMHG = 100.0
MAP_MAX_MMHG = 1600.0
RPM_MIN = 0.0
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
assert len(LOW_VE_TABLE) == len(MAP_AXIS) * len(LOW_RPM_AXIS)
assert len(HIGH_VE_TABLE) == len(MAP_AXIS) * len(HIGH_RPM_AXIS)
assert LOW_VE_DATA_ADDR + len(LOW_VE_TABLE) * 4 == HIGH_VE_DATA_ADDR
assert HIGH_VE_DATA_ADDR + len(HIGH_VE_TABLE) * 4 - 1 == DUAL_VE_END


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
    """Calculate airflow from the committed-state-selected VE surface."""
    a = Asm(WRAPPER_ADDR)
    a.stsl_pr()

    a.movl_pool(1, RPM_ADDR).fmov_load(5, 1)
    a.fcmpeq(5, 5).bf("early_invalid_rpm")
    a.fldi0(3).fcmpeq(3, 5).bf("rpm_precheck_done")
    a.bra("store_zero").nop()
    a.label("early_invalid_rpm")
    a.bra("failsafe").nop()
    a.bra("failsafe").nop()
    a.label("rpm_precheck_done")

    emit_float_range_gate(a, MAP_ADDR, MAP_MIN_ADDR, MAP_MAX_ADDR, 4, "invalid_inputs")
    emit_float_range_gate(a, RPM_ADDR, RPM_MIN_ADDR, RPM_MAX_ADDR, 5, "invalid_inputs")
    emit_float_range_gate(a, IAT_ADDR, IAT_MIN_ADDR, IAT_MAX_ADDR, 4, "invalid_inputs")
    emit_positive_calibration_gate(a, GLOBAL_MULTIPLIER_ADDR, 2, "invalid_inputs")
    emit_positive_calibration_gate(a, DISPLACEMENT_ADDR, 2, "invalid_inputs")
    emit_positive_calibration_gate(a, MAX_AIRFLOW_ADDR, 2, "invalid_inputs")
    a.bra("inputs_valid").nop()
    a.label("invalid_inputs")
    a.bra("failsafe").nop()
    a.label("inputs_valid")

    # Mode 3 is the Ghidra-verified committed high-lift state. Startup,
    # inhibited, and unexpected states use the conservative low-lift surface.
    a.movl_pool(1, AVLS_COMMITTED_MODE_ADDR).movb_at(0, 1)
    a.cmp_eq_imm(AVLS_HIGH_MODE).bt("high_lift")
    a.movl_pool(4, LOW_VE_DESC_ADDR)
    a.bra("descriptor_selected").nop()
    a.label("high_lift")
    a.movl_pool(4, HIGH_VE_DESC_ADDR)
    a.label("descriptor_selected")

    a.movl_pool(1, MAP_ADDR).fmov_load(4, 1)
    a.movl_pool(1, RPM_ADDR).fmov_load(5, 1)
    a.movl_pool(2, TABLE_3D_LOOKUP).jsr(2).nop()
    emit_positive_finite_value_gate(a, 0, "invalid_ve")
    a.bra("ve_valid").nop()
    a.label("invalid_ve")
    a.bra("failsafe").nop()
    a.label("ve_valid")

    a.movl_pool(1, MAP_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, RPM_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, DISPLACEMENT_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, AIRFLOW_CONSTANT_ADDR).fmov_load(2, 1).fmul(2, 0)
    a.movl_pool(1, GLOBAL_MULTIPLIER_ADDR).fmov_load(2, 1).fmul(2, 0)

    a.fpush(0)
    a.movl_pool(1, IAT_ADDR).fmov_load(4, 1)
    a.movl_pool(4, IAT_DESC_ADDR)
    a.movl_pool(2, TABLE_2D_LOOKUP).jsr(2).nop()
    emit_positive_finite_value_gate(a, 0, "drop_and_failsafe")
    a.fpop(1).fmul(1, 0)

    emit_positive_finite_value_gate(a, 0, "invalid_product")
    a.bra("product_valid").nop()
    a.label("invalid_product")
    a.bra("failsafe").nop()
    a.label("product_valid")
    a.movl_pool(1, MAX_AIRFLOW_ADDR).fmov_load(2, 1)
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
    a.movl_pool(1, FAILSAFE_AIRFLOW_ADDR).fmov_load(0, 1)

    a.label("store_all")
    for address in (
        FINAL_MASS_AIRFLOW_ADDR,
        SYNTHETIC_RAW_AIRFLOW_ADDR,
        SYNTHETIC_FILTER_A_ADDR,
        SYNTHETIC_FILTER_B_ADDR,
    ):
        a.movl_pool(1, address).fmov_store(0, 1)
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
        ("speed_density_fixed_failsafe_airflow", FAILSAFE_AIRFLOW_ADDR, f32(FAILSAFE_AIRFLOW_G_S)),
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
        (
            "speed_density_low_lift_ve_descriptor",
            LOW_VE_DESC_ADDR,
            desc_3d_float(
                len(MAP_AXIS), len(LOW_RPM_AXIS), MAP_AXIS_ADDR,
                LOW_RPM_AXIS_ADDR, LOW_VE_DATA_ADDR,
            ),
        ),
        (
            "speed_density_high_lift_ve_descriptor",
            HIGH_VE_DESC_ADDR,
            desc_3d_float(
                len(MAP_AXIS), len(HIGH_RPM_AXIS), MAP_AXIS_ADDR,
                HIGH_RPM_AXIS_ADDR, HIGH_VE_DATA_ADDR,
            ),
        ),
        ("speed_density_low_lift_rpm_axis", LOW_RPM_AXIS_ADDR,
         b"".join(f32(value) for value in LOW_RPM_AXIS)),
        ("speed_density_high_lift_rpm_axis", HIGH_RPM_AXIS_ADDR,
         b"".join(f32(value) for value in HIGH_RPM_AXIS)),
        ("speed_density_low_lift_ve_table", LOW_VE_DATA_ADDR,
         b"".join(f32(value) for value in LOW_VE_TABLE)),
        ("speed_density_high_lift_ve_table", HIGH_VE_DATA_ADDR,
         b"".join(f32(value) for value in HIGH_VE_TABLE)),
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
        in_core = FREE_START <= address and end - 1 <= COMPONENT_END
        in_dual_ve = DUAL_VE_START <= address and end - 1 <= DUAL_VE_END
        if address < previous_end or not (in_core or in_dual_ve):
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
        be32(STOCK_MAF_AIRFLOW_TASK),
        be32(STOCK_MAF_AIRFLOW_TASK),
        "retained stock airflow/load periodic-task pointer",
    )
    checked_write(
        rom,
        FINAL_AIRFLOW_CALL_SEQUENCE_ADDR,
        FINAL_AIRFLOW_CALL_SEQUENCE_STOCK,
        FINAL_AIRFLOW_CALL_SEQUENCE_STOCK,
        "retained final-airflow call and B420 store sequence",
    )
    checked_write(
        rom,
        FINAL_AIRFLOW_HELPER_PTR,
        be32(STOCK_FINAL_AIRFLOW_HELPER),
        be32(WRAPPER_ADDR),
        "stock final-airflow helper pointer",
    )
    for address in MAF_CONVERSION_CALL_ADDRS:
        checked_write(
            rom,
            address,
            MAF_CONVERSION_CALL_STOCK,
            MAF_CONVERSION_CALL_PATCHED,
            "raw MAF conversion call",
        )
    checked_write(
        rom,
        MAF_LIMIT_UPDATE_CALL_ADDR,
        MAF_LIMIT_UPDATE_CALL_STOCK,
        MAF_CONVERSION_CALL_PATCHED,
        "stock MAF limit/filter update call",
    )
    checked_write(
        rom,
        MAF_INPUT_DIAGNOSTIC_TASK_PTR,
        be32(STOCK_MAF_INPUT_DIAGNOSTIC_TASK),
        be32(NOOP_TASK),
        "MAF high/low input diagnostic task pointer",
    )
    for address in TEMPERATURE_MAF_CONDITION_TASK_PTRS:
        checked_write(
            rom,
            address,
            be32(STOCK_TEMPERATURE_MAF_CONDITION_TASK),
            be32(NOOP_TASK),
            "temperature/MAF diagnostic-condition task pointer",
        )
    checked_write(rom, P0102_SWITCH_ADDR, b"\x01", b"\x00", "P0102 MAF low-input switch")
    checked_write(rom, P0103_SWITCH_ADDR, b"\x01", b"\x00", "P0103 MAF high-input switch")
    for _, address, data in blobs:
        rom[address : address + len(data)] = data
    return blobs


def apply_predictable_avls_calibration(
    rom: bytearray,
) -> dict[str, tuple[int, bytes]]:
    """Disable road-speed engagement and retain 3200/3000 RPM hysteresis."""
    writes = {
        "AVLS Vehicle Speed Threshold (Normal Oil Temperature)": (
            AVLS_NORMAL_SPEED_DATA_ADDR,
            b"".join(f32(value) for value in AVLS_SPEED_DISABLED),
        ),
        "AVLS Vehicle Speed Threshold (High Oil Temperature)": (
            AVLS_HOT_SPEED_DATA_ADDR,
            b"".join(f32(value) for value in AVLS_SPEED_DISABLED),
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
        "AVLS High Cam Release RPM": (
            AVLS_RELEASE_RPM_ADDR, f32(AVLS_RELEASE_RPM)
        ),
        "AVLS High Cam Engage RPM": (
            AVLS_ENGAGE_RPM_ADDR, f32(AVLS_ENGAGE_RPM)
        ),
    }
    for address, data in writes.values():
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
    apply_predictable_avls_calibration(rom)
    fix_checksum(rom)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)

    if STOCK.read_bytes() != stock_bytes:
        raise RuntimeError("canonical root stock ROM changed during patch build")

    changed = [index for index, pair in enumerate(zip(stock_bytes, rom)) if pair[0] != pair[1]]
    print("Speed-density dual-VE component written: %s" % output)
    print("  stock source   : %s (UNCHANGED, SHA-256 %s)" % (STOCK, stock_hash))
    print("  output SHA-256 : %s" % hashlib.sha256(rom).hexdigest())
    print(
        "  retained task  : 0x%05X -> 0x%08X"
        % (AIRFLOW_TASK_PTR, STOCK_MAF_AIRFLOW_TASK)
    )
    print(
        "  airflow hook   : 0x%05X 0x%08X -> 0x%08X"
        % (FINAL_AIRFLOW_HELPER_PTR, STOCK_FINAL_AIRFLOW_HELPER, WRAPPER_ADDR)
    )
    print("  MAF execution  : converter + raw limit/filter NOP; final MAF calculation replaced")
    print("  MAF diagnostics: input + mixed temperature/MAF tasks bypassed; P0102/P0103 off")
    print("  modeled output : 0x%08X mass airflow, maximum %.1f g/s" %
          (FINAL_MASS_AIRFLOW_ADDR, MAX_AIRFLOW_G_S))
    print("  fault output   : fixed %.1f g/s rich/high-load fail-safe" % FAILSAFE_AIRFLOW_G_S)
    print("  AVLS VE        : low 13x%d 0..3200 RPM; high 13x%d 3000..7500 RPM" %
          (len(LOW_RPM_AXIS), len(HIGH_RPM_AXIS)))
    print("  AVLS switch    : committed mode 3 high; fixed 3200/3000 RPM hysteresis")
    print("  changed bytes  : %d" % len(changed))
    print(
        "  changed ranges : %s"
        % ", ".join("0x%05X..0x%05X" % pair for pair in merge_ranges(changed))
    )
    for name, address, data in blobs:
        print("  %-34s @0x%05X : %d bytes" % (name, address, len(data)))
    print("\n*** STATIC DEVELOPMENT COMPONENT: verify checksum and dyno-calibrate before use. ***")


if __name__ == "__main__":
    main()
