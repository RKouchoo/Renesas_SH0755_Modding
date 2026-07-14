#!/usr/bin/env python3
"""Binary audit for the standalone D2WD610H single-front-A/F patch.

Usage:  python3 verify_single_front_af.py [patched.bin]
"""
import hashlib
import os
import sys

import patch_single_front_af as patch
from sh2_disasm import dis_one


HERE = os.path.dirname(os.path.abspath(__file__))
PATCHED = (os.path.abspath(sys.argv[1]) if len(sys.argv) > 1
           else os.path.join(HERE, "D2WD610H_single_front_af.bin"))
if len(sys.argv) > 2:
    raise SystemExit("usage: python3 verify_single_front_af.py [patched.bin]")


def expect(image, address, data, label):
    actual = image[address:address + len(data)]
    if actual != data:
        raise SystemExit("FAIL: %s @0x%05X is %s, expected %s"
                         % (label, address, actual.hex(), data.hex()))


def add_allowed(allowed, address, length):
    allowed.update(range(address, address + length))


def decode_span(image, start, end):
    decoded = []
    for address in range(start, end, 2):
        text, _ = dis_one(image, address)
        if text.startswith(".word"):
            raise SystemExit("FAIL: unknown opcode at 0x%05X: %s" % (address, text))
        decoded.append((address, text))
    return decoded


