#!/usr/bin/env python3
"""Speed density component with smoothed low-lift VE table for master_patch_v2.

Fixes the idle-recovery VE cliff and the 1600-RPM hump while retaining the
identical code wrapper, descriptors, axes, and validation gates from
patches/speed_density/patch_speed_density.py, including its local bypass of
the obsolete MAF-fault load substitution.
"""
from __future__ import annotations

import struct
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SD_DIR = ROOT / "patches/speed_density"
sys.path.insert(0, str(SD_DIR))

import patch_speed_density as sd

# Re-export all necessary symbols from speed_density
MAP_AXIS = sd.MAP_AXIS
LOW_RPM_AXIS = sd.LOW_RPM_AXIS
HIGH_RPM_AXIS = sd.HIGH_RPM_AXIS
HIGH_VE_TABLE = sd.HIGH_VE_TABLE

FREE_START = sd.FREE_START
COMPONENT_END = sd.COMPONENT_END
FREE_END = sd.FREE_END
DUAL_VE_START = sd.DUAL_VE_START
DUAL_VE_END = sd.DUAL_VE_END

LOW_VE_DESC_ADDR = sd.LOW_VE_DESC_ADDR
HIGH_VE_DESC_ADDR = sd.HIGH_VE_DESC_ADDR
LOW_RPM_AXIS_ADDR = sd.LOW_RPM_AXIS_ADDR
HIGH_RPM_AXIS_ADDR = sd.HIGH_RPM_AXIS_ADDR
LOW_VE_DATA_ADDR = sd.LOW_VE_DATA_ADDR
HIGH_VE_DATA_ADDR = sd.HIGH_VE_DATA_ADDR
MAP_AXIS_ADDR = sd.MAP_AXIS_ADDR
MAP_MIN_ADDR = sd.MAP_MIN_ADDR

AIRFLOW_TASK_PTR = sd.AIRFLOW_TASK_PTR
STOCK_MAF_AIRFLOW_TASK = sd.STOCK_MAF_AIRFLOW_TASK
FINAL_AIRFLOW_CALL_SEQUENCE_ADDR = sd.FINAL_AIRFLOW_CALL_SEQUENCE_ADDR
FINAL_AIRFLOW_CALL_SEQUENCE_STOCK = sd.FINAL_AIRFLOW_CALL_SEQUENCE_STOCK
FINAL_AIRFLOW_HELPER_PTR = sd.FINAL_AIRFLOW_HELPER_PTR
STOCK_FINAL_AIRFLOW_HELPER = sd.STOCK_FINAL_AIRFLOW_HELPER
MAF_LOAD_FALLBACK_HELPER_PTR = sd.MAF_LOAD_FALLBACK_HELPER_PTR
STOCK_MAF_LOAD_FALLBACK_HELPER = sd.STOCK_MAF_LOAD_FALLBACK_HELPER
CONSTANT_ZERO_RETURN = sd.CONSTANT_ZERO_RETURN
CONSTANT_ZERO_RETURN_STOCK = sd.CONSTANT_ZERO_RETURN_STOCK
CALLER_RPM_CAPTURE_ADDR = sd.CALLER_RPM_CAPTURE_ADDR
CALLER_RPM_CAPTURE_STOCK = sd.CALLER_RPM_CAPTURE_STOCK
STOCK_ENGINE_LOAD_CALC_ADDR = sd.STOCK_ENGINE_LOAD_CALC_ADDR
STOCK_ENGINE_LOAD_CALC_SEQUENCE = sd.STOCK_ENGINE_LOAD_CALC_SEQUENCE
LOAD_FILTER_ALPHA_ADDR = sd.LOAD_FILTER_ALPHA_ADDR
LOAD_FILTER_ALPHA_STOCK = sd.LOAD_FILTER_ALPHA_STOCK
WRAPPER_ADDR = sd.WRAPPER_ADDR

MAF_CONVERSION_CALL_ADDRS = sd.MAF_CONVERSION_CALL_ADDRS
MAF_CONVERSION_CALL_STOCK = sd.MAF_CONVERSION_CALL_STOCK
MAF_CONVERSION_CALL_PATCHED = sd.MAF_CONVERSION_CALL_PATCHED
MAF_LIMIT_UPDATE_CALL_ADDR = sd.MAF_LIMIT_UPDATE_CALL_ADDR
MAF_LIMIT_UPDATE_CALL_STOCK = sd.MAF_LIMIT_UPDATE_CALL_STOCK
MAF_INPUT_DIAGNOSTIC_TASK_PTR = sd.MAF_INPUT_DIAGNOSTIC_TASK_PTR
STOCK_MAF_INPUT_DIAGNOSTIC_TASK = sd.STOCK_MAF_INPUT_DIAGNOSTIC_TASK
TEMPERATURE_MAF_CONDITION_TASK_PTRS = sd.TEMPERATURE_MAF_CONDITION_TASK_PTRS
STOCK_TEMPERATURE_MAF_CONDITION_TASK = sd.STOCK_TEMPERATURE_MAF_CONDITION_TASK
NOOP_TASK = sd.NOOP_TASK
P0102_SWITCH_ADDR = sd.P0102_SWITCH_ADDR
P0103_SWITCH_ADDR = sd.P0103_SWITCH_ADDR

