#!/usr/bin/env python3
"""Independent structural audit for the D2WD610H AVLS dual-VE image."""

from __future__ import annotations

import hashlib
import importlib.util
import math
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for directory in (ROOT / "patch", ROOT / "speed_density", HERE):
    sys.path.insert(0, str(directory))

import patch_avls_ve as avls_ve  # noqa: E402
import patch_speed_density as speed_density  # noqa: E402
import sh2_disasm  # noqa: E402

_definition_spec = importlib.util.spec_from_file_location(
    "avls_ve_build_definition", HERE / "build_definition.py"
)
if _definition_spec is None or _definition_spec.loader is None:
    raise RuntimeError("cannot load AVLS dual-VE definition generator")
definition = importlib.util.module_from_spec(_definition_spec)
_definition_spec.loader.exec_module(definition)


OUTPUT = HERE / "D2WD610H_avls_dual_ve.bin"
DEFINITION = HERE / "D2WD610H_AVLS_dual_ve_patch.xml"
EXPECTED_OUTPUT_SHA256 = "9cfcf45d075818c1a8320e540eb855979289ce25a6e03b8879a0c4767db49d16"


def fail(message: str) -> None:
    raise SystemExit("FAIL: " + message)


def read_floats(image: bytes, address: int, count: int) -> tuple[float, ...]:
    return struct.unpack_from(">" + "f" * count, image, address)


def descriptor(image: bytes, address: int) -> tuple[int, int, int, int, int, int]:
    return struct.unpack_from(">HHIIII", image, address)


def rebuild() -> bytes:
    stock = avls_ve.STOCK.read_bytes()
    rom = bytearray(stock)
    speed_density.apply_to_rom(rom)
    avls_ve.apply_to_rom(rom)
    avls_ve.apply_predictable_avls_calibration(rom)
    avls_ve.fix_checksum(rom)
    return bytes(rom)


def verify_wrapper(image: bytes) -> None:
    wrapper = avls_ve.build_wrapper()
    actual = image[avls_ve.WRAPPER_ADDR : avls_ve.WRAPPER_ADDR + len(wrapper)]
    if actual != wrapper:
        fail("committed-state dual-VE airflow wrapper differs from builder")

    required_literals = {
        speed_density.RPM_ADDR,
        speed_density.MAP_ADDR,
        speed_density.IAT_ADDR,
        speed_density.MAP_MIN_ADDR,
        speed_density.MAP_MAX_ADDR,
        speed_density.RPM_MIN_ADDR,
        speed_density.RPM_MAX_ADDR,
        speed_density.IAT_MIN_ADDR,
        speed_density.IAT_MAX_ADDR,
        speed_density.GLOBAL_MULTIPLIER_ADDR,
        speed_density.DISPLACEMENT_ADDR,
        speed_density.MAX_AIRFLOW_ADDR,
        speed_density.FINITE_FLOAT_MAX_ADDR,
        speed_density.AIRFLOW_CONSTANT_ADDR,
        speed_density.IAT_DESC_ADDR,
        speed_density.TABLE_3D_LOOKUP,
        speed_density.TABLE_2D_LOOKUP,
        speed_density.FAILSAFE_AIRFLOW_ADDR,
        speed_density.FINAL_MASS_AIRFLOW_ADDR,
        speed_density.SYNTHETIC_RAW_AIRFLOW_ADDR,
        speed_density.SYNTHETIC_FILTER_A_ADDR,
        speed_density.SYNTHETIC_FILTER_B_ADDR,
        avls_ve.AVLS_COMMITTED_MODE_ADDR,
        avls_ve.LOW_VE_DESC_ADDR,
        avls_ve.HIGH_VE_DESC_ADDR,
    }
    pool_start = avls_ve.WRAPPER_ADDR + len(wrapper) - 4 * len(required_literals)
    if pool_start & 3:
        fail("dual-VE wrapper literal pool is not aligned")
    actual_literals = {
        struct.unpack_from(">I", wrapper, offset)[0]
        for offset in range(pool_start - avls_ve.WRAPPER_ADDR, len(wrapper), 4)
    }
    if actual_literals != required_literals:
        fail(
            "dual-VE literal pool differs: missing=%s extra=%s"
            % (sorted(required_literals - actual_literals), sorted(actual_literals - required_literals))
        )
    if speed_density.VE_DESC_ADDR in actual_literals:
        fail("dual-VE wrapper still references the obsolete single full-range descriptor")

    decoded: list[str] = []
    for address in range(avls_ve.WRAPPER_ADDR, pool_start, 2):
        instruction, _ = sh2_disasm.dis_one(image, address)
        if instruction.startswith(".word"):
            fail(f"unknown dual-VE opcode at 0x{address:05X}: {instruction}")
        decoded.append(instruction)
    joined = "\n".join(decoded)
    if "cmp/eq #3,r0" not in joined:
        fail("wrapper lacks committed high-lift mode comparison")
    if decoded.count("jsr @r2") != 2:
        fail("wrapper must contain exactly the VE and IAT lookup calls")


