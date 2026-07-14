#!/usr/bin/env python3
"""Binary and composition audit for the standalone D2WD610H rotational-idle patch.

Usage:  python3 verify_rotational_idle.py [patched.bin]
"""
from pathlib import Path
import hashlib
import struct
import sys

import patch_boost as boost
import patch_rotational_idle as patch
import patch_single_front_af as front
from sh2_disasm import dis_one


HERE = Path(__file__).resolve().parent
PATCHED = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "D2WD610H_rotational_idle.bin"
if len(sys.argv) > 2:
    raise SystemExit("usage: python3 verify_rotational_idle.py [patched.bin]")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def expect(image, address, data, label):
    actual = image[address:address + len(data)]
    if actual != data:
        raise SystemExit("FAIL: %s @0x%05X is %s, expected %s"
                         % (label, address, actual.hex(), data.hex()))


def changed_offsets(before, after):
    return {index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]}


def read_float(image, address):
    return struct.unpack_from(">f", image, address)[0]


def close(actual, expected):
    return abs(actual - expected) <= max(1e-6, abs(expected) * 1e-6)


def model_final_angles(stock_angles, enable=1, ect=90.0, rpm=800.0,
                       throttle=0.5, speed=0.0, map_value=300.0,
                       offsets=patch.CYLINDER_OFFSETS,
                       max_retard=patch.MAX_RETARD,
                       minimum=patch.MIN_FINAL_TIMING):
    """Executable specification of the injected post-processing policy."""
    stock_angles = tuple(stock_angles)
    in_window = (
        patch.ECT_MIN <= ect <= patch.ECT_MAX and
        patch.RPM_MIN <= rpm <= patch.RPM_MAX and
        throttle <= patch.THROTTLE_MAX and
        speed <= patch.VEHICLE_SPEED_MAX and
        patch.MAP_MIN <= map_value <= patch.MAP_MAX
    )
    if enable != 1 or not in_window:
        return stock_angles

    results = []
    for stock, requested in zip(stock_angles, offsets):
        if requested != requested or not max_retard > 0.0:  # NaN or invalid maximum
            bounded = 0.0
        else:
            bounded = min(requested, 0.0)
            if -max_retard > bounded:
                bounded = -max_retard
        if minimum != minimum:
            results.append(stock)
            continue
        candidate = max(stock + bounded, minimum)
        results.append(min(candidate, stock))
    return tuple(results)


def verify_policy_model():
    stock = (20.0, 18.0, 15.0, 12.0, 9.0, 3.0)
    expected = (14.0, 18.0, 9.0, 12.0, 5.0, 3.0)
    if model_final_angles(stock) != expected:
        raise SystemExit("FAIL: default rotational-idle policy model changed")

    for disabled in (0, 2, 0xFF):
        if model_final_angles(stock, enable=disabled) != stock:
            raise SystemExit("FAIL: non-01 enable value does not model as stock")

    # Every gate is inclusive at its documented boundary and exits immediately
    # on the unsafe side. The opposite side is covered by each min/max pair.
    boundary_cases = (
        {"ect": patch.ECT_MIN}, {"ect": patch.ECT_MAX},
        {"rpm": patch.RPM_MIN}, {"rpm": patch.RPM_MAX},
        {"throttle": patch.THROTTLE_MAX},
        {"speed": patch.VEHICLE_SPEED_MAX},
        {"map_value": patch.MAP_MIN}, {"map_value": patch.MAP_MAX},
    )
    for kwargs in boundary_cases:
        if model_final_angles(stock, **kwargs) == stock:
            raise SystemExit("FAIL: inclusive boundary unexpectedly disables policy: %r" % kwargs)

    outside_cases = (
        {"ect": patch.ECT_MIN - 0.01}, {"ect": patch.ECT_MAX + 0.01},
        {"rpm": patch.RPM_MIN - 0.01}, {"rpm": patch.RPM_MAX + 0.01},
        {"throttle": patch.THROTTLE_MAX + 0.01},
        {"speed": patch.VEHICLE_SPEED_MAX + 0.01},
        {"map_value": patch.MAP_MIN - 0.01}, {"map_value": patch.MAP_MAX + 0.01},
    )
    for kwargs in outside_cases:
        if model_final_angles(stock, **kwargs) != stock:
            raise SystemExit("FAIL: outside-window policy did not return stock: %r" % kwargs)

    # Positive requests and a malformed negative max-retard value cannot add
    # advance because the machine code applies a final original-angle ceiling.
    positive = model_final_angles(stock, offsets=(20.0,) * 6)
    malformed = model_final_angles(stock, offsets=(-20.0,) * 6, max_retard=-8.0)
    if positive != stock or malformed != stock:
        raise SystemExit("FAIL: retard-only model can add advance")
    nan = float("nan")
    nan_inputs = (
        {"ect": nan}, {"rpm": nan}, {"throttle": nan},
        {"speed": nan}, {"map_value": nan},
    )
    for kwargs in nan_inputs:
        if model_final_angles(stock, **kwargs) != stock:
            raise SystemExit("FAIL: NaN input does not fail closed: %r" % kwargs)
    if model_final_angles(stock, offsets=(nan,) * 6) != stock:
        raise SystemExit("FAIL: NaN cylinder offset does not fail closed")
    if model_final_angles(stock, offsets=(-20.0,) * 6, max_retard=nan) != stock:
        raise SystemExit("FAIL: NaN maximum-retard calibration does not fail closed")
    if model_final_angles(stock, minimum=nan) != stock:
        raise SystemExit("FAIL: NaN minimum-timing calibration does not fail closed")
    limited = model_final_angles((20.0,) * 6, offsets=(-20.0,) * 6,
                                 max_retard=2.0, minimum=0.0)
    if limited != (18.0,) * 6:
        raise SystemExit("FAIL: maximum-retard bound is not enforced")
    for original, result in zip(stock, model_final_angles(stock)):
        if result > original:
            raise SystemExit("FAIL: result exceeds its original stock angle")


