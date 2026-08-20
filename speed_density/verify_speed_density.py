#!/usr/bin/env python3
"""Static and binary verification for the D2WD610H speed-density component."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PATCH_DIR = ROOT / "patch"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PATCH_DIR))

import build_definition as definition  # noqa: E402
import patch_speed_density as patch  # noqa: E402
import patch_boost as boost  # noqa: E402
import patch_rotational_idle as rotational  # noqa: E402
import patch_single_front_af as front_af  # noqa: E402
import sh2_disasm  # noqa: E402


DEFAULT_IMAGE = HERE / "D2WD610H_speed_density.bin"


def expect(image: bytes, address: int, expected: bytes, label: str) -> None:
    actual = image[address : address + len(expected)]
    if actual != expected:
        raise SystemExit(
            "FAIL: %s @0x%05X is %s (expected %s)"
            % (label, address, actual.hex(), expected.hex())
        )


def changed_set(before: bytes, after: bytes) -> set[int]:
    return {
        index
        for index, (old, new) in enumerate(zip(before, after))
        if old != new
    }


def linear_interpolate(axis: tuple[float, ...], values: tuple[float, ...], point: float) -> float:
    if point <= axis[0]:
        return values[0]
    if point >= axis[-1]:
        return values[-1]
    for index in range(len(axis) - 1):
        if point <= axis[index + 1]:
            fraction = (point - axis[index]) / (axis[index + 1] - axis[index])
            return values[index] + fraction * (values[index + 1] - values[index])
    raise AssertionError("unreachable interpolation path")


def interpolate_ve(map_mmhg: float, rpm: float) -> float:
    row_values = []
    width = len(patch.MAP_AXIS)
    for row in range(len(patch.RPM_AXIS)):
        values = patch.VE_TABLE[row * width : (row + 1) * width]
        row_values.append(linear_interpolate(patch.MAP_AXIS, values, map_mmhg))
    return linear_interpolate(patch.RPM_AXIS, tuple(row_values), rpm)


def policy_model(
    map_mmhg: float,
    rpm: float,
    iat_c: float,
    global_multiplier: float = patch.GLOBAL_MULTIPLIER,
    displacement_litres: float = patch.DISPLACEMENT_LITRES,
    maximum_airflow: float = patch.MAX_AIRFLOW_G_S,
    map_minimum: float = patch.MAP_MIN_MMHG,
    map_maximum: float = patch.MAP_MAX_MMHG,
    rpm_minimum: float = patch.RPM_MIN,
    rpm_maximum: float = patch.RPM_MAX,
    iat_minimum: float = patch.IAT_MIN_C,
    iat_maximum: float = patch.IAT_MAX_C,
) -> float:
    if not math.isfinite(rpm):
        return patch.FAILSAFE_AIRFLOW_G_S
    if rpm == 0.0:
        return 0.0

    values = (
        map_mmhg,
        rpm,
        iat_c,
        global_multiplier,
        displacement_litres,
        maximum_airflow,
        map_minimum,
        map_maximum,
        rpm_minimum,
        rpm_maximum,
        iat_minimum,
        iat_maximum,
    )
    if not all(math.isfinite(value) for value in values):
        return patch.FAILSAFE_AIRFLOW_G_S
    if not (map_minimum <= map_mmhg <= map_maximum):
        return patch.FAILSAFE_AIRFLOW_G_S
    if not (rpm_minimum <= rpm <= rpm_maximum):
        return patch.FAILSAFE_AIRFLOW_G_S
    if not (iat_minimum <= iat_c <= iat_maximum):
        return patch.FAILSAFE_AIRFLOW_G_S
    if global_multiplier <= 0 or displacement_litres <= 0 or maximum_airflow <= 0:
        return patch.FAILSAFE_AIRFLOW_G_S

    ve = interpolate_ve(map_mmhg, rpm)
    iat_correction = linear_interpolate(
        patch.IAT_AXIS, patch.IAT_DENSITY_CORRECTION, iat_c
    )
    airflow = (
        ve
        * map_mmhg
        * rpm
        * displacement_litres
        * patch.AIRFLOW_CONSTANT_PER_LITRE_AT_20C
        * iat_correction
        * global_multiplier
    )
    if not math.isfinite(airflow) or airflow <= 0:
        return patch.FAILSAFE_AIRFLOW_G_S
    return min(airflow, maximum_airflow)


def retained_stock_load_model(airflow_g_s: float, rpm: float) -> float:
    """Model the Ghidra-verified B420 -> B428 normalization retained in stock code."""
    if rpm <= 0.0:
        return 0.0
    return min(airflow_g_s * 60.0 / rpm, 4.0)


def verify_policy_model() -> None:
    invalid_cases = (
        (math.nan, 3000.0, 20.0),
        (760.0, math.inf, 20.0),
        (760.0, 3000.0, math.nan),
        (patch.MAP_MIN_MMHG - 1.0, 3000.0, 20.0),
        (patch.MAP_MAX_MMHG + 1.0, 3000.0, 20.0),
        (760.0, patch.RPM_MIN - 1.0, 20.0),
        (760.0, patch.RPM_MAX + 1.0, 20.0),
        (760.0, 3000.0, patch.IAT_MIN_C - 1.0),
        (760.0, 3000.0, patch.IAT_MAX_C + 1.0),
    )
    for map_mmhg, rpm, iat_c in invalid_cases:
        if policy_model(map_mmhg, rpm, iat_c) != patch.FAILSAFE_AIRFLOW_G_S:
            raise SystemExit("FAIL: invalid sensor input did not select fixed fail-safe airflow")

    for invalid in (0.0, -1.0, math.nan, math.inf):
        if policy_model(760.0, 3000.0, 20.0, invalid) != patch.FAILSAFE_AIRFLOW_G_S:
            raise SystemExit("FAIL: invalid global multiplier did not select fail-safe")
        if (
            policy_model(
                760.0,
                3000.0,
                20.0,
                displacement_litres=invalid,
            )
            != patch.FAILSAFE_AIRFLOW_G_S
        ):
            raise SystemExit("FAIL: invalid displacement did not select fail-safe")
        if (
            policy_model(
                760.0,
                3000.0,
                20.0,
                maximum_airflow=invalid,
            )
            != patch.FAILSAFE_AIRFLOW_G_S
        ):
            raise SystemExit("FAIL: invalid maximum airflow did not select fail-safe")

    for gate_name in (
        "map_minimum",
        "map_maximum",
        "rpm_minimum",
        "rpm_maximum",
        "iat_minimum",
        "iat_maximum",
    ):
        for invalid in (math.nan, math.inf, -math.inf):
            if (
                policy_model(
                    760.0,
                    3000.0,
                    20.0,
                    **{gate_name: invalid},
                )
                != patch.FAILSAFE_AIRFLOW_G_S
            ):
                raise SystemExit(
                    "FAIL: invalid %s did not select fail-safe airflow" % gate_name
                )

    if policy_model(760.0, 0.0, 20.0) != 0.0:
        raise SystemExit("FAIL: exact zero RPM did not publish zero airflow")
    if policy_model(math.nan, 0.0, math.inf, map_minimum=math.nan) != 0.0:
        raise SystemExit("FAIL: zero RPM did not override uninitialized sensor/calibration data")

    samples = (
        ((300.0, 700.0, 20.0), 4.59107145),
        ((760.0, 3000.0, 20.0), 90.27877076),
        ((1018.5747, 6800.0, 20.0), 271.33833237),
        ((1150.0, 6800.0, 40.0), 290.80075930),
    )
    for arguments, expected in samples:
        actual = policy_model(*arguments)
        if not math.isclose(actual, expected, rel_tol=2e-7, abs_tol=2e-5):
            raise SystemExit(
                "FAIL: model sample %r = %.9f (expected %.9f)"
                % (arguments, actual, expected)
            )

    load_samples = (
        ((760.0, 3000.0, 20.0), 1.80557542),
        ((1018.5747, 6800.0, 20.0), 2.39416176),
    )
    for arguments, expected in load_samples:
        airflow = policy_model(*arguments)
        actual = retained_stock_load_model(airflow, arguments[1])
        if not math.isclose(actual, expected, rel_tol=2e-7, abs_tol=2e-6):
            raise SystemExit(
                "FAIL: retained calculated-load sample %r = %.9f g/rev (expected %.9f)"
                % (arguments, actual, expected)
            )

    capped = policy_model(1500.0, 7500.0, -10.0, maximum_airflow=300.0)
    if capped != 300.0:
        raise SystemExit("FAIL: maximum-airflow clamp model did not cap at 300 g/s")


def verify_definition() -> None:
    definition_bytes = definition.OUTPUT.read_text(encoding="utf-8")
    if definition_bytes != definition.render_definition():
        raise SystemExit("FAIL: generated RomRaider definition is stale")

    root = ET.fromstring(definition_bytes)
    roms = root.findall("rom")
    if len(roms) != 2:
        raise SystemExit("FAIL: speed-density definition must contain base + one D2WD610H ROM")
    targets = [
        rom
        for rom in roms
        if rom.findtext("romid/xmlid") == "D2WD610H_AVLS_SPEED_DENSITY_ONLY"
    ]
    if len(targets) != 1:
        raise SystemExit("FAIL: speed-density target xmlid missing or duplicated")
    target = targets[0]
    if target.findtext("romid/internalidstring") != "D2WD610H":
        raise SystemExit("FAIL: definition internal ID is not D2WD610H")

    expected_addresses = {
        "Speed Density Global Airflow Multiplier": patch.GLOBAL_MULTIPLIER_ADDR,
        "Speed Density Engine Displacement": patch.DISPLACEMENT_ADDR,
        "Speed Density Maximum Airflow": patch.MAX_AIRFLOW_ADDR,
        "Speed Density MAP Valid Range": patch.MAP_MIN_ADDR,
        "Speed Density RPM Valid Range": patch.RPM_MIN_ADDR,
        "Speed Density IAT Valid Range": patch.IAT_MIN_ADDR,
        "Speed Density VE (MAP x RPM)": patch.VE_DATA_ADDR,
        "Speed Density IAT Density Correction": patch.IAT_DATA_ADDR,
    }
    tables = {table.get("name"): table for table in target.findall("table")}
    for name, address in expected_addresses.items():
        table = tables.get(name)
        if table is None:
            raise SystemExit("FAIL: missing RomRaider target table %s" % name)
        actual = int(table.get("storageaddress", "0"), 16)
        if actual != address:
            raise SystemExit(
                "FAIL: %s address is 0x%X (expected 0x%X)" % (name, actual, address)
            )

    ve = tables["Speed Density VE (MAP x RPM)"]
    if int(ve.get("sizex", "0")) != len(patch.MAP_AXIS):
        raise SystemExit("FAIL: RomRaider VE X dimension mismatch")
    if int(ve.get("sizey", "0")) != len(patch.RPM_AXIS):
        raise SystemExit("FAIL: RomRaider VE Y dimension mismatch")
    child_addresses = {
        child.get("type"): int(child.get("storageaddress", "0"), 16)
        for child in ve.findall("table")
    }
    if child_addresses != {
        "X Axis": patch.MAP_AXIS_ADDR,
        "Y Axis": patch.RPM_AXIS_ADDR,
    }:
        raise SystemExit("FAIL: RomRaider VE axis addresses mismatch")

    inherited_names = {
        table.get("name")
        for rom in roms
        for table in rom.iter("table")
    }
    leaked = definition.REMOVED_MAF_TABLES & inherited_names
    if leaked:
        raise SystemExit("FAIL: generated MAFless definition retains %s" % sorted(leaked))
    if "Speed Density Patch Enable" in inherited_names:
        raise SystemExit("FAIL: generated MAFless definition retains the old fallback switch")


def verify_composition(stock: bytes) -> None:
    modules = (
        ("boost", boost),
        ("front-A/F", front_af),
        ("rotational idle", rotational),
        ("speed density", patch),
    )
    change_sets: dict[str, set[int]] = {}
    independent: dict[str, bytes] = {}
    for name, module in modules:
        candidate = bytearray(stock)
        module.apply_to_rom(candidate)
        independent[name] = bytes(candidate)
        change_sets[name] = changed_set(stock, candidate)

    for index, (left_name, _) in enumerate(modules):
        for right_name, _ in modules[index + 1 :]:
            overlap = change_sets[left_name] & change_sets[right_name]
            if overlap:
                raise SystemExit(
                    "FAIL: %s and %s overlap at %s"
                    % (
                        left_name,
                        right_name,
                        ", ".join("0x%05X" % value for value in sorted(overlap)[:16]),
                    )
                )

    combined = bytearray(stock)
    for _, module in modules:
        module.apply_to_rom(combined)
    union = set().union(*(change_sets[name] for name, _ in modules))
    if changed_set(stock, combined) != union:
        raise SystemExit("FAIL: four-component in-memory composition is not an exact union")
    for name, _ in modules:
        for address in change_sets[name]:
            if combined[address] != independent[name][address]:
                raise SystemExit(
                    "FAIL: composed %s byte differs at 0x%05X" % (name, address)
                )


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv if argv is None else argv
    if len(argv) > 2:
        raise SystemExit("usage: python3 verify_speed_density.py [patched.bin]")
    image_path = Path(argv[1]).resolve() if len(argv) == 2 else DEFAULT_IMAGE.resolve()

    stock = patch.STOCK.read_bytes()
    image = image_path.read_bytes()
    if len(stock) != 0x80000 or len(image) != 0x80000:
        raise SystemExit("FAIL: stock and patched images must both be exactly 512 KiB")
    stock_hash = hashlib.sha256(stock).hexdigest()
    if stock_hash != patch.STOCK_SHA256:
        raise SystemExit("FAIL: canonical root stock SHA-256 changed")

    expected = bytearray(stock)
    blobs = patch.apply_to_rom(expected)
    if image != expected:
        difference = sorted(changed_set(expected, image))
        raise SystemExit(
            "FAIL: image differs from deterministic rebuild at %s"
            % ", ".join("0x%05X" % address for address in difference[:32])
        )

    expect(
        image,
        patch.AIRFLOW_TASK_PTR,
        patch.be32(patch.STOCK_MAF_AIRFLOW_TASK),
        "retained stock airflow/load task pointer",
    )
    expect(
        image,
        patch.FINAL_AIRFLOW_CALL_SEQUENCE_ADDR,
        patch.FINAL_AIRFLOW_CALL_SEQUENCE_STOCK,
        "retained final-airflow call and B420 store sequence",
    )
    expect(
        image,
        patch.FINAL_AIRFLOW_HELPER_PTR,
        patch.be32(patch.WRAPPER_ADDR),
        "final-airflow helper hook",
    )
    expect(
        image,
        patch.STOCK_ENGINE_LOAD_CALC_ADDR,
        patch.STOCK_ENGINE_LOAD_CALC_SEQUENCE,
        "retained B420 * 60 / RPM to B428 engine-load calculation",
    )
    expect(
        image,
        patch.ENGINE_LOAD_SCALE_ADDR,
        patch.f32(60.0),
        "retained g/s-to-g/rev load scale",
    )
    expect(
        image,
        patch.ENGINE_LOAD_LIMIT_ADDR,
        patch.f32(4.0),
        "retained 4.0 g/rev engine-load limit",
    )
    for address in patch.MAF_CONVERSION_CALL_ADDRS:
        expect(
            image,
            address,
            patch.MAF_CONVERSION_CALL_PATCHED,
            "raw MAF conversion call removal",
        )
    expect(
        image,
        patch.MAF_LIMIT_UPDATE_CALL_ADDR,
        patch.MAF_CONVERSION_CALL_PATCHED,
        "stock MAF limit/filter update call removal",
    )
    expect(
        image,
        patch.MAF_INPUT_DIAGNOSTIC_TASK_PTR,
        patch.be32(patch.NOOP_TASK),
        "MAF input diagnostic task bypass",
    )
    for address in patch.TEMPERATURE_MAF_CONDITION_TASK_PTRS:
        expect(
            image,
            address,
            patch.be32(patch.NOOP_TASK),
            "temperature/MAF diagnostic-condition task bypass",
        )
    expect(image, patch.P0102_SWITCH_ADDR, b"\x00", "P0102 disabled")
    expect(image, patch.P0103_SWITCH_ADDR, b"\x00", "P0103 disabled")
    expect(
        image,
        patch.FAILSAFE_AIRFLOW_ADDR,
        patch.f32(patch.FAILSAFE_AIRFLOW_G_S),
        "fixed MAFless fail-safe airflow",
    )
    expect(
        image,
        patch.FINITE_FLOAT_MAX_ADDR,
        patch.be32(0x7F7FFFFF),
        "fixed maximum-finite-float guard",
    )
    for name, address, data in blobs:
        expect(image, address, data, name)

    expected_changed = {
        patch.FINAL_AIRFLOW_HELPER_PTR + offset for offset in range(4)
    }
    for address in patch.MAF_CONVERSION_CALL_ADDRS:
        expected_changed.update(
            range(address, address + len(patch.MAF_CONVERSION_CALL_PATCHED))
        )
    expected_changed.update(
        range(
            patch.MAF_LIMIT_UPDATE_CALL_ADDR,
            patch.MAF_LIMIT_UPDATE_CALL_ADDR + len(patch.MAF_CONVERSION_CALL_PATCHED),
        )
    )
    expected_changed.update(
        range(
            patch.MAF_INPUT_DIAGNOSTIC_TASK_PTR,
            patch.MAF_INPUT_DIAGNOSTIC_TASK_PTR + 4,
        )
    )
    for address in patch.TEMPERATURE_MAF_CONDITION_TASK_PTRS:
        expected_changed.update(range(address, address + 4))
    expected_changed.add(patch.P0102_SWITCH_ADDR)
    expected_changed.add(patch.P0103_SWITCH_ADDR)
    for _, address, data in blobs:
        expected_changed.update(range(address, address + len(data)))
    actual_changed = changed_set(stock, image)
    if actual_changed - expected_changed:
        raise SystemExit("FAIL: image contains changes outside the guarded hook/component")

    ve_descriptor = struct.unpack_from(">HHIIII", image, patch.VE_DESC_ADDR)
    if ve_descriptor != (
        len(patch.MAP_AXIS),
        len(patch.RPM_AXIS),
        patch.MAP_AXIS_ADDR,
        patch.RPM_AXIS_ADDR,
        patch.VE_DATA_ADDR,
        0,
    ):
        raise SystemExit("FAIL: float 3D VE descriptor mismatch")
    iat_descriptor = struct.unpack_from(">HBBII", image, patch.IAT_DESC_ADDR)
    if iat_descriptor != (
        len(patch.IAT_AXIS),
        0,
        0,
        patch.IAT_AXIS_ADDR,
        patch.IAT_DATA_ADDR,
    ):
        raise SystemExit("FAIL: float 2D IAT descriptor mismatch")

    for name, axis in (("MAP", patch.MAP_AXIS), ("RPM", patch.RPM_AXIS),
                       ("IAT", patch.IAT_AXIS)):
        if not all(axis[index] < axis[index + 1] for index in range(len(axis) - 1)):
            raise SystemExit("FAIL: %s axis is not strictly monotonic" % name)
    if not all(0.0 < value <= 1.15 for value in patch.VE_TABLE):
        raise SystemExit("FAIL: VE table contains an invalid default")
    if not all(math.isfinite(value) and value > 0 for value in patch.IAT_DENSITY_CORRECTION):
        raise SystemExit("FAIL: IAT correction contains an invalid default")

    # Decode the executable region only. Locate its single balanced return and
    # derive the aligned literal-pool boundary from the deterministic wrapper.
    wrapper = patch.build_wrapper()
    return_bytes = bytes.fromhex("4f26000b0009")
    return_offset = wrapper.find(return_bytes)
    if return_offset < 0 or wrapper.find(return_bytes, return_offset + 1) >= 0:
        raise SystemExit("FAIL: wrapper does not contain exactly one balanced return")
    wrapper_pool_addr = patch.WRAPPER_ADDR + ((return_offset + len(return_bytes) + 3) & ~3)
    wrapper_end = patch.WRAPPER_ADDR + len(wrapper)
    decoded = []
    for address in range(patch.WRAPPER_ADDR, wrapper_pool_addr, 2):
        text, _ = sh2_disasm.dis_one(image, address)
        decoded.append(text)
        if text.startswith(".word"):
            raise SystemExit(
                "FAIL: unknown injected opcode at 0x%05X: %s" % (address, text)
            )
    expect(
        image,
        patch.WRAPPER_ADDR + return_offset,
        return_bytes,
        "balanced wrapper return",
    )
    finite_guard_references = sum(
        "=0x%08x" % patch.FINITE_FLOAT_MAX_ADDR in text for text in decoded
    )
    if finite_guard_references != 12:
        raise SystemExit(
            "FAIL: expected 12 maximum-finite-float guard loads, found %d"
            % finite_guard_references
        )

    required_literals = {
        patch.FAILSAFE_AIRFLOW_ADDR,
        patch.MAP_ADDR,
        patch.RPM_ADDR,
        patch.IAT_ADDR,
        patch.VE_DESC_ADDR,
        patch.IAT_DESC_ADDR,
        patch.TABLE_3D_LOOKUP,
        patch.TABLE_2D_LOOKUP,
        patch.FINAL_MASS_AIRFLOW_ADDR,
        patch.SYNTHETIC_RAW_AIRFLOW_ADDR,
        patch.SYNTHETIC_FILTER_A_ADDR,
        patch.SYNTHETIC_FILTER_B_ADDR,
        patch.FINITE_FLOAT_MAX_ADDR,
    }
    literal_values = {
        struct.unpack_from(">I", image, address)[0]
        for address in range(wrapper_pool_addr, wrapper_end, 4)
    }
    if not required_literals <= literal_values:
        raise SystemExit("FAIL: wrapper literal pool is missing a pinned dependency")
    if patch.STOCK_MAF_AIRFLOW_TASK in literal_values:
        raise SystemExit(
            "FAIL: MAFless airflow helper contains the retained stock task address"
        )

    verify_policy_model()
    verify_definition()
    verify_composition(stock)
    if patch.STOCK.read_bytes() != stock:
        raise SystemExit("FAIL: canonical root stock ROM changed during verification")

    print("speed-density binary audit PASS")
    print("  stock SHA-256   : %s" % stock_hash)
    print("  output SHA-256  : %s" % hashlib.sha256(image).hexdigest())
    print("  retained task   : 0x%05X -> 0x%05X; B420*60/RPM -> B428/B438 g/rev remains active"
          % (patch.AIRFLOW_TASK_PTR, patch.STOCK_MAF_AIRFLOW_TASK))
    print("  airflow hook    : helper pointer 0x%05X -> 0x%05X before B420 store"
          % (patch.FINAL_AIRFLOW_HELPER_PTR, patch.WRAPPER_ADDR))
    print("  MAF removal     : converter/raw filter/diagnostics bypassed; final calculation replaced")
    print("  calibration     : %dx%d VE + %d-point IAT correction; %.3f L default"
          % (len(patch.MAP_AXIS), len(patch.RPM_AXIS), len(patch.IAT_AXIS),
             patch.DISPLACEMENT_LITRES))
    print("  output path     : final stock mass-airflow channel 0x%08X, capped at %.1f g/s"
          % (patch.FINAL_MASS_AIRFLOW_ADDR, patch.MAX_AIRFLOW_G_S))
    print("  fault policy    : fixed %.1f g/s rich/high-load value; zero only at zero RPM"
          % patch.FAILSAFE_AIRFLOW_G_S)
    print("  composition     : boost + front-A/F + rotational idle + speed density are disjoint")
    print("  definition      : regenerated from metric D2WD610H AVLS base; no unrelated ROM IDs")


if __name__ == "__main__":
    main()