def verify_tables(image: bytes) -> None:
    low_desc = descriptor(image, avls_ve.LOW_VE_DESC_ADDR)
    high_desc = descriptor(image, avls_ve.HIGH_VE_DESC_ADDR)
    expected_low = (
        len(speed_density.MAP_AXIS), len(avls_ve.LOW_RPM_AXIS),
        speed_density.MAP_AXIS_ADDR, avls_ve.LOW_RPM_AXIS_ADDR,
        avls_ve.LOW_VE_DATA_ADDR, 0,
    )
    expected_high = (
        len(speed_density.MAP_AXIS), len(avls_ve.HIGH_RPM_AXIS),
        speed_density.MAP_AXIS_ADDR, avls_ve.HIGH_RPM_AXIS_ADDR,
        avls_ve.HIGH_VE_DATA_ADDR, 0,
    )
    if low_desc != expected_low or high_desc != expected_high:
        fail("dual-VE descriptor contents are wrong")

    low_axis = read_floats(image, avls_ve.LOW_RPM_AXIS_ADDR, len(avls_ve.LOW_RPM_AXIS))
    high_axis = read_floats(image, avls_ve.HIGH_RPM_AXIS_ADDR, len(avls_ve.HIGH_RPM_AXIS))
    if low_axis != avls_ve.LOW_RPM_AXIS or high_axis != avls_ve.HIGH_RPM_AXIS:
        fail("dual-VE RPM axis differs from the truthful operating ranges")
    if low_axis[-1] != avls_ve.AVLS_ENGAGE_RPM:
        fail("low-lift table does not stop at engage RPM")
    if high_axis[0] != avls_ve.AVLS_RELEASE_RPM:
        fail("high-lift table does not start at release RPM")

    low = read_floats(image, avls_ve.LOW_VE_DATA_ADDR, len(avls_ve.LOW_VE_TABLE))
    high = read_floats(image, avls_ve.HIGH_VE_DATA_ADDR, len(avls_ve.HIGH_VE_TABLE))
    for label, actual, expected in (
        ("low", low, avls_ve.LOW_VE_TABLE),
        ("high", high, avls_ve.HIGH_VE_TABLE),
    ):
        if any(not math.isclose(a, b, abs_tol=1e-7) for a, b in zip(actual, expected)):
            fail(f"{label}-lift VE seed differs from the original conservative surface")
        if any(not math.isfinite(value) or value <= 0.0 for value in actual):
            fail(f"{label}-lift VE contains an invalid value")

    columns = len(speed_density.MAP_AXIS)
    low_3000 = low[-2 * columns : -columns]
    high_3000 = high[:columns]
    if low_3000 != high_3000:
        fail("low/high seed surfaces are discontinuous at 3000 RPM")


