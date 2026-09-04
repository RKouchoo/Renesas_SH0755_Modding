#!/usr/bin/env python3
"""Static, structural, and deterministic audit of D2WD610H master_patch."""

from __future__ import annotations

from io import BytesIO
import hashlib
import math
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PATCH_DIR = ROOT / "patch"
SD_DIR = ROOT / "speed_density"
FUEL_SAFETY_DIR = ROOT / "fueling_safety"
for directory in (PATCH_DIR, SD_DIR, FUEL_SAFETY_DIR, HERE):
    sys.path.insert(0, str(directory))

import build_definition as definition  # noqa: E402
import build_master_patch as master  # noqa: E402
import wideband_component as wideband  # noqa: E402
import patch_boost as boost  # noqa: E402
import patch_speed_density as speed_density  # noqa: E402
import patch_rotational_idle as rotational_idle  # noqa: E402
import verify_rotational_idle as rotational_idle_verify  # noqa: E402
import master_calibration as calibration  # noqa: E402
import verify_master_calibration as calibration_verify  # noqa: E402
import sh2_disasm  # noqa: E402
import fueling_safety_component as fueling_safety  # noqa: E402
import verify_fueling_safety as fueling_safety_verify  # noqa: E402
import install_master_logger as logger_definition  # noqa: E402


OUTPUT = HERE / "D2WD610H_master_patch.bin"
DEFINITION = HERE / "D2WD610H_master_patch.xml"
LOGGER_FRAGMENT = HERE / "D2WD610H_master_logger_ecuparams.xml"
LOGGER_DEFINITION = HERE / "D2WD610H_master_logger.xml"
LOGGER_PROFILE = HERE / "D2WD610H_idle_diagnostic_profile.xml"
EXPECTED_OUTPUT_SHA256 = "0390ff9d856c66f58e0c44db9c8a4024e26072b905540ef30a116fffca9b9f86"
EXPECTED_LOGGER_SHA256 = "e21f5d6633605369faa013027155adeeca8583ef0f1a9486d603dbbca2e68e0b"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def expect(image: bytes | bytearray, address: int, expected: bytes, label: str) -> None:
    actual = bytes(image[address : address + len(expected)])
    if actual != expected:
        fail(
            f"{label} @0x{address:05X} is {actual.hex()} "
            f"(expected {expected.hex()})"
        )


def changed_set(before: bytes, after: bytes) -> set[int]:
    return {
        index for index, (old, new) in enumerate(zip(before, after)) if old != new
    }


def add_range(owned: set[int], address: int, size: int, label: str) -> None:
    if size <= 0 or address < 0 or address + size > master.ROM_SIZE:
        fail(f"invalid declared range for {label}: 0x{address:05X} + 0x{size:X}")
    region = set(range(address, address + size))
    overlap = owned & region
    if overlap:
        fail(f"declared ownership overlap for {label} at 0x{min(overlap):05X}")
    owned.update(region)


def rebuild_component_stage(stock: bytes) -> tuple[
    bytes, dict[str, list[tuple[str, int, bytes]]]
]:
    stage = bytearray(stock)
    blobs: dict[str, list[tuple[str, int, bytes]]] = {}
    blobs["boost"] = boost.apply_to_rom(stage)
    master.apply_omni_map_calibration(stage)
    blobs["rotational_idle"] = rotational_idle.apply_to_rom(stage)
    blobs["speed_density"] = speed_density.apply_to_rom(stage)
    blobs["wideband"] = wideband.apply_to_rom(stage)
    blobs["fueling_safety"] = fueling_safety.apply_to_rom(stage)
    return bytes(stage), blobs


def verify_layout(
    stock: bytes,
    image: bytes,
    blobs: dict[str, list[tuple[str, int, bytes]]],
    calibration_writes: dict[str, tuple[int, bytes]],
) -> None:
    free_owned: set[int] = set()
    for component, component_blobs in blobs.items():
        for name, address, data in component_blobs:
            add_range(free_owned, address, len(data), f"{component}/{name}")

    # Component reservations are deliberately adjacent at the live boundary:
    # the wideband prerequisite guard ends at 0x7E63F and dual VE starts at
    # 0x7E640.  These exact checks prevent a later component expansion from
    # relying only on today's blob lengths.
    wideband_guard_end = (
        wideband.BOOST_READY_GUARD_ADDR
        + len(wideband.build_boost_ready_guard())
        - 1
    )
    if wideband.COMPONENT_END != wideband_guard_end:
        fail(
            "wideband reserved end does not equal its final guard byte: "
            f"0x{wideband.COMPONENT_END:05X} vs 0x{wideband_guard_end:05X}"
        )
    if wideband.COMPONENT_END + 1 != speed_density.DUAL_VE_START:
        fail("wideband and speed-density dual-VE segments are not exactly adjacent")
    if speed_density.COMPONENT_END >= wideband.CONSTANTS_ADDR:
        fail("speed-density reservation enters the wideband component region")
    if speed_density.DUAL_VE_END + 1 != fueling_safety.COMPONENT_START:
        fail("dual-VE and fueling-safety segments are not exactly adjacent")
    safety_end = (
        fueling_safety.LEAN_CUT_WRAPPER_ADDR
        + len(fueling_safety.build_lean_cut_wrapper())
        - 1
    )
    if fueling_safety.COMPONENT_END != safety_end:
        fail("fueling-safety reserved end does not equal its final wrapper byte")

    rotational_end = (
        rotational_idle.ROT_IDLE_WRAPPER_ADDR
        + len(rotational_idle.build_wrapper())
        - 1
    )
    if rotational_end != 0x0007DCEB:
        fail(f"rotational-idle wrapper boundary moved to 0x{rotational_end:05X}")
    if rotational_end >= speed_density.FREE_START:
        fail("rotational-idle component reaches the speed-density allocation")

    calibration_owned: set[int] = set()
    for label, (address, data) in calibration_writes.items():
        add_range(calibration_owned, address, len(data), f"calibration/{label}")

    # These are deliberate tune-data replacements inside the boost component.
    # No calibration write is allowed to touch injected executable code,
    # descriptors, SD data, wideband data, or dual-VE data.
    expected_component_calibration = set()
    for address, size in (
        (boost.TARGET_DATA, len(calibration.BOOST_TARGET_NATIVE) * 4),
        (boost.BASE_DATA, len(boost.BASE_DUTY)),
        (boost.KP_ADDR, 4),
        (boost.MAXR_ADDR, 4),
        (boost.OVERB_ADDR, 4),
        (boost.OVERB_FC_ADDR, 4),
    ):
        expected_component_calibration.update(range(address, address + size))
    component_calibration_overlap = free_owned & calibration_owned
    if component_calibration_overlap != expected_component_calibration:
        unexpected = component_calibration_overlap - expected_component_calibration
        missing = expected_component_calibration - component_calibration_overlap
        fail(
            "component/calibration ownership differs from the explicit boost-data "
            "exception: unexpected=%s missing=%s"
            % (
                [f"0x{x:05X}" for x in sorted(unexpected)[:8]],
                [f"0x{x:05X}" for x in sorted(missing)[:8]],
            )
        )

    hook_owned: set[int] = set()
    for address, size, label in (
        (boost.MAP_SCALING_ADDR, 8, "Omni MAP scaling"),
        (master.MAP_LOW_CEL_RAW_ADDR, 2, "Omni MAP low diagnostic threshold"),
        (boost.HIJACK_LITERAL, 4, "composed boost/wideband output hook"),
        (boost.REVLIM_FNPTR, 4, "overboost fuel-cut task hook"),
        (speed_density.FINAL_AIRFLOW_HELPER_PTR, 4, "speed-density airflow hook"),
        (speed_density.MAF_LIMIT_UPDATE_CALL_ADDR, 2, "MAF-limit bypass"),
        (speed_density.MAF_INPUT_DIAGNOSTIC_TASK_PTR, 4, "MAF diagnostic bypass"),
        (wideband.FRONT_AF_PROCESS_ENTRY, 12, "front A/F process hook"),
        (wideband.BANK1_INHIBIT_ENTRY, 12, "bank-1 inhibit hook"),
        (wideband.BANK2_INHIBIT_ENTRY, 12, "bank-2 inhibit hook"),
        (wideband.FRONT_PUMP_DIAG_TASK_PTR, 4, "front pump diagnostic bypass"),
        (wideband.REAR_O2_PROCESS_ENTRY, 12, "rear O2 process bypass"),
        (fueling_safety.PRIMARY_OL_TASK_PTR, 4, "pressure-forced OL task hook"),
        (fueling_safety.LEAN_STATE_INIT_TASK_PTR, 4, "lean-state initialization hook"),
        (rotational_idle.FINAL_TIMING_TASK_PTR, 4, "rotational-idle timing task hook"),
    ):
        add_range(hook_owned, address, size, f"hook/{label}")
    for address in speed_density.MAF_CONVERSION_CALL_ADDRS:
        add_range(hook_owned, address, 2, f"hook/MAF conversion bypass @0x{address:05X}")
    for address in speed_density.TEMPERATURE_MAF_CONDITION_TASK_PTRS:
        add_range(hook_owned, address, 4, f"hook/MAF temperature bypass @0x{address:05X}")
    for address in (speed_density.P0102_SWITCH_ADDR, speed_density.P0103_SWITCH_ADDR):
        add_range(hook_owned, address, 1, f"hook/MAF DTC switch @0x{address:05X}")
    for address, _, _ in wideband.REAR_O2_TASK_POINTERS:
        add_range(hook_owned, address, 4, f"hook/rear O2 task bypass @0x{address:05X}")
    for address in wideband.DISABLED_O2_DTC_SWITCHES.values():
        add_range(hook_owned, address, 1, f"hook/O2 DTC switch @0x{address:05X}")

    if hook_owned & (free_owned | calibration_owned):
        fail("stock hook ownership collides with component or calibration space")

    allowed = free_owned | hook_owned | calibration_owned

    actual = changed_set(stock, image)
    outside = actual - allowed
    if outside:
        fail(f"master contains an undeclared change at 0x{min(outside):05X}")


