#!/usr/bin/env python3
"""Experimental single-front-A/F patch for Subaru EZ30R D2WD610H.

The retained stock RH/Bank-1 front A/F sensor remains the only closed-loop
feedback source. Its processed lambda, pump-current, and readiness results are
mirrored into the Bank-2 paths so the stock per-bank conditioning and fuel-control
code can remain in place after the LH/Bank-2 front sensor is removed.

When the same runtime switch is enabled, both stock rear narrowband channels are
also removed from ECU processing: their ADC conversion, filtering, response
integration/ratio publication, and voltage-diagnostic dispatch are bypassed. All
eight mapped D2WD610H rear-sensor/heater DTC switches are disabled in the generated image.
An aftermarket post-turbo wideband, if fitted, remains external instrumentation
and is not connected to or decoded by this ROM patch.

This standalone development patch has a runtime-enable byte at 0x7D91C and its
code starts at 0x7D920, after the boost patch's 0x7D790..0x7D903 allocation.
patch_combined.py applies both guarded components to one fresh stock image with
no collision. Never use a generated image as patch input.

Usage:  python3 patch_single_front_af.py [out.bin]
"""
import hashlib
import os
import struct
import sys

from sh2_asm import Asm


HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.abspath(os.path.join(HERE, "..", "2005 BLE MT.bin"))
DEFAULT_OUT = os.path.join(HERE, "D2WD610H_single_front_af.bin")
OUT = (os.path.abspath(sys.argv[1]) if __name__ == "__main__" and len(sys.argv) > 1
       else DEFAULT_OUT)
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"
if __name__ == "__main__" and len(sys.argv) > 2:
    raise SystemExit("usage: python3 patch_single_front_af.py [out.bin]")


# ---- Ghidra-verified stock hooks / RAM anchors ----
FRONT_AF_PROCESS_ENTRY = 0x0000B690
FRONT_AF_PROCESS_RESUME = 0x0000B69C
FRONT_PUMP_DIAG_TASK_PTR = 0x00006A6C
STOCK_FRONT_PUMP_DIAG_THUNK = 0x0000B658
BANK1_INHIBIT_ENTRY = 0x00064FD0
BANK2_INHIBIT_ENTRY = 0x0006500C
BANK2_INHIBIT_FLAG = 0xFFFFD26C

REAR_O2_PROCESS_ENTRY = 0x0000E0D0
REAR_O2_PROCESS_RESUME = 0x0000E0DC
REAR_O2_RAW_ADC_BASE = 0xFFFFAB00
REAR_O2_RAW_COPY_BASE = 0xFFFFB094
REAR_O2_THRESHOLD_TASK_PTR = 0x00011488
STOCK_REAR_O2_THRESHOLD_UPDATE = 0x00033B12
REAR_O2_FILTER_TASK_PTR = 0x0001148C
STOCK_REAR_O2_FILTER_UPDATE = 0x00033AAC
REAR_O2_INTEGRATOR_TASK_PTR = 0x00011490
STOCK_REAR_O2_INTEGRATOR_UPDATE = 0x00033970
REAR_O2_RESPONSE_RATIO_TASK_PTR = 0x00011494
STOCK_REAR_O2_RESPONSE_RATIO_UPDATE = 0x00034BE4
REAR_O2_VOLTAGE_DIAG_TASK_PTR = 0x000114A0
STOCK_REAR_O2_VOLTAGE_DIAG_DISPATCH = 0x00069568

FRONT_LAMBDA_BANK1 = 0xFFFFAE60
FRONT_LAMBDA_BANK2 = 0xFFFFAE64
FRONT_CURRENT_BANK1 = 0xFFFFAE68
FRONT_CURRENT_BANK2 = 0xFFFFAE6C
FRONT_READY_METRIC_BANK1 = 0xFFFFAE70
FRONT_READY_METRIC_BANK2 = 0xFFFFAE74

# Disable diagnostics belonging to the physically removed LH/Bank-2 front A/F
# sensor. The retained RH/Bank-1 front sensor keeps its stock diagnostics.
DISABLED_FRONT_AF_DTC_SWITCHES = {
    "P0051": 0x0005BDB4,
    "P0052": 0x0005BDB3,
    "P0151": 0x0005BDA1,
    "P0152": 0x0005BDA3,
    "P0154": 0x0005BDBC,
}

