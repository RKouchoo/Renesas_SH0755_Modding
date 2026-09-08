#!/usr/bin/env python3
"""Audit combined overboost fuel cut + single-front-A/F/rear-O2-delete image.

The electronic actuator is retired and the real radiator-fan output remains
stock. Legacy actuator data are preserved only as inert flash reservations.

Usage: python3 tests/verify_combined.py [patched.bin]
"""

import _test_paths  # Shared offline-test imports and repository root.

from pathlib import Path
import hashlib
import sys

import extract_srf
import patch_boost as boost
import patch_combined as combined_builder
import patch_single_front_af as front
from sh2_disasm import dis_one


HERE = (_test_paths.ROOT / "patches/core")
PATCHED = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else
           HERE / "D2WD610H_boost_single_front_af.bin")
if len(sys.argv) > 2:
    raise SystemExit("usage: python3 tests/verify_combined.py [patched.bin]")


def expect(image, address, data, label):
    actual = image[address:address + len(data)]
    if actual != data:
        raise SystemExit("FAIL: %s @0x%05X is %s, expected %s"
                         % (label, address, actual.hex(), data.hex()))


def decode_span(image, start, end):
    decoded = []
    for address in range(start, end, 2):
        text, _ = dis_one(image, address)
        if text.startswith(".word"):
            raise SystemExit("FAIL: unknown opcode at 0x%05X: %s" % (address, text))
        decoded.append((address, text))
    return decoded