def verify_omni_map(image: bytes) -> None:
    stored_offset, stored_multiplier = struct.unpack_from(
        ">2f", image, master.MAP_SCALING_ADDR
    )
    if not math.isclose(stored_offset, master.OMNI_MAP_OFFSET, abs_tol=1e-4):
        fail(f"Omni MAP offset is {stored_offset}, expected {master.OMNI_MAP_OFFSET}")
    if not math.isclose(stored_multiplier, master.OMNI_MAP_MULTIPLIER, abs_tol=1e-4):
        fail(
            f"Omni MAP multiplier is {stored_multiplier}, "
            f"expected {master.OMNI_MAP_MULTIPLIER}"
        )

    low_native = stored_offset + stored_multiplier * master.OMNI_MIN_VOLTS
    high_native = stored_offset + stored_multiplier * master.OMNI_MAX_VOLTS
    if not math.isclose(
        low_native, master.OMNI_MIN_KPA * master.KPA_TO_MMHG, abs_tol=2e-4
    ):
        fail("stored Omni transfer does not reproduce the 0.60 V / 30 kPa endpoint")
    if not math.isclose(
        high_native, master.OMNI_MAX_KPA * master.KPA_TO_MMHG, abs_tol=2e-3
    ):
        fail("stored Omni transfer does not reproduce the 4.75 V / 300 kPa endpoint")

    high_raw, low_raw = struct.unpack_from(">2H", image, 0x0007B284)
    if high_raw != 0xFBF5:
        fail(f"Omni high-input CEL threshold unexpectedly changed to 0x{high_raw:04X}")
    if low_raw != master.MASTER_MAP_LOW_CEL_RAW:
        fail(
            f"Omni low-input CEL threshold is 0x{low_raw:04X}, "
            f"expected 0x{master.MASTER_MAP_LOW_CEL_RAW:04X}"
        )
    if not (
        speed_density.MAP_MIN_MMHG
        < max(calibration.BOOST_TARGET_NATIVE)
        < speed_density.MAP_MAX_MMHG
    ):
        fail("5 psi target is outside the speed-density MAP validity window")


def verify_avls_dual_ve(image: bytes) -> None:
    expected_low_desc = speed_density.desc_3d_float(
        len(speed_density.MAP_AXIS),
        len(speed_density.LOW_RPM_AXIS),
        speed_density.MAP_AXIS_ADDR,
        speed_density.LOW_RPM_AXIS_ADDR,
        speed_density.LOW_VE_DATA_ADDR,
    )
    expected_high_desc = speed_density.desc_3d_float(
        len(speed_density.MAP_AXIS),
        len(speed_density.HIGH_RPM_AXIS),
        speed_density.MAP_AXIS_ADDR,
        speed_density.HIGH_RPM_AXIS_ADDR,
        speed_density.HIGH_VE_DATA_ADDR,
    )
    expect(image, speed_density.LOW_VE_DESC_ADDR, expected_low_desc, "low-lift VE descriptor")
    expect(image, speed_density.HIGH_VE_DESC_ADDR, expected_high_desc, "high-lift VE descriptor")
    expect(
        image,
        speed_density.WRAPPER_ADDR,
        speed_density.build_wrapper(),
        "committed-state AVLS dual-VE airflow wrapper",
    )
    if speed_density.VE_DESC_ADDR.to_bytes(4, "big") in speed_density.build_wrapper():
        fail("master dual-VE wrapper still embeds the obsolete single VE descriptor")

    low_axis = struct.unpack_from(
        ">" + "f" * len(speed_density.LOW_RPM_AXIS), image, speed_density.LOW_RPM_AXIS_ADDR
    )
    high_axis = struct.unpack_from(
        ">" + "f" * len(speed_density.HIGH_RPM_AXIS), image, speed_density.HIGH_RPM_AXIS_ADDR
    )
    if low_axis != speed_density.LOW_RPM_AXIS or high_axis != speed_density.HIGH_RPM_AXIS:
        fail("master dual-VE axes do not match their real AVLS operating ranges")
    if low_axis[-1] != speed_density.AVLS_ENGAGE_RPM or high_axis[0] != speed_density.AVLS_RELEASE_RPM:
        fail("master dual-VE axes do not cover the real hysteresis endpoints")

    for label, address, expected in (
        ("low", speed_density.LOW_VE_DATA_ADDR, speed_density.LOW_VE_TABLE),
        ("high", speed_density.HIGH_VE_DATA_ADDR, speed_density.HIGH_VE_TABLE),
    ):
        actual = struct.unpack_from(">" + "f" * len(expected), image, address)
        if any(not math.isclose(a, b, abs_tol=1e-7) for a, b in zip(actual, expected)):
            fail(f"master {label}-lift VE seed changed unexpectedly")

    for address in (speed_density.AVLS_NORMAL_SPEED_DATA_ADDR, speed_density.AVLS_HOT_SPEED_DATA_ADDR):
        actual = struct.unpack_from(">7f", image, address)
        if actual != speed_density.AVLS_SPEED_DISABLED:
            fail(f"master retains a vehicle-speed AVLS request at 0x{address:05X}")
    for address in (speed_density.AVLS_FIXED_SPEED_A_ADDR, speed_density.AVLS_FIXED_SPEED_B_ADDR):
        if struct.unpack_from(">f", image, address)[0] != speed_density.AVLS_SPEED_DISABLED_VALUE:
            fail(f"master retains a fixed/fallback speed request at 0x{address:05X}")
    actual_rpm_policy = tuple(
        struct.unpack_from(">f", image, address)[0]
        for address in (
            speed_density.AVLS_ACTUATION_MIN_RPM_ADDR,
            speed_density.AVLS_RELEASE_RPM_ADDR,
            speed_density.AVLS_ENGAGE_RPM_ADDR,
        )
    )
    if actual_rpm_policy != (
        speed_density.AVLS_ACTUATION_MIN_RPM,
        speed_density.AVLS_RELEASE_RPM,
        speed_density.AVLS_ENGAGE_RPM,
    ):
        fail(f"master predictable AVLS RPM policy is {actual_rpm_policy}")