# Ghidra and the D2WD610H RomRaider definition expose these eight rear-S2
# voltage/heater switches.  No P0139/P0140/P0141/P0159/P0160/P0161 or
# P0420/P0430 switches are defined for this calibration.
DISABLED_REAR_O2_DTC_SWITCHES = {
    "P0037": 0x0005BDAB,
    "P0038": 0x0005BDA9,
    "P0057": 0x0005BDC1,
    "P0058": 0x0005BDC2,
    "P0137": 0x0005BD9F,
    "P0138": 0x0005BDA4,
    "P0157": 0x0005BDC3,
    "P0158": 0x0005BDC4,
}


# ---- single-front-A/F free-space layout (boost patch ends at 0x7D903) ----
FRONT_AF_ENABLE_ADDR = 0x0007D91C  # uint8: exact 1=front mirror + rear delete; else stock logic
FRONT_MIRROR_WRAPPER_ADDR = 0x0007D920
FRONT_ORIGINAL_TRAMPOLINE_ADDR = 0x0007D9A0
FRONT_DIAG_MIRROR_WRAPPER_ADDR = 0x0007D9E0
BANK2_INHIBIT_SELECTOR_ADDR = 0x0007DA20
REAR_O2_PROCESS_SELECTOR_ADDR = 0x0007DA60
REAR_O2_ORIGINAL_TRAMPOLINE_ADDR = 0x0007DA80
REAR_O2_THRESHOLD_SELECTOR_ADDR = 0x0007DAA0
REAR_O2_FILTER_SELECTOR_ADDR = 0x0007DAC0
REAR_O2_INTEGRATOR_SELECTOR_ADDR = 0x0007DAE0
REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR = 0x0007DB00
REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR = 0x0007DB20
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
    """Run stock front-A/F processing; mirror Bank 1 only while the patch is enabled."""
    a = Asm(FRONT_MIRROR_WRAPPER_ADDR)
    a.stsl_pr()
    a.movl_pool(1, FRONT_ORIGINAL_TRAMPOLINE_ADDR).jsr(1).nop()
    a.movl_pool(1, FRONT_AF_ENABLE_ADDR); a.movb_at(0, 1); a.cmp_eq_imm(0x01)
    a.bf('done')
    emit_float_copy(a, FRONT_LAMBDA_BANK1, FRONT_LAMBDA_BANK2)
    emit_float_copy(a, FRONT_CURRENT_BANK1, FRONT_CURRENT_BANK2)
    emit_float_copy(a, FRONT_READY_METRIC_BANK1, FRONT_READY_METRIC_BANK2)
    a.label('done')
    a.ldsl_pr().rts().nop()
    return a.assemble()


def build_front_diag_mirror_wrapper():
    """Run stock diagnostics; mirror Bank-1 readiness only while enabled."""
    a = Asm(FRONT_DIAG_MIRROR_WRAPPER_ADDR)
    a.stsl_pr()
    a.movl_pool(1, STOCK_FRONT_PUMP_DIAG_THUNK).jsr(1).nop()
    a.movl_pool(1, FRONT_AF_ENABLE_ADDR); a.movb_at(0, 1); a.cmp_eq_imm(0x01)
    a.bf('done')
    emit_float_copy(a, FRONT_READY_METRIC_BANK1, FRONT_READY_METRIC_BANK2)
    a.label('done')
    a.ldsl_pr().rts().nop()
    return a.assemble()


def build_bank2_inhibit_selector():
    """Select patched Bank-1 inhibit status or reproduce the stock Bank-2 helper.

    The stock Bank-2 entry is overwritten by its hook, so the disabled path
    reconstructs that helper's complete behavior: return 2 when bit 0 of
    0xFFFFD26C is set, otherwise return 0.
    """
    a = Asm(BANK2_INHIBIT_SELECTOR_ADDR)
    a.movl_pool(1, FRONT_AF_ENABLE_ADDR); a.movb_at(0, 1); a.cmp_eq_imm(0x01)
    a.bf('stock_bank2')
    a.movl_pool(1, BANK1_INHIBIT_ENTRY); a.jmp(1); a.nop()
    a.label('stock_bank2')
    a.movl_pool(1, BANK2_INHIBIT_FLAG); a.movb_at(0, 1); a.and_imm(0x01)
    a.tst_reg(0, 0); a.bf('inhibited')
    a.rts(); a.mov_imm(0, 0)
    a.label('inhibited')
    a.rts(); a.mov_imm(2, 0)
    return a.assemble()


