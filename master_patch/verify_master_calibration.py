#!/usr/bin/env python3
"""Independent policy checks for the master fuel/timing calibration."""

from __future__ import annotations

import math
import struct

import master_calibration as base


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def read_float(image: bytes, address: int) -> float:
    return struct.unpack_from(">f", image, address)[0]


def interpolated_reference_raw(source: bytes, rpm: float, column: int) -> int:
    """Independent executable specification of conservative RPM resampling."""
    axis = base.STOCK_FUEL_RPM_AXIS
    if rpm <= axis[0]:
        left = right = 0
        fraction = 0.0
    elif rpm >= axis[-1]:
        left = right = len(axis) - 1
        fraction = 0.0
    else:
        left = next(
            index
            for index in range(len(axis) - 1)
            if axis[index] <= rpm <= axis[index + 1]
        )
        right = left + 1
        fraction = (rpm - axis[left]) / (axis[right] - axis[left])
    low = source[left * base.PRIMARY_OL_X + column]
    high = source[right * base.PRIMARY_OL_X + column]
    return math.ceil(low + (high - low) * fraction - 1e-12)


def raw_to_lambda(raw: int) -> float:
    return 1.0 / (1.0 + raw / 128.0)


def raw_to_base_timing(raw: int) -> float:
    return raw * 0.3515625 - 20.0


def raw_to_kca(raw: int) -> float:
    return raw * 0.3515625


def verify_fueling(reference: bytes, image: bytes) -> None:
    load_axis = base.read_floats(image, base.PRIMARY_OL_A_LOAD_AXIS, base.PRIMARY_OL_X)
    load_axis_b = base.read_floats(image, base.PRIMARY_OL_B_LOAD_AXIS, base.PRIMARY_OL_X)
    if any(abs(a - b) > 1e-5 for a, b in zip(load_axis, base.TUNED_FUEL_LOAD_AXIS)) or any(
        abs(a - b) > 1e-5 for a, b in zip(load_axis_b, base.TUNED_FUEL_LOAD_AXIS)
    ):
        fail(f"Primary OL load axes are not the intended expanded axis: {load_axis}/{load_axis_b}")
    rpm_axis = base.read_floats(image, base.PRIMARY_OL_A_RPM_AXIS, base.PRIMARY_OL_Y)
    rpm_axis_b = base.read_floats(image, base.PRIMARY_OL_B_RPM_AXIS, base.PRIMARY_OL_Y)
    if rpm_axis != base.TUNED_FUEL_RPM_AXIS or rpm_axis_b != base.TUNED_FUEL_RPM_AXIS:
        fail(f"Primary OL RPM axes are not the intended 1000..6800 range: {rpm_axis}/{rpm_axis_b}")
    data_size = base.PRIMARY_OL_X * base.PRIMARY_OL_Y
    ref_a = reference[base.PRIMARY_OL_A_ADDR:base.PRIMARY_OL_A_ADDR + data_size]
    ref_b = reference[base.PRIMARY_OL_B_ADDR:base.PRIMARY_OL_B_ADDR + data_size]
    out_a = image[base.PRIMARY_OL_A_ADDR:base.PRIMARY_OL_A_ADDR + data_size]
    out_b = image[base.PRIMARY_OL_B_ADDR:base.PRIMARY_OL_B_ADDR + data_size]

    for y_index, rpm in enumerate(rpm_axis):
        for x_index, load in enumerate(load_axis):
            offset = y_index * base.PRIMARY_OL_X + x_index
            expected_a = interpolated_reference_raw(ref_a, rpm, x_index)
            expected_b = interpolated_reference_raw(ref_b, rpm, x_index)
            rounded_load = round(load, 2)
            if rounded_load not in base.FUEL_LAMBDA_CAPS:
                if out_a[offset] != expected_a or out_b[offset] != expected_b:
                    fail(
                        f"Primary OL does not match conservative RPM resampling at "
                        f"{rpm:.0f} RPM/{load:.2f}"
                    )
                continue
            if out_a[offset] != out_b[offset]:
                fail(f"Primary OL bank targets differ at {rpm:.0f} RPM/{load:.2f}")
            if out_a[offset] < expected_a or out_b[offset] < expected_b:
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
    if image[base.boost.EBCS_ENABLE_ADDR] != 0x00:
        fail("spring-only electronic boost-control switch is not OFF")
    if image[base.boost.OVERBOOST_ENABLE_ADDR] != 0x01 or image[0x7D91C] != 0x01:
        fail("hard-overboost or O2 architecture enable is not ON")
    expected_target = base.pack_floats(base.BOOST_TARGET_NATIVE)
    if image[base.boost.TARGET_DATA:base.boost.TARGET_DATA + len(expected_target)] != expected_target:
        fail("boost target is not flat at 5 psi from 2500 RPM through redline")

    # The target is calibrated above, but at max-ratio zero it cannot command
    # duty. RPM axis, throttle gate, obsolete MAF tables, and the retained load
    # ceiling remain unchanged by this calibration layer.
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
