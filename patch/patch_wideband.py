#!/usr/bin/env python3
"""Experimental hybrid-O2 patch for Subaru EZ30R D2WD610H.

The retained stock RH/Bank-1 front A/F sensor remains the only closed-loop feedback
source.  Its processed lambda, pump-current, and readiness results are mirrored into
the Bank-2 paths so the stock per-bank conditioning and fuel-control code can remain
in place after the LH/Bank-2 front sensor is removed.

An AEM X-Series Inline 30-0310 is installed post-turbo and connected through a
buffered/protected 0.5--4.5 V to 0.1--0.9 V conditioner to the repurposed RH rear-O2
input (ECM B137-24 / engine-harness E61-3, raw ADC 0xFFFFAB20).  The patch converts
that input to lambda and publishes it at 0xFFFFB098 for direct RomRaider logging.  It
does not use the AEM value for closed-loop fueling.

The external conditioner is required hardware and is not supplied by this patch.  The
stock rear input has a 0.2--0.5 V disconnected bias, so the software voltage-window
test cannot by itself guarantee ECU-side wire-disconnect detection.

This remains a separate development patch.  Its free-space allocation starts at
0x7D900, after the boost patch's 0x7D790..0x7D8DF allocation, so both can later be
merged from a fresh stock image without collision.  Never use a generated image as
patch input.

Usage:  python3 patch_wideband.py [out.bin]
"""
import hashlib
import os
import struct
import sys

from sh2_asm import Asm


HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.abspath(os.path.join(HERE, "..", "2005 BLE MT.bin"))
OUT = (os.path.abspath(sys.argv[1]) if len(sys.argv) > 1
       else os.path.join(HERE, "D2WD610H_wideband.bin"))
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"
if len(sys.argv) > 2:
    raise SystemExit("usage: python3 patch_wideband.py [out.bin]")


# ---- Ghidra-verified stock hooks / RAM anchors ----
FRONT_AF_PROCESS_ENTRY = 0x0000B690
FRONT_AF_PROCESS_RESUME = 0x0000B69C
FRONT_PUMP_DIAG_TASK_PTR = 0x00006A6C
STOCK_FRONT_PUMP_DIAG_THUNK = 0x0000B658
BANK1_INHIBIT_ENTRY = 0x00064FD0
BANK2_INHIBIT_ENTRY = 0x0006500C
REAR_O2_PROCESS_ENTRY = 0x0000E0D0
REAR_O2_PROCESS_RESUME = 0x0000E0DC

RAW_ADC_BLOCK = 0xFFFFAB00
RAW_AEM_ADC = 0xFFFFAB20          # module-1 ADC ch4; RH rear O2 signal B137-24 / E61-3
REAR_O2_RAW_COPY = 0xFFFFB094
AEM_LOG_LAMBDA = 0xFFFFB098       # former RH rear-O2 processed-voltage float

FRONT_LAMBDA_BANK1 = 0xFFFFAE60
FRONT_LAMBDA_BANK2 = 0xFFFFAE64
FRONT_CURRENT_BANK1 = 0xFFFFAE68
FRONT_CURRENT_BANK2 = 0xFFFFAE6C
FRONT_READY_METRIC_BANK1 = 0xFFFFAE70
FRONT_READY_METRIC_BANK2 = 0xFFFFAE74

# Remove only the absent LH/Bank-2 front A/F sensor diagnostics and the repurposed
# RH rear-O2/heater diagnostics.  The retained RH/Bank-1 front sensor and the LH rear
# sensor keep their stock diagnostics.
DISABLED_O2_DTC_SWITCHES = {
    "P0037": 0x0005BDAB,
    "P0038": 0x0005BDA9,
    "P0051": 0x0005BDB4,
    "P0052": 0x0005BDB3,
    "P0137": 0x0005BD9F,
    "P0138": 0x0005BDA4,
    "P0151": 0x0005BDA1,
    "P0152": 0x0005BDA3,
    "P0154": 0x0005BDBC,
}


# ---- wideband-only free-space layout (boost patch ends at 0x7D8DF) ----
RAW_TO_CONTROLLER_VOLTS_ADDR = 0x0007D900
CONTROLLER_VOLTS_OFFSET_ADDR = 0x0007D904
LAMBDA_SLOPE_ADDR = 0x0007D908
LAMBDA_OFFSET_ADDR = 0x0007D90C
VALID_MIN_VOLTS_ADDR = 0x0007D910
VALID_MAX_VOLTS_ADDR = 0x0007D914

