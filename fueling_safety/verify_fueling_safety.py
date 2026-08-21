#!/usr/bin/env python3
"""Structural and policy checks for the master fueling-safety component."""

from __future__ import annotations

import math
from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for directory in (ROOT / "patch", ROOT / "master_patch", HERE):
    sys.path.insert(0, str(directory))

import sh2_disasm  # noqa: E402
import fueling_safety_component as safety  # noqa: E402


def expect(image: bytes, address: int, expected: bytes, label: str) -> None:
    actual = image[address : address + len(expected)]
    if actual != expected:
        raise AssertionError(
            f"{label} @0x{address:05X} is {actual.hex()}, expected {expected.hex()}"
        )


def decode(image: bytes, base: int, blob: bytes, literals: set[int]) -> list[str]:
    pool = base + len(blob) - 4 * len(literals)
    if pool & 3:
        raise AssertionError("literal pool is not aligned")
    actual = {
        struct.unpack_from(">I", blob, offset)[0]
        for offset in range(pool - base, len(blob), 4)
    }
    if actual != literals:
        raise AssertionError(f"literal pool differs: actual={actual}, expected={literals}")
    result = []
    for address in range(base, pool, 2):
        instruction, _ = sh2_disasm.dis_one(image, address)
        if instruction.startswith(".word"):
            raise AssertionError(f"unknown opcode at 0x{address:05X}: {instruction}")
        result.append(instruction)
    return result


class LeanPolicy:
    def __init__(self) -> None:
        self.state = 0
        self.counter = 0

    def step(
        self, map_mm_hg: float, baro_mm_hg: float, afr: float | None,
        enabled: bool = True,
    ) -> bool:
        if not enabled:
            self.state = self.counter = 0
            return False
        delta = map_mm_hg - baro_mm_hg
        reset_delta = struct.unpack(">f", safety.f32(safety.LEAN_RESET_PSI * safety.NATIVE_PER_PSI))[0]
        arm_delta = struct.unpack(">f", safety.f32(safety.LEAN_ARM_PSI * safety.NATIVE_PER_PSI))[0]
        if self.state == 3:
            valid_release_pressure = (
                math.isfinite(delta)
                and safety.speed_density.MAP_MIN_MMHG <= map_mm_hg <= safety.speed_density.MAP_MAX_MMHG
                and safety.BARO_MIN_MMHG <= baro_mm_hg <= safety.BARO_MAX_MMHG
            )
            if not valid_release_pressure or delta > reset_delta:
                return True
            self.state = self.counter = 0
            return False
        valid_pressure = (
            math.isfinite(delta)
            and safety.speed_density.MAP_MIN_MMHG <= map_mm_hg <= safety.speed_density.MAP_MAX_MMHG
            and safety.BARO_MIN_MMHG <= baro_mm_hg <= safety.BARO_MAX_MMHG
            and delta >= arm_delta
        )
        if not valid_pressure:
            self.state = self.counter = 0
            return False
        if self.state == 0:
            self.state = 1
            self.counter = 0
            return False
        if self.state == 1:
            self.counter += 1
            if self.counter >= safety.LEAN_TRANSPORT_COUNT:
                self.state = 2
                self.counter = 0
            return False
        if afr is not None and math.isfinite(afr) and afr <= safety.LEAN_AFR_THRESHOLD:
            self.counter = 0
            return False
        self.counter += 1
        if self.counter >= safety.LEAN_CONFIRM_COUNT:
            self.state = 3
            self.counter = 0
            return True
        return False


