#!/usr/bin/env python3
"""Bounded rotational-idle patch for Subaru EZ30R D2WD610H.

The stock firmware calculates six independent final ignition angles at
0xFFFFC0EC..0xFFFFC100.  This component replaces the periodic task pointer at
0x11E30 with a wrapper that:

1. runs the complete stock final-timing calculation at 0x279CC;
2. returns without changes unless the runtime switch is exactly 01;
3. requires a warm, stationary, closed-throttle, high-vacuum idle; and
4. applies six bounded retard-only offsets to the stock final angles.

The wrapper cannot add ignition advance.  Every requested positive offset is
clamped to zero, negative offsets are limited by Maximum Retard, every result
is clamped at Minimum Final Timing, and a final cap prevents the result from
exceeding the original stock angle.  It does not cut fuel, force AVLS, alter
idle airflow, disable misfire detection, or allocate persistent RAM.

The generated image defaults OFF (00).  The canonical root stock ROM is read
only and is never used as an output.

Usage:  python3 patch_rotational_idle.py [out.bin]
"""
import hashlib
import os
import struct
import sys

from sh2_asm import Asm


HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.abspath(os.path.join(HERE, "..", "2005 BLE MT.bin"))
DEFAULT_OUT = os.path.join(HERE, "D2WD610H_rotational_idle.bin")
OUT = (os.path.abspath(sys.argv[1]) if __name__ == "__main__" and len(sys.argv) > 1
       else DEFAULT_OUT)
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"
if __name__ == "__main__" and len(sys.argv) > 2:
    raise SystemExit("usage: python3 patch_rotational_idle.py [out.bin]")


# Ghidra-verified stock hook and calculation path.
FINAL_TIMING_TASK_PTR = 0x00011E30
STOCK_FINAL_TIMING_TASK = 0x000279CC
FINAL_TIMING_ARRAY = 0xFFFFC0EC       # float[6], one final angle per cylinder

# Confirmed live inputs, all read only.
ECT_ADDR = 0xFFFFB3AC                 # deg C, float
RPM_ADDR = 0xFFFFB544                 # RPM, float
THROTTLE_ADDR = 0xFFFFB314            # processed throttle opening, float
VEHICLE_SPEED_ADDR = 0xFFFFB538       # km/h, float
MAP_ADDR = 0xFFFFABC4                 # mmHg absolute, float

# Free space begins immediately after the single-front/rear-delete component.
ROT_IDLE_ENABLE_ADDR = 0x0007DB40     # uint8: exact 01 enables; default 00
ECT_MIN_ADDR = 0x0007DB44
ECT_MAX_ADDR = 0x0007DB48
RPM_MIN_ADDR = 0x0007DB4C
RPM_MAX_ADDR = 0x0007DB50
THROTTLE_MAX_ADDR = 0x0007DB54
VEHICLE_SPEED_MAX_ADDR = 0x0007DB58
MAP_MIN_ADDR = 0x0007DB5C
MAP_MAX_ADDR = 0x0007DB60
MAX_RETARD_ADDR = 0x0007DB64
MIN_FINAL_TIMING_ADDR = 0x0007DB68
CYLINDER_OFFSETS_ADDR = 0x0007DB6C    # float[6]
ROT_IDLE_WRAPPER_ADDR = 0x0007DB90
FREE_START, FREE_END = 0x0007DB40, 0x0007FAF7
COMPONENT_END = 0x0007DCFF


# Conservative defaults.  Cylinder 1 is included in the retarded group so the
# factory Ignition Timing logger (which reports cylinder A/1) visibly confirms
# application when the feature is enabled.
ECT_MIN = 80.0
ECT_MAX = 105.0
RPM_MIN = 600.0
RPM_MAX = 1050.0
THROTTLE_MAX = 1.68                    # about 2.0% using the x/.84 display convention
VEHICLE_SPEED_MAX = 1.0
MAP_MIN = 150.0                        # 20.0 kPa absolute
MAP_MAX = 550.0                        # 73.3 kPa absolute; exits as vacuum is lost
MAX_RETARD = 8.0
MIN_FINAL_TIMING = 5.0                 # do not command ATDC timing in the supplied calibration
CYLINDER_OFFSETS = (-6.0, 0.0, -6.0, 0.0, -6.0, 0.0)


def be32(value):
    return struct.pack(">I", value & 0xFFFFFFFF)


def f32(value):
    return struct.pack(">f", value)


def emit_min_gate(a, value_addr, minimum_addr, exit_label="done"):
    """Exit for NaN input/threshold or when value < minimum; equality is allowed."""
    a.movl_pool(1, value_addr).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf(exit_label)       # NaN is not equal to itself
    a.movl_pool(1, minimum_addr).fmov_load(3, 1)
    a.fcmpeq(3, 3).bf(exit_label)
    a.fcmpgt(4, 3).bt(exit_label)       # T = minimum > value


