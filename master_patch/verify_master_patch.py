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
BASE_TURBO_DIR = ROOT / "base_turbo_map"
for directory in (PATCH_DIR, SD_DIR, BASE_TURBO_DIR, HERE):
    sys.path.insert(0, str(directory))

import build_definition as definition  # noqa: E402
import build_master_patch as master  # noqa: E402
import wideband_component as wideband  # noqa: E402
import patch_boost as boost  # noqa: E402
import patch_speed_density as speed_density  # noqa: E402
import build_base_turbo_map as base_turbo  # noqa: E402
import verify_base_turbo_map as base_turbo_verify  # noqa: E402
import sh2_disasm  # noqa: E402


OUTPUT = HERE / "D2WD610H_master_patch.bin"
DEFINITION = HERE / "D2WD610H_master_patch.xml"
LOGGER_FRAGMENT = HERE / "D2WD610H_master_logger_ecuparams.xml"
EXPECTED_OUTPUT_SHA256 = "6557eda87eebaef51892b6607175cbd19b909565c3de6d9f90fe5e597aec0fac"
ROTATIONAL_IDLE_RESERVED_START = 0x0007DB40
ROTATIONAL_IDLE_RESERVED_END = 0x0007DCEB


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
    blobs["speed_density"] = speed_density.apply_to_rom(stage)
    blobs["wideband"] = wideband.apply_to_rom(stage)
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

    # The optional rotational-idle component has a reserved, intentionally
    # unused allocation between boost and speed density.  Master must not
    # silently absorb or alter it.
    if image[ROTATIONAL_IDLE_RESERVED_START : ROTATIONAL_IDLE_RESERVED_END + 1] != stock[
        ROTATIONAL_IDLE_RESERVED_START : ROTATIONAL_IDLE_RESERVED_END + 1
    ]:
        fail("master modifies the separate rotational-idle reserved region")

    allowed = set(free_owned)
    for address, size in (
        (boost.MAP_SCALING_ADDR, 8),
        (master.MAP_LOW_CEL_RAW_ADDR, 2),
        (boost.HIJACK_LITERAL, 4),
        (boost.REVLIM_FNPTR, 4),
        (speed_density.FINAL_AIRFLOW_HELPER_PTR, 4),
        (speed_density.MAF_LIMIT_UPDATE_CALL_ADDR, 2),
        (speed_density.MAF_INPUT_DIAGNOSTIC_TASK_PTR, 4),
        (wideband.FRONT_AF_PROCESS_ENTRY, 12),
        (wideband.BANK1_INHIBIT_ENTRY, 12),
        (wideband.BANK2_INHIBIT_ENTRY, 12),
        (wideband.FRONT_PUMP_DIAG_TASK_PTR, 4),
        (wideband.REAR_O2_PROCESS_ENTRY, 12),
    ):
        allowed.update(range(address, address + size))
    for address in speed_density.MAF_CONVERSION_CALL_ADDRS:
        allowed.update(range(address, address + 2))
    for address in speed_density.TEMPERATURE_MAF_CONDITION_TASK_PTRS:
        allowed.update(range(address, address + 4))
    for address in (speed_density.P0102_SWITCH_ADDR, speed_density.P0103_SWITCH_ADDR):
        allowed.add(address)
    for address, _, _ in wideband.REAR_O2_TASK_POINTERS:
        allowed.update(range(address, address + 4))
    for address in wideband.DISABLED_O2_DTC_SWITCHES.values():
        allowed.add(address)
    for _, (address, data) in calibration_writes.items():
        allowed.update(range(address, address + len(data)))

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
        < max(base_turbo.BOOST_TARGET_NATIVE)
        < speed_density.MAP_MAX_MMHG
    ):
        fail("5 psi target is outside the speed-density MAP validity window")


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
    sample = wideband_policy(round(2.5 / wideband.RAW_ADC_TO_VOLTS))
    if sample is None or not math.isclose(sample[1], 0.90425, abs_tol=2e-5):
        fail("wideband policy does not reproduce the AEM 2.5 V lambda value")

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
    ve = tables.get("Speed Density VE (MAP x RPM)")
    if ve is None or (
        int(ve.get("sizex", "0")), int(ve.get("sizey", "0"))
    ) != (len(speed_density.MAP_AXIS), len(speed_density.RPM_AXIS)):
        fail("master definition VE dimensions do not match firmware")
    axes = {
        child.get("type"): int(child.get("storageaddress", "0"), 0)
        for child in ve.findall("table")
    }
    if axes != {
        "X Axis": speed_density.MAP_AXIS_ADDR,
        "Y Axis": speed_density.RPM_AXIS_ADDR,
    }:
        fail("master definition VE axes do not match firmware")

    parent_names = {table.get("name") for table in roms[0].findall("table")}
    target_names = set(tables)
    obsolete = definition.DROP_NAMES & (parent_names | target_names)
    if obsolete:
        fail(f"master definition retains obsolete tables: {sorted(obsolete)}")
    categories = {table.get("category") for table in roms[0].findall("table")}
    if categories & definition.DROP_CATEGORIES:
        fail("master definition retains diagnostic/readiness categories")

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
        "E500": ("0xFFB098", "4", "float", {"x", "x*14.7"}),
        "E501": (
            "0xFFAB06",
            "2",
            "uint16",
            {"x", "x*0.0000762939453125"},
        ),
        "E502": ("0xFFAE70", "4", "float", {"x"}),
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


