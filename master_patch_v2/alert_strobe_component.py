#!/usr/bin/env python3
"""Custom Alert Strobe Component for D2WD610H (SH7055).

Rapidly strobes/pulses the Check Engine Light (MIL) on the instrument cluster
when critical engine conditions occur under boost:
1. Hard Overboost Fuel Cut is active (6.5 psi trip).
2. Wideband Lean Fuel Cut is active (2.5 psi / 12.8 AFR trip).
3. Real Detonation / Knock under boost (RPM >= 1500, Load >= 1.40 g/rev, FBKC <= -1.40 deg).

Hook:
  Replaces task pointer at 0x0067DC (stock points to 0x0000F710).
  The wrapper executes every periodic lamp update cycle. If an alert is active,
  it toggles 0xFFFFB134 between 0 and 1 at ~8 Hz for ~0.5s hold time.
  When no alert is active, stock 0x0000F710 runs completely untouched.
"""

from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "patches/core"))

from sh2_asm import Asm

WRAPPER_ADDR = 0x0007EE00
LOAD_THRESH_ADDR = 0x0007EEA0
KNOCK_THRESH_ADDR = 0x0007EEA4
RPM_THRESH_ADDR = 0x0007EEA8

HOOK_PTR_ADDR = 0x000067DC
STOCK_TARGET_ADDR = 0x0000F710

# RAM addresses
LEAN_STATE_RAM = 0xFFFFC860       # uint8: 3 = latched lean cut
OVERBOOST_FLAG_RAM = 0xFFFFBF6C   # uint8: bit 0x80 = hard cut active
RPM_RAM = 0xFFFFB544              # float32: Engine Speed (RPM)
LOAD_RAM = 0xFFFFB438             # float32: Conditioned Engine Load (g/rev)
FBKC_RAM = 0xFFFFCD14             # float32: Feedback Knock Correction (degrees)

HOLD_TIMER_RAM = 0xFFFFC861       # uint8: hold counter (reclaimed rear-O2 RAM)
STROBE_COUNTER_RAM = 0xFFFFC862   # uint8: strobe phase counter
MIL_STATE_RAM = 0xFFFFB134        # uint8: stock MIL lamp state (0=off, 1=on)

# Thresholds
KNOCK_LOAD_MIN = 1.40             # g/rev
KNOCK_RETARD_MAX = -1.40          # degrees (retard is negative)
RPM_MIN = 1500.0                  # RPM

ALERT_HOLD_TICKS = 30             # ~0.5s hold time


def f32(val: float) -> bytes:
    return struct.pack(">f", val)


def build_alert_wrapper() -> bytes:
    a = Asm(WRAPPER_ADDR)
    a.stsl_pr()

    # 1. Lean Cut: byte @ 0xFFFFC860 == 3
    a.movl_pool(1, LEAN_STATE_RAM).movb_at(0, 1).and_imm(0xFF).cmp_eq_imm(3)
    a.bt("alert_active")

    # 2. Overboost Cut: byte @ 0xFFFFBF6C & 0x80
    a.movl_pool(1, OVERBOOST_FLAG_RAM).movb_at(0, 1).tst_imm(0x80)
    a.bf("alert_active")

    # 3. Knock under boost:
    # RPM >= 1500.0
    a.movl_pool(1, RPM_RAM).fmov_load(0, 1)
    a.movl_pool(1, RPM_THRESH_ADDR).fmov_load(1, 1)
    a.fcmpgt(0, 1).bt("check_timer")  # if 1500.0 > RPM, skip knock check

    # Load >= 1.40 g/rev
    a.movl_pool(1, LOAD_RAM).fmov_load(0, 1)
    a.movl_pool(1, LOAD_THRESH_ADDR).fmov_load(1, 1)
    a.fcmpgt(0, 1).bt("check_timer")  # if 1.40 > Load, skip knock check

    # FBKC <= -1.40 deg
    a.movl_pool(1, FBKC_RAM).fmov_load(0, 1)
    a.movl_pool(1, KNOCK_THRESH_ADDR).fmov_load(1, 1)
    a.fcmpgt(1, 0).bt("check_timer")  # if FBKC > -1.40, skip knock check

    a.label("alert_active")
    a.mov_imm(ALERT_HOLD_TICKS, 0).movl_pool(1, HOLD_TIMER_RAM).movb_store(0, 1)

    a.label("check_timer")
    a.movl_pool(1, HOLD_TIMER_RAM).movb_at(0, 1).and_imm(0xFF).tst_reg(0, 0)
    a.bt("normal_mil")

    # Decrement hold timer
    a.add_imm(-1, 0).movb_store(0, 1)

    # Increment strobe counter
    a.movl_pool(1, STROBE_COUNTER_RAM).movb_at(0, 1).add_imm(1, 0).movb_store(0, 1)
    # Check bit 2 (toggles on/off every 4 ticks = ~8 Hz rapid strobe)
    a.tst_imm(0x04)
    a.bt("strobe_on")
    a.mov_imm(0, 0).bra("set_mil").nop()

    a.label("strobe_on")
    a.mov_imm(1, 0)

    a.label("set_mil")
    a.movl_pool(1, MIL_STATE_RAM).movb_store(0, 1)

    a.label("normal_mil")
    a.movl_pool(3, STOCK_TARGET_ADDR).jsr(3).nop()
    a.ldsl_pr().rts().nop()

    code = a.assemble()
    assert len(code) <= (LOAD_THRESH_ADDR - WRAPPER_ADDR), f"Wrapper overflow: {len(code)} bytes"
    padding = b"\xFF" * ((LOAD_THRESH_ADDR - WRAPPER_ADDR) - len(code))

    constants = f32(KNOCK_LOAD_MIN) + f32(KNOCK_RETARD_MAX) + f32(RPM_MIN)
    return code + padding + constants


def apply_to_rom(rom: bytearray) -> list[tuple[str, int, bytes]]:
    # Hook verification
    expected_hook = struct.pack(">I", STOCK_TARGET_ADDR)
    current_hook = bytes(rom[HOOK_PTR_ADDR : HOOK_PTR_ADDR + 4])
    if current_hook != expected_hook:
        raise SystemExit(
            f"REFUSING: MIL task pointer @0x{HOOK_PTR_ADDR:05X} is 0x{current_hook.hex()} "
            f"(expected 0x{expected_hook.hex()})"
        )

    # Write hook
    new_hook = struct.pack(">I", WRAPPER_ADDR)
    rom[HOOK_PTR_ADDR : HOOK_PTR_ADDR + 4] = new_hook

    # Write wrapper blob
    payload = build_alert_wrapper()
    rom[WRAPPER_ADDR : WRAPPER_ADDR + len(payload)] = payload

    return [
        ("mil_alert_wrapper", WRAPPER_ADDR, payload),
    ]


if __name__ == "__main__":
    p = build_alert_wrapper()
    print(f"Alert Strobe Component built successfully: {len(p)} bytes at 0x{WRAPPER_ADDR:05X}")