def literal_pool_boundary(blob: bytes, base: int, required: set[int]) -> int:
    pool_start = base + len(blob) - 4 * len(required)
    if pool_start & 3:
        fail(f"literal pool for 0x{base:05X} is not 4-byte aligned")
    actual = {
        struct.unpack_from(">I", blob, offset)[0]
        for offset in range(pool_start - base, len(blob), 4)
    }
    if actual != required:
        fail(
            f"literal pool for 0x{base:05X} differs: "
            f"missing={sorted(required - actual)}, extra={sorted(actual - required)}"
        )
    return pool_start


def decode_executable(
    image: bytes, blob: bytes, base: int, required_literals: set[int], label: str
) -> list[str]:
    pool_start = literal_pool_boundary(blob, base, required_literals)
    decoded: list[str] = []
    for address in range(base, pool_start, 2):
        instruction, _ = sh2_disasm.dis_one(image, address)
        decoded.append(instruction)
        if instruction.startswith(".word"):
            fail(f"unknown {label} opcode at 0x{address:05X}: {instruction}")
    return decoded


def wideband_policy(raw_adc: int) -> tuple[float, float] | None:
    volts = raw_adc * wideband.RAW_ADC_TO_VOLTS
    if not wideband.VALID_MIN_VOLTS <= volts <= wideband.VALID_MAX_VOLTS:
        return None
    value = wideband.LAMBDA_SLOPE * volts + wideband.LAMBDA_OFFSET
    if not math.isfinite(value) or value <= 0.0:
        return None
    return volts, value


def boost_guard_policy(
    ready: float,
    map_mm_hg: float,
    rpm: float,
    iat_c: float,
    modeled_airflow: float,
) -> bool:
    ranges = (
        (map_mm_hg, speed_density.MAP_MIN_MMHG, speed_density.MAP_MAX_MMHG),
        (rpm, speed_density.RPM_MIN, speed_density.RPM_MAX),
        (iat_c, speed_density.IAT_MIN_C, speed_density.IAT_MAX_C),
    )
    if not math.isfinite(ready) or ready <= wideband.READY_THRESHOLD:
        return False
    for value, minimum, maximum in ranges:
        if not all(math.isfinite(item) for item in (value, minimum, maximum)):
            return False
        if not minimum <= value <= maximum:
            return False
    if rpm < boost.RPM_BREAKS[0]:
        return False
    if not math.isfinite(modeled_airflow):
        return False
    return modeled_airflow != speed_density.FAILSAFE_AIRFLOW_G_S