def verify_image(image: bytes) -> None:
    constants = (
        b"FS01\x01\x01\xFF\xFF"
        + safety.f32(safety.PRESSURE_OL_MARGIN_PSI * safety.NATIVE_PER_PSI)
        + safety.f32(safety.LEAN_ARM_PSI * safety.NATIVE_PER_PSI)
        + safety.f32(safety.LEAN_RESET_PSI * safety.NATIVE_PER_PSI)
        + safety.f32(safety.LEAN_AFR_THRESHOLD / safety.GASOLINE_STOICH_AFR)
        + safety.f32(safety.BARO_MIN_MMHG)
        + safety.f32(safety.BARO_MAX_MMHG)
        + struct.pack(">HH", safety.LEAN_TRANSPORT_COUNT, safety.LEAN_CONFIRM_COUNT)
    )
    expect(image, safety.COMPONENT_START, constants, "fueling-safety defaults")
    expect(
        image, safety.PRIMARY_OL_TASK_PTR, safety.be32(safety.PRESSURE_OL_WRAPPER_ADDR),
        "pressure OL hook",
    )
    expect(
        image, safety.LEAN_CUT_TASK_PTR, safety.be32(safety.LEAN_CUT_WRAPPER_ADDR),
        "lean-cut composed hook",
    )
    expect(
        image, safety.LEAN_STATE_INIT_TASK_PTR,
        safety.be32(safety.LEAN_STATE_INITIALIZE_ADDR), "lean-state initialization hook",
    )

    init_blob = safety.build_lean_state_initialize()
    expect(image, safety.LEAN_STATE_INITIALIZE_ADDR, init_blob, "lean-state zero initializer")
    init_decoded = decode(
        image, safety.LEAN_STATE_INITIALIZE_ADDR, init_blob,
        {safety.LEAN_COUNTER_RAM, safety.LEAN_STATE_RAM},
    )
    if init_decoded.count("mov.l r0,@r1") != 2 or "mov #0,r0" not in init_decoded:
        raise AssertionError("lean-state initializer does not zero both reclaimed words")

    pressure_blob = safety.build_pressure_ol_wrapper()
    expect(image, safety.PRESSURE_OL_WRAPPER_ADDR, pressure_blob, "pressure OL wrapper")
    pressure_decoded = decode(
        image, safety.PRESSURE_OL_WRAPPER_ADDR, pressure_blob,
        {
            safety.PRIMARY_OL_TARGET_UPDATE, safety.PRESSURE_OL_ENABLE_ADDR,
            safety.ATMOSPHERIC_PRESSURE, safety.BARO_MIN_ADDR, safety.BARO_MAX_ADDR,
            safety.PRESSURE_OL_MARGIN_ADDR, safety.MAP_PRESSURE,
            safety.CL_OL_STATE_FLAGS,
        },
    )
    if "and #127,r0" not in pressure_decoded:
        raise AssertionError("pressure wrapper does not clear only CL bit 0x80")
    if pressure_decoded.count("jsr @r2") != 1:
        raise AssertionError("pressure wrapper does not call the stock target update once")

    lean_blob = safety.build_lean_cut_wrapper()
    expect(image, safety.LEAN_CUT_WRAPPER_ADDR, lean_blob, "lean-cut wrapper")
    lean_decoded = decode(
        image, safety.LEAN_CUT_WRAPPER_ADDR, lean_blob,
        {
            safety.PRIOR_FUEL_CUT_WRAPPER, safety.LEAN_CUT_ENABLE_ADDR,
            safety.LEAN_STATE_RAM, safety.LEAN_COUNTER_RAM, safety.MAP_PRESSURE,
            safety.speed_density.MAP_MIN_ADDR, safety.speed_density.MAP_MAX_ADDR,
            safety.ATMOSPHERIC_PRESSURE, safety.BARO_MIN_ADDR, safety.BARO_MAX_ADDR,
            safety.LEAN_ARM_DELTA_ADDR, safety.wideband.FRONT_READY_METRIC_BANK1,
            safety.wideband.READY_THRESHOLD_ADDR,
            safety.wideband.WIDEBAND_LOG_LAMBDA_BANK1,
            safety.LEAN_AFR_THRESHOLD_ADDR, safety.LEAN_CONFIRM_COUNT_ADDR,
            safety.LEAN_TRANSPORT_COUNT_ADDR, safety.LEAN_RESET_DELTA_ADDR,
            safety.FUEL_CUT_FLAG,
        },
    )
    if "or #128,r0" not in lean_decoded:
        raise AssertionError("lean wrapper does not set the verified fuel-cut bit")
    if lean_decoded.count("jsr @r2") != 1:
        raise AssertionError("lean wrapper does not call the prior cut wrapper once")
    if sum(text.startswith("cmp/hs") for text in lean_decoded) != 2:
        raise AssertionError("lean wrapper lacks both unsigned delay-count comparisons")

    policy = LeanPolicy()
    boost_map = 760.0 + safety.NATIVE_PER_PSI
    if policy.step(boost_map, 760.0, 15.0):
        raise AssertionError("lean policy trips when first armed")
    for _ in range(safety.LEAN_TRANSPORT_COUNT):
        if policy.step(boost_map, 760.0, 15.0):
            raise AssertionError("lean policy trips during sensor transport delay")
    if policy.state != 2:
        raise AssertionError("lean policy does not enter monitoring after exact delay")
    for _ in range(safety.LEAN_CONFIRM_COUNT - 1):
        if policy.step(boost_map, 760.0, None):
            raise AssertionError("lean policy trips before exact confirmation count")
    if not policy.step(boost_map, 760.0, None) or policy.state != 3:
        raise AssertionError("lean policy does not trip on exact confirmation count")
    if not policy.step(boost_map, 760.0, 10.0):
        raise AssertionError("rich AFR incorrectly releases a latched cut")
    if not policy.step(math.nan, 760.0, 10.0):
        raise AssertionError("invalid pressure incorrectly releases a latched cut")
    release_delta = struct.unpack(">f", safety.f32(safety.LEAN_RESET_PSI * safety.NATIVE_PER_PSI))[0]
    release_map = 760.0 + release_delta - 0.001
    if policy.step(release_map, 760.0, 10.0) or policy.state != 0:
        raise AssertionError("lean cut does not release at its pressure boundary")


def main() -> None:
    import build_master_patch as master  # local import avoids module cycle

    _, image, _, _ = master.build_image()
    verify_image(image)
    print("fueling safety audit PASS")
    print("  pressure OL : live-baro minus 0.50 psi, stock target routine retained")
    print("  lean cut    : 13.00 AFR, 50-call delay, 8-call confirm, pressure release")


if __name__ == "__main__":
    main()
