#!/usr/bin/env python3
"""Experimental single-front-A/F patch for Subaru EZ30R D2WD610H.

The retained stock RH/Bank-1 front A/F sensor remains the only closed-loop
feedback source. Its processed lambda, pump-current, and readiness results are
mirrored into the Bank-2 paths so the stock per-bank conditioning and fuel-control
code can remain in place after the LH/Bank-2 front sensor is removed.

Both stock rear narrowband channels remain untouched. An aftermarket post-turbo
wideband, if fitted, is external instrumentation and is not connected to or
decoded by this ROM patch.

This remains a separate development patch. Its free-space allocation starts at
0x7D920, after the boost patch's 0x7D790..0x7D8DF allocation, so both can later be
merged from a fresh stock image without collision. Never use a generated image as
patch input.

Usage:  python3 patch_single_front_af.py [out.bin]
"""
import hashlib
import os
import struct
import sys

from sh2_asm import Asm


HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.abspath(os.path.join(HERE, "..", "2005 BLE MT.bin"))
OUT = (os.path.abspath(sys.argv[1]) if len(sys.argv) > 1
       else os.path.join(HERE, "D2WD610H_single_front_af.bin"))
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"
if len(sys.argv) > 2:
    raise SystemExit("usage: python3 patch_single_front_af.py [out.bin]")


# ---- Ghidra-verified stock hooks / RAM anchors ----
FRONT_AF_PROCESS_ENTRY = 0x0000B690
FRONT_AF_PROCESS_RESUME = 0x0000B69C
FRONT_PUMP_DIAG_TASK_PTR = 0x00006A6C
STOCK_FRONT_PUMP_DIAG_THUNK = 0x0000B658
BANK1_INHIBIT_ENTRY = 0x00064FD0
BANK2_INHIBIT_ENTRY = 0x0006500C

FRONT_LAMBDA_BANK1 = 0xFFFFAE60
FRONT_LAMBDA_BANK2 = 0xFFFFAE64
FRONT_CURRENT_BANK1 = 0xFFFFAE68
FRONT_CURRENT_BANK2 = 0xFFFFAE6C
FRONT_READY_METRIC_BANK1 = 0xFFFFAE70
FRONT_READY_METRIC_BANK2 = 0xFFFFAE74

# Disable only diagnostics belonging to the physically removed LH/Bank-2 front
# A/F sensor. The retained RH/Bank-1 front sensor and both rear narrowband sensors
# keep their stock diagnostics.
DISABLED_FRONT_AF_DTC_SWITCHES = {
    "P0051": 0x0005BDB4,
    "P0052": 0x0005BDB3,
    "P0151": 0x0005BDA1,
    "P0152": 0x0005BDA3,
    "P0154": 0x0005BDBC,
}


# ---- single-front-A/F free-space layout (boost patch ends at 0x7D8DF) ----
FRONT_MIRROR_WRAPPER_ADDR = 0x0007D920
FRONT_ORIGINAL_TRAMPOLINE_ADDR = 0x0007D9A0
FRONT_DIAG_MIRROR_WRAPPER_ADDR = 0x0007D9E0
FREE_START, FREE_END = 0x0007D900, 0x0007FAF7


def be32(value):
    return struct.pack(">I", value & 0xFFFFFFFF)


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
    """Retain stock diagnostics, then mirror Bank-1 readiness into Bank 2."""
    a = Asm(FRONT_DIAG_MIRROR_WRAPPER_ADDR)
    a.stsl_pr()
    a.movl_pool(1, STOCK_FRONT_PUMP_DIAG_THUNK).jsr(1).nop()
    emit_float_copy(a, FRONT_READY_METRIC_BANK1, FRONT_READY_METRIC_BANK2)
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

    blobs = [
        ("front_sensor_mirror_wrapper", FRONT_MIRROR_WRAPPER_ADDR,
         build_front_mirror_wrapper()),
        ("front_original_trampoline", FRONT_ORIGINAL_TRAMPOLINE_ADDR,
         build_front_original_trampoline()),
        ("front_diagnostic_mirror_wrapper", FRONT_DIAG_MIRROR_WRAPPER_ADDR,
         build_front_diag_mirror_wrapper()),
    ]
    limits = {
        "front_sensor_mirror_wrapper": FRONT_ORIGINAL_TRAMPOLINE_ADDR,
        "front_original_trampoline": FRONT_DIAG_MIRROR_WRAPPER_ADDR,
        "front_diagnostic_mirror_wrapper": FREE_END + 1,
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
    for code, address in DISABLED_FRONT_AF_DTC_SWITCHES.items():
        checked_write(rom, address, b"\x01", b"\x00", "%s switch" % code)

    for _, address, data in blobs:
        rom[address:address + len(data)] = data

    with open(OUT, "wb") as handle:
        handle.write(rom)

    with open(STOCK, "rb") as handle:
        if handle.read() != stock_bytes:
            raise RuntimeError("canonical root stock ROM changed during patch build")

    changed = [index for index, (old, new) in enumerate(zip(stock_bytes, rom)) if old != new]
    output_hash = hashlib.sha256(rom).hexdigest()
    print("Experimental single-front-A/F patch written: %s" % OUT)
    print("  stock source : %s (UNCHANGED, SHA-256 %s)" % (STOCK, stock_hash))
    print("  output SHA-256: %s" % output_hash)
    print("  changed bytes : %d" % len(changed))
    print("  changed ranges: %s" % ", ".join("0x%05X..0x%05X" % pair
                                                   for pair in merge_ranges(changed)))
    for name, address, data in blobs:
        print("  %-34s @0x%05X : %d bytes" % (name, address, len(data)))
    print("  closed loop   : stock RH/Bank-1 front A/F -> mirrored Bank-1/Bank-2 paths")
    print("  rear sensors  : both stock rear narrowband paths and diagnostics unchanged")
    print("  ext. wideband : external logger only; no ECU electrical or firmware interface")
    print("\n*** DEVELOPMENT IMAGE: validate the retained sensor and both-bank behavior before use. ***")


if __name__ == "__main__":
    main()