def verify_wideband(image: bytes) -> None:
    expect(
        image,
        wideband.FRONT_AF_PROCESS_ENTRY,
        wideband.build_entry_hook(
            wideband.FRONT_AF_PROCESS_ENTRY, wideband.WIDEBAND_UPDATE_ADDR
        ),
        "external-wideband front-pair hook",
    )
    for address in (wideband.BANK1_INHIBIT_ENTRY, wideband.BANK2_INHIBIT_ENTRY):
        expect(
            image,
            address,
            wideband.build_entry_hook(address, wideband.INHIBIT_HELPER_ADDR),
            "external-wideband bank-inhibit hook",
        )
    expect(
        image,
        wideband.FRONT_PUMP_DIAG_TASK_PTR,
        wideband.be32(wideband.NOOP_TASK),
        "front pump diagnostic task bypass",
    )
    expect(
        image,
        wideband.REAR_O2_PROCESS_ENTRY,
        wideband.build_entry_hook(wideband.REAR_O2_PROCESS_ENTRY, wideband.NOOP_TASK),
        "rear O2 conversion bypass",
    )
    for pointer, _, label in wideband.REAR_O2_TASK_POINTERS:
        expect(image, pointer, wideband.be32(wideband.NOOP_TASK), label)
    for code, address in wideband.DISABLED_O2_DTC_SWITCHES.items():
        expect(image, address, b"\x00", f"{code} O2 DTC disable")
    expect(
        image,
        boost.HIJACK_LITERAL,
        wideband.be32(wideband.BOOST_READY_GUARD_ADDR),
        "master sensor/SD-validity boost-duty gate",
    )

    constants = (
        wideband.RAW_ADC_TO_VOLTS,
        wideband.LAMBDA_SLOPE,
        wideband.LAMBDA_OFFSET,
        wideband.VALID_MIN_VOLTS,
        wideband.VALID_MAX_VOLTS,
        wideband.READY_VALID_VALUE,
        wideband.READY_THRESHOLD,
    )
    expect(
        image,
        wideband.CONSTANTS_ADDR,
        b"".join(wideband.f32(value) for value in constants),
        "external-wideband fixed/editable constants",
    )

    update_literals = {
        wideband.RAW_WIDEBAND_ADC,
        wideband.RAW_TO_VOLTS_ADDR,
        wideband.VALID_MIN_VOLTS_ADDR,
        wideband.VALID_MAX_VOLTS_ADDR,
        wideband.LAMBDA_SLOPE_ADDR,
        wideband.LAMBDA_OFFSET_ADDR,
        speed_density.FINITE_FLOAT_MAX_ADDR,
        wideband.FRONT_LAMBDA_BANK1,
        wideband.FRONT_LAMBDA_BANK2,
        wideband.WIDEBAND_LOG_LAMBDA_BANK1,
        wideband.WIDEBAND_LOG_LAMBDA_BANK2,
        wideband.FRONT_CURRENT_BANK1,
        wideband.FRONT_CURRENT_BANK2,
        wideband.READY_VALID_VALUE_ADDR,
        wideband.FRONT_READY_METRIC_BANK1,
        wideband.FRONT_READY_METRIC_BANK2,
    }
    update_blob = wideband.build_wideband_update()
    update_decoded = decode_executable(
        image,
        update_blob,
        wideband.WIDEBAND_UPDATE_ADDR,
        update_literals,
        "wideband update",
    )
    for required_instruction in ("extu.w r0,r0", "lds r0,fpul", "float fpul,fr0"):
        if update_decoded.count(required_instruction) != 1:
            fail(f"wideband update lacks one {required_instruction!r} instruction")
    if sum(text.startswith("fcmp/gt") for text in update_decoded) < 4:
        fail("wideband update lacks the expected range/positive/finite comparisons")
    if sum(text.startswith("fmov.s fr") and "@r1" in text for text in update_decoded) < 16:
        fail("wideband update lacks the expected synthetic-bank/logger writes")

    inhibit_decoded = decode_executable(
        image,
        wideband.build_inhibit_helper(),
        wideband.INHIBIT_HELPER_ADDR,
        {wideband.FRONT_READY_METRIC_BANK1, wideband.READY_THRESHOLD_ADDR},
        "wideband inhibit helper",
    )
    if "mov #2,r0" not in inhibit_decoded or "mov #0,r0" not in inhibit_decoded:
        fail("wideband inhibit helper does not contain stock inhibited/ready return values")

    guard_decoded = decode_executable(
        image,
        wideband.build_boost_ready_guard(),
        wideband.BOOST_READY_GUARD_ADDR,
        {
            wideband.FRONT_READY_METRIC_BANK1,
            wideband.READY_THRESHOLD_ADDR,
            speed_density.MAP_ADDR,
            speed_density.MAP_MIN_ADDR,
            speed_density.MAP_MAX_ADDR,
            speed_density.RPM_ADDR,
            speed_density.RPM_MIN_ADDR,
            speed_density.RPM_MAX_ADDR,
            speed_density.IAT_ADDR,
            speed_density.IAT_MIN_ADDR,
            speed_density.IAT_MAX_ADDR,
            boost.RPM_AXIS,
            speed_density.FINAL_MASS_AIRFLOW_ADDR,
            speed_density.FAILSAFE_AIRFLOW_ADDR,
            boost.STOCK_OUTPUT,
            boost.STUB_ADDR,
        },
        "master boost prerequisite guard",
    )
    if guard_decoded.count("fldi0 fr4") != 1:
        fail("master boost guard does not force the output duty register to zero")
    if sum(text.startswith("jmp @") for text in guard_decoded) != 2:
        fail("master boost guard does not have exactly two tail-call outcomes")
    if sum(text.startswith("fcmp/eq") for text in guard_decoded) < 12:
        fail("master boost guard lacks the expected NaN/bound/fail-sentinel checks")
    if sum(text.startswith("fcmp/gt") for text in guard_decoded) < 8:
        fail("master boost guard lacks the expected readiness/range/RPM comparisons")

    # Exercise ADC unsigned conversion and both inclusive validity boundaries.
    if wideband_policy(0) is not None or wideband_policy(0xFFFF) is not None:
        fail("wideband policy accepts an obvious rail fault")
    minimum_valid = math.ceil(wideband.VALID_MIN_VOLTS / wideband.RAW_ADC_TO_VOLTS)
    maximum_valid = math.floor(wideband.VALID_MAX_VOLTS / wideband.RAW_ADC_TO_VOLTS)
    if wideband_policy(minimum_valid) is None or wideband_policy(maximum_valid) is None:
        fail("wideband policy rejects a quantized in-range endpoint")
    if wideband_policy(minimum_valid - 1) is not None:
        fail("wideband policy accepts an ADC count below its minimum")
    if wideband_policy(maximum_valid + 1) is not None:
        fail("wideband policy accepts an ADC count above its maximum")
    if not math.isclose(
        wideband.LAMBDA_SLOPE, 2.0 / 14.64, rel_tol=0.0, abs_tol=1e-12
    ) or not math.isclose(
        wideband.LAMBDA_OFFSET, 10.0 / 14.64, rel_tol=0.0, abs_tol=1e-12
    ):
        fail("wideband constants do not match the supplied 50-4110 P0/P1 table")
    sample = wideband_policy(round(2.5 / wideband.RAW_ADC_TO_VOLTS))
    expected_lambda = 15.0 / 14.64
    if sample is None or not math.isclose(sample[1], expected_lambda, abs_tol=2e-5):
        fail("wideband policy does not reproduce 15.00 AFR at 2.50 V")

    nominal_guard = (50.0, 1019.0, 3500.0, 30.0, 250.0)
    if not boost_guard_policy(*nominal_guard):
        fail("master boost guard rejects a nominal valid running state")
    invalid_guard_cases = (
        (35.0, 1019.0, 3500.0, 30.0, 250.0),
        (50.0, speed_density.MAP_MIN_MMHG - 0.01, 3500.0, 30.0, 250.0),
        (50.0, speed_density.MAP_MAX_MMHG + 0.01, 3500.0, 30.0, 250.0),
        (50.0, 1019.0, boost.RPM_BREAKS[0] - 0.01, 30.0, 250.0),
        (50.0, 1019.0, speed_density.RPM_MAX + 0.01, 30.0, 250.0),
        (50.0, 1019.0, 3500.0, speed_density.IAT_MIN_C - 0.01, 250.0),
        (50.0, 1019.0, 3500.0, speed_density.IAT_MAX_C + 0.01, 250.0),
        (50.0, 1019.0, 3500.0, 30.0, speed_density.FAILSAFE_AIRFLOW_G_S),
        (50.0, math.nan, 3500.0, 30.0, 250.0),
        (50.0, 1019.0, math.inf, 30.0, 250.0),
        (50.0, 1019.0, 3500.0, math.nan, 250.0),
        (50.0, 1019.0, 3500.0, 30.0, math.nan),
    )
    if any(boost_guard_policy(*case) for case in invalid_guard_cases):
        fail("master boost guard accepts an invalid sensor/SD prerequisite")
    inclusive_guard_cases = (
        (
            50.0,
            speed_density.MAP_MIN_MMHG,
            boost.RPM_BREAKS[0],
            speed_density.IAT_MIN_C,
            100.0,
        ),
        (
            50.0,
            speed_density.MAP_MAX_MMHG,
            speed_density.RPM_MAX,
            speed_density.IAT_MAX_C,
            499.0,
        ),
    )
    if not all(boost_guard_policy(*case) for case in inclusive_guard_cases):
        fail("master boost guard does not preserve its inclusive valid boundaries")


