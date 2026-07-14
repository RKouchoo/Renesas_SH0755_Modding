#!/usr/bin/env python3
"""Build the D2WD610H conservative 5 psi / 98 RON base-turbo calibration.

The image is not stacked onto a generated ROM.  It reconstructs the verified
combined boost + single-front-A/F/rear-O2-delete image from the hash-pinned root
stock ROM, proves that stage is byte-identical to the canonical combined
artifact, then applies calibration-only changes to an in-memory copy.

This is a spring-pressure commissioning baseline, not a finished tune.  The
5 psi wastegate spring is the only source of boost: base WGDC, proportional
gain, and the final duty clamp are all zero.  The boost patch remains enabled
so its hard MAP fuel cut remains active.  Injector data is translated from a
hash-pinned A4TE002B factory STI-pink ROM; AVLS is brought in earlier, tuned
load axes extend to 3.0 g/rev, and the operating limiter is set to 6800/6770 RPM.

Usage: python3 base_turbo_map/build_base_turbo_map.py [out.bin]
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import math
import os
import struct
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PATCH_DIR = ROOT / "patch"
sys.path.insert(0, str(PATCH_DIR))

import extract_srf  # noqa: E402
import patch_boost as boost  # noqa: E402
import patch_combined as combined_patch  # noqa: E402


STOCK = ROOT / "2005 BLE MT.bin"
BASE_STOCK = ROOT / "base_roms" / "2005 BLE MT.bin"
SOURCE_SRF = ROOT / "base_roms" / "2005 BLE MT.srf"
COMBINED_ARTIFACT = PATCH_DIR / "D2WD610H_boost_single_front_af.bin"
PINK_INJECTOR_DONOR = (
    ROOT / "base_roms" / "A4TE002B-2003-JDM-Subaru-Impreza-STi.hex"
)
DEFAULT_OUT = HERE / "D2WD610H_5psi_98RON_base_turbo.bin"

ROM_SIZE = 0x80000
STOCK_SHA256 = boost.STOCK_SHA256
COMBINED_SHA256 = "019e06e509afce2e798bfe29543e2536524c259d3ab6683c7dd3131ee069fb5e"
PINK_INJECTOR_DONOR_SIZE = 0x30000
PINK_INJECTOR_DONOR_SHA256 = (
    "e3cc868a51476aaa25c1ffb63e8af8ba3e35ca4ace404e842f193bf117754b44"
)

# RomRaider's Subaru checksum table.  Entry 0 covers 0x2000 through the
# 32-bit word beginning at 0x7FAF4.  The stored difference is at +0x08.
CHECKSUM_TABLE_ADDR = 0x7FB80
CHECKSUM_TOTAL = 0x5AA5A55A

# Calibration table locations from the matching combined RomRaider definition.
PRIMARY_OL_A_ADDR = 0x7777C
PRIMARY_OL_B_ADDR = 0x77868
PRIMARY_OL_A_LOAD_AXIS = 0x7771C
PRIMARY_OL_B_LOAD_AXIS = 0x77808
PRIMARY_OL_A_RPM_AXIS = 0x77754
PRIMARY_OL_B_RPM_AXIS = 0x77840
PRIMARY_OL_X = 14
PRIMARY_OL_Y = 10

CL_OL_DELAY_ADDR = 0x772DC

TIMING_LOAD_AXIS_ADDR = 0x780BC
TIMING_X = 15
TIMING_MAPS = (
    ("Base Timing A", 0x78AA0, 0x78A68, 14),
    ("Base Timing B", 0x78BAC, 0x78B74, 14),
    ("Base Timing C", 0x78CD0, 0x78C80, 20),
    ("Base Timing D", 0x78E34, 0x78DFC, 14),
    ("Base Timing E", 0x78F40, 0x78F08, 14),
    ("Base Timing F", 0x79064, 0x79014, 20),
)

KCA_MAPS = (
    ("Knock Correction Advance Max A", 0x7924C, 0x791D8, 0x79214, 14),
    ("Knock Correction Advance Max B", 0x793AC, 0x79320, 0x7935C, 20),
)

IAT_TIMING_COMP_ADDR = 0x7834C
REV_LIMIT_A_ADDR = 0x7644C

# Installed Denso/Subaru STI pink-injector calibration.  The source bytes are
# pinned from the 2003 JDM STI A4TE002B factory ROM.  Its 16-bit RomRaider
# conversion is 2707090/raw and .004 ms/count.  D2WD610H uses a different
# underlying flow constant and finer latency resolution, so the displayed
# OEM values are translated rather than copying the raw bytes verbatim.
INJECTOR_FLOW_ADDR = 0x76014
INJECTOR_FLOW_DISPLAY_CONSTANT = 1804727.0
INJECTOR_LATENCY_ADDR = 0x7B318
INJECTOR_LATENCY_SIZE = 10
INJECTOR_VOLTAGE_AXIS_ADDR = 0x7B304
EXPECTED_INJECTOR_VOLTAGE_AXIS = (6.5, 9.0, 11.5, 14.0, 16.5)
PINK_DONOR_FLOW_ADDR = 0x2866B
PINK_DONOR_FLOW_DISPLAY_CONSTANT = 2707090.0
PINK_DONOR_LATENCY_ADDR = 0x28673
PINK_DONOR_EXPECTED_FLOW_RAW = 4900
PINK_DONOR_EXPECTED_LATENCY_RAW = (697, 372, 245, 171, 95)
PINK_DONOR_LATENCY_SCALE_MS = 0.004
D2WD_LATENCY_SCALE_MS = 0.00025

CRANKING_IPW_MAPS = (
    ("Cranking Fuel Injector Pulse Width A", 0x76B76, 16),
    ("Cranking Fuel Injector Pulse Width B", 0x76B96, 16),
    ("Cranking Fuel Injector Pulse Width C", 0x76BB6, 16),
    ("Cranking Fuel Injector Pulse Width D", 0x76BD6, 16),
)
TIP_IN_IPW_MAPS = (
    ("Throttle Tip-in Enrichment A", 0x7739C, 5),
    ("Throttle Tip-in Enrichment B", 0x773BC, 5),
)
MIN_TIP_IN_ACTIVATION_ADDR = 0x763E0

# AVLS comes in under load from 2500 RPM and is forced onto high cam by 3200
# RPM.  The stock 10-load-unit hysteresis is retained to avoid chatter.
AVLS_THRESHOLD_1_ADDR = 0x7D67C
AVLS_THRESHOLD_2_ADDR = 0x7D6B4
AVLS_THRESHOLD_1 = (100.0, 100.0, 25.0, 20.0, 15.0, 10.0, 5.0)
AVLS_THRESHOLD_2 = (100.0, 100.0, 60.0, 35.0, 20.0, 10.0, 0.0)
AVLS_HYSTERESIS_A_ADDR = 0x7D480
AVLS_HYSTERESIS_B_ADDR = 0x7D484
AVLS_ACTUATION_MIN_RPM_ADDR = 0x7D4AC
AVLS_RELEASE_RPM_ADDR = 0x7D4B8
AVLS_ENGAGE_RPM_ADDR = 0x7D4BC
AVLS_HYSTERESIS = 10.0
AVLS_ACTUATION_MIN_RPM = 2500.0
AVLS_RELEASE_RPM = 3000.0
AVLS_ENGAGE_RPM = 3200.0

# Hardware-dependent MAF calibration remains unchanged and verified.
MAF_VOLTAGE_AXIS_ADDR = 0x7B4B8
MAF_SCALING_ADDR = 0x7B568
MAF_SCALING_COUNT = 44
MAF_LIMIT_ADDR = 0x73C68
ENGINE_LOAD_LIMIT_ADDR = 0x17620

STOCK_FUEL_LOAD_AXIS = (
    0.15, 0.35, 0.55, 0.70, 0.83, 0.96, 1.09,
    1.22, 1.35, 1.48, 1.61, 1.74, 1.87, 2.00,
)
TUNED_FUEL_LOAD_AXIS = (
    0.15, 0.35, 0.55, 0.70, 0.83, 0.96, 1.09,
    1.22, 1.40, 1.60, 1.85, 2.15, 2.50, 3.00,
)
EXPECTED_FUEL_RPM_AXIS = (
    3200.0, 3600.0, 4000.0, 4400.0, 4800.0,
    5200.0, 5600.0, 6000.0, 6400.0, 6800.0,
)
STOCK_TIMING_LOAD_AXIS = (
    0.15, 0.35, 0.45, 0.55, 0.70, 0.83, 0.96, 1.09,
    1.22, 1.35, 1.48, 1.61, 1.74, 1.87, 2.00,
)
TUNED_TIMING_LOAD_AXIS = (
    0.15, 0.35, 0.45, 0.55, 0.70, 0.83, 0.96, 1.09,
    1.22, 1.40, 1.60, 1.85, 2.15, 2.50, 3.00,
)

# Richest permitted target (lambda) at each high-load column.  Existing cells
# are retained whenever they are already richer.  At >=6000 RPM, columns at
# and above 1.22 g/rev get another 0.01 lambda of enrichment.
FUEL_LAMBDA_CAPS = {
    0.96: 0.93,
    1.09: 0.88,
    1.22: 0.83,
    1.40: 0.80,
    1.60: 0.78,
    1.85: 0.78,
    2.15: 0.78,
    2.50: 0.78,
    3.00: 0.78,
}

# Full-boost base-timing ceiling for load >=1.60 g/rev.  Torque-onset timing is
# one to two degrees more conservative than the first baseline.  The 1.09,
# 1.22, and 1.40 columns use +8, +4, and +2 degrees respectively.  Existing
# timing is never increased.  Positive KCA is independently removed from
# >=1.22 g/rev.  All six base maps are covered, including early-AVLS paths.
FULL_BOOST_TIMING_CAP = (
    (2000.0, -2.0),
    (2400.0, 0.0),
    (2800.0, 2.0),
    (3200.0, 4.0),
    (3600.0, 5.0),
    (4000.0, 6.0),
    (4400.0, 7.0),
    (4800.0, 8.0),
    (5200.0, 9.0),
    (5600.0, 10.0),
    (6000.0, 11.0),
    (6400.0, 12.0),
    (6800.0, 13.0),
)
TIMING_LOAD_OFFSETS = {
    1.09: 8.0,
    1.22: 4.0,
    1.40: 2.0,
    1.60: 0.0,
    1.85: 0.0,
    2.15: 0.0,
    2.50: 0.0,
    3.00: 0.0,
}

# More assertive high-IAT retard than stock, still using the stock 50..110 C
# axis.  Quantized values are 0, -1.05, -2.11, -4.22, -6.33, -8.09, -10.20 deg.
IAT_TIMING_COMP_RAW = bytes((128, 125, 122, 116, 110, 105, 99))

REV_LIMIT_CUT_RPM = 6800.0
REV_LIMIT_RESUME_RPM = 6770.0
SOFT_OVERBOOST_PSI = 5.5
HARD_OVERBOOST_PSI = 6.5
BOOST_TARGET_PSI = (1.482142857, 2.285714286, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0)
BOOST_TARGET_NATIVE = tuple(
    boost.ATM_PRESSURE_NATIVE + psi * boost.NATIVE_PER_PSI for psi in BOOST_TARGET_PSI
)


CALIBRATION_REGIONS = (
    ("Primary Open Loop Load Axis A", PRIMARY_OL_A_LOAD_AXIS, PRIMARY_OL_X * 4),
    ("Primary Open Loop Load Axis B", PRIMARY_OL_B_LOAD_AXIS, PRIMARY_OL_X * 4),
    ("Primary Open Loop Fueling A", PRIMARY_OL_A_ADDR, PRIMARY_OL_X * PRIMARY_OL_Y),
    ("Primary Open Loop Fueling B", PRIMARY_OL_B_ADDR, PRIMARY_OL_X * PRIMARY_OL_Y),
    ("CL to OL Delay", CL_OL_DELAY_ADDR, 4),
    ("Base Timing Load Axis", TIMING_LOAD_AXIS_ADDR, TIMING_X * 4),
    *((name, addr, TIMING_X * rows) for name, addr, _, rows in TIMING_MAPS),
    *((name + " Load Axis", load_addr, TIMING_X * 4)
      for name, _, load_addr, _, _ in KCA_MAPS),
    *((name, addr, TIMING_X * rows) for name, addr, _, _, rows in KCA_MAPS),
    ("Timing Compensation IAT", IAT_TIMING_COMP_ADDR, len(IAT_TIMING_COMP_RAW)),
    ("Rev Limit A", REV_LIMIT_A_ADDR, 8),
    ("Injector Flow Scaling", INJECTOR_FLOW_ADDR, 4),
    ("Injector Latency", INJECTOR_LATENCY_ADDR, INJECTOR_LATENCY_SIZE),
    *((name, addr, count * 2) for name, addr, count in CRANKING_IPW_MAPS),
    *((name, addr, count * 2) for name, addr, count in TIP_IN_IPW_MAPS),
    ("Minimum Tip-in Enrichment Activation", MIN_TIP_IN_ACTIVATION_ADDR, 4),
    ("AVLS Switchover Load Threshold 1", AVLS_THRESHOLD_1_ADDR, len(AVLS_THRESHOLD_1) * 4),
    ("AVLS Switchover Load Threshold 2", AVLS_THRESHOLD_2_ADDR, len(AVLS_THRESHOLD_2) * 4),
    ("AVLS Actuation Minimum RPM", AVLS_ACTUATION_MIN_RPM_ADDR, 4),
    ("AVLS High Cam Release RPM", AVLS_RELEASE_RPM_ADDR, 4),
    ("AVLS High Cam Engage RPM", AVLS_ENGAGE_RPM_ADDR, 4),
    ("Boost Target", boost.TARGET_DATA, len(BOOST_TARGET_NATIVE) * 4),
    ("Boost Wastegate Duty", boost.BASE_DATA, len(boost.BASE_DUTY)),
    ("Boost Kp", boost.KP_ADDR, 4),
    ("Boost Max Duty Ratio", boost.MAXR_ADDR, 4),
    ("Boost Soft Overboost", boost.OVERB_ADDR, 4),
    ("Boost Hard Overboost", boost.OVERB_FC_ADDR, 4),
    ("Subaru checksum", CHECKSUM_TABLE_ADDR + 8, 4),
)


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def f32(value: float) -> bytes:
    return struct.pack(">f", value)


def pack_floats(values: tuple[float, ...]) -> bytes:
    return b"".join(f32(value) for value in values)


def read_floats(image: bytes | bytearray, address: int, count: int) -> tuple[float, ...]:
    return struct.unpack_from(">" + "f" * count, image, address)


def assert_axis(
    image: bytes | bytearray,
    address: int,
    expected: tuple[float, ...],
    label: str,
) -> tuple[float, ...]:
    actual = read_floats(image, address, len(expected))
    if any(abs(left - right) > 1e-5 for left, right in zip(actual, expected)):
        raise SystemExit(f"REFUSING: unexpected {label} at 0x{address:05X}: {actual}")
    return actual


def pink_injector_calibration() -> tuple[float, tuple[int, ...], float]:
    """Translate the pinned A4TE002B STI-pink calibration into D2WD units.

    Returns D2WD's raw float injector scale, five D2WD latency counts, and the
    donor's estimated RomRaider flow display.  Hard-coded source values are
    checked as a second guard in addition to the complete donor-ROM hash.
    """
    donor = PINK_INJECTOR_DONOR.read_bytes()
    if len(donor) != PINK_INJECTOR_DONOR_SIZE:
        raise SystemExit("REFUSING: STI pink-injector donor ROM has the wrong size")
    if sha256(donor) != PINK_INJECTOR_DONOR_SHA256:
        raise SystemExit("REFUSING: STI pink-injector donor ROM hash changed")
    if donor[0x200:0x208] != b"A4TE002B":
        raise SystemExit("REFUSING: STI pink-injector donor CALID is not A4TE002B")

    flow_raw = struct.unpack_from(">H", donor, PINK_DONOR_FLOW_ADDR)[0]
    latency_raw = struct.unpack_from(">5H", donor, PINK_DONOR_LATENCY_ADDR)
    if flow_raw != PINK_DONOR_EXPECTED_FLOW_RAW:
        raise SystemExit(f"REFUSING: unexpected STI pink flow raw value {flow_raw}")
    if latency_raw != PINK_DONOR_EXPECTED_LATENCY_RAW:
        raise SystemExit(f"REFUSING: unexpected STI pink latency raw values {latency_raw}")

    estimated_flow = PINK_DONOR_FLOW_DISPLAY_CONSTANT / flow_raw
    d2wd_flow_raw = INJECTOR_FLOW_DISPLAY_CONSTANT / estimated_flow
    latency_ratio = PINK_DONOR_LATENCY_SCALE_MS / D2WD_LATENCY_SCALE_MS
    d2wd_latency_raw = tuple(round(value * latency_ratio) for value in latency_raw)
    if any(
        abs(target * D2WD_LATENCY_SCALE_MS - source * PINK_DONOR_LATENCY_SCALE_MS)
        > 1e-12
        for source, target in zip(latency_raw, d2wd_latency_raw)
    ):
        raise AssertionError("STI pink latency cannot be represented exactly in D2WD units")
    return d2wd_flow_raw, d2wd_latency_raw, estimated_flow


def scale_u16_table(
    reference: bytes,
    address: int,
    count: int,
    ratio: float,
    label: str,
) -> bytes:
    old = struct.unpack_from(">" + "H" * count, reference, address)
    # Round toward a longer pulse so quantization cannot make the starting
    # estimate leaner than the universal injector-ratio multiplier.
    new = tuple(math.ceil(value * ratio - 1e-12) for value in old)
    if any(not 0 <= value <= 0xFFFF for value in new):
        raise ValueError(f"{label} cannot be represented as uint16")
    return struct.pack(">" + "H" * count, *new)


def interpolate(points: tuple[tuple[float, float], ...], value: float) -> float:
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= value <= x1:
            fraction = (value - x0) / (x1 - x0)
            return y0 + fraction * (y1 - y0)
    raise AssertionError("interpolation range failure")


def fuel_raw_for_lambda(lambda_target: float) -> int:
    # Primary OL lambda = 1 / (1 + raw/128).  Round toward richer so the
    # encoded cell cannot be leaner than the requested cap.
    raw = math.ceil(((1.0 / lambda_target) - 1.0) * 128.0 - 1e-12)
    if not 0 <= raw <= 255:
        raise ValueError(f"lambda target {lambda_target} cannot be encoded")
    return raw


def timing_raw_at_or_below(degrees: float) -> int:
    # Base timing = raw*0.3515625 - 20.  Floor toward less advance.
    raw = math.floor((degrees + 20.0) / 0.3515625 + 1e-12)
    return max(0, min(255, raw))


def kca_raw_at_or_below(degrees: float) -> int:
    # KCA max = raw*0.3515625.  Floor toward less positive advance.
    raw = math.floor(degrees / 0.3515625 + 1e-12)
    return max(0, min(255, raw))


def merge_ranges(addresses: set[int]) -> list[tuple[int, int]]:
    if not addresses:
        return []
    result: list[tuple[int, int]] = []
    start = previous = min(addresses)
    for address in sorted(addresses)[1:]:
        if address != previous + 1:
            result.append((start, previous))
            start = address
        previous = address
    result.append((start, previous))
    return result


def build_primary_open_loop(reference: bytes) -> tuple[bytes, bytes]:
    assert_axis(
        reference, PRIMARY_OL_A_LOAD_AXIS, STOCK_FUEL_LOAD_AXIS, "Primary OL A load axis"
    )
    assert_axis(
        reference, PRIMARY_OL_B_LOAD_AXIS, STOCK_FUEL_LOAD_AXIS, "Primary OL B load axis"
    )
    fuel_rpm = assert_axis(
        reference, PRIMARY_OL_A_RPM_AXIS, EXPECTED_FUEL_RPM_AXIS, "Primary OL A RPM axis"
    )
    assert_axis(
        reference, PRIMARY_OL_B_RPM_AXIS, EXPECTED_FUEL_RPM_AXIS, "Primary OL B RPM axis"
    )

    old_a = reference[PRIMARY_OL_A_ADDR:PRIMARY_OL_A_ADDR + PRIMARY_OL_X * PRIMARY_OL_Y]
    old_b = reference[PRIMARY_OL_B_ADDR:PRIMARY_OL_B_ADDR + PRIMARY_OL_X * PRIMARY_OL_Y]
    new_a = bytearray(old_a)
    new_b = bytearray(old_b)

    for y_index, rpm in enumerate(fuel_rpm):
        for x_index, load in enumerate(TUNED_FUEL_LOAD_AXIS):
            rounded_load = round(load, 2)
            if rounded_load not in FUEL_LAMBDA_CAPS:
                continue
            lambda_cap = FUEL_LAMBDA_CAPS[rounded_load]
            if rpm >= 6000.0 and load >= 1.22 - 1e-5:
                lambda_cap -= 0.01
            required = fuel_raw_for_lambda(lambda_cap)
            offset = y_index * PRIMARY_OL_X + x_index
            # Use the richer stock bank as the common minimum, then apply the
            # turbo cap.  This avoids introducing a leaner bank target.
            common = max(old_a[offset], old_b[offset], required)
            new_a[offset] = common
            new_b[offset] = common

    return bytes(new_a), bytes(new_b)


def build_timing_map(
    reference: bytes,
    data_address: int,
    rpm_axis_address: int,
    rows: int,
    label: str,
) -> bytes:
    assert_axis(
        reference, TIMING_LOAD_AXIS_ADDR, STOCK_TIMING_LOAD_AXIS, "base-timing load axis"
    )
    rpm_axis = read_floats(reference, rpm_axis_address, rows)
    old = reference[data_address:data_address + TIMING_X * rows]
    new = bytearray(old)

    for y_index, rpm in enumerate(rpm_axis):
        if rpm < 2000.0:
            continue
        full_boost_cap = interpolate(FULL_BOOST_TIMING_CAP, rpm)
        for x_index, load in enumerate(TUNED_TIMING_LOAD_AXIS):
            rounded_load = round(load, 2)
            if rounded_load not in TIMING_LOAD_OFFSETS:
                continue
            cap = full_boost_cap + TIMING_LOAD_OFFSETS[rounded_load]
            cap_raw = timing_raw_at_or_below(cap)
            offset = y_index * TIMING_X + x_index
            new[offset] = min(old[offset], cap_raw)

    if len(new) != TIMING_X * rows:
        raise AssertionError(f"{label} size changed")
    return bytes(new)


def build_kca_map(
    reference: bytes,
    data_address: int,
    load_axis_address: int,
    rpm_axis_address: int,
    rows: int,
    label: str,
) -> bytes:
    assert_axis(
        reference, load_axis_address, STOCK_TIMING_LOAD_AXIS, f"{label} load axis"
    )
    rpm_axis = read_floats(reference, rpm_axis_address, rows)
    old = reference[data_address:data_address + TIMING_X * rows]
    new = bytearray(old)

    for y_index, rpm in enumerate(rpm_axis):
        if rpm < 2000.0:
            continue
        for x_index, load in enumerate(TUNED_TIMING_LOAD_AXIS):
            rounded_load = round(load, 2)
            if rounded_load == 1.09:
                cap_raw = kca_raw_at_or_below(2.0)
            elif rounded_load >= 1.22:
                cap_raw = 0
            else:
                continue
            offset = y_index * TIMING_X + x_index
            new[offset] = min(old[offset], cap_raw)

    if len(new) != TIMING_X * rows:
        raise AssertionError(f"{label} size changed")
    return bytes(new)


def checksum_value(image: bytes | bytearray) -> tuple[int, int, int]:
    start, end, stored = struct.unpack_from(">III", image, CHECKSUM_TABLE_ADDR)
    if (start, end) != (0x2000, 0x7FAF7):
        raise SystemExit(
            "REFUSING: unexpected Subaru checksum range "
            f"0x{start:X}..0x{end:X} at 0x{CHECKSUM_TABLE_ADDR:05X}"
        )
    word_sum = sum(struct.unpack_from(">I", image, address)[0]
                   for address in range(start, end, 4)) & 0xFFFFFFFF
    calculated = (CHECKSUM_TOTAL - word_sum) & 0xFFFFFFFF
    return stored, calculated, word_sum


def apply_calibration(rom: bytearray, reference: bytes) -> dict[str, tuple[int, bytes]]:
    if bytes(rom) != reference:
        raise SystemExit("REFUSING: calibration input differs from pinned combined reference")

    writes: dict[str, tuple[int, bytes]] = {}
    owned: set[int] = set()

    def write(label: str, address: int, data: bytes) -> None:
        region = set(range(address, address + len(data)))
        overlap = owned & region
        if overlap:
            first = min(overlap)
            raise AssertionError(f"calibration write overlap at 0x{first:05X}: {label}")
        if rom[address:address + len(data)] != reference[address:address + len(data)]:
            raise SystemExit(f"REFUSING: {label} source guard failed at 0x{address:05X}")
        rom[address:address + len(data)] = data
        owned.update(region)
        writes[label] = (address, data)

    fuel_a, fuel_b = build_primary_open_loop(reference)
    write("Primary Open Loop Load Axis A", PRIMARY_OL_A_LOAD_AXIS, pack_floats(TUNED_FUEL_LOAD_AXIS))
    write("Primary Open Loop Load Axis B", PRIMARY_OL_B_LOAD_AXIS, pack_floats(TUNED_FUEL_LOAD_AXIS))
    write("Primary Open Loop Fueling A", PRIMARY_OL_A_ADDR, fuel_a)
    write("Primary Open Loop Fueling B", PRIMARY_OL_B_ADDR, fuel_b)

    # A zero delay makes the enriched Primary OL target decide the transition,
    # avoiding the stock high-load delay path below the original 3600/4000 RPM
    # thresholds.
    write("CL to OL Delay", CL_OL_DELAY_ADDR, struct.pack(">HH", 0, 0))

    write("Base Timing Load Axis", TIMING_LOAD_AXIS_ADDR, pack_floats(TUNED_TIMING_LOAD_AXIS))
    for label, data_address, rpm_axis_address, rows in TIMING_MAPS:
        write(
            label,
            data_address,
            build_timing_map(reference, data_address, rpm_axis_address, rows, label),
        )

    for label, data_address, load_axis_address, rpm_axis_address, rows in KCA_MAPS:
        write(label + " Load Axis", load_axis_address, pack_floats(TUNED_TIMING_LOAD_AXIS))
        write(
            label,
            data_address,
            build_kca_map(
                reference, data_address, load_axis_address, rpm_axis_address, rows, label
            ),
        )

    write("Timing Compensation IAT", IAT_TIMING_COMP_ADDR, IAT_TIMING_COMP_RAW)
    # Firmware/Ghidra ordering is cut first, resume second.
    write(
        "Rev Limit A",
        REV_LIMIT_A_ADDR,
        f32(REV_LIMIT_CUT_RPM) + f32(REV_LIMIT_RESUME_RPM),
    )

    # Translate the exact factory STI-pink values into this ECU's raw units.
    # Absolute cranking/tip-in pulse widths use the injector-scale ratio as the
    # documented universal starting multiplier; first-start logs still decide
    # their final values on this six-cylinder installation.
    pink_flow_raw, pink_latency_raw, _ = pink_injector_calibration()
    stock_flow_raw = struct.unpack_from(">f", reference, INJECTOR_FLOW_ADDR)[0]
    injector_ratio = pink_flow_raw / stock_flow_raw
    if not 0.0 < injector_ratio < 1.0:
        raise SystemExit(f"REFUSING: invalid injector scale ratio {injector_ratio}")
    assert_axis(
        reference,
        INJECTOR_VOLTAGE_AXIS_ADDR,
        EXPECTED_INJECTOR_VOLTAGE_AXIS,
        "injector latency voltage axis",
    )
    write("Injector Flow Scaling", INJECTOR_FLOW_ADDR, f32(pink_flow_raw))
    write(
        "Injector Latency",
        INJECTOR_LATENCY_ADDR,
        struct.pack(">5H", *pink_latency_raw),
    )
    for label, address, count in CRANKING_IPW_MAPS:
        write(label, address, scale_u16_table(reference, address, count, injector_ratio, label))
    for label, address, count in TIP_IN_IPW_MAPS:
        write(label, address, scale_u16_table(reference, address, count, injector_ratio, label))
    min_tip_in_raw = struct.unpack_from(">f", reference, MIN_TIP_IN_ACTIVATION_ADDR)[0]
    write(
        "Minimum Tip-in Enrichment Activation",
        MIN_TIP_IN_ACTIVATION_ADDR,
        f32(min_tip_in_raw * injector_ratio),
    )

    # Earlier AVLS: retain stock hysteresis, allow oil-valve actuation at 2500,
    # lower both load-dependent curves, and force high cam by 3200 RPM.
    if read_floats(reference, AVLS_HYSTERESIS_A_ADDR, 1)[0] != AVLS_HYSTERESIS:
        raise SystemExit("REFUSING: AVLS hysteresis A is not the expected stock value")
    if read_floats(reference, AVLS_HYSTERESIS_B_ADDR, 1)[0] != AVLS_HYSTERESIS:
        raise SystemExit("REFUSING: AVLS hysteresis B is not the expected stock value")
    write(
        "AVLS Switchover Load Threshold 1",
        AVLS_THRESHOLD_1_ADDR,
        pack_floats(AVLS_THRESHOLD_1),
    )
    write(
        "AVLS Switchover Load Threshold 2",
        AVLS_THRESHOLD_2_ADDR,
        pack_floats(AVLS_THRESHOLD_2),
    )
    write("AVLS Actuation Minimum RPM", AVLS_ACTUATION_MIN_RPM_ADDR, f32(AVLS_ACTUATION_MIN_RPM))
    write("AVLS High Cam Release RPM", AVLS_RELEASE_RPM_ADDR, f32(AVLS_RELEASE_RPM))
    write("AVLS High Cam Engage RPM", AVLS_ENGAGE_RPM_ADDR, f32(AVLS_ENGAGE_RPM))

    # Five-psi spring-only commissioning: no electronic duty can be produced,
    # even if a table or gain is accidentally non-zero.  Keep enable=01 so the
    # separate hard-MAP fuel-cut wrapper is active.
    write("Boost Target", boost.TARGET_DATA, pack_floats(BOOST_TARGET_NATIVE))
    write("Boost Wastegate Duty", boost.BASE_DATA, bytes(len(boost.BASE_DUTY)))
    write("Boost Kp", boost.KP_ADDR, f32(0.0))
    write("Boost Max Duty Ratio", boost.MAXR_ADDR, f32(0.0))
    write(
        "Boost Soft Overboost",
        boost.OVERB_ADDR,
        f32(boost.ATM_PRESSURE_NATIVE + SOFT_OVERBOOST_PSI * boost.NATIVE_PER_PSI),
    )
    write(
        "Boost Hard Overboost",
        boost.OVERB_FC_ADDR,
        f32(boost.ATM_PRESSURE_NATIVE + HARD_OVERBOOST_PSI * boost.NATIVE_PER_PSI),
    )

    if rom[boost.BOOST_ENABLE_ADDR] != 0x01:
        raise SystemExit("REFUSING: boost patch is not enabled in combined reference")
    if rom[0x7D91C] != 0x01:
        raise SystemExit("REFUSING: single-front-A/F patch is not enabled in combined reference")

    # Air-metering data cannot be guessed without the installed MAF/housing.
    # The MAF limiter is already at its uint16 encoding maximum, and the 4.0
    # g/rev engine-load limit remains above the expanded 3.0 g/rev tune axes.
    for address, size, label in (
        (INJECTOR_VOLTAGE_AXIS_ADDR, len(EXPECTED_INJECTOR_VOLTAGE_AXIS) * 4,
         "injector voltage axis"),
        (MAF_VOLTAGE_AXIS_ADDR, MAF_SCALING_COUNT * 4, "MAF voltage axis"),
        (MAF_SCALING_ADDR, MAF_SCALING_COUNT * 4, "MAF scaling"),
        (MAF_LIMIT_ADDR, 4, "MAF maximum limit"),
        (ENGINE_LOAD_LIMIT_ADDR, 4, "engine-load limit"),
    ):
        if rom[address:address + size] != reference[address:address + size]:
            raise AssertionError(f"hardware-specific {label} changed unexpectedly")
    if reference[MAF_LIMIT_ADDR:MAF_LIMIT_ADDR + 4] != b"\xFF\xFF\xFF\xFF":
        raise SystemExit("REFUSING: MAF limit is not already at maximum encoding")
    if read_floats(reference, ENGINE_LOAD_LIMIT_ADDR, 1)[0] != 4.0:
        raise SystemExit("REFUSING: engine-load limit is not the expected 4.0 g/rev")

    # Checksum data is outside its own covered range, so updating the stored
    # difference cannot perturb the calculation.
    _, calculated, _ = checksum_value(rom)
    checksum_address = CHECKSUM_TABLE_ADDR + 8
    if set(range(checksum_address, checksum_address + 4)) & owned:
        raise AssertionError("checksum write overlaps calibration ownership")
    rom[checksum_address:checksum_address + 4] = struct.pack(">I", calculated)
    writes["Subaru checksum"] = (checksum_address, struct.pack(">I", calculated))

    stored, recalculated, _ = checksum_value(rom)
    if stored != recalculated:
        raise AssertionError("Subaru checksum correction did not validate")
    return writes


def refuse_output_alias(output: Path) -> None:
    protected = (STOCK, BASE_STOCK, SOURCE_SRF, COMBINED_ARTIFACT, PINK_INJECTOR_DONOR)
    output_real = Path(os.path.realpath(output))
    for path in protected:
        if output_real == Path(os.path.realpath(path)):
            raise SystemExit(f"REFUSING: output aliases protected source: {path}")
        if output.exists() and path.exists() and os.path.samefile(output, path):
            raise SystemExit(f"REFUSING: output is a hard link to protected source: {path}")


def build_image() -> tuple[bytes, bytes, bytes, dict[str, tuple[int, bytes]]]:
    stock = STOCK.read_bytes()
    if len(stock) != ROM_SIZE or sha256(stock) != STOCK_SHA256:
        raise SystemExit("REFUSING: root stock ROM is not the pinned D2WD610H image")
    if BASE_STOCK.read_bytes() != stock:
        raise SystemExit("REFUSING: base_roms stock BIN differs from canonical root stock ROM")

    try:
        srf_payload, _, _, _ = extract_srf.extract_memd(SOURCE_SRF)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"REFUSING: SRF provenance check failed: {exc}") from exc
    if srf_payload != stock:
        raise SystemExit("REFUSING: original SRF MEMD payload differs from canonical stock ROM")

    rebuilt, _, _, _, _ = combined_patch.build_combined(stock)
    combined_reference = bytes(rebuilt)
    if sha256(combined_reference) != COMBINED_SHA256:
        raise SystemExit("REFUSING: reconstructed combined stage has an unexpected SHA-256")
    if COMBINED_ARTIFACT.read_bytes() != combined_reference:
        raise SystemExit("REFUSING: canonical combined artifact differs from reconstructed stage")

    rom = bytearray(combined_reference)
    writes = apply_calibration(rom, combined_reference)
    return stock, combined_reference, bytes(rom), writes


def main() -> None:
    if len(sys.argv) > 2:
        raise SystemExit("usage: python3 base_turbo_map/build_base_turbo_map.py [out.bin]")
    output = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else DEFAULT_OUT.resolve()
    refuse_output_alias(output)

    stock, combined_reference, output_bytes, writes = build_image()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(output_bytes)

    # Re-read every protected source after output generation.
    if STOCK.read_bytes() != stock or BASE_STOCK.read_bytes() != stock:
        raise RuntimeError("protected stock BIN changed during base-map build")
    if extract_srf.extract_memd(SOURCE_SRF)[0] != stock:
        raise RuntimeError("protected SRF provenance changed during base-map build")
    if COMBINED_ARTIFACT.read_bytes() != combined_reference:
        raise RuntimeError("canonical combined artifact changed during base-map build")
    # Re-run all size, hash, CALID, and source-byte checks on the injector donor.
    pink_injector_calibration()

    changed = {
        index for index, (before, after) in enumerate(zip(combined_reference, output_bytes))
        if before != after
    }
    stored, calculated, _ = checksum_value(output_bytes)
    print(f"Base turbo calibration written: {output}")
    print(f"  stock source     : {STOCK} (UNCHANGED, SHA-256 {sha256(stock)})")
    print(f"  combined stage   : SHA-256 {sha256(combined_reference)} (reconstructed from stock)")
    print(f"  output SHA-256   : {sha256(output_bytes)}")
    print(f"  changed bytes    : {len(changed)} beyond combined stage")
    print("  changed ranges   : " + ", ".join(
        f"0x{start:05X}..0x{end:05X}" for start, end in merge_ranges(changed)
    ))
    print(f"  owned tables     : {len(writes)}")
    print("  boost command    : spring-only; WGDC=0%, Kp=0, max ratio=0")
    print(f"  overboost limits : soft {SOFT_OVERBOOST_PSI:.1f} psi / hard {HARD_OVERBOOST_PSI:.1f} psi")
    print(f"  rev limit A      : cut {REV_LIMIT_CUT_RPM:.0f} / resume {REV_LIMIT_RESUME_RPM:.0f} RPM")
    pink_flow_raw, _, pink_flow_display = pink_injector_calibration()
    print(
        f"  injectors        : STI pink OEM calibration; {pink_flow_display:.2f} cc/min "
        f"estimated (D2WD raw {pink_flow_raw:.6f})"
    )
    print(
        f"  AVLS             : load-based from {AVLS_ACTUATION_MIN_RPM:.0f} RPM; "
        f"forced high cam {AVLS_ENGAGE_RPM:.0f}/{AVLS_RELEASE_RPM:.0f} RPM"
    )
    print(f"  checksum         : 0x{stored:08X} (valid={stored == calculated})")
    print("\n*** NOT FLASH-READY until injector identity, fuel-pressure, MAF, MAP, and wideband checks in README.md pass. ***")


if __name__ == "__main__":
    main()