def verify_component_hooks(image: bytes, component_stage: bytes) -> None:
    expect(
        image,
        boost.REVLIM_FNPTR,
        boost.be32(boost.REVWRAP_ADDR),
        "overboost rev-limiter wrapper pointer",
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
            speed_density.WRAPPER_ADDR,
            len(speed_density.build_wrapper()),
            "speed-density wrapper",
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
    ):
        expect(image, address, component_stage[address : address + size], label)


def main() -> None:
    stock, expected, _, calibration_writes = master.build_image()
    component_stage, blobs = rebuild_component_stage(stock)
    independently_calibrated = bytearray(component_stage)
    independent_writes = base_turbo.apply_calibration(
        independently_calibrated, component_stage
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
    verify_omni_map(image)
    verify_wideband(image)

    # Reuse the already-audited tune-policy verifier against the new master
    # component stage: fueling, all six calibrated timing surfaces (including
    # dormant B/E), KCA, injectors, AVLS, spring-only boost, rev limit/checksum.
    base_turbo_verify.verify_fueling(component_stage, image)
    base_turbo_verify.verify_base_timing(component_stage, image)
    base_turbo_verify.verify_kca(component_stage, image)
    base_turbo_verify.verify_injectors(component_stage, image)
    base_turbo_verify.verify_avls(component_stage, image)
    base_turbo_verify.verify_auxiliary(component_stage, image)
    verify_definition()
    verify_logger_fragment()

    if master.STOCK.read_bytes() != stock or master.BASE_STOCK.read_bytes() != stock:
        fail("canonical stock or base_roms stock changed during verification")
    if master.extract_srf.extract_memd(master.SOURCE_SRF)[0] != stock:
        fail("original SRF payload changed during verification")

    stored, calculated, _ = base_turbo.checksum_value(image)
    print("master patch audit PASS")
    print(f"  stock SHA-256     : {master.STOCK_SHA256}")
    print(f"  output SHA-256    : {output_hash}")
    print(f"  checksum          : 0x{stored:08X} (valid={stored == calculated})")
    print("  air model         : always-on MAFless 13x17 VE speed density")
    print("  MAP               : Omni MAP-SUP-3BR 30..300 kPa / 0.60..4.75 V")
    print("  wideband/O2       : former-MAF AEM input; four stock paths + 18 DTCs removed")
    print("  boost             : zero-duty spring baseline; throttle/SD/sensor/soft/hard gates")
    print("  injectors         : pinned A4TE002B STI-pink flow/deadtime translation")
    print("  timing/AVLS       : cam + AVCS-tracking endpoints identified; conservative caps; early AVLS")
    print("  definition        : focused master XML; dormant timing pair and obsolete defs omitted")
    print("  logger            : D2WD610H-only lambda/raw-ADC/readiness fragment validated")
    print("  provenance        : root stock, base copy, and SRF payload remain byte-identical")


if __name__ == "__main__":
    main()