def verify_rotational_idle(image: bytes) -> None:
    expect(
        image,
        rotational_idle.FINAL_TIMING_TASK_PTR,
        rotational_idle.be32(rotational_idle.ROT_IDLE_WRAPPER_ADDR),
        "rotational-idle task hook",
    )
    expect(
        image,
        rotational_idle.ROT_IDLE_ENABLE_ADDR,
        b"\x00",
        "default-OFF rotational-idle switch",
    )
    gates = b"".join(
        rotational_idle.f32(value)
        for value in (
            rotational_idle.ECT_MIN,
            rotational_idle.ECT_MAX,
            rotational_idle.RPM_MIN,
            rotational_idle.RPM_MAX,
            rotational_idle.THROTTLE_MAX,
            rotational_idle.VEHICLE_SPEED_MAX,
            rotational_idle.MAP_MIN,
            rotational_idle.MAP_MAX,
            rotational_idle.MAX_RETARD,
            rotational_idle.MIN_FINAL_TIMING,
        )
    )
    expect(image, rotational_idle.ECT_MIN_ADDR, gates, "rotational-idle gate defaults")
    offsets = b"".join(rotational_idle.f32(value) for value in rotational_idle.CYLINDER_OFFSETS)
    expect(
        image,
        rotational_idle.CYLINDER_OFFSETS_ADDR,
        offsets,
        "rotational-idle cylinder offsets",
    )

    wrapper = rotational_idle.build_wrapper()
    decoded = decode_executable(
        image,
        wrapper,
        rotational_idle.ROT_IDLE_WRAPPER_ADDR,
        {
            rotational_idle.STOCK_FINAL_TIMING_TASK,
            rotational_idle.ROT_IDLE_ENABLE_ADDR,
            rotational_idle.ECT_ADDR,
            rotational_idle.ECT_MIN_ADDR,
            rotational_idle.ECT_MAX_ADDR,
            rotational_idle.RPM_ADDR,
            rotational_idle.RPM_MIN_ADDR,
            rotational_idle.RPM_MAX_ADDR,
            rotational_idle.THROTTLE_ADDR,
            rotational_idle.THROTTLE_MAX_ADDR,
            rotational_idle.VEHICLE_SPEED_ADDR,
            rotational_idle.VEHICLE_SPEED_MAX_ADDR,
            rotational_idle.MAP_ADDR,
            rotational_idle.MAP_MIN_ADDR,
            rotational_idle.MAP_MAX_ADDR,
            rotational_idle.FINAL_TIMING_ARRAY,
            rotational_idle.CYLINDER_OFFSETS_ADDR,
            rotational_idle.MAX_RETARD_ADDR,
            rotational_idle.MIN_FINAL_TIMING_ADDR,
        },
        "rotational-idle wrapper",
    )
    if decoded.count("jsr @r2") != 1:
        fail("rotational-idle wrapper does not call the complete stock timing task once")
    if "cmp/eq #1,r0" not in decoded:
        fail("rotational-idle wrapper lacks the exact-01 enable decision")
    if decoded.count("dt r2") != 1 or decoded.count("fmov.s fr4,@r4") != 1:
        fail("rotational-idle wrapper lacks its bounded six-cylinder output loop")
    try:
        rotational_idle_verify.verify_policy_model()
    except SystemExit as exc:
        fail(f"rotational-idle policy model: {exc}")


def render_definition() -> bytes:
    tree = definition.build_tree()
    ET.indent(tree, space=" ")
    buffer = BytesIO()
    tree.write(buffer, encoding="utf-8", xml_declaration=True)
    return buffer.getvalue()


def verify_definition() -> None:
    if not DEFINITION.exists():
        fail(f"missing generated definition {DEFINITION}")
    expected = render_definition()
    actual = DEFINITION.read_bytes()
    if actual != expected:
        fail("master RomRaider definition is stale relative to its generator")

    root = ET.fromstring(actual)
    definition.validate(root)
    roms = root.findall("rom")
    xmlids = [rom.findtext("romid/xmlid") for rom in roms]
    if xmlids != ["32BITBASE", "D2WD610H_MASTER_PATCH"]:
        fail(f"definition contains an unrelated ROM identity: {xmlids}")
    target = roms[1]
    if target.findtext("romid/internalidstring") != "D2WD610H":
        fail("definition target is not internally matched to D2WD610H")

    tables = {table.get("name"): table for table in target.findall("table")}
    expected_ve = {
        "Speed Density VE - AVLS Low Lift": (
            speed_density.LOW_VE_DATA_ADDR,
            len(speed_density.LOW_RPM_AXIS),
            speed_density.LOW_RPM_AXIS_ADDR,
        ),
        "Speed Density VE - AVLS High Lift": (
            speed_density.HIGH_VE_DATA_ADDR,
            len(speed_density.HIGH_RPM_AXIS),
            speed_density.HIGH_RPM_AXIS_ADDR,
        ),
    }
    for name, (data_address, rows, rpm_axis) in expected_ve.items():
        ve = tables.get(name)
        if ve is None or (
            int(ve.get("sizex", "0")), int(ve.get("sizey", "0"))
        ) != (len(speed_density.MAP_AXIS), rows):
            fail(f"master definition {name} dimensions do not match firmware")
        if int(ve.get("storageaddress", "0"), 0) != data_address:
            fail(f"master definition {name} data address is wrong")
        axes = {
            child.get("type"): int(child.get("storageaddress", "0"), 0)
            for child in ve.findall("table")
        }
        if axes != {
            "X Axis": speed_density.MAP_AXIS_ADDR,
            "Y Axis": rpm_axis,
        }:
            fail(f"master definition {name} axes do not match firmware")
    if "Speed Density VE (MAP x RPM)" in tables:
        fail("master definition retains the obsolete single full-range VE table")

    parent_names = {table.get("name") for table in roms[0].findall("table")}
    parent_tables = {table.get("name"): table for table in roms[0].findall("table")}
    iat_template = parent_tables.get("Intake Temp Sensor Scaling")
    if (
        iat_template is None
        or iat_template.findtext("description") != definition.IAT_SENSOR_DESCRIPTION
    ):
        fail("master definition lacks the provisional HT-010206/1.00k IAT warning")
    for name in expected_ve:
        template = parent_tables.get(name)
        if template is None or template.get("endian") != "little":
            fail(f"master definition {name} has wrong RomRaider float endianness")
        if any(axis.get("endian") != "little" for axis in template.findall("table")):
            fail(f"master definition {name} axes have wrong RomRaider float endianness")
    target_names = set(tables)
    obsolete = definition.DROP_NAMES & (parent_names | target_names)
    if obsolete:
        fail(f"master definition retains obsolete tables: {sorted(obsolete)}")
    categories = {table.get("category") for table in roms[0].findall("table")}
    if categories & definition.DROP_CATEGORIES:
        fail("master definition retains diagnostic/readiness categories")

    expected_pump_commands = {
        "Fuel Pump Low-Speed Command": (0x0002A610, 33.3),
        "Fuel Pump Medium-Speed Command": (0x0002A60C, 66.7),
    }
    stock = master.STOCK.read_bytes()
    patched = OUTPUT.read_bytes()
    for name, (address, expected_value) in expected_pump_commands.items():
        table = tables.get(name)
        if table is None:
            fail(f"master definition is missing {name}")
        if int(table.get("storageaddress", "0"), 0) != address:
            fail(f"master definition {name} points at the wrong code literal")
        if (
            table.get("type") != "1D"
            or table.get("storagetype") != "float"
            or table.get("endian") != "big"
            or table.get("category") != definition.CAT_FUEL_PUMP
        ):
            fail(f"master definition {name} has unsafe type/category metadata")
        stock_value = struct.unpack_from(">f", stock, address)[0]
        patched_value = struct.unpack_from(">f", patched, address)[0]
        if not math.isclose(stock_value, expected_value, abs_tol=1e-4):
            fail(f"stock {name} literal is {stock_value}, expected {expected_value}")
        if patched_value != stock_value:
            fail(f"master build unexpectedly changes stock {name}")
        description = table.findtext("description", "")
        if "P47" not in description:
            fail(f"master definition {name} does not document P47 verification")
    if not math.isclose(
        struct.unpack_from(">f", stock, 0x0002A5FC)[0], 100.0, abs_tol=1e-6
    ) or patched[0x0002A5FC:0x0002A600] != stock[0x0002A5FC:0x0002A600]:
        fail("fuel-pump 100-percent normalization/high-mode literal changed")

    expected_timing_addresses = {
        "Base Timing - Normal Cam (AVCS Tracking Ratio 1.0)": 0x00078AA0,
        "Base Timing - AVLS High Cam (AVCS Tracking Ratio 1.0)": 0x00078CD0,
        "Base Timing - Normal Cam (AVCS Tracking Ratio 0.0)": 0x00078E34,
        "Base Timing - AVLS High Cam (AVCS Tracking Ratio 0.0)": 0x00079064,
        "Knock Correction Advance Max - Normal Cam": 0x0007924C,
        "Knock Correction Advance Max - AVLS High Cam": 0x000793AC,
    }
    timing_names = set(expected_timing_addresses)
    if not timing_names <= target_names:
        fail("master definition is missing a Ghidra-identified active timing path")
    for name, expected_address in expected_timing_addresses.items():
        target_address = int(tables[name].get("storageaddress", "0"), 0)
        if target_address != expected_address:
            fail(
                f"master definition timing identity {name} points to "
                f"0x{target_address:05X}, expected 0x{expected_address:05X}"
            )
        parent_table = next(table for table in roms[0].findall("table") if table.get("name") == name)
        description = parent_table.findtext("description", "")
        if "Ghidra" not in description and "Ghidra-verified" not in description:
            fail(f"timing identity evidence is absent from {name}")

    expected_avcs_layout = {
        "Intake AVCS Target - AVLS Low Cam": (
            0x0007C5B0,
            0x0007C54C,
            0x0007C584,
            (14, 11),
        ),
        "Intake AVCS Target - AVLS High Cam": (
            0x0007C764,
            0x0007C6E4,
            0x0007C71C,
            (14, 18),
        ),
    }
    parent_tables = {
        table.get("name"): table for table in roms[0].findall("table")
    }
    for name, (expected_address, expected_x, expected_y, expected_size) in (
        expected_avcs_layout.items()
    ):
        table = tables.get(name)
        if table is None:
            fail(f"master definition is missing Ghidra-identified AVCS table {name}")
        target_address = int(table.get("storageaddress", "0"), 0)
        if target_address != expected_address:
            fail(
                f"master definition AVCS identity {name} points to "
                f"0x{target_address:05X}, expected 0x{expected_address:05X}"
            )
        axes = {
            child.get("type"): int(child.get("storageaddress", "0"), 0)
            for child in table.findall("table")
        }
        if axes != {"X Axis": expected_x, "Y Axis": expected_y}:
            fail(f"master definition AVCS axes are wrong for {name}: {axes}")
        parent_table = parent_tables[name]
        effective_size = (
            int(table.get("sizex", parent_table.get("sizex", "0"))),
            int(table.get("sizey", parent_table.get("sizey", "0"))),
        )
        if effective_size != expected_size:
            fail(
                f"master definition AVCS dimensions for {name} are "
                f"{effective_size}, expected {expected_size}"
            )
        description = table.findtext("description", "")
        if "not a left/right-bank map" not in description:
            fail(f"AVCS A/B selector meaning is absent from {name}")

    old_ambiguous_names = {
        "Intake Cam Advance Angle A (AVCS)",
        "Intake Cam Advance Angle B (AVCS)",
    }
    if old_ambiguous_names & (parent_names | target_names):
        fail("master definition retains ambiguous AVCS A/B labels")


