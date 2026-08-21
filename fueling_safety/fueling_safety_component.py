#!/usr/bin/env python3
"""Pressure-forced open loop and time-qualified wideband lean fuel cut.

This is a master-patch component, not a stock-ROM standalone patch.  It composes
after boost, speed density, and the former-MAF wideband component so it can use
their verified signals and retain the stock rev-limit/overboost behavior.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for directory in (ROOT / "patch", ROOT / "speed_density", ROOT / "master_patch"):
    sys.path.insert(0, str(directory))

from sh2_asm import Asm  # noqa: E402
import patch_boost as boost  # noqa: E402
import patch_speed_density as speed_density  # noqa: E402
import wideband_component as wideband  # noqa: E402


# Stock/Ghidra-verified integration points.
PRIMARY_OL_TASK_PTR = 0x00011D78
PRIMARY_OL_TARGET_UPDATE = 0x00022454
CL_OL_STATE_FLAGS = 0xFFFFBE38
CLOSED_LOOP_ALLOWED_BIT = 0x80
ATMOSPHERIC_PRESSURE = 0xFFFFCFBC
MAP_PRESSURE = 0xFFFFABC4

# The boost component already composes the stock rev limiter and hard-overboost
# cut at this task pointer.  Our wrapper calls that wrapper first, then adds the
# latched lean decision through the same stock fuel-cut flag/aggregator path.
LEAN_CUT_TASK_PTR = boost.REVLIM_FNPTR
PRIOR_FUEL_CUT_WRAPPER = boost.REVWRAP_ADDR
FUEL_CUT_FLAG = boost.FUELCUT_FLAG

# Reclaimed rear-O2 state. The master wideband component bypasses every traced
# runtime reader/writer of these locations. The stock initialization task writes
# float 1.0, so this component also replaces that task with an explicit zeroer.
LEAN_COUNTER_RAM = 0xFFFFC85C  # uint16
LEAN_STATE_RAM = 0xFFFFC860    # uint8: 0 idle, 1 delay, 2 monitor, 3 latched
LEAN_STATE_INIT_TASK_PTR = 0x0001055C
STOCK_REAR_O2_INTEGRATOR_INITIALIZE = 0x00033964

# Remaining checksum-covered free flash begins at 0x7EAC8.
COMPONENT_START = 0x0007EAC8
SIGNATURE_ADDR = 0x0007EAC8
PRESSURE_OL_ENABLE_ADDR = 0x0007EACC
LEAN_CUT_ENABLE_ADDR = 0x0007EACD
PRESSURE_OL_MARGIN_ADDR = 0x0007EAD0
LEAN_ARM_DELTA_ADDR = 0x0007EAD4
LEAN_RESET_DELTA_ADDR = 0x0007EAD8
LEAN_AFR_THRESHOLD_ADDR = 0x0007EADC  # stored as lambda; definition displays AFR
BARO_MIN_ADDR = 0x0007EAE0
BARO_MAX_ADDR = 0x0007EAE4
LEAN_TRANSPORT_COUNT_ADDR = 0x0007EAE8
LEAN_CONFIRM_COUNT_ADDR = 0x0007EAEA
PRESSURE_OL_WRAPPER_ADDR = 0x0007EB20
LEAN_STATE_INITIALIZE_ADDR = 0x0007EBA0
LEAN_CUT_WRAPPER_ADDR = 0x0007EC00
COMPONENT_END = 0x0007EDE7

NATIVE_PER_PSI = boost.NATIVE_PER_PSI
GASOLINE_STOICH_AFR = wideband.GASOLINE_STOICH_AFR
PRESSURE_OL_MARGIN_PSI = 0.50
LEAN_ARM_PSI = 0.50
LEAN_RESET_PSI = -0.50
LEAN_AFR_THRESHOLD = 13.0
BARO_MIN_MMHG = 300.0
BARO_MAX_MMHG = 850.0
LEAN_TRANSPORT_COUNT = 50
LEAN_CONFIRM_COUNT = 8


def be32(value: int) -> bytes:
    return struct.pack(">I", value & 0xFFFFFFFF)


def f32(value: float) -> bytes:
    return struct.pack(">f", value)


def build_pressure_ol_wrapper() -> bytes:
    """Run the stock target update, then revoke CL permission near atmosphere."""
    a = Asm(PRESSURE_OL_WRAPPER_ADDR)
    a.stsl_pr()
    a.movl_pool(2, PRIMARY_OL_TARGET_UPDATE).jsr(2).nop()

    a.movl_pool(1, PRESSURE_OL_ENABLE_ADDR).movb_at(0, 1).cmp_eq_imm(1)
    a.bf("done")

    # Fail toward open loop for malformed barometric calibration/signal.  A
    # low MAP value is harmless; +infinity naturally takes the force path.
    a.movl_pool(1, ATMOSPHERIC_PRESSURE).fmov_load(3, 1)
    a.fcmpeq(3, 3).bf("force_ol")
    a.movl_pool(1, BARO_MIN_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("force_ol")
    a.fcmpgt(3, 4).bt("force_ol")       # minimum > baro
    a.movl_pool(1, BARO_MAX_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("force_ol")
    a.fcmpgt(4, 3).bt("force_ol")       # baro > maximum
    a.movl_pool(1, PRESSURE_OL_MARGIN_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("force_ol")
    a.fldi0(2).fcmpgt(2, 4).bf("force_ol")  # margin must be > 0

    a.fsub(4, 3)                         # fr3 = baro - margin
    a.movl_pool(1, MAP_PRESSURE).fmov_load(2, 1)
    a.fcmpeq(2, 2).bf("force_ol")
    a.fcmpgt(2, 3).bt("done")           # threshold > MAP: keep stock state

    a.label("force_ol")
    a.movl_pool(1, CL_OL_STATE_FLAGS).movb_at(0, 1)
    a.and_imm(0x7F).movb_store(0, 1)     # clear only verified CL-allowed bit
    a.label("done")
    a.ldsl_pr().rts().nop()
    return a.assemble()


def _clear_state(a: Asm, return_label: str) -> None:
    a.mov_imm(0, 0)
    a.movl_pool(1, LEAN_STATE_RAM).movb_store(0, 1)
    a.movl_pool(1, LEAN_COUNTER_RAM).movw_store(0, 1)
    a.bra(return_label).nop()


def _increment_counter_and_test(a: Asm, limit_address: int, reached: str, pending: str) -> None:
    a.movl_pool(1, LEAN_COUNTER_RAM).movw_at(0, 1).extu_w(0, 0)
    a.add_imm(1, 0).movw_store(0, 1).mov_reg(0, 2)
    a.movl_pool(1, limit_address).movw_at(0, 1).extu_w(0, 0)
    a.cmp_hs(0, 2).bt(reached)
    a.bra(pending).nop()


def build_lean_cut_wrapper() -> bytes:
    """Compose prior cuts, then apply a pressure-armed, latched lean cut."""
    a = Asm(LEAN_CUT_WRAPPER_ADDR)
    a.stsl_pr()
    a.movl_pool(2, PRIOR_FUEL_CUT_WRAPPER).jsr(2).nop()

    a.movl_pool(1, LEAN_CUT_ENABLE_ADDR).movb_at(0, 1).cmp_eq_imm(1)
    a.bt("enabled")
    a.mov_imm(0, 0)
    a.movl_pool(1, LEAN_STATE_RAM).movb_store(0, 1)
    a.movl_pool(1, LEAN_COUNTER_RAM).movw_store(0, 1)
    a.ldsl_pr().rts().nop()

    a.label("enabled")
    a.movl_pool(1, LEAN_STATE_RAM).movb_at(0, 1).cmp_eq_imm(3)
    a.bf("not_latched")
    a.bra("latched").nop()
    a.label("not_latched")

    # A non-latched protection disarms on unusable pressure data.  The SD and
    # hard-overboost paths retain their independent failure handling.
    a.movl_pool(1, MAP_PRESSURE).fmov_load(2, 1)
    a.fcmpeq(2, 2).bf("invalid_pressure")
    a.movl_pool(1, speed_density.MAP_MIN_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("invalid_pressure")
    a.fcmpgt(2, 4).bt("invalid_pressure")
    a.movl_pool(1, speed_density.MAP_MAX_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("invalid_pressure")
    a.fcmpgt(4, 2).bt("invalid_pressure")
    a.movl_pool(1, ATMOSPHERIC_PRESSURE).fmov_load(3, 1)
    a.fcmpeq(3, 3).bf("invalid_pressure")
    a.movl_pool(1, BARO_MIN_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("invalid_pressure")
    a.fcmpgt(3, 4).bt("invalid_pressure")
    a.movl_pool(1, BARO_MAX_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("invalid_pressure")
    a.fcmpgt(4, 3).bt("invalid_pressure")
    a.fsub(3, 2)                         # fr2 = MAP - baro
    a.movl_pool(1, LEAN_ARM_DELTA_ADDR).fmov_load(3, 1)
    a.fcmpeq(3, 3).bf("invalid_pressure")
    a.fldi0(4).fcmpgt(4, 3).bf("invalid_pressure")  # arm delta must be > 0
    a.fcmpgt(2, 3).bt("invalid_pressure")  # arm delta > actual delta
    a.bra("pressure_armed").nop()

    a.label("invalid_pressure")
    a.bra("disarm").nop()

    a.label("pressure_armed")

    a.movl_pool(1, LEAN_STATE_RAM).movb_at(0, 1).cmp_eq_imm(0)
    a.bt("start_delay")
    a.cmp_eq_imm(1).bt("delay")

    # State 2: only valid/readied wideband values at or richer than the AFR
    # threshold reset the confirm counter. Everything else counts as lean.
    a.movl_pool(1, wideband.FRONT_READY_METRIC_BANK1).fmov_load(0, 1)
    a.movl_pool(1, wideband.READY_THRESHOLD_ADDR).fmov_load(1, 1)
    a.fcmpgt(1, 0).bf("lean_sample")
    a.movl_pool(1, wideband.WIDEBAND_LOG_LAMBDA_BANK1).fmov_load(0, 1)
    a.fcmpeq(0, 0).bf("lean_sample")
    a.movl_pool(1, LEAN_AFR_THRESHOLD_ADDR).fmov_load(1, 1)
    a.fcmpeq(1, 1).bf("lean_sample")
    a.fldi0(4).fcmpgt(4, 1).bf("lean_sample")
    a.fcmpgt(1, 0).bt("lean_sample")     # actual lambda > threshold
    a.mov_imm(0, 0).movl_pool(1, LEAN_COUNTER_RAM).movw_store(0, 1)
    a.bra("done").nop()

    a.label("lean_sample")
    _increment_counter_and_test(a, LEAN_CONFIRM_COUNT_ADDR, "trip", "done")

    a.label("start_delay")
    a.mov_imm(1, 0).movl_pool(1, LEAN_STATE_RAM).movb_store(0, 1)
    a.mov_imm(0, 0).movl_pool(1, LEAN_COUNTER_RAM).movw_store(0, 1)
    a.bra("done").nop()

    a.label("delay")
    _increment_counter_and_test(a, LEAN_TRANSPORT_COUNT_ADDR, "monitor", "done")

    a.label("monitor")
    a.mov_imm(2, 0).movl_pool(1, LEAN_STATE_RAM).movb_store(0, 1)
    a.mov_imm(0, 0).movl_pool(1, LEAN_COUNTER_RAM).movw_store(0, 1)
    a.bra("done").nop()

    a.label("trip")
    a.mov_imm(3, 0).movl_pool(1, LEAN_STATE_RAM).movb_store(0, 1)
    a.mov_imm(0, 0).movl_pool(1, LEAN_COUNTER_RAM).movw_store(0, 1)
    a.bra("set_cut").nop()

    # Once tripped, AFR is deliberately ignored because this wrapper itself
    # removes fuel. Release only after MAP falls below the calibrated reset
    # delta; invalid pressure keeps the cut latched.
    a.label("latched")
    a.movl_pool(1, MAP_PRESSURE).fmov_load(2, 1)
    a.fcmpeq(2, 2).bf("set_cut")
    a.movl_pool(1, speed_density.MAP_MIN_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("set_cut")
    a.fcmpgt(2, 4).bt("set_cut")
    a.movl_pool(1, speed_density.MAP_MAX_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("set_cut")
    a.fcmpgt(4, 2).bt("set_cut")
    a.movl_pool(1, ATMOSPHERIC_PRESSURE).fmov_load(3, 1)
    a.fcmpeq(3, 3).bf("set_cut")
    a.movl_pool(1, BARO_MIN_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("set_cut")
    a.fcmpgt(3, 4).bt("set_cut")
    a.movl_pool(1, BARO_MAX_ADDR).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf("set_cut")
    a.fcmpgt(4, 3).bt("set_cut")
    a.fsub(3, 2)
    a.movl_pool(1, LEAN_RESET_DELTA_ADDR).fmov_load(3, 1)
    a.fcmpeq(3, 3).bf("set_cut")
    a.fldi0(4).fcmpgt(3, 4).bf("set_cut")  # reset delta must be < 0
    a.fcmpgt(3, 2).bf("disarm")          # release when delta <= reset

    a.label("set_cut")
    a.movl_pool(1, FUEL_CUT_FLAG).movb_at(0, 1)
    a.or_imm(0x80).movb_store(0, 1)
    a.bra("done").nop()

    a.label("disarm")
    _clear_state(a, "done")

    a.label("done")
    a.ldsl_pr().rts().nop()
    return a.assemble()


def build_lean_state_initialize() -> bytes:
    """Replace the stock rear-O2 float-1.0 initializer with integer zero state."""
    a = Asm(LEAN_STATE_INITIALIZE_ADDR)
    a.mov_imm(0, 0)
    a.movl_pool(1, LEAN_COUNTER_RAM).movl_store(0, 1)
    a.movl_pool(1, LEAN_STATE_RAM).movl_store(0, 1)
    a.rts().nop()
    return a.assemble()


def build_blobs() -> list[tuple[str, int, bytes]]:
    constants = (
        b"FS01"
        + b"\x01\x01\xFF\xFF"
        + f32(PRESSURE_OL_MARGIN_PSI * NATIVE_PER_PSI)
        + f32(LEAN_ARM_PSI * NATIVE_PER_PSI)
        + f32(LEAN_RESET_PSI * NATIVE_PER_PSI)
        + f32(LEAN_AFR_THRESHOLD / GASOLINE_STOICH_AFR)
        + f32(BARO_MIN_MMHG)
        + f32(BARO_MAX_MMHG)
        + struct.pack(">HH", LEAN_TRANSPORT_COUNT, LEAN_CONFIRM_COUNT)
    )
    assert len(constants) == 0x24
    return [
        ("fueling_safety_constants", COMPONENT_START, constants),
        ("pressure_open_loop_wrapper", PRESSURE_OL_WRAPPER_ADDR, build_pressure_ol_wrapper()),
        ("lean_state_initialize", LEAN_STATE_INITIALIZE_ADDR, build_lean_state_initialize()),
        ("lean_cut_wrapper", LEAN_CUT_WRAPPER_ADDR, build_lean_cut_wrapper()),
    ]


def checked_pointer(rom: bytearray, address: int, expected: int, replacement: int, label: str) -> None:
    current = struct.unpack_from(">I", rom, address)[0]
    if current != expected:
        raise SystemExit(
            "REFUSING: %s @0x%05X is 0x%08X (expected 0x%08X)"
            % (label, address, current, expected)
        )
    rom[address : address + 4] = be32(replacement)


def apply_to_rom(rom: bytearray) -> list[tuple[str, int, bytes]]:
    if len(rom) != 0x80000:
        raise SystemExit("REFUSING: fueling safety requires a 512 KiB master-derived ROM")
    if rom[wideband.MASTER_O2_SIGNATURE_ADDR] != 1:
        raise SystemExit("REFUSING: fueling safety requires the master wideband component")
    for address, _, label in wideband.REAR_O2_TASK_POINTERS:
        if struct.unpack_from(">I", rom, address)[0] != wideband.NOOP_TASK:
            raise SystemExit("REFUSING: reclaimed lean-cut RAM is not safe; %s remains active" % label)

    blobs = build_blobs()
    for name, address, data in blobs:
        if not (COMPONENT_START <= address and address + len(data) - 1 <= COMPONENT_END):
            raise SystemExit("layout error: %s exceeds fueling-safety reservation" % name)
        if any(value != 0xFF for value in rom[address : address + len(data)]):
            raise SystemExit("REFUSING: %s destination is not verified free flash" % name)

    checked_pointer(
        rom, PRIMARY_OL_TASK_PTR, PRIMARY_OL_TARGET_UPDATE,
        PRESSURE_OL_WRAPPER_ADDR, "primary open-loop fueling task pointer",
    )
    checked_pointer(
        rom, LEAN_STATE_INIT_TASK_PTR, STOCK_REAR_O2_INTEGRATOR_INITIALIZE,
        LEAN_STATE_INITIALIZE_ADDR, "retired rear-O2 integrator initialization task",
    )
    checked_pointer(
        rom, LEAN_CUT_TASK_PTR, PRIOR_FUEL_CUT_WRAPPER,
        LEAN_CUT_WRAPPER_ADDR, "composed rev-limit/overboost task pointer",
    )
    for _, address, data in blobs:
        rom[address : address + len(data)] = data
    return blobs