def emit_max_gate(a, value_addr, maximum_addr, exit_label="done"):
    """Exit for NaN input/threshold or when value > maximum; equality is allowed."""
    a.movl_pool(1, value_addr).fmov_load(4, 1)
    a.fcmpeq(4, 4).bf(exit_label)       # NaN is not equal to itself
    a.movl_pool(1, maximum_addr).fmov_load(3, 1)
    a.fcmpeq(3, 3).bf(exit_label)
    a.fcmpgt(3, 4).bt(exit_label)       # T = value > maximum


def build_wrapper():
    """Run stock timing, then conditionally apply bounded retard to six outputs."""
    a = Asm(ROT_IDLE_WRAPPER_ADDR)
    a.stsl_pr()
    a.movl_pool(2, STOCK_FINAL_TIMING_TASK).jsr(2).nop()

    # Exact-enable and fail-closed operating window.
    a.movl_pool(1, ROT_IDLE_ENABLE_ADDR).movb_at(0, 1).cmp_eq_imm(0x01)
    a.bf("done")
    emit_min_gate(a, ECT_ADDR, ECT_MIN_ADDR)
    emit_max_gate(a, ECT_ADDR, ECT_MAX_ADDR)
    emit_min_gate(a, RPM_ADDR, RPM_MIN_ADDR)
    emit_max_gate(a, RPM_ADDR, RPM_MAX_ADDR)
    emit_max_gate(a, THROTTLE_ADDR, THROTTLE_MAX_ADDR)
    emit_max_gate(a, VEHICLE_SPEED_ADDR, VEHICLE_SPEED_MAX_ADDR)
    emit_min_gate(a, MAP_ADDR, MAP_MIN_ADDR)
    emit_max_gate(a, MAP_ADDR, MAP_MAX_ADDR)

    # Six stock final angles are modified in place.  Offset is constrained to
    # [-MaximumRetard, 0], then the result is constrained to MinimumFinalTiming
    # without ever exceeding the original stock angle.
    a.movl_pool(4, FINAL_TIMING_ARRAY)
    a.movl_pool(3, CYLINDER_OFFSETS_ADDR)
    a.mov_imm(6, 2)
    a.fldi0(1)
    a.label("cylinder_loop")
    a.fmov_load(4, 4)                  # fr4 = stock final timing
    a.fmov(4, 5)                       # fr5 = immutable stock-angle ceiling
    a.fmov_load(3, 3)                  # fr3 = requested per-cylinder offset
    a.fcmpeq(3, 3).bf("offset_invalid")  # NaN request -> zero offset
    a.fcmpgt(1, 3).bf("offset_not_positive")  # requested > 0?
    a.fmov(1, 3)                       # never add advance: positive -> 0
    a.bra("offset_ready").nop()
    a.label("offset_not_positive")
    a.movl_pool(1, MAX_RETARD_ADDR).fmov_load(2, 1)
    a.fcmpgt(1, 2).bf("offset_invalid")  # require positive, non-NaN maximum
    a.fneg(2)
    a.fcmpgt(3, 2).bf("offset_ready") # -maxRetard > requested?
    a.fmov(2, 3)
    a.bra("offset_ready").nop()
    a.label("offset_invalid")
    a.fmov(1, 3)
    a.label("offset_ready")
    a.fadd(3, 4)
    a.movl_pool(1, MIN_FINAL_TIMING_ADDR).fmov_load(2, 1)
    a.fcmpeq(2, 2).bt("minimum_valid")  # NaN floor -> retain stock angle
    a.fmov(5, 4)
    a.bra("write_timing").nop()
    a.label("minimum_valid")
    a.fcmpgt(4, 2).bf("store_timing")  # minimum > result?
    a.fmov(2, 4)
    a.label("store_timing")
    a.fcmpgt(5, 4).bf("not_above_stock")  # result > original stock angle?
    a.fmov(5, 4)
    a.label("not_above_stock")
    a.label("write_timing")
    a.fmov_store(4, 4)
    a.add_imm(4, 4).add_imm(4, 3).dt(2).bf("cylinder_loop")

    a.label("done")
    a.ldsl_pr().rts().nop()
    return a.assemble()


def build_blobs():
    gates = b"".join(f32(value) for value in (
        ECT_MIN, ECT_MAX, RPM_MIN, RPM_MAX, THROTTLE_MAX,
        VEHICLE_SPEED_MAX, MAP_MIN, MAP_MAX, MAX_RETARD, MIN_FINAL_TIMING,
    ))
    return [
        ("rot_idle_enable", ROT_IDLE_ENABLE_ADDR, b"\x00"),
        ("rot_idle_gates", ECT_MIN_ADDR, gates),
        ("rot_idle_cylinder_offsets", CYLINDER_OFFSETS_ADDR,
         b"".join(f32(value) for value in CYLINDER_OFFSETS)),
        ("rot_idle_wrapper", ROT_IDLE_WRAPPER_ADDR, build_wrapper()),
    ]