def verify_logger_fragment() -> None:
    if not LOGGER_FRAGMENT.exists():
        fail(f"missing master logger fragment {LOGGER_FRAGMENT}")
    try:
        root = ET.parse(LOGGER_FRAGMENT).getroot()
    except ET.ParseError as exc:
        fail(f"master logger fragment does not parse: {exc}")
    if root.tag != "ecuparams":
        fail(f"master logger fragment root is <{root.tag}>, expected <ecuparams>")

    expected = {
        "E500": ("0xFFB098", "4", "float", {"x", "x*14.64"}),
        "E501": (
            "0xFFAB06",
            "2",
            "uint16",
            {"x", "x*0.0000762939453125"},
        ),
        "E502": ("0xFFAE70", "4", "float", {"x"}),
        "E503": ("0xFFCD86", "1", "uint8", {"x"}),
        "E504": ("0xFFC860", "1", "uint8", {"x"}),
        "E505": ("0xFFC85C", "2", "uint16", {"x"}),
        "E506": ("0xFFBE38", "1", "uint8", {"x"}),
        "E507": ("0xFFB688", "2", "uint16", {"x", "x/100"}),
        "E508": ("0xFFB834", "4", "float", {"x"}),
        "E509": ("0xFFB854", "4", "float", {"x"}),
        "E510": ("0xFFB868", "4", "float", {"x"}),
        "E511": ("0xFFB874", "4", "float", {"x"}),
        "E512": ("0xFFBE40", "4", "float", {"x"}),
        "E513": ("0xFFBE48", "4", "float", {"x"}),
    }
    parameters = list(root.findall("ecuparam"))
    by_id = {parameter.get("id"): parameter for parameter in parameters}
    if len(parameters) != len(by_id) or set(by_id) != set(expected):
        fail("master logger fragment has duplicate, missing, or unrelated parameter IDs")

    for parameter_id, (address, length, storage_type, expressions) in expected.items():
        parameter = by_id[parameter_id]
        ecus = list(parameter.findall("ecu"))
        if len(ecus) != 1 or ecus[0].get("id") != "3C5A387116":
            fail(f"logger parameter {parameter_id} is not restricted to D2WD610H ECU ID")
        addresses = list(ecus[0].findall("address"))
        if (
            len(addresses) != 1
            or addresses[0].get("length") != length
            or (addresses[0].text or "").strip() != address
        ):
            fail(f"logger parameter {parameter_id} has the wrong RAM address/length")
        conversions = list(parameter.findall("conversions/conversion"))
        if not conversions or {item.get("expr") for item in conversions} != expressions:
            fail(f"logger parameter {parameter_id} has unexpected conversions")
        if {item.get("storagetype") for item in conversions} != {storage_type}:
            fail(f"logger parameter {parameter_id} has the wrong storage type")

    if "fault sentinel" not in (by_id["E500"].get("desc") or ""):
        fail("logger lambda parameter does not document its 0.0 fault sentinel")
    if "greater than" not in (by_id["E502"].get("desc") or ""):
        fail("logger readiness parameter does not document the boost/CL threshold")
    if "committed" not in (by_id["E503"].get("desc") or ""):
        fail("logger AVLS parameter does not document committed-state selection")
    if "releases only" not in (by_id["E504"].get("desc") or ""):
        fail("logger lean-cut state does not document latch release")
    if "not milliseconds" not in (by_id["E505"].get("desc") or ""):
        fail("logger lean-cut counter does not document task-call units")
    if "derived" not in (by_id["E507"].get("desc") or ""):
        fail("logger engine-run counter does not qualify its derived timebase")
    for parameter_id in ("E508", "E509", "E510", "E511", "E512", "E513"):
        if "final fueling" not in (by_id[parameter_id].get("desc") or ""):
            fail(f"logger {parameter_id} does not document its fueling-path role")


def xml_signature(element: ET.Element) -> tuple:
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        (element.text or "").strip(),
        tuple(xml_signature(child) for child in element),
    )


