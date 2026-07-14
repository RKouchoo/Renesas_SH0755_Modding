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
        ("front mirror wrapper", patch.FRONT_MIRROR_WRAPPER_ADDR,
         patch.build_front_mirror_wrapper()),
        ("front original trampoline", patch.FRONT_ORIGINAL_TRAMPOLINE_ADDR,
         patch.build_front_original_trampoline()),
        ("front diagnostic mirror wrapper", patch.FRONT_DIAG_MIRROR_WRAPPER_ADDR,
         patch.build_front_diag_mirror_wrapper()),
    ]
    for label, address, data in blobs:
        expect(image, address, data, label)

    fixed_edits = [
        (patch.FRONT_AF_PROCESS_ENTRY,
         patch.build_entry_hook(patch.FRONT_AF_PROCESS_ENTRY, patch.FRONT_MIRROR_WRAPPER_ADDR),
         "front A/F process hook"),
        (patch.BANK2_INHIBIT_ENTRY,
         patch.build_entry_hook(patch.BANK2_INHIBIT_ENTRY, patch.BANK1_INHIBIT_ENTRY),
         "bank-2-to-bank-1 inhibit hook"),
        (patch.FRONT_PUMP_DIAG_TASK_PTR, patch.be32(patch.FRONT_DIAG_MIRROR_WRAPPER_ADDR),
         "front diagnostic wrapper pointer"),
    ]
    for address, data, label in fixed_edits:
        expect(image, address, data, label)
    for code, address in patch.DISABLED_FRONT_AF_DTC_SWITCHES.items():
        expect(image, address, b"\x00", "%s disabled" % code)

    # Retained paths are safety-critical to the architecture.
    expect(image, patch.BANK1_INHIBIT_ENTRY,
           bytes.fromhex("907a6000c8088f020009000b"),
           "retained bank-1 front-A/F inhibit helper")
    expect(image, 0x00073E08, bytes.fromhex("b3339b448df48000"),
           "retained factory front-A/F atmospheric compensation")
    expect(image, 0x0000E0D0, bytes.fromhex("2fd6e020d521e700d421e600"),
           "stock rear-O2 process entry")
    retained_dtc_switches = {
        "P0031 retained RH front": 0x0005BDAC,
        "P0032 retained RH front": 0x0005BDAA,
        "P0131 retained RH front": 0x0005BDA0,
        "P0132 retained RH front": 0x0005BDA2,
        "P0134 retained RH front": 0x0005BDBD,
        "P0037 retained RH rear": 0x0005BDAB,
        "P0038 retained RH rear": 0x0005BDA9,
        "P0137 retained RH rear": 0x0005BD9F,
        "P0138 retained RH rear": 0x0005BDA4,
        "P0057 retained LH rear": 0x0005BDC1,
        "P0058 retained LH rear": 0x0005BDC2,
        "P0157 retained LH rear": 0x0005BDC3,
        "P0158 retained LH rear": 0x0005BDC4,
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
    changed = [index for index, (old, new) in enumerate(zip(stock, image)) if old != new]
    unexpected = [index for index in changed if index not in allowed]
    if unexpected:
        raise SystemExit("FAIL: unexpected changed offsets: %s"
                         % ", ".join("0x%05X" % value for value in unexpected[:32]))
    if image[0x7D790:0x7D8E0] != stock[0x7D790:0x7D8E0]:
        raise SystemExit("FAIL: standalone front-A/F image modifies the reserved boost region")
    if image[0x7D900:0x7D920] != stock[0x7D900:0x7D920]:
        raise SystemExit("FAIL: retired external-wideband calibration region is not stock/erased")
    if image[0x7DA60:0x7DB40] != stock[0x7DA60:0x7DB40]:
        raise SystemExit("FAIL: retired external-wideband code region is not stock/erased")

    # Instruction ends are the aligned literal-pool starts produced by Asm.
    instruction_spans = [
        (patch.FRONT_MIRROR_WRAPPER_ADDR, 0x7D948),
        (patch.FRONT_ORIGINAL_TRAMPOLINE_ADDR, 0x7D9B4),
        (patch.FRONT_DIAG_MIRROR_WRAPPER_ADDR, 0x7D9F8),
    ]
    decoded = []
    for start, end in instruction_spans:
        decoded.extend(decode_span(image, start, end))

    # The overwritten stock prologue is reproduced byte-for-byte before the
    # trampoline jumps to the first untouched instruction.
    expect(image, patch.FRONT_ORIGINAL_TRAMPOLINE_ADDR,
           bytes.fromhex("2fe62fd62fc62fb62fa62f96"),
           "replayed front-A/F prologue")

    print("single-front-A/F binary audit PASS")
    print("  stock SHA-256  : %s" % hashlib.sha256(stock).hexdigest())
    print("  output SHA-256 : %s" % hashlib.sha256(image).hexdigest())
    print("  changed bytes  : %d (all inside guarded front hooks/DTCs/free-space allocations)"
          % len(changed))
    print("  injected code  : %d decoded instructions; no unknown opcodes" % len(decoded))
    print("  front feedback : stock Bank 1 mirrored to Bank 2; Bank-1 diagnostics retained")
    print("  rear O2 paths  : both stock processing paths and checked DTC switches retained")
    print("  ext. wideband  : no ECU hook, ADC conversion, RAM publication, or definition")
    print("  boost region   : 0x7D790..0x7D8DF unchanged")


if __name__ == "__main__":
    main()