def checked_write(rom, address, expected, replacement, label):
    current = bytes(rom[address:address + len(expected)])
    if current != expected:
        raise SystemExit("REFUSING: %s @0x%05X is %s (expected %s)"
                         % (label, address, current.hex(), expected.hex()))
    rom[address:address + len(replacement)] = replacement


def merge_ranges(addresses):
    if not addresses:
        return []
    result = []
    start = previous = addresses[0]
    for address in addresses[1:]:
        if address != previous + 1:
            result.append((start, previous))
            start = address
        previous = address
    result.append((start, previous))
    return result


def apply_to_rom(rom):
    """Apply the component to a mutable stock-derived image with exact guards."""
    if len(rom) != 0x80000:
        raise SystemExit("REFUSING: expected a 512 KB stock-derived image, got %d bytes"
                         % len(rom))
    blobs = build_blobs()
    previous_end = FREE_START
    for name, address, data in sorted(blobs, key=lambda item: item[1]):
        end = address + len(data)
        if address < previous_end or end - 1 > COMPONENT_END:
            raise SystemExit("layout error: %s @0x%05X..0x%05X overlaps or exceeds component"
                             % (name, address, end - 1))
        if not (FREE_START <= address and end - 1 <= FREE_END):
            raise SystemExit("layout error: %s is outside verified free flash" % name)
        if any(byte != 0xFF for byte in rom[address:end]):
            raise SystemExit("REFUSING: %s @0x%05X..0x%05X is not 0xFF-free"
                             % (name, address, end - 1))
        previous_end = end

    checked_write(rom, FINAL_TIMING_TASK_PTR, be32(STOCK_FINAL_TIMING_TASK),
                  be32(ROT_IDLE_WRAPPER_ADDR), "final per-cylinder timing task pointer")
    for _, address, data in blobs:
        rom[address:address + len(data)] = data
    return blobs


def main():
    if os.path.realpath(OUT) == os.path.realpath(STOCK):
        raise SystemExit("REFUSING: output path aliases the canonical stock ROM: %s" % STOCK)
    if os.path.exists(OUT) and os.path.samefile(OUT, STOCK):
        raise SystemExit("REFUSING: output file is the canonical stock ROM (or a hard link to it)")

    with open(STOCK, "rb") as handle:
        stock_bytes = handle.read()
    stock_hash = hashlib.sha256(stock_bytes).hexdigest()
    if stock_hash != STOCK_SHA256:
        raise SystemExit("REFUSING: canonical stock ROM hash is %s (expected %s)"
                         % (stock_hash, STOCK_SHA256))
    rom = bytearray(stock_bytes)
    blobs = apply_to_rom(rom)
    with open(OUT, "wb") as handle:
        handle.write(rom)

    with open(STOCK, "rb") as handle:
        if handle.read() != stock_bytes:
            raise RuntimeError("canonical root stock ROM changed during patch build")

    changed = [index for index, (old, new) in enumerate(zip(stock_bytes, rom)) if old != new]
    print("Rotational-idle development patch written: %s" % OUT)
    print("  stock source : %s (UNCHANGED, SHA-256 %s)" % (STOCK, stock_hash))
    print("  output SHA-256: %s" % hashlib.sha256(rom).hexdigest())
    print("  task hook    @0x%05X : 0x%08X -> 0x%08X"
          % (FINAL_TIMING_TASK_PTR, STOCK_FINAL_TIMING_TASK, ROT_IDLE_WRAPPER_ADDR))
    print("  changed bytes : %d" % len(changed))
    print("  changed ranges: %s" % ", ".join("0x%05X..0x%05X" % pair
                                                   for pair in merge_ranges(changed)))
    for name, address, data in blobs:
        print("  %-28s @0x%05X : %d bytes" % (name, address, len(data)))
    print("  runtime switch @0x%05X defaults OFF (00); only exact 01 enables" % ROT_IDLE_ENABLE_ADDR)
    print("  default offsets: %s degrees; retard-only, maximum %.1f, final timing >= %.1f BTDC"
          % (CYLINDER_OFFSETS, MAX_RETARD, MIN_FINAL_TIMING))
    print("  gates: ECT %.0f..%.0f C, RPM %.0f..%.0f, throttle <= %.2f native, "
          "speed <= %.1f km/h, MAP %.0f..%.0f mmHg absolute"
          % (ECT_MIN, ECT_MAX, RPM_MIN, RPM_MAX, THROTTLE_MAX,
             VEHICLE_SPEED_MAX, MAP_MIN, MAP_MAX))
    print("\n*** DEVELOPMENT IMAGE: bench/log with the switch OFF first; enable only for warm idle testing. ***")


if __name__ == "__main__":
    main()
