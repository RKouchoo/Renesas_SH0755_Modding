#!/usr/bin/env python3
"""Binary verifier for D2WD610H_5psi_98RON_base_turbo.bin."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import build_base_turbo_map as base  # noqa: E402


OUTPUT = HERE / "D2WD610H_5psi_98RON_base_turbo.bin"
DEFINITION = ROOT / "defs" / "D2WD610H_AVLS_boost_single_front_af_patch.xml"
EXPECTED_OUTPUT_SHA256 = "fd9a9354c7a9f2d82813253d41b17adb058b68ceb3f426a0c197a6322fbf2c0f"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def read_float(image: bytes, address: int) -> float:
    return struct.unpack_from(">f", image, address)[0]


def raw_to_lambda(raw: int) -> float:
    return 1.0 / (1.0 + raw / 128.0)


def raw_to_base_timing(raw: int) -> float:
    return raw * 0.3515625 - 20.0


def raw_to_kca(raw: int) -> float:
    return raw * 0.3515625


def allowed_offsets() -> set[int]:
    allowed: set[int] = set()
    for _, address, size in base.CALIBRATION_REGIONS:
        region = set(range(address, address + size))
        if allowed & region:
            fail(f"declared calibration regions overlap at 0x{min(allowed & region):05X}")
        allowed.update(region)
    return allowed


def verify_definition() -> None:
    root = ET.parse(DEFINITION).getroot()
    roms = root.findall("rom")
    if len(roms) != 2:
        fail(f"combined definition should contain 32BITBASE + one target, found {len(roms)}")
    target = roms[-1]
    xmlid = target.findtext("./romid/xmlid")
    if xmlid != "D2WD610H_AVLS_BOOST_SINGLE_FRONT_AF_PATCH":
        fail(f"unexpected combined definition XMLID {xmlid!r}")

    expected_addresses = {
        "Primary Open Loop Fueling A ": base.PRIMARY_OL_A_ADDR,
        "Primary Open Loop Fueling B ": base.PRIMARY_OL_B_ADDR,
        "CL to OL Delay (Atm. Pressure)": base.CL_OL_DELAY_ADDR,
        "Base Timing A": 0x78AA0,
        "Base Timing B": 0x78BAC,
        "Base Timing C": 0x78CD0,
        "Base Timing D": 0x78E34,
        "Base Timing E": 0x78F40,
        "Base Timing F": 0x79064,
        "Knock Correction Advance Max A": 0x7924C,
        "Knock Correction Advance Max B": 0x793AC,
        "Timing Compensation (IAT)": base.IAT_TIMING_COMP_ADDR,
        "Rev Limit A": base.REV_LIMIT_A_ADDR,
        "Injector Latency": base.INJECTOR_LATENCY_ADDR,
        "Injector Flow Scaling ": base.INJECTOR_FLOW_ADDR,
        "Cranking Fuel Injector Pulse Width A (ECT)": 0x76B76,
        "Cranking Fuel Injector Pulse Width B (ECT)": 0x76B96,
        "Cranking Fuel Injector Pulse Width C (ECT)": 0x76BB6,
        "Cranking Fuel Injector Pulse Width D (ECT)": 0x76BD6,
        "Throttle Tip-in Enrichment A": 0x7739C,
        "Throttle Tip-in Enrichment B": 0x773BC,
        "Minimum Tip-in Enrichment Activation": base.MIN_TIP_IN_ACTIVATION_ADDR,
        "AVLS Switchover Load Threshold 1": base.AVLS_THRESHOLD_1_ADDR,
        "AVLS Switchover Load Threshold 2": base.AVLS_THRESHOLD_2_ADDR,
        "AVLS Actuation Minimum RPM": base.AVLS_ACTUATION_MIN_RPM_ADDR,
        "AVLS High Cam Release RPM": base.AVLS_RELEASE_RPM_ADDR,
        "AVLS High Cam Engage RPM": base.AVLS_ENGAGE_RPM_ADDR,
        "Boost Wastegate Duty (RPM)": base.boost.BASE_DATA,
        "Boost Target (RPM)": base.boost.TARGET_DATA,
        "Boost Kp (proportional gain)": base.boost.KP_ADDR,
        "Boost Max Duty Ratio": base.boost.MAXR_ADDR,
        "Boost Overboost Cut (Duty, soft)": base.boost.OVERB_ADDR,
        "Boost Overboost Fuel Cut (hard)": base.boost.OVERB_FC_ADDR,
        "Boost Control Patch Enable": base.boost.BOOST_ENABLE_ADDR,
        "Single Front A/F Patch Enable": 0x7D91C,
        "Checksum Fix": base.CHECKSUM_TABLE_ADDR,
    }
    target_tables = {table.get("name"): table for table in target.findall("table")}
    for name, address in expected_addresses.items():
        table = target_tables.get(name)
        if table is None:
            fail(f"combined definition is missing {name}")
        actual = int(table.get("storageaddress", "-1"), 0)
        if actual != address:
            fail(f"{name} XML address is 0x{actual:X}, expected 0x{address:X}")


def verify_fueling(reference: bytes, image: bytes) -> None:
    load_axis = base.read_floats(image, base.PRIMARY_OL_A_LOAD_AXIS, base.PRIMARY_OL_X)
    load_axis_b = base.read_floats(image, base.PRIMARY_OL_B_LOAD_AXIS, base.PRIMARY_OL_X)
    if any(abs(a - b) > 1e-5 for a, b in zip(load_axis, base.TUNED_FUEL_LOAD_AXIS)) or any(
        abs(a - b) > 1e-5 for a, b in zip(load_axis_b, base.TUNED_FUEL_LOAD_AXIS)
    ):
        fail(f"Primary OL load axes are not the intended expanded axis: {load_axis}/{load_axis_b}")
    rpm_axis = base.read_floats(image, base.PRIMARY_OL_A_RPM_AXIS, base.PRIMARY_OL_Y)
    data_size = base.PRIMARY_OL_X * base.PRIMARY_OL_Y
    ref_a = reference[base.PRIMARY_OL_A_ADDR:base.PRIMARY_OL_A_ADDR + data_size]
    ref_b = reference[base.PRIMARY_OL_B_ADDR:base.PRIMARY_OL_B_ADDR + data_size]
    out_a = image[base.PRIMARY_OL_A_ADDR:base.PRIMARY_OL_A_ADDR + data_size]
    out_b = image[base.PRIMARY_OL_B_ADDR:base.PRIMARY_OL_B_ADDR + data_size]

    for y_index, rpm in enumerate(rpm_axis):
        for x_index, load in enumerate(load_axis):
            offset = y_index * base.PRIMARY_OL_X + x_index
            rounded_load = round(load, 2)
            if rounded_load not in base.FUEL_LAMBDA_CAPS:
                if out_a[offset] != ref_a[offset] or out_b[offset] != ref_b[offset]:
                    fail(f"Primary OL changed outside high-load policy at {rpm:.0f} RPM/{load:.2f}")
                continue
            if out_a[offset] != out_b[offset]:
                fail(f"Primary OL bank targets differ at {rpm:.0f} RPM/{load:.2f}")
            if out_a[offset] < ref_a[offset] or out_b[offset] < ref_b[offset]:
                fail(f"Primary OL became leaner at {rpm:.0f} RPM/{load:.2f}")
            lambda_cap = base.FUEL_LAMBDA_CAPS[rounded_load]
            if rpm >= 6000.0 and load >= 1.22 - 1e-5:
                lambda_cap -= 0.01
            if raw_to_lambda(out_a[offset]) > lambda_cap + 1e-9:
                fail(f"Primary OL exceeds lambda cap at {rpm:.0f} RPM/{load:.2f}")

    if struct.unpack_from(">HH", image, base.CL_OL_DELAY_ADDR) != (0, 0):
        fail("CL-to-OL atmospheric delay is not zeroed")


def verify_base_timing(reference: bytes, image: bytes) -> None:
    load_axis = base.read_floats(image, base.TIMING_LOAD_AXIS_ADDR, base.TIMING_X)
    if any(abs(a - b) > 1e-5 for a, b in zip(load_axis, base.TUNED_TIMING_LOAD_AXIS)):
        fail(f"base-timing load axis is not the intended expanded axis: {load_axis}")
    for label, address, rpm_axis_address, rows in base.TIMING_MAPS:
        rpm_axis = base.read_floats(image, rpm_axis_address, rows)
        size = base.TIMING_X * rows
        old = reference[address:address + size]
        new = image[address:address + size]
        for y_index, rpm in enumerate(rpm_axis):
            for x_index, load in enumerate(load_axis):
                offset = y_index * base.TIMING_X + x_index
                if new[offset] > old[offset]:
                    fail(f"{label} advanced at {rpm:.0f} RPM/{load:.2f}")
                rounded_load = round(load, 2)
                in_policy = rpm >= 2000.0 and rounded_load in base.TIMING_LOAD_OFFSETS
                if not in_policy and new[offset] != old[offset]:
                    fail(f"{label} changed outside boost region at {rpm:.0f} RPM/{load:.2f}")
                if in_policy:
                    cap = (base.interpolate(base.FULL_BOOST_TIMING_CAP, rpm)
                           + base.TIMING_LOAD_OFFSETS[rounded_load])
                    if raw_to_base_timing(new[offset]) > cap + 1e-9:
                        fail(f"{label} exceeds timing cap at {rpm:.0f} RPM/{load:.2f}")


def verify_kca(reference: bytes, image: bytes) -> None:
    for label, address, load_axis_address, rpm_axis_address, rows in base.KCA_MAPS:
        load_axis = base.read_floats(image, load_axis_address, base.TIMING_X)
        if any(abs(a - b) > 1e-5 for a, b in zip(load_axis, base.TUNED_TIMING_LOAD_AXIS)):
            fail(f"{label} load axis is not the intended expanded axis: {load_axis}")
        rpm_axis = base.read_floats(image, rpm_axis_address, rows)
        size = base.TIMING_X * rows
        old = reference[address:address + size]
        new = image[address:address + size]
        for y_index, rpm in enumerate(rpm_axis):
            for x_index, load in enumerate(load_axis):
                offset = y_index * base.TIMING_X + x_index
                if new[offset] > old[offset]:
                    fail(f"{label} increased at {rpm:.0f} RPM/{load:.2f}")
                rounded_load = round(load, 2)
                in_policy = rpm >= 2000.0 and rounded_load >= 1.09
                if not in_policy and new[offset] != old[offset]:
                    fail(f"{label} changed outside boost region at {rpm:.0f} RPM/{load:.2f}")
                if in_policy:
                    cap = 2.0 if rounded_load == 1.09 else 0.0
                    if raw_to_kca(new[offset]) > cap + 1e-9:
                        fail(f"{label} exceeds KCA cap at {rpm:.0f} RPM/{load:.2f}")


def verify_injectors(reference: bytes, image: bytes) -> None:
    target_flow_raw, target_latency_raw, estimated_flow = base.pink_injector_calibration()
    if image[base.INJECTOR_FLOW_ADDR:base.INJECTOR_FLOW_ADDR + 4] != base.f32(target_flow_raw):
        fail("injector flow bytes do not match the translated A4TE002B STI-pink value")
    actual_flow_raw = read_float(image, base.INJECTOR_FLOW_ADDR)
    actual_display = base.INJECTOR_FLOW_DISPLAY_CONSTANT / actual_flow_raw
    if abs(actual_display - estimated_flow) > 1e-5:
        fail(f"translated injector flow displays {actual_display}, expected {estimated_flow}")
    expected_latency = struct.pack(">5H", *target_latency_raw)
    if image[base.INJECTOR_LATENCY_ADDR:base.INJECTOR_LATENCY_ADDR + 10] != expected_latency:
        fail("injector latency bytes do not match the translated A4TE002B STI-pink curve")
    if base.read_floats(
        image, base.INJECTOR_VOLTAGE_AXIS_ADDR, len(base.EXPECTED_INJECTOR_VOLTAGE_AXIS)
    ) != base.EXPECTED_INJECTOR_VOLTAGE_AXIS:
        fail("injector latency voltage axis changed")

    stock_flow_raw = read_float(reference, base.INJECTOR_FLOW_ADDR)
    ratio = target_flow_raw / stock_flow_raw
    for label, address, count in (*base.CRANKING_IPW_MAPS, *base.TIP_IN_IPW_MAPS):
        expected = base.scale_u16_table(reference, address, count, ratio, label)
        if image[address:address + len(expected)] != expected:
            fail(f"{label} does not match the injector-ratio starting multiplier")
        old = struct.unpack_from(">" + "H" * count, reference, address)
        new = struct.unpack_from(">" + "H" * count, image, address)
        if any(after >= before for before, after in zip(old, new)):
            fail(f"{label} did not reduce every absolute pulse width")

    min_tip_in_raw = read_float(reference, base.MIN_TIP_IN_ACTIVATION_ADDR)
    expected_min = base.f32(min_tip_in_raw * ratio)
    if image[base.MIN_TIP_IN_ACTIVATION_ADDR:base.MIN_TIP_IN_ACTIVATION_ADDR + 4] != expected_min:
        fail("minimum tip-in activation does not match the injector-ratio multiplier")


def verify_avls(reference: bytes, image: bytes) -> None:
    if base.read_floats(image, base.AVLS_THRESHOLD_1_ADDR, 7) != base.AVLS_THRESHOLD_1:
        fail("AVLS threshold 1 does not match the early high-cam policy")
    if base.read_floats(image, base.AVLS_THRESHOLD_2_ADDR, 7) != base.AVLS_THRESHOLD_2:
        fail("AVLS threshold 2 does not match the early high-cam policy")
    for label, address, expected in (
        ("actuation minimum", base.AVLS_ACTUATION_MIN_RPM_ADDR, base.AVLS_ACTUATION_MIN_RPM),
        ("release", base.AVLS_RELEASE_RPM_ADDR, base.AVLS_RELEASE_RPM),
        ("engage", base.AVLS_ENGAGE_RPM_ADDR, base.AVLS_ENGAGE_RPM),
    ):
        if read_float(image, address) != expected:
            fail(f"AVLS {label} RPM is {read_float(image, address)}, expected {expected}")
    if not base.AVLS_ACTUATION_MIN_RPM < base.AVLS_RELEASE_RPM < base.AVLS_ENGAGE_RPM:
        fail("AVLS RPM ordering is not minimum < release < engage")
    for address, label in (
        (base.AVLS_HYSTERESIS_A_ADDR, "A"),
        (base.AVLS_HYSTERESIS_B_ADDR, "B"),
    ):
        if read_float(image, address) != base.AVLS_HYSTERESIS:
            fail(f"AVLS hysteresis {label} changed from the intended stock value")
        if image[address:address + 4] != reference[address:address + 4]:
            fail(f"AVLS hysteresis {label} changed relative to the combined reference")


def verify_auxiliary(reference: bytes, image: bytes) -> None:
    if image[base.IAT_TIMING_COMP_ADDR:
             base.IAT_TIMING_COMP_ADDR + len(base.IAT_TIMING_COMP_RAW)] != base.IAT_TIMING_COMP_RAW:
        fail("IAT timing compensation bytes do not match the intended curve")

    rev_cut, rev_resume = base.read_floats(image, base.REV_LIMIT_A_ADDR, 2)
    if (rev_cut, rev_resume) != (base.REV_LIMIT_CUT_RPM, base.REV_LIMIT_RESUME_RPM):
        fail(
            f"Rev Limit A is {(rev_cut, rev_resume)}, expected "
            f"{base.REV_LIMIT_CUT_RPM:.0f}/{base.REV_LIMIT_RESUME_RPM:.0f}"
        )

    if image[base.boost.BASE_DATA:base.boost.BASE_DATA + len(base.boost.BASE_DUTY)] != bytes(8):
        fail("spring-only base WGDC is not all zero")
    if read_float(image, base.boost.KP_ADDR) != 0.0:
        fail("spring-only boost Kp is not zero")
    if read_float(image, base.boost.MAXR_ADDR) != 0.0:
        fail("spring-only final duty clamp is not zero")
    expected_soft = base.boost.ATM_PRESSURE_NATIVE + base.SOFT_OVERBOOST_PSI * base.boost.NATIVE_PER_PSI
    expected_hard = base.boost.ATM_PRESSURE_NATIVE + base.HARD_OVERBOOST_PSI * base.boost.NATIVE_PER_PSI
    if abs(read_float(image, base.boost.OVERB_ADDR) - expected_soft) > 1e-3:
        fail("soft overboost threshold is not 5.5 psi relative to 760 mmHg")
    if abs(read_float(image, base.boost.OVERB_FC_ADDR) - expected_hard) > 1e-3:
        fail("hard overboost threshold is not 6.5 psi relative to 760 mmHg")
    if image[base.boost.BOOST_ENABLE_ADDR] != 0x01 or image[0x7D91C] != 0x01:
        fail("one or both combined patch enables are not ON")
    expected_target = base.pack_floats(base.BOOST_TARGET_NATIVE)
    if image[base.boost.TARGET_DATA:base.boost.TARGET_DATA + len(expected_target)] != expected_target:
        fail("boost target is not flat at 5 psi from 2500 RPM through redline")

    # The target is calibrated above, but at max-ratio zero it cannot command
    # duty.  RPM axis, throttle gate, and MAF/housing data remain unchanged.
    for address, size, label in (
        (base.boost.RPM_AXIS, len(base.boost.RPM_BREAKS) * 4, "boost RPM axis"),
        (base.boost.THROTTLE_GATE_ADDR, 4, "boost throttle gate"),
        (base.INJECTOR_VOLTAGE_AXIS_ADDR,
         len(base.EXPECTED_INJECTOR_VOLTAGE_AXIS) * 4, "injector voltage axis"),
        (base.MAF_VOLTAGE_AXIS_ADDR, base.MAF_SCALING_COUNT * 4, "MAF voltage axis"),
        (base.MAF_SCALING_ADDR, base.MAF_SCALING_COUNT * 4, "MAF scaling"),
        (base.MAF_LIMIT_ADDR, 4, "MAF maximum limit"),
        (base.ENGINE_LOAD_LIMIT_ADDR, 4, "engine-load limit"),
    ):
        if image[address:address + size] != reference[address:address + size]:
            fail(f"hardware-dependent or retained {label} changed unexpectedly")
    if image[base.MAF_LIMIT_ADDR:base.MAF_LIMIT_ADDR + 4] != b"\xFF\xFF\xFF\xFF":
        fail("MAF maximum limit is not at the uint16 encoding maximum")
    if read_float(image, base.ENGINE_LOAD_LIMIT_ADDR) != 4.0:
        fail("engine-load limit is not the expected non-restrictive 4.0 g/rev")

    stored, calculated, _ = base.checksum_value(image)
    if stored != calculated:
        fail(f"Subaru checksum invalid: stored 0x{stored:08X}, calculated 0x{calculated:08X}")


def main() -> None:
    stock, reference, expected, writes = base.build_image()
    if base.sha256(stock) != base.STOCK_SHA256:
        fail("stock hash changed")
    if base.sha256(reference) != base.COMBINED_SHA256:
        fail("combined-stage hash changed")
    if base.sha256(expected) != EXPECTED_OUTPUT_SHA256:
        fail(
            "generated output hash changed; audit the calibration and update the pinned hash only intentionally"
        )
    if not OUTPUT.exists():
        fail(f"missing generated artifact {OUTPUT}")
    image = OUTPUT.read_bytes()
    if image != expected:
        fail("generated artifact is not byte-identical to a fresh verified rebuild")

    changed = {
        index for index, (before, after) in enumerate(zip(reference, image)) if before != after
    }
    if not changed:
        fail("output has no calibration changes beyond the combined stage")
    outside = changed - allowed_offsets()
    if outside:
        fail(f"unexpected output change at 0x{min(outside):05X}")

    verify_fueling(reference, image)
    verify_base_timing(reference, image)
    verify_kca(reference, image)
    verify_injectors(reference, image)
    verify_avls(reference, image)
    verify_auxiliary(reference, image)
    verify_definition()

    print("base turbo map binary audit PASS")
    print(f"  stock SHA-256    : {base.sha256(stock)}")
    print(f"  combined stage   : {base.sha256(reference)}")
    print(f"  output SHA-256   : {base.sha256(image)}")
    print(f"  calibration delta: {len(changed)} bytes across {len(writes)} owned writes")
    print("  fueling          : both-bank high-load caps, lambda 0.93 -> 0.78/0.77; no leaner cells")
    print("  injectors        : A4TE002B STI-pink flow/deadtime + ratio-scaled start/transient IPW")
    print("  ignition         : all six maps capped on expanded 3.0 g/rev axis; KCA zero >=1.22")
    print("  AVLS             : load-based from 2500 RPM; forced high cam 3200/3000 RPM")
    print("  boost            : 5 psi spring only (zero duty/Kp/clamp), 6.5 psi hard cut")
    print("  operating range  : 6800/6770 RPM limiter; 5 psi target held to redline")
    print("  checksum         : valid Subaru 32-bit additive checksum")
    print("  MAF/load limits  : MAF cap already max-encoded; load limit retained at 4.0 g/rev")


if __name__ == "__main__":
    main()