def main():
    stock = combined_builder.STOCK.read_bytes()
    image = PATCHED.read_bytes()
    stock_hash = hashlib.sha256(stock).hexdigest()
    if stock_hash != combined_builder.STOCK_SHA256:
        raise SystemExit("FAIL: canonical root stock hash changed")
    if len(stock) != 0x80000 or len(image) != 0x80000:
        raise SystemExit("FAIL: stock and combined images must both be exactly 512 KiB")

    srf_payload, _, _, payload_offset = extract_srf.extract_memd(combined_builder.SOURCE_SRF)
    if srf_payload != stock or combined_builder.BASE_STOCK.read_bytes() != stock:
        raise SystemExit("FAIL: SRF/base-ROM provenance no longer matches canonical stock")

    expected, _, _, boost_changed, front_changed = combined_builder.build_combined(stock)
    if bytes(expected) != image:
        differing = [index for index, pair in enumerate(zip(expected, image))
                     if pair[0] != pair[1]]
        raise SystemExit("FAIL: image differs from regenerated combined build at %s"
                         % ", ".join("0x%05X" % value for value in differing[:32]))
    if boost_changed & front_changed:
        raise SystemExit("FAIL: boost and front-A/F byte ownership overlaps")

    # Pin fan preservation, actuator retirement, and the remaining hard-cut
    # hook independently of regeneration from the shared blob builders.
    expect(stock, 0x3FD8C, bytes.fromhex("0000e8c4"), "canonical fan output identity")
    expect(image, 0x3FD8C, bytes.fromhex("0000e8c4"), "preserved fan output")
    expect(image, boost.REVLIM_FNPTR, boost.be32(boost.REVWRAP_ADDR), "boost rev-limit hook")
    expect(image, boost.EBCS_ENABLE_ADDR, b"\x00", "inert retired actuator byte")
    expect(image, boost.OVERBOOST_ENABLE_ADDR, b"\x01", "overboost enable default")
    expect(image, 0x7D810, bytes.fromhex("000b0009") + b"\xff" * 168,
           "retired actuator return and erased 172-byte reservation")
    expect(image, 0x7D8C4, bytes.fromhex("4f22d30d430be410d20c420b2f06"),
           "native lock then limiter; preserve prior mask in delay slot")
    expect(image, 0x7D8D2,
           bytes.fromhex("d10c601088018b0c"),
           "added-fuel-cut disabled branch")
    expect(image, 0x7D8E2, bytes.fromhex("f2358b06d10a6010cb802100d109e0ff2101"),
           "pressure comparison; publish BF6C and native B744 inhibition")
    expect(image, 0x7D8F4, bytes.fromhex("64f6d308432b4f26"),
           "restore prior mask through native unlock with caller PR")
    expect(image, 0x7D8FC,
           bytes.fromhex("00003af400024b240007d80dffffabc40007d8c0ffffbf6cffffb74400003b08"),
           "hard-cut lock, limiter, enable, MAP, threshold, flag, inhibit and unlock literals")

    boost_allowed = set(range(boost.MAP_SCALING_ADDR, boost.MAP_SCALING_ADDR + 8))
    boost_allowed.update(range(boost.REVLIM_FNPTR, boost.REVLIM_FNPTR + 4))
    for _, address, data in boost.build_blobs():
        boost_allowed.update(range(address, address + len(data)))
    if boost_changed - boost_allowed:
        raise SystemExit("FAIL: boost component changes bytes outside its retained allocations")
    if set(range(0x3FD8C, 0x3FD90)) & (boost_changed | front_changed):
        raise SystemExit("FAIL: fan output pointer belongs to neither patch's changed bytes")

    # Pin all front-A/F hooks, enable branches, and generated DTC edits.
    expect(image, front.FRONT_AF_PROCESS_ENTRY,
           front.build_entry_hook(front.FRONT_AF_PROCESS_ENTRY,
                                  front.FRONT_MIRROR_WRAPPER_ADDR),
           "front A/F process hook")
    expect(image, front.BANK2_INHIBIT_ENTRY,
           front.build_entry_hook(front.BANK2_INHIBIT_ENTRY,
                                  front.BANK2_INHIBIT_SELECTOR_ADDR),
           "bank-2 inhibit selector hook")
    expect(image, front.FRONT_PUMP_DIAG_TASK_PTR,
           front.be32(front.FRONT_DIAG_MIRROR_WRAPPER_ADDR),
           "front diagnostic wrapper pointer")
    expect(image, front.FRONT_AF_ENABLE_ADDR, b"\x01", "front-A/F runtime enable")
    expect(image, front.FRONT_MIRROR_WRAPPER_ADDR + 8,
           bytes.fromhex("d10a601088018b0b"), "front-mirror enable branch")
    expect(image, front.FRONT_DIAG_MIRROR_WRAPPER_ADDR + 8,
           bytes.fromhex("d106601088018b03"), "diagnostic-mirror enable branch")
    expect(image, front.BANK2_INHIBIT_SELECTOR_ADDR,
           bytes.fromhex("d107601088018b02"), "Bank-2 selector enable branch")
    expect(image, front.REAR_O2_PROCESS_ENTRY,
           front.build_entry_hook(front.REAR_O2_PROCESS_ENTRY,
                                  front.REAR_O2_PROCESS_SELECTOR_ADDR),
           "rear O2 process selector hook")
    rear_task_hooks = (
        (front.REAR_O2_THRESHOLD_TASK_PTR, front.REAR_O2_THRESHOLD_SELECTOR_ADDR),
        (front.REAR_O2_FILTER_TASK_PTR, front.REAR_O2_FILTER_SELECTOR_ADDR),
        (front.REAR_O2_INTEGRATOR_TASK_PTR, front.REAR_O2_INTEGRATOR_SELECTOR_ADDR),
        (front.REAR_O2_RESPONSE_RATIO_TASK_PTR, front.REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR),
        (front.REAR_O2_VOLTAGE_DIAG_TASK_PTR, front.REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR),
    )
    for pointer, selector in rear_task_hooks:
        expect(image, pointer, front.be32(selector),
               "rear O2 task selector pointer @0x%05X" % pointer)
    selector_prefix = bytes.fromhex("d104601088018b01000b0009d102412b")
    for address in (
            front.REAR_O2_PROCESS_SELECTOR_ADDR,
            front.REAR_O2_THRESHOLD_SELECTOR_ADDR,
            front.REAR_O2_FILTER_SELECTOR_ADDR,
            front.REAR_O2_INTEGRATOR_SELECTOR_ADDR,
            front.REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR,
            front.REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR):
        expect(image, address, selector_prefix,
               "rear O2 exact-01 no-op selector @0x%05X" % address)
    for code, address in front.DISABLED_FRONT_AF_DTC_SWITCHES.items():
        expect(image, address, b"\x00", "%s disabled" % code)
    for code, address in front.DISABLED_REAR_O2_DTC_SWITCHES.items():
        expect(image, address, b"\x00", "%s rear O2 disabled" % code)

    # These paths must remain stock even in the combined image.
    expect(image, front.BANK1_INHIBIT_ENTRY,
           bytes.fromhex("907a6000c8088f020009000b"),
           "retained Bank-1 front-A/F inhibit helper")
    retained_dtc_switches = {
        "P0031 retained RH front": 0x0005BDAC,
        "P0032 retained RH front": 0x0005BDAA,
        "P0131 retained RH front": 0x0005BDA0,
        "P0132 retained RH front": 0x0005BDA2,
        "P0134 retained RH front": 0x0005BDBD,
    }
    for label, address in retained_dtc_switches.items():
        expect(image, address, b"\x01", label)
    if image[0x7DB3C:0x7DB40] != stock[0x7DB3C:0x7DB40]:
        raise SystemExit("FAIL: post-rear-patch free region is not stock/erased")

    instruction_spans = [
        (boost.REVWRAP_ADDR, 0x7D8FC),
        (front.FRONT_MIRROR_WRAPPER_ADDR, 0x7D950),
        (front.FRONT_ORIGINAL_TRAMPOLINE_ADDR, 0x7D9B4),
        (front.FRONT_DIAG_MIRROR_WRAPPER_ADDR, 0x7DA00),
        (front.BANK2_INHIBIT_SELECTOR_ADDR, 0x7DA40),
        (front.REAR_O2_PROCESS_SELECTOR_ADDR, 0x7DA74),
        (front.REAR_O2_ORIGINAL_TRAMPOLINE_ADDR, 0x7DA94),
        (front.REAR_O2_THRESHOLD_SELECTOR_ADDR, 0x7DAB4),
        (front.REAR_O2_FILTER_SELECTOR_ADDR, 0x7DAD4),
        (front.REAR_O2_INTEGRATOR_SELECTOR_ADDR, 0x7DAF4),
        (front.REAR_O2_RESPONSE_RATIO_SELECTOR_ADDR, 0x7DB14),
        (front.REAR_O2_VOLTAGE_DIAG_SELECTOR_ADDR, 0x7DB34),
    ]
    decoded = []
    for start, end in instruction_spans:
        decoded.extend(decode_span(image, start, end))

    all_changed = boost_changed | front_changed
    print("combined binary audit PASS")
    print("  stock/SRF      : MEMD @0x%X, SHA-256 %s" % (payload_offset, stock_hash))
    print("  output SHA-256 : %s" % hashlib.sha256(image).hexdigest())
    print("  changed bytes  : %d = boost %d + front-A/F %d; no overlap"
          % (len(all_changed), len(boost_changed), len(front_changed)))
    print("  injected code  : %d decoded instructions; no unknown opcodes" % len(decoded))
    print("  retired actuator: RTS/NOP plus erased padding; no switch can enable it")
    print("  fan output     : 0x3FD8C remains stock 0x0000E8C4")
    print("  runtime enables: hard cut 0x%05X=01; front-A/F 0x%05X=01"
          % (boost.OVERBOOST_ENABLE_ADDR, front.FRONT_AF_ENABLE_ADDR))
    print("  O2 architecture: retained Bank-1 factory A/F; both rear narrowbands bypassed")
    print("  regenerated    : byte-identical from fresh stock; no generated input stacking")


if __name__ == "__main__":
    main()