def main():
    stock = Path(patch.STOCK).read_bytes()
    image = PATCHED.read_bytes()
    if len(stock) != 0x80000 or len(image) != 0x80000:
        raise SystemExit("FAIL: stock and patched images must both be exactly 512 KiB")
    if sha256(stock) != patch.STOCK_SHA256:
        raise SystemExit("FAIL: canonical root stock ROM hash changed")

    expected = bytearray(stock)
    blobs = patch.apply_to_rom(expected)
    if image != bytes(expected):
        mismatch = next(index for index, pair in enumerate(zip(image, expected))
                        if pair[0] != pair[1])
        raise SystemExit("FAIL: image differs from a fresh guarded rebuild at 0x%05X" % mismatch)

    expect(image, patch.FINAL_TIMING_TASK_PTR, patch.be32(patch.ROT_IDLE_WRAPPER_ADDR),
           "periodic final-timing task hook")
    expect(image, patch.ROT_IDLE_ENABLE_ADDR, b"\x00", "default-OFF runtime switch")
    wrapper = patch.build_wrapper()
    expect(image, patch.ROT_IDLE_WRAPPER_ADDR, wrapper, "rotational-idle wrapper")
    if patch.ROT_IDLE_WRAPPER_ADDR + len(wrapper) - 1 > patch.COMPONENT_END:
        raise SystemExit("FAIL: rotational-idle wrapper exceeds its reserved component region")

    calibration = (
        (patch.ECT_MIN_ADDR, patch.ECT_MIN, "ECT minimum"),
        (patch.ECT_MAX_ADDR, patch.ECT_MAX, "ECT maximum"),
        (patch.RPM_MIN_ADDR, patch.RPM_MIN, "RPM minimum"),
        (patch.RPM_MAX_ADDR, patch.RPM_MAX, "RPM maximum"),
        (patch.THROTTLE_MAX_ADDR, patch.THROTTLE_MAX, "throttle maximum"),
        (patch.VEHICLE_SPEED_MAX_ADDR, patch.VEHICLE_SPEED_MAX, "speed maximum"),
        (patch.MAP_MIN_ADDR, patch.MAP_MIN, "MAP minimum"),
        (patch.MAP_MAX_ADDR, patch.MAP_MAX, "MAP maximum"),
        (patch.MAX_RETARD_ADDR, patch.MAX_RETARD, "maximum retard"),
        (patch.MIN_FINAL_TIMING_ADDR, patch.MIN_FINAL_TIMING, "minimum final timing"),
    )
    for address, expected_value, label in calibration:
        if not close(read_float(image, address), expected_value):
            raise SystemExit("FAIL: %s calibration @0x%05X" % (label, address))
    actual_offsets = tuple(read_float(image, patch.CYLINDER_OFFSETS_ADDR + index * 4)
                           for index in range(6))
    if any(not close(actual, expected_value)
           for actual, expected_value in zip(actual_offsets, patch.CYLINDER_OFFSETS)):
        raise SystemExit("FAIL: per-cylinder offset calibration changed")

    allowed = set(range(patch.FINAL_TIMING_TASK_PTR, patch.FINAL_TIMING_TASK_PTR + 4))
    for _, address, data in blobs:
        allowed.update(range(address, address + len(data)))
    changed = changed_offsets(stock, image)
    unexpected = changed - allowed
    if unexpected:
        raise SystemExit("FAIL: unexpected changed offsets: %s"
                         % ", ".join("0x%05X" % value for value in sorted(unexpected)[:32]))
    if image[boost.BASE_DESC:front.FRONT_AF_ENABLE_ADDR] != stock[boost.BASE_DESC:front.FRONT_AF_ENABLE_ADDR]:
        raise SystemExit("FAIL: standalone rotational image modifies boost/front patch space")
    if image[front.FRONT_AF_ENABLE_ADDR:patch.FREE_START] != stock[front.FRONT_AF_ENABLE_ADDR:patch.FREE_START]:
        raise SystemExit("FAIL: standalone rotational image modifies front-A/F patch space")

    # Decode only instructions; the aligned literal pool starts at 0x7DCA0.
    decoded = []
    for address in range(patch.ROT_IDLE_WRAPPER_ADDR, 0x0007DCA0, 2):
        instruction, _ = dis_one(image, address)
        if instruction.startswith(".word"):
            raise SystemExit("FAIL: unknown injected opcode at 0x%05X: %s"
                             % (address, instruction))
        decoded.append((address, instruction))
    expect(image, patch.ROT_IDLE_WRAPPER_ADDR + 10, bytes.fromhex("60108801"),
           "exact-01 enable comparison")
    if sum(instruction.startswith("fcmp/eq") for _, instruction in decoded) != 18:
        raise SystemExit("FAIL: expected 16 gate, one offset, and one floor NaN check")
    expect(image, 0x0007DC78, bytes.fromhex("f2248902f45ca0060009"),
           "NaN minimum-timing stock restore")
    expect(image, 0x0007DC88, bytes.fromhex("f4558b00f45c"),
           "original-stock-angle ceiling")
    expect(image, 0x0007DC8E, bytes.fromhex("f44a7404730442108bd7"),
           "six-cylinder store/increment loop")
    expect(image, 0x0007DC98, bytes.fromhex("4f26000b0009"),
           "balanced PR restore and return")

    verify_policy_model()

    # Prove that the component API can later be composed with both existing
    # components without changing patch_combined.py or writing a combined ROM.
    modules = (("boost", boost), ("front-A/F", front), ("rotational idle", patch))
    change_sets = {}
    independent = {}
    for name, module in modules:
        candidate = bytearray(stock)
        module.apply_to_rom(candidate)
        independent[name] = candidate
        change_sets[name] = changed_offsets(stock, candidate)
    names = tuple(change_sets)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            overlap = change_sets[left] & change_sets[right]
            if overlap:
                raise SystemExit("FAIL: %s and %s components overlap at 0x%05X"
                                 % (left, right, min(overlap)))

    composed = bytearray(stock)
    for _, module in modules:
        module.apply_to_rom(composed)
    union = set().union(*(change_sets[name] for name in names))
    if changed_offsets(stock, composed) != union:
        raise SystemExit("FAIL: future three-component composition is not an exact union")
    for name in names:
        for address in change_sets[name]:
            if composed[address] != independent[name][address]:
                raise SystemExit("FAIL: composed byte differs from %s at 0x%05X"
                                 % (name, address))

    if Path(patch.STOCK).read_bytes() != stock:
        raise SystemExit("FAIL: canonical root stock ROM changed during verification")

    print("rotational-idle binary audit PASS")
    print("  stock SHA-256  : %s" % sha256(stock))
    print("  output SHA-256 : %s" % sha256(image))
    print("  changed bytes  : %d (one task pointer plus bounded component flash)" % len(changed))
    print("  injected code  : %d decoded instructions; NaN gates and retard-only ceiling pinned"
          % len(decoded))
    print("  runtime switch : 0x%05X=00 by default; only 01 enables" % patch.ROT_IDLE_ENABLE_ADDR)
    print("  final outputs  : six stock angles post-processed in place; no fuel cut or RAM allocation")
    print("  composition    : boost + front-A/F + rotational-idle byte sets are pairwise disjoint")
    print("  combined patch : unchanged; compatibility was exercised in memory only")


if __name__ == "__main__":
    main()