def build_runtime_noop_selector(address, stock_target):
    """Return immediately when enabled; tail-jump to stock for every other value."""
    a = Asm(address)
    a.movl_pool(1, FRONT_AF_ENABLE_ADDR); a.movb_at(0, 1); a.cmp_eq_imm(0x01)
    a.bf('stock')
    a.rts(); a.nop()
    a.label('stock')
    a.movl_pool(1, stock_target); a.jmp(1); a.nop()
    return a.assemble()


def build_rear_o2_original_trampoline():
    """Reconstruct the six overwritten rear-ADC instructions, then resume stock."""
    a = Asm(REAR_O2_ORIGINAL_TRAMPOLINE_ADDR)
    a.push(13).mov_imm(0x20, 0)
    a.movl_pool(5, REAR_O2_RAW_ADC_BASE).mov_imm(0, 7)
    a.movl_pool(4, REAR_O2_RAW_COPY_BASE).mov_imm(0, 6)
    a.movl_pool(1, REAR_O2_PROCESS_RESUME).jmp(1).nop()
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


def build_blobs():
    return [
        ("front_patch_enable", FRONT_AF_ENABLE_ADDR, b"\x01"),
        ("front_sensor_mirror_wrapper", FRONT_MIRROR_WRAPPER_ADDR,
         build_front_mirror_wrapper()),
        ("front_original_trampoline", FRONT_ORIGINAL_TRAMPOLINE_ADDR,
         build_front_original_trampoline()),
        ("front_diagnostic_mirror_wrapper", FRONT_DIAG_MIRROR_WRAPPER_ADDR,
         build_front_diag_mirror_wrapper()),
        ("bank2_inhibit_selector", BANK2_INHIBIT_SELECTOR_ADDR,
         build_bank2_inhibit_selector()),
        ("rear_o2_process_selector", REAR_O2_PROCESS_SELECTOR_ADDR,
         build_runtime_noop_selector(REAR_O2_PROCESS_SELECTOR_ADDR,
                                     REAR_O2_ORIGINAL_TRAMPOLINE_ADDR)),
        ("rear_o2_original_trampoline", REAR_O2_ORIGINAL_TRAMPOLINE_ADDR,
         build_rear_o2_original_trampoline()),
        ("rear_o2_threshold_selector", REAR_O2_THRESHOLD_SELECTOR_ADDR,
         build_runtime_noop_selector(REAR_O2_THRESHOLD_SELECTOR_ADDR,
                                     STOCK_REAR_O2_THRESHOLD_UPDATE)),
        ("rear_o2_filter_selector", REAR_O2_FILTER_SELECTOR_ADDR,
         build_runtime_noop_selector(REAR_O2_FILTER_SELECTOR_ADDR,
                                     STOCK_REAR_O2_FILTER_UPDATE)),
        ("rear_o2_integrator_selector", REAR_O2_INTEGRATOR_SELECTOR_ADDR,
         build_runtime_noop_selector(REAR_O2_INTEGRATOR_SELECTOR_ADDR,
                                     STOCK_REAR_O2_INTEGRATOR_UPDATE)),
        ("rear_o2_response_ratio_selector", REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR,
         build_runtime_noop_selector(REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR,
                                     STOCK_REAR_O2_RESPONSE_RATIO_UPDATE)),
        ("rear_o2_voltage_diag_selector", REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR,
         build_runtime_noop_selector(REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR,
                                     STOCK_REAR_O2_VOLTAGE_DIAG_DISPATCH)),
    ]