def verify_predictable_avls(image: bytes) -> None:
    expected_speed = avls_ve.AVLS_SPEED_DISABLED
    for address in (avls_ve.AVLS_NORMAL_SPEED_DATA_ADDR, avls_ve.AVLS_HOT_SPEED_DATA_ADDR):
        if read_floats(image, address, avls_ve.AVLS_SPEED_ROWS) != expected_speed:
            fail(f"vehicle-speed AVLS request remains active at 0x{address:05X}")
    for address in (avls_ve.AVLS_FIXED_SPEED_A_ADDR, avls_ve.AVLS_FIXED_SPEED_B_ADDR):
        if read_floats(image, address, 1)[0] != avls_ve.AVLS_SPEED_DISABLED_VALUE:
            fail(f"fixed/fallback vehicle-speed AVLS request remains active at 0x{address:05X}")
    values = (
        read_floats(image, avls_ve.AVLS_ACTUATION_MIN_RPM_ADDR, 1)[0],
        read_floats(image, avls_ve.AVLS_RELEASE_RPM_ADDR, 1)[0],
        read_floats(image, avls_ve.AVLS_ENGAGE_RPM_ADDR, 1)[0],
    )
    if values != (
        avls_ve.AVLS_ACTUATION_MIN_RPM,
        avls_ve.AVLS_RELEASE_RPM,
        avls_ve.AVLS_ENGAGE_RPM,
    ):
        fail(f"predictable AVLS RPM policy is {values}")
    if not values[0] == values[1] < values[2]:
        fail("AVLS engage/release/minimum ordering is unsafe")


def verify_definition() -> None:
    if not DEFINITION.is_file():
        fail(f"missing generated definition {DEFINITION}")
    generated = definition.build_tree().getroot()
    stored = ET.parse(DEFINITION).getroot()
    definition.validate(stored)
    ET.indent(generated, space=" ")
    generated_xml = ET.canonicalize(
        xml_data=ET.tostring(generated, encoding="unicode"),
        strip_text=True,
    )
    stored_xml = ET.canonicalize(
        xml_data=ET.tostring(stored, encoding="unicode"),
        strip_text=True,
    )
    if stored_xml != generated_xml:
        fail("dual-VE definition is stale")


def main() -> None:
    stock = avls_ve.STOCK.read_bytes()
    if hashlib.sha256(stock).hexdigest() != avls_ve.STOCK_SHA256:
        fail("canonical stock hash changed")
    if not OUTPUT.is_file():
        fail(f"missing generated artifact {OUTPUT}")
    image = OUTPUT.read_bytes()
    rebuilt = rebuild()
    if image != rebuilt:
        fail("generated artifact is not byte-identical to a fresh rebuild")
    digest = hashlib.sha256(image).hexdigest()
    if digest != EXPECTED_OUTPUT_SHA256:
        fail(f"output SHA-256 is {digest}, expected {EXPECTED_OUTPUT_SHA256}")
    stored, calculated = avls_ve.checksum_value(image)
    if stored != calculated:
        fail("Subaru checksum is invalid")

    verify_wrapper(image)
    verify_tables(image)
    verify_predictable_avls(image)
    verify_definition()
    if avls_ve.STOCK.read_bytes() != stock:
        fail("canonical stock changed during verification")

    print("AVLS dual-VE audit PASS")
    print(f"  output SHA-256 : {digest}")
    print(f"  checksum       : 0x{stored:08X}")
    print("  selector       : committed AVLS mode 3 -> high; all other modes -> low")
    print(f"  low-lift VE    : 13x{len(avls_ve.LOW_RPM_AXIS)}, 0..3200 RPM")
    print(f"  high-lift VE   : 13x{len(avls_ve.HIGH_RPM_AXIS)}, 3000..7500 RPM")
    print("  AVLS policy    : vehicle-speed path unreachable; 3200/3000 RPM hysteresis")


if __name__ == "__main__":
    main()