FRONT_MIRROR_WRAPPER_ADDR = 0x0007D920
FRONT_ORIGINAL_TRAMPOLINE_ADDR = 0x0007D9A0
FRONT_DIAG_MIRROR_WRAPPER_ADDR = 0x0007D9E0
REAR_AEM_WRAPPER_ADDR = 0x0007DA60
REAR_ORIGINAL_TRAMPOLINE_ADDR = 0x0007DB20
FREE_START, FREE_END = 0x0007D900, 0x0007FAF7


# AEM X-Series Inline Wideband Controller 30-0310 analog calibration.
#
# Stock RH rear-input conversion at the ECU pin is:
#   pin_volts = raw * (5/65536) * 0.334 - 0.035
#
# The default external-conditioner model is 0.2 V/V (AEM 0.5--4.5 V becomes
# 0.1--0.9 V at E61-3).  The scale and offset stay editable because the exact
# conditioner plus the biased stock input must be characterized with a current-limited
# source on the actual ECU before the logged value is trusted.
CONDITIONER_GAIN = 0.2
REAR_ADC_GAIN = 0.33399999141693115
REAR_ADC_OFFSET = -0.034999996423721313
RAW_TO_CONTROLLER_VOLTS = (5.0 / 65536.0) * REAR_ADC_GAIN / CONDITIONER_GAIN
CONTROLLER_VOLTS_OFFSET = REAR_ADC_OFFSET / CONDITIONER_GAIN
LAMBDA_SLOPE = 0.1621
LAMBDA_OFFSET = 0.4990
VALID_MIN_VOLTS = 0.5
VALID_MAX_VOLTS = 4.5


def be32(value):
    return struct.pack(">I", value & 0xFFFFFFFF)


def f32(value):
    return struct.pack(">f", value)


def build_entry_hook(address, target):
    """12-byte entry trampoline: mov.l target,r1; jmp @r1; nop; inline literal."""
    a = Asm(address)
    a.movl_pool(1, target).jmp(1).nop().nop()
    data = a.assemble()
    assert len(data) == 12
    return data


def emit_float_copy(a, source, destination):
    a.movl_pool(1, source).fmov_load(0, 1)
    a.movl_pool(1, destination).fmov_store(0, 1)


def build_front_original_trampoline():
    """Replay the six overwritten stock pushes, then resume at 0xB69C."""
    a = Asm(FRONT_ORIGINAL_TRAMPOLINE_ADDR)
    a.push(14).push(13).push(12).push(11).push(10).push(9)
    a.movl_pool(1, FRONT_AF_PROCESS_RESUME).jmp(1).nop()
    return a.assemble()


def build_front_mirror_wrapper():
    """Run the complete stock front-A/F process, then mirror Bank 1 into Bank 2."""
    a = Asm(FRONT_MIRROR_WRAPPER_ADDR)
    a.stsl_pr()
    a.movl_pool(1, FRONT_ORIGINAL_TRAMPOLINE_ADDR).jsr(1).nop()
    emit_float_copy(a, FRONT_LAMBDA_BANK1, FRONT_LAMBDA_BANK2)
    emit_float_copy(a, FRONT_CURRENT_BANK1, FRONT_CURRENT_BANK2)
    emit_float_copy(a, FRONT_READY_METRIC_BANK1, FRONT_READY_METRIC_BANK2)
    a.ldsl_pr().rts().nop()
    return a.assemble()


def build_front_diag_mirror_wrapper():
    """Retain both-bank stock diagnostics, then mirror Bank-1 readiness into Bank 2."""
    a = Asm(FRONT_DIAG_MIRROR_WRAPPER_ADDR)
    a.stsl_pr()
    a.movl_pool(1, STOCK_FRONT_PUMP_DIAG_THUNK).jsr(1).nop()
    emit_float_copy(a, FRONT_READY_METRIC_BANK1, FRONT_READY_METRIC_BANK2)
    a.ldsl_pr().rts().nop()
    return a.assemble()


def build_rear_original_trampoline():
    """Replay the overwritten rear-O2 prologue, then resume at 0xE0DC."""
    a = Asm(REAR_ORIGINAL_TRAMPOLINE_ADDR)
    a.push(13)
    a.mov_imm(0x20, 0)
    a.movl_pool(5, RAW_ADC_BLOCK)
    a.mov_imm(0, 7)
    a.movl_pool(4, REAR_O2_RAW_COPY)
    a.mov_imm(0, 6)
    a.movl_pool(1, REAR_O2_PROCESS_RESUME).jmp(1).nop()
    return a.assemble()