apply_predictable_avls_calibration = sd.apply_predictable_avls_calibration
checked_write = sd.checked_write
f32 = sd.f32
be32 = sd.be32

# Load the candidate low-lift VE table as the starting point
CANDIDATE_BIN = ROOT / "master_patch" / "candidates" / "D2WD610H_idle_recovery_candidate.bin"
_cand_bytes = CANDIDATE_BIN.read_bytes()

_cand_ve = [
    list(struct.unpack_from(">13f", _cand_bytes, LOW_VE_DATA_ADDR + y * 13 * 4))
    for y in range(len(LOW_RPM_AXIS))
]

# 1. 0 RPM row matches 500 RPM row to prevent modeled air collapse on deep decel
_cand_ve[0] = list(_cand_ve[1])

# 2. 1600 RPM row smoothly bridges 1200 RPM and 2000 RPM (removes the +59% spike)
for c in range(len(MAP_AXIS)):
    _cand_ve[4][c] = round((_cand_ve[3][c] + _cand_ve[5][c]) / 2.0, 4)

SMOOTHED_LOW_VE_TABLE = tuple(val for row in _cand_ve for val in row)
assert len(SMOOTHED_LOW_VE_TABLE) == len(LOW_RPM_AXIS) * len(MAP_AXIS)

# Replace LOW_VE_TABLE with our smoothed table
LOW_VE_TABLE = SMOOTHED_LOW_VE_TABLE


def build_blobs() -> list[tuple[str, int, bytes]]:
    """Build all speed density flash blobs, using the smoothed low-lift table."""
    blobs = []
    # Copy all blobs from original sd except the low lift ve table
    for name, addr, data in sd.build_blobs():
        if name == "speed_density_low_lift_ve_table":
            blobs.append((
                "speed_density_low_lift_ve_table",
                LOW_VE_DATA_ADDR,
                b"".join(f32(value) for value in LOW_VE_TABLE),
            ))
        else:
            blobs.append((name, addr, data))
    return blobs


def apply_to_rom(rom: bytearray) -> list[tuple[str, int, bytes]]:
    """Apply speed density component with smoothed low VE table to ROM."""
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
    checked_write(
        rom,
        CONSTANT_ZERO_RETURN,
        CONSTANT_ZERO_RETURN_STOCK,
        CONSTANT_ZERO_RETURN_STOCK,
        "stock constant-zero return helper",
    )
    checked_write(
        rom,
        CALLER_RPM_CAPTURE_ADDR,
        CALLER_RPM_CAPTURE_STOCK,
        CALLER_RPM_CAPTURE_STOCK,
        "caller RPM capture into FR15",
    )
    checked_write(
        rom,
        STOCK_ENGINE_LOAD_CALC_ADDR,
        STOCK_ENGINE_LOAD_CALC_SEQUENCE,
        STOCK_ENGINE_LOAD_CALC_SEQUENCE,
        "retained load calculation and FR15 divisor",
    )
    checked_write(
        rom,
        LOAD_FILTER_ALPHA_ADDR,
        LOAD_FILTER_ALPHA_STOCK,
        LOAD_FILTER_ALPHA_STOCK,
        "retained stock load smoothing alpha",
    )
    checked_write(
        rom,
        MAF_LOAD_FALLBACK_HELPER_PTR,
        be32(STOCK_MAF_LOAD_FALLBACK_HELPER),
        be32(CONSTANT_ZERO_RETURN),
        "local obsolete MAF load-fallback bypass",
    )
    for call_address in MAF_CONVERSION_CALL_ADDRS:
        checked_write(
            rom,
            call_address,
            MAF_CONVERSION_CALL_STOCK,
            MAF_CONVERSION_CALL_PATCHED,
            "bypassed raw MAF conversion call",
        )
    checked_write(
        rom,
        MAF_LIMIT_UPDATE_CALL_ADDR,
        MAF_LIMIT_UPDATE_CALL_STOCK,
        MAF_CONVERSION_CALL_PATCHED,
        "bypassed MAF limit update call",
    )
    checked_write(
        rom,
        MAF_INPUT_DIAGNOSTIC_TASK_PTR,
        be32(STOCK_MAF_INPUT_DIAGNOSTIC_TASK),
        be32(NOOP_TASK),
        "MAF-input diagnostic task pointer",
    )
    for task_pointer in TEMPERATURE_MAF_CONDITION_TASK_PTRS:
        checked_write(
            rom,
            task_pointer,
            be32(STOCK_TEMPERATURE_MAF_CONDITION_TASK),
            be32(NOOP_TASK),
            "temperature/MAF diagnostic task pointer",
        )
    for dtc_switch in (P0102_SWITCH_ADDR, P0103_SWITCH_ADDR):
        checked_write(
            rom, dtc_switch, b"\x01", b"\x00", "cleared MAF-input DTC switch"
        )
    for _, address, data in blobs:
        rom[address : address + len(data)] = data
    return blobs