def main():
    with open(patch.STOCK, "rb") as handle:
        stock = handle.read()
    with open(PATCHED, "rb") as handle:
        image = handle.read()
    if hashlib.sha256(stock).hexdigest() != patch.STOCK_SHA256:
        raise SystemExit("FAIL: canonical root stock hash changed")
    if len(stock) != 0x80000 or len(image) != 0x80000:
        raise SystemExit("FAIL: both images must be exactly 512 KiB")

    blobs = [
        ("front patch enable", patch.FRONT_AF_ENABLE_ADDR, b"\x01"),
        ("front mirror wrapper", patch.FRONT_MIRROR_WRAPPER_ADDR,
         patch.build_front_mirror_wrapper()),
        ("front original trampoline", patch.FRONT_ORIGINAL_TRAMPOLINE_ADDR,
         patch.build_front_original_trampoline()),
        ("front diagnostic mirror wrapper", patch.FRONT_DIAG_MIRROR_WRAPPER_ADDR,
         patch.build_front_diag_mirror_wrapper()),
        ("bank-2 inhibit selector", patch.BANK2_INHIBIT_SELECTOR_ADDR,
         patch.build_bank2_inhibit_selector()),
        ("rear O2 process selector", patch.REAR_O2_PROCESS_SELECTOR_ADDR,
         patch.build_runtime_noop_selector(patch.REAR_O2_PROCESS_SELECTOR_ADDR,
                                           patch.REAR_O2_ORIGINAL_TRAMPOLINE_ADDR)),
        ("rear O2 original trampoline", patch.REAR_O2_ORIGINAL_TRAMPOLINE_ADDR,
         patch.build_rear_o2_original_trampoline()),
        ("rear O2 threshold selector", patch.REAR_O2_THRESHOLD_SELECTOR_ADDR,
         patch.build_runtime_noop_selector(patch.REAR_O2_THRESHOLD_SELECTOR_ADDR,
                                           patch.STOCK_REAR_O2_THRESHOLD_UPDATE)),
        ("rear O2 filter selector", patch.REAR_O2_FILTER_SELECTOR_ADDR,
         patch.build_runtime_noop_selector(patch.REAR_O2_FILTER_SELECTOR_ADDR,
                                           patch.STOCK_REAR_O2_FILTER_UPDATE)),
        ("rear O2 integrator selector", patch.REAR_O2_INTEGRATOR_SELECTOR_ADDR,
         patch.build_runtime_noop_selector(patch.REAR_O2_INTEGRATOR_SELECTOR_ADDR,
                                           patch.STOCK_REAR_O2_INTEGRATOR_UPDATE)),
        ("rear O2 response-ratio selector", patch.REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR,
         patch.build_runtime_noop_selector(patch.REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR,
                                           patch.STOCK_REAR_O2_RESPONSE_RATIO_UPDATE)),
        ("rear O2 voltage diagnostic selector", patch.REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR,
         patch.build_runtime_noop_selector(patch.REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR,
                                           patch.STOCK_REAR_O2_VOLTAGE_DIAG_DISPATCH)),
    ]
    for label, address, data in blobs:
        expect(image, address, data, label)

    fixed_edits = [
        (patch.FRONT_AF_PROCESS_ENTRY,
         patch.build_entry_hook(patch.FRONT_AF_PROCESS_ENTRY, patch.FRONT_MIRROR_WRAPPER_ADDR),
         "front A/F process hook"),
        (patch.BANK2_INHIBIT_ENTRY,
         patch.build_entry_hook(patch.BANK2_INHIBIT_ENTRY, patch.BANK2_INHIBIT_SELECTOR_ADDR),
         "bank-2 runtime inhibit-selector hook"),
        (patch.FRONT_PUMP_DIAG_TASK_PTR, patch.be32(patch.FRONT_DIAG_MIRROR_WRAPPER_ADDR),
         "front diagnostic wrapper pointer"),
        (patch.REAR_O2_PROCESS_ENTRY,
         patch.build_entry_hook(patch.REAR_O2_PROCESS_ENTRY,
                                patch.REAR_O2_PROCESS_SELECTOR_ADDR),
         "rear O2 process selector hook"),
        (patch.REAR_O2_THRESHOLD_TASK_PTR, patch.be32(patch.REAR_O2_THRESHOLD_SELECTOR_ADDR),
         "rear O2 threshold selector pointer"),
        (patch.REAR_O2_FILTER_TASK_PTR, patch.be32(patch.REAR_O2_FILTER_SELECTOR_ADDR),
         "rear O2 filter selector pointer"),
        (patch.REAR_O2_INTEGRATOR_TASK_PTR, patch.be32(patch.REAR_O2_INTEGRATOR_SELECTOR_ADDR),
         "rear O2 integrator selector pointer"),
        (patch.REAR_O2_RESPONSE_RATIO_TASK_PTR,
         patch.be32(patch.REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR),
         "rear O2 response-ratio selector pointer"),
        (patch.REAR_O2_VOLTAGE_DIAG_TASK_PTR,
         patch.be32(patch.REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR),
         "rear O2 voltage diagnostic selector pointer"),
    ]
    for address, data, label in fixed_edits:
        expect(image, address, data, label)
    for code, address in patch.DISABLED_FRONT_AF_DTC_SWITCHES.items():
        expect(image, address, b"\x00", "%s disabled" % code)
    for code, address in patch.DISABLED_REAR_O2_DTC_SWITCHES.items():
        expect(image, address, b"\x00", "%s rear O2 disabled" % code)

    # Pin each runtime decision independently of blob regeneration. The first
    # two sequences branch over their copies unless the flag is exactly 01. The
    # third selects the reconstructed stock Bank-2 helper for every other value.
    expect(image, patch.FRONT_MIRROR_WRAPPER_ADDR + 8,
           bytes.fromhex("d10a601088018b0b"), "front-mirror enable branch")
    expect(image, patch.FRONT_DIAG_MIRROR_WRAPPER_ADDR + 8,
           bytes.fromhex("d106601088018b03"), "diagnostic-mirror enable branch")
    expect(image, patch.BANK2_INHIBIT_SELECTOR_ADDR,
           bytes.fromhex("d107601088018b02"), "Bank-2 selector enable branch")
    expect(image, patch.BANK2_INHIBIT_SELECTOR_ADDR + 14,
           bytes.fromhex("d1066010c90120088b01000be000000be002"),
           "reconstructed stock Bank-2 inhibit behavior")
    selector_prefix = bytes.fromhex("d104601088018b01000b0009d102412b")
    rear_selectors = (
        patch.REAR_O2_PROCESS_SELECTOR_ADDR,
        patch.REAR_O2_THRESHOLD_SELECTOR_ADDR,
        patch.REAR_O2_FILTER_SELECTOR_ADDR,
        patch.REAR_O2_INTEGRATOR_SELECTOR_ADDR,
        patch.REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR,
        patch.REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR,
    )
    for address in rear_selectors:
        expect(image, address, selector_prefix,
               "rear O2 exact-01 no-op selector @0x%05X" % address)

    # Retained paths are safety-critical to the architecture.
    expect(image, patch.BANK1_INHIBIT_ENTRY,
           bytes.fromhex("907a6000c8088f020009000b"),
           "retained bank-1 front-A/F inhibit helper")
    expect(image, 0x00073E08, bytes.fromhex("b3339b448df48000"),
           "retained factory front-A/F atmospheric compensation")
    retained_dtc_switches = {
        "P0031 retained RH front": 0x0005BDAC,
        "P0032 retained RH front": 0x0005BDAA,
        "P0131 retained RH front": 0x0005BDA0,
        "P0132 retained RH front": 0x0005BDA2,
        "P0134 retained RH front": 0x0005BDBD,
    }
    for label, address in retained_dtc_switches.items():
        expect(image, address, b"\x01", label)

    allowed = set()
    for _, address, data in blobs:
        add_allowed(allowed, address, len(data))
    for address, data, _ in fixed_edits:
        add_allowed(allowed, address, len(data))
    for address in patch.DISABLED_FRONT_AF_DTC_SWITCHES.values():
        add_allowed(allowed, address, 1)
    for address in patch.DISABLED_REAR_O2_DTC_SWITCHES.values():
        add_allowed(allowed, address, 1)
    changed = [index for index, (old, new) in enumerate(zip(stock, image)) if old != new]
    unexpected = [index for index in changed if index not in allowed]
    if unexpected:
        raise SystemExit("FAIL: unexpected changed offsets: %s"
                         % ", ".join("0x%05X" % value for value in unexpected[:32]))
    if image[0x7D790:0x7D904] != stock[0x7D790:0x7D904]:
        raise SystemExit("FAIL: standalone front-A/F image modifies the reserved boost region")
    if (image[0x7D904:patch.FRONT_AF_ENABLE_ADDR] !=
            stock[0x7D904:patch.FRONT_AF_ENABLE_ADDR] or
            image[patch.FRONT_AF_ENABLE_ADDR + 1:patch.FRONT_MIRROR_WRAPPER_ADDR] !=
            stock[patch.FRONT_AF_ENABLE_ADDR + 1:patch.FRONT_MIRROR_WRAPPER_ADDR]):
        raise SystemExit("FAIL: unused pre-wrapper free space is not stock/erased")
    if image[0x7DB3C:0x7DB40] != stock[0x7DB3C:0x7DB40]:
        raise SystemExit("FAIL: post-rear-patch free region is not stock/erased")

    # Instruction ends are the aligned literal-pool starts produced by Asm.
    instruction_spans = [
        (patch.FRONT_MIRROR_WRAPPER_ADDR, 0x7D950),
        (patch.FRONT_ORIGINAL_TRAMPOLINE_ADDR, 0x7D9B4),
        (patch.FRONT_DIAG_MIRROR_WRAPPER_ADDR, 0x7DA00),
        (patch.BANK2_INHIBIT_SELECTOR_ADDR, 0x7DA40),
        (patch.REAR_O2_PROCESS_SELECTOR_ADDR, 0x7DA74),
        (patch.REAR_O2_ORIGINAL_TRAMPOLINE_ADDR, 0x7DA94),
        (patch.REAR_O2_THRESHOLD_SELECTOR_ADDR, 0x7DAB4),
        (patch.REAR_O2_FILTER_SELECTOR_ADDR, 0x7DAD4),
        (patch.REAR_O2_INTEGRATOR_SELECTOR_ADDR, 0x7DAF4),
        (patch.REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR, 0x7DB14),
        (patch.REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR, 0x7DB34),
    ]
    decoded = []
    for start, end in instruction_spans:
        decoded.extend(decode_span(image, start, end))

    # The overwritten stock prologue is reproduced byte-for-byte before the
    # trampoline jumps to the first untouched instruction.
    expect(image, patch.FRONT_ORIGINAL_TRAMPOLINE_ADDR,
           bytes.fromhex("2fe62fd62fc62fb62fa62f96"),
           "replayed front-A/F prologue")
    expect(image, patch.REAR_O2_ORIGINAL_TRAMPOLINE_ADDR,
           bytes.fromhex("2fd6e020"), "replayed rear-O2 prologue start")
    expect(image, patch.REAR_O2_ORIGINAL_TRAMPOLINE_ADDR + 20,
           bytes.fromhex("ffffab00ffffb0940000e0dc"),
           "rear-O2 relocated literals and resume target")

    print("single-front-A/F binary audit PASS")
    print("  stock SHA-256  : %s" % hashlib.sha256(stock).hexdigest())
    print("  output SHA-256 : %s" % hashlib.sha256(image).hexdigest())
    print("  changed bytes  : %d (all inside guarded O2 hooks/DTCs/free-space allocations)"
          % len(changed))
    print("  injected code  : %d decoded instructions; no unknown opcodes; enable branches pinned"
          % len(decoded))
    print("  front feedback : stock Bank 1 mirrored to Bank 2; Bank-1 diagnostics retained")
    print("  runtime switch : 0x%05X=01; 00 selects stock front/rear runtime logic"
          % patch.FRONT_AF_ENABLE_ADDR)
    print("  OFF caveat     : all 13 removed-sensor DTC bytes remain disabled until re-enabled")
    print("  rear O2 paths  : ADC conversion and five monitor stages bypassed; 8 DTCs disabled")
    print("  ext. wideband  : no ECU hook, ADC conversion, RAM publication, or definition")
    print("  boost region   : 0x7D790..0x7D903 unchanged")


if __name__ == "__main__":
    main()