def emit_controller_volts(a):
    """Leave reconstructed AEM output volts in FR0; clobbers R0/R1/FPUL/FR1."""
    a.movl_pool(1, RAW_AEM_ADC)
    a.movw_at(0, 1).extu_w(0, 0).lds_fpul(0).float_fpul(0)
    a.movl_pool(1, RAW_TO_CONTROLLER_VOLTS_ADDR).fmov_load(1, 1).fmul(1, 0)
    a.movl_pool(1, CONTROLLER_VOLTS_OFFSET_ADDR).fmov_load(1, 1).fadd(1, 0)


def emit_voltage_window_check(a, invalid_label):
    """Branch when FR0 is outside the inclusive AEM valid-output window."""
    a.movl_pool(1, VALID_MIN_VOLTS_ADDR).fmov_load(1, 1)
    a.fcmpgt(0, 1).bt(invalid_label)      # minimum > volts
    a.movl_pool(1, VALID_MAX_VOLTS_ADDR).fmov_load(1, 1)
    a.fcmpgt(1, 0).bt(invalid_label)      # volts > maximum


def build_rear_aem_wrapper():
    """Keep stock rear processing, then overwrite RH rear output with logged AEM lambda."""
    a = Asm(REAR_AEM_WRAPPER_ADDR)
    a.stsl_pr()
    a.movl_pool(1, REAR_ORIGINAL_TRAMPOLINE_ADDR).jsr(1).nop()
    emit_controller_volts(a)
    emit_voltage_window_check(a, "invalid")
    a.movl_pool(1, LAMBDA_SLOPE_ADDR).fmov_load(1, 1).fmul(1, 0)
    a.movl_pool(1, LAMBDA_OFFSET_ADDR).fmov_load(1, 1).fadd(1, 0)
    a.bra("publish").nop()
    a.label("invalid").fldi0(0)          # explicit logging fault sentinel; never fuels engine
    a.label("publish")
    a.movl_pool(1, AEM_LOG_LAMBDA).fmov_store(0, 1)
    a.ldsl_pr().rts().nop()
    return a.assemble()


def checked_write(rom, address, expected, replacement, label):
    current = bytes(rom[address:address + len(expected)])
    if current != expected:
        raise SystemExit("REFUSING: %s @0x%05X is %s (expected %s)"
                         % (label, address, current.hex(), expected.hex()))
    rom[address:address + len(replacement)] = replacement