def apply_to_rom(rom):
    """Apply only the single-front-A/F changes to a stock-derived ROM image.

    This is shared by the standalone and combined builders.  All stock hooks,
    diagnostic bytes, and free-space allocations keep their original guards.
    """
    if len(rom) != 0x80000:
        raise SystemExit("REFUSING: expected a 512 KB stock-derived image, got %d bytes"
                         % len(rom))

    blobs = build_blobs()
    limits = {
        "front_patch_enable": FRONT_MIRROR_WRAPPER_ADDR,
        "front_sensor_mirror_wrapper": FRONT_ORIGINAL_TRAMPOLINE_ADDR,
        "front_original_trampoline": FRONT_DIAG_MIRROR_WRAPPER_ADDR,
        "front_diagnostic_mirror_wrapper": BANK2_INHIBIT_SELECTOR_ADDR,
        "bank2_inhibit_selector": REAR_O2_PROCESS_SELECTOR_ADDR,
        "rear_o2_process_selector": REAR_O2_ORIGINAL_TRAMPOLINE_ADDR,
        "rear_o2_original_trampoline": REAR_O2_THRESHOLD_SELECTOR_ADDR,
        "rear_o2_threshold_selector": REAR_O2_FILTER_SELECTOR_ADDR,
        "rear_o2_filter_selector": REAR_O2_INTEGRATOR_SELECTOR_ADDR,
        "rear_o2_integrator_selector": REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR,
        "rear_o2_response_ratio_selector": REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR,
        "rear_o2_voltage_diag_selector": FREE_END + 1,
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
                  build_entry_hook(BANK2_INHIBIT_ENTRY, BANK2_INHIBIT_SELECTOR_ADDR),
                  "bank-2 front A/F inhibit entry")
    checked_write(rom, FRONT_PUMP_DIAG_TASK_PTR, be32(STOCK_FRONT_PUMP_DIAG_THUNK),
                  be32(FRONT_DIAG_MIRROR_WRAPPER_ADDR),
                  "front pump-current diagnostic task pointer")
    checked_write(rom, REAR_O2_PROCESS_ENTRY,
                  bytes.fromhex("2fd6e020d521e700d421e600"),
                  build_entry_hook(REAR_O2_PROCESS_ENTRY, REAR_O2_PROCESS_SELECTOR_ADDR),
                  "rear O2 ADC process entry")
    rear_task_hooks = (
        (REAR_O2_THRESHOLD_TASK_PTR, STOCK_REAR_O2_THRESHOLD_UPDATE,
         REAR_O2_THRESHOLD_SELECTOR_ADDR, "rear O2 threshold task pointer"),
        (REAR_O2_FILTER_TASK_PTR, STOCK_REAR_O2_FILTER_UPDATE,
         REAR_O2_FILTER_SELECTOR_ADDR, "rear O2 filter task pointer"),
        (REAR_O2_INTEGRATOR_TASK_PTR, STOCK_REAR_O2_INTEGRATOR_UPDATE,
         REAR_O2_INTEGRATOR_SELECTOR_ADDR, "rear O2 response task pointer"),
        (REAR_O2_RESPONSE_RATIO_TASK_PTR, STOCK_REAR_O2_RESPONSE_RATIO_UPDATE,
         REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR, "rear O2 response-ratio task pointer"),
        (REAR_O2_VOLTAGE_DIAG_TASK_PTR, STOCK_REAR_O2_VOLTAGE_DIAG_DISPATCH,
         REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR, "rear O2 voltage diagnostic task pointer"),
    )
    for pointer, stock_target, selector, label in rear_task_hooks:
        checked_write(rom, pointer, be32(stock_target), be32(selector), label)
    for code, address in DISABLED_FRONT_AF_DTC_SWITCHES.items():
        checked_write(rom, address, b"\x01", b"\x00", "%s switch" % code)
    for code, address in DISABLED_REAR_O2_DTC_SWITCHES.items():
        checked_write(rom, address, b"\x01", b"\x00", "%s rear-O2 switch" % code)

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
    if len(stock_bytes) != 0x80000:
        raise SystemExit("REFUSING: expected a 512 KB stock image, got %d bytes" % len(stock_bytes))
    rom = bytearray(stock_bytes)
    blobs = apply_to_rom(rom)

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
    print("  rear sensors  : both rear narrowband ADC/monitor paths bypassed while enabled")
    print("  ext. wideband : external logger only; no ECU electrical or firmware interface")
    print("  runtime switch: @0x%05X defaults ON (01); OFF restores stock front/rear logic"
          % FRONT_AF_ENABLE_ADDR)
    print("  switch caveat : OFF does not re-enable the 13 statically disabled O2 DTC switches")
    print("\n*** DEVELOPMENT IMAGE: validate the retained sensor and both-bank behavior before use. ***")


if __name__ == "__main__":
    main()