def verify_logger_definition() -> None:
    if not LOGGER_DEFINITION.exists():
        fail(f"missing complete master logger definition {LOGGER_DEFINITION}")
    logger_bytes = LOGGER_DEFINITION.read_bytes()
    logger_hash = hashlib.sha256(logger_bytes).hexdigest()
    if logger_hash != EXPECTED_LOGGER_SHA256:
        fail(
            "complete master logger definition hash is "
            f"{logger_hash}, expected {EXPECTED_LOGGER_SHA256}"
        )
    text = logger_bytes.decode("utf-8")
    if "<!DOCTYPE logger [" not in text:
        fail("complete master logger definition lost its embedded DTD")
    try:
        logger_definition.validate_generated(
            text, retained=len(logger_definition.STOCK_ECU_PARAMETER_IDS)
        )
    except SystemExit as exc:
        fail(str(exc))

    root = ET.fromstring(text)
    if root.get("version") != "370":
        fail("complete master logger definition is not based on metric v370")
    protocol = root.find("./protocols/protocol")
    if protocol is None:
        fail("complete master logger definition has no SSM protocol")
    for required in ("transports", "parameters", "switches", "dtcodes", "ecuparams"):
        if protocol.find(required) is None:
            fail(f"complete master logger definition is missing <{required}>")

    generated = {
        item.get("id"): item
        for item in protocol.findall("parameters/parameter")
        if item.get("id") in logger_definition.PARAMETER_IDS
    }
    fragment_root = ET.parse(LOGGER_FRAGMENT).getroot()
    fragment = {
        item.get("id"): logger_definition.make_unconditional_parameter(item)
        for item in fragment_root.findall("ecuparam")
    }
    if set(generated) != set(fragment):
        fail("complete logger and project fragment have different master parameters")
    for parameter_id in sorted(fragment):
        if xml_signature(generated[parameter_id]) != xml_signature(fragment[parameter_id]):
            fail(f"complete logger parameter {parameter_id} is stale relative to fragment")
        if generated[parameter_id].find("address") is None:
            fail(f"complete logger parameter {parameter_id} is not always visible")


def verify_logger_profile() -> None:
    try:
        profile = ET.parse(LOGGER_PROFILE).getroot()
        logger = ET.parse(LOGGER_DEFINITION).getroot()
    except (OSError, ET.ParseError) as exc:
        fail(f"idle diagnostic logger profile is missing or invalid: {exc}")
    if profile.tag != "profile" or profile.get("protocol") != "SSM":
        fail("idle diagnostic logger profile is not an SSM profile")
    profile_parameters = profile.findall("./parameters/parameter")
    selected_ids = {item.get("id") for item in profile_parameters}
    logger_ids = {
        item.get("id")
        for path in (
            "./protocols/protocol/parameters/parameter",
            "./protocols/protocol/ecuparams/ecuparam",
        )
        for item in logger.findall(path)
    }
    if not selected_ids or not selected_ids <= logger_ids:
        fail("idle diagnostic profile refers to absent logger parameters")
    expected_custom = logger_definition.PARAMETER_IDS - {"E503", "E504", "E505"}
    live_custom = {
        item.get("id")
        for item in profile_parameters
        if item.get("livedata") == "selected" and item.get("id") in logger_definition.PARAMETER_IDS
    }
    if live_custom != expected_custom:
        fail("idle diagnostic profile has the wrong project parameter set")
    dashboard_custom = {
        item.get("id")
        for item in profile_parameters
        if item.get("dash") == "selected" and item.get("id") in logger_definition.PARAMETER_IDS
    }
    if dashboard_custom != expected_custom:
        fail("idle diagnostic profile has the wrong project dashboard channels")
    expected_stock_diagnostics = logger_definition.ALWAYS_VISIBLE_STOCK_PARAMETER_IDS
    selected_stock_diagnostics = selected_ids & expected_stock_diagnostics
    if selected_stock_diagnostics != expected_stock_diagnostics:
        fail("idle diagnostic profile omits a required stock high-resolution channel")


def verify_component_hooks(image: bytes, component_stage: bytes) -> None:
    expect(
        image,
        boost.REVLIM_FNPTR,
        boost.be32(fueling_safety.LEAN_CUT_WRAPPER_ADDR),
        "composed rev-limit/overboost/lean-cut wrapper pointer",
    )
    expect(
        image,
        rotational_idle.FINAL_TIMING_TASK_PTR,
        rotational_idle.be32(rotational_idle.ROT_IDLE_WRAPPER_ADDR),
        "rotational-idle final-timing wrapper pointer",
    )
    expect(
        image,
        speed_density.FINAL_AIRFLOW_HELPER_PTR,
        speed_density.be32(speed_density.WRAPPER_ADDR),
        "MAFless final-airflow helper pointer",
    )
    for address in speed_density.MAF_CONVERSION_CALL_ADDRS:
        expect(
            image,
            address,
            speed_density.MAF_CONVERSION_CALL_PATCHED,
            "raw MAF conversion removal",
        )
    expect(
        image,
        speed_density.MAF_LIMIT_UPDATE_CALL_ADDR,
        speed_density.MAF_CONVERSION_CALL_PATCHED,
        "raw MAF filter/limit removal",
    )
    expect(
        image,
        speed_density.MAF_INPUT_DIAGNOSTIC_TASK_PTR,
        speed_density.be32(speed_density.NOOP_TASK),
        "MAF input diagnostic bypass",
    )
    for address in speed_density.TEMPERATURE_MAF_CONDITION_TASK_PTRS:
        expect(
            image,
            address,
            speed_density.be32(speed_density.NOOP_TASK),
            "MAF-dependent diagnostic-condition bypass",
        )
    expect(image, speed_density.P0102_SWITCH_ADDR, b"\x00", "P0102 disable")
    expect(image, speed_density.P0103_SWITCH_ADDR, b"\x00", "P0103 disable")

    # Calibration edits intentionally alter some boost/free-space table bytes.
    # Every executable blob must remain byte-identical to the component stage.
    for address, size, label in (
        (boost.STUB_ADDR, len(boost.build_stub()), "boost controller"),
        (boost.REVWRAP_ADDR, len(boost.build_fuelcut_wrapper()), "overboost wrapper"),
        (
            rotational_idle.ROT_IDLE_WRAPPER_ADDR,
            len(rotational_idle.build_wrapper()),
            "bounded rotational-idle wrapper",
        ),
        (
            speed_density.WRAPPER_ADDR,
            len(speed_density.build_wrapper()),
            "committed-state dual-VE speed-density wrapper",
        ),
        (
            wideband.WIDEBAND_UPDATE_ADDR,
            len(wideband.build_wideband_update()),
            "wideband update",
        ),
        (
            wideband.INHIBIT_HELPER_ADDR,
            len(wideband.build_inhibit_helper()),
            "wideband inhibit helper",
        ),
        (
            wideband.BOOST_READY_GUARD_ADDR,
            len(wideband.build_boost_ready_guard()),
            "master sensor/SD-validity boost gate",
        ),
        (
            fueling_safety.PRESSURE_OL_WRAPPER_ADDR,
            len(fueling_safety.build_pressure_ol_wrapper()),
            "pressure-forced open-loop wrapper",
        ),
        (
            fueling_safety.LEAN_STATE_INITIALIZE_ADDR,
            len(fueling_safety.build_lean_state_initialize()),
            "lean-state zero initializer",
        ),
        (
            fueling_safety.LEAN_CUT_WRAPPER_ADDR,
            len(fueling_safety.build_lean_cut_wrapper()),
            "latched lean-cut wrapper",
        ),
    ):
        expect(image, address, component_stage[address : address + size], label)