def merge_ranges(addresses):
    """Return inclusive contiguous ranges for a sorted collection of changed offsets."""
    if not addresses:
        return []
    out = []
    start = previous = addresses[0]
    for address in addresses[1:]:
        if address != previous + 1:
            out.append((start, previous))
            start = address
        previous = address
    out.append((start, previous))
    return out


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
    if len(stock_bytes) != 0x80000:
        raise SystemExit("REFUSING: expected a 512 KB stock image, got %d bytes" % len(stock_bytes))
    rom = bytearray(stock_bytes)

    constants = (f32(RAW_TO_CONTROLLER_VOLTS) + f32(CONTROLLER_VOLTS_OFFSET)
                 + f32(LAMBDA_SLOPE) + f32(LAMBDA_OFFSET)
                 + f32(VALID_MIN_VOLTS) + f32(VALID_MAX_VOLTS))
    blobs = [
        ("hybrid_O2_constants", RAW_TO_CONTROLLER_VOLTS_ADDR, constants),
        ("front_sensor_mirror_wrapper", FRONT_MIRROR_WRAPPER_ADDR,
         build_front_mirror_wrapper()),
        ("front_original_trampoline", FRONT_ORIGINAL_TRAMPOLINE_ADDR,
         build_front_original_trampoline()),
        ("front_diagnostic_mirror_wrapper", FRONT_DIAG_MIRROR_WRAPPER_ADDR,
         build_front_diag_mirror_wrapper()),
        ("rear_AEM_logging_wrapper", REAR_AEM_WRAPPER_ADDR, build_rear_aem_wrapper()),
        ("rear_original_trampoline", REAR_ORIGINAL_TRAMPOLINE_ADDR,
         build_rear_original_trampoline()),
    ]
    limits = {
        "hybrid_O2_constants": FRONT_MIRROR_WRAPPER_ADDR,
        "front_sensor_mirror_wrapper": FRONT_ORIGINAL_TRAMPOLINE_ADDR,
        "front_original_trampoline": FRONT_DIAG_MIRROR_WRAPPER_ADDR,
        "front_diagnostic_mirror_wrapper": REAR_AEM_WRAPPER_ADDR,
        "rear_AEM_logging_wrapper": REAR_ORIGINAL_TRAMPOLINE_ADDR,
        "rear_original_trampoline": FREE_END + 1,
    }
    previous_end = FREE_START
    for name, address, data in sorted(blobs, key=lambda item: item[1]):
        if address < previous_end or address + len(data) > limits[name]:
            raise SystemExit("layout error: %s @0x%05X (%d bytes) overlaps its allocation"
                             % (name, address, len(data)))
        if not (FREE_START <= address and address + len(data) - 1 <= FREE_END):
            raise SystemExit("layout error: %s is outside verified free flash" % name)
        if any(byte != 0xFF for byte in rom[address:address + len(data)]):
            raise SystemExit("REFUSING: %s @0x%05X..0x%05X is not 0xFF-free"
                             % (name, address, address + len(data) - 1))
        previous_end = address + len(data)

    # Exact guards for every stock-code/data mutation.
    checked_write(rom, FRONT_AF_PROCESS_ENTRY,
                  bytes.fromhex("2fe62fd62fc62fb62fa62f96"),
                  build_entry_hook(FRONT_AF_PROCESS_ENTRY, FRONT_MIRROR_WRAPPER_ADDR),
                  "front A/F process entry")
    checked_write(rom, BANK2_INHIBIT_ENTRY,
                  bytes.fromhex("905c6000c901600c20088f02"),
                  build_entry_hook(BANK2_INHIBIT_ENTRY, BANK1_INHIBIT_ENTRY),
                  "bank-2 front A/F inhibit entry")
    checked_write(rom, FRONT_PUMP_DIAG_TASK_PTR, be32(STOCK_FRONT_PUMP_DIAG_THUNK),
                  be32(FRONT_DIAG_MIRROR_WRAPPER_ADDR),
                  "front pump-current diagnostic task pointer")
    checked_write(rom, REAR_O2_PROCESS_ENTRY,
                  bytes.fromhex("2fd6e020d521e700d421e600"),
                  build_entry_hook(REAR_O2_PROCESS_ENTRY, REAR_AEM_WRAPPER_ADDR),
                  "rear O2 process entry")
    for code, address in DISABLED_O2_DTC_SWITCHES.items():
        checked_write(rom, address, b"\x01", b"\x00", "%s switch" % code)

    for _, address, data in blobs:
        rom[address:address + len(data)] = data

    # AEM manual formula and logging-sentinel checks.
    assert abs((VALID_MIN_VOLTS * LAMBDA_SLOPE + LAMBDA_OFFSET) - 0.58005) < 1e-7
    assert abs((VALID_MAX_VOLTS * LAMBDA_SLOPE + LAMBDA_OFFSET) - 1.22845) < 1e-7

    with open(OUT, "wb") as handle:
        handle.write(rom)

    with open(STOCK, "rb") as handle:
        if handle.read() != stock_bytes:
            raise RuntimeError("canonical root stock ROM changed during patch build")

    changed = [index for index, (old, new) in enumerate(zip(stock_bytes, rom)) if old != new]
    output_hash = hashlib.sha256(rom).hexdigest()
    print("Experimental hybrid-O2 patch written: %s" % OUT)
    print("  stock source : %s (UNCHANGED, SHA-256 %s)" % (STOCK, stock_hash))
    print("  output SHA-256: %s" % output_hash)
    print("  changed bytes : %d" % len(changed))
    print("  changed ranges: %s" % ", ".join("0x%05X..0x%05X" % pair
                                                   for pair in merge_ranges(changed)))
    for name, address, data in blobs:
        print("  %-34s @0x%05X : %d bytes" % (name, address, len(data)))
    print("  closed loop   : stock RH/Bank-1 front A/F -> mirrored Bank-1/Bank-2 paths")
    print("  AEM input     : 30-0310 -> protected 0.2 V/V conditioner -> E61-3/B137-24")
    print("  input model   : AEM volts = raw*%.10g %+.7g (bench-calibrate both terms)"
          % (RAW_TO_CONTROLLER_VOLTS, CONTROLLER_VOLTS_OFFSET))
    print("  AEM logging   : lambda = %.4f*V + %.4f -> 0x%08X; invalid output -> 0.0"
          % (LAMBDA_SLOPE, LAMBDA_OFFSET, AEM_LOG_LAMBDA))
    print("  factory logs  : RomRaider E91/E109 remain stock-sensor lambda at B4E8/B4EC")
    print("\n*** DEVELOPMENT IMAGE: exact-harness continuity and analog bench calibration are required. ***")
    print("*** The AEM value is logging-only; it does not protect the engine or correct fueling. ***")


if __name__ == "__main__":
    main()