def verify_independent_boost_switches(image: bytes) -> None:
    """Pin the two exact-01 decisions independently of the blob builders."""
    expect(image, boost.EBCS_ENABLE_ADDR, b"\x00", "spring-only EBCS default")
    expect(image, boost.OVERBOOST_ENABLE_ADDR, b"\x01", "hard-cut enable default")

    controller_blob = boost.build_stub()
    controller_decoded = decode_executable(
        image,
        controller_blob,
        boost.STUB_ADDR,
        {
            boost.EBCS_ENABLE_ADDR,
            boost.STOCK_OUTPUT,
            boost.THROTTLE_ADDR,
            boost.THROTTLE_GATE_ADDR,
            boost.RPM_ADDR,
            boost.BASE_DESC,
            boost.INTERP_2D,
            boost.TARGET_DESC,
            boost.MAP_ADDR,
            boost.OVERB_ADDR,
            boost.KP_ADDR,
            boost.MAXR_ADDR,
        },
        "boost controller",
    )
    expect(
        image,
        boost.STUB_ADDR,
        bytes.fromhex("d11e601088018903f48dd21d422b0009"),
        "exact-01 EBCS disabled path",
    )
    if controller_decoded.count("fldi0 fr4") < 2:
        fail("boost controller lacks zero-duty disabled/gated outcomes")

    cut_blob = boost.build_fuelcut_wrapper()
    cut_decoded = decode_executable(
        image,
        cut_blob,
        boost.REVWRAP_ADDR,
        {
            boost.REVLIMITER,
            boost.OVERBOOST_ENABLE_ADDR,
            boost.MAP_ADDR,
            boost.OVERB_FC_ADDR,
            boost.FUELCUT_FLAG,
        },
        "overboost fuel-cut wrapper",
    )
    expect(
        image,
        boost.REVWRAP_ADDR + 8,
        bytes.fromhex("d109601088018b09"),
        "independent exact-01 hard-cut branch",
    )
    if "or #128,r0" not in cut_decoded:
        fail("hard-cut wrapper does not set the verified fuel-cut flag bit")


def main() -> None:
    stock, expected, _, calibration_writes = master.build_image()
    component_stage, blobs = rebuild_component_stage(stock)
    independently_calibrated = bytearray(component_stage)
    independent_writes = calibration.apply_calibration(
        independently_calibrated, component_stage
    )
    independent_writes.update(
        speed_density.apply_predictable_avls_calibration(independently_calibrated)
    )
    speed_density.fix_checksum(independently_calibrated)
    checksum_data = bytes(
        independently_calibrated[
            calibration.CHECKSUM_TABLE_ADDR + 8 : calibration.CHECKSUM_TABLE_ADDR + 12
        ]
    )
    independent_writes["Subaru checksum"] = (
        calibration.CHECKSUM_TABLE_ADDR + 8,
        checksum_data,
    )
    if bytes(independently_calibrated) != expected:
        fail("independent component/calibration composition differs from master builder")
    if calibration_writes != independent_writes:
        fail("master calibration write manifest is not deterministic")

    if not OUTPUT.exists():
        fail(f"missing generated artifact {OUTPUT}")
    image = OUTPUT.read_bytes()
    if len(image) != master.ROM_SIZE:
        fail(f"master artifact is {len(image)} bytes, expected {master.ROM_SIZE}")
    if image != expected:
        differences = sorted(changed_set(expected, image))
        fail(
            "master artifact differs from a fresh rebuild at "
            + ", ".join(f"0x{address:05X}" for address in differences[:16])
        )
    output_hash = hashlib.sha256(image).hexdigest()
    if output_hash != EXPECTED_OUTPUT_SHA256:
        fail(
            f"master output hash changed to {output_hash}; update the pin only after audit"
        )

    if hashlib.sha256(stock).hexdigest() != master.STOCK_SHA256:
        fail("canonical stock SHA-256 changed")
    verify_layout(stock, image, blobs, calibration_writes)
    verify_component_hooks(image, component_stage)
    verify_independent_boost_switches(image)
    verify_rotational_idle(image)
    verify_omni_map(image)
    verify_avls_dual_ve(image)
    verify_wideband(image)
    try:
        fueling_safety_verify.verify_image(image)
    except AssertionError as exc:
        fail(f"fueling-safety audit: {exc}")

    # Run the independent calibration policy checks against the master
    # component stage: OL/CL fueling, all six calibrated timing surfaces
    # (including dormant B/E), KCA, AVCS, injectors, spring-only boost, rev
    # limit, and checksum.
    calibration_verify.verify_fueling(component_stage, image)
    calibration_verify.verify_cl_fueling(component_stage, image)
    calibration_verify.verify_base_timing(component_stage, image)
    calibration_verify.verify_kca(component_stage, image)
    calibration_verify.verify_avcs(component_stage, image)
    calibration_verify.verify_injectors(component_stage, image)
    calibration_verify.verify_auxiliary(component_stage, image)
    verify_definition()
    verify_logger_fragment()
    verify_logger_definition()
    verify_logger_profile()

    if master.STOCK.read_bytes() != stock or master.BASE_STOCK.read_bytes() != stock:
        fail("canonical stock or base_roms stock changed during verification")
    if master.extract_srf.extract_memd(master.SOURCE_SRF)[0] != stock:
        fail("original SRF payload changed during verification")

    stored, calculated, _ = calibration.checksum_value(image)
    print("master patch audit PASS")
    print(f"  stock SHA-256     : {master.STOCK_SHA256}")
    print(f"  output SHA-256    : {output_hash}")
    print(f"  checksum          : 0x{stored:08X} (valid={stored == calculated})")
    print("  air model         : always-on MAFless committed-state dual VE speed density")
    print("  MAP               : Omni MAP-SUP-3BR 30..300 kPa / 0.60..4.75 V")
    print("  IAT               : provisional HT-010206 curve; assumed 1.00-kohm ECU pull-up")
    print("  wideband/O2       : former-MAF 50-4110 P0/P1 input; four stock paths removed")
    print("  boost             : EBCS OFF; independent hard cut ON; zero-duty spring baseline")
    print("  load axes         : all eight active axes extend to 4.0 g/rev")
    print("  primary OL        : exact 1000..6800 RPM axes; conservative resample verified")
    print("  injectors         : pinned A4TE002B STI-pink flow/deadtime translation")
    print("  timing/AVLS       : dual VE; fixed 3200/3000 lift switch; cam timing endpoints identified")
    print("  rotational idle   : bounded retard-only component installed, default OFF")
    print("  memory layout     : no component, hook, calibration, or RAM collisions")
    print("  definition        : workflow-grouped master XML; dormant timing pair and obsolete defs omitted")
    print("  fueling safety    : pressure-forced OL ON; 13.0-AFR delayed/latched cut ON")
    print("  logger            : complete D2WD610H-only SSM definition and fragment validated")
    print("  provenance        : root stock, base copy, and SRF payload remain byte-identical")


if __name__ == "__main__":
    main()
