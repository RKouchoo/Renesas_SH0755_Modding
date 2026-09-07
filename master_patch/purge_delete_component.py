#!/usr/bin/env python3
"""Master-only CPC delete for removed and capped canister-purge plumbing.

The actual CPC command is B6D4 (SSM P38, address 0x32), published by 1BAF0
and sent to B182.  CD54 / E8C4 belong to radiator-fan control and are NOT
touched here.  This component does not implement electronic boost control.

Two bounded, in-place function-entry replacements are sufficient:
* 1BAF0 clears requested purge duty, modeled purge airflow and its mode, then
  tail-calls the unchanged stock CPC request writer with exactly +0.0 in FR4.
* 23054 stores exactly +0.0 at its R4 destination, independently of coolant,
  trim and stale/NaN filter state.  Its two stock callers target BE60 / BE64,
  the bank terms subtracted by final_fueling_multiplier_compose at 1DD04.

The original purge airflow/duty mode helpers have no callers outside 1BAF0
in the inspected stock Ghidra database.  No incoming xrefs were found to the
interior of the replaced 40-byte entry.  Existing initialization, filter RAM,
the actual CPC output driver, scheduler and radiator-fan code remain intact.
Both entries are stackless and preserve all callee-saved registers and PR.
No free-flash allocation or new runtime RAM is required.  A zero ECU command
does not establish hardware output polarity or an installed valve's condition.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "patch"))
from sh2_asm import Asm  # noqa: E402


ROM_SIZE = 0x80000
PURGE_DISPATCH_ENTRY = 0x1BAF0
PURGE_DISPATCH_ENTRY_STOCK = bytes.fromhex(
    "2fe64f2293727ff4d23a6030420b80f8d339430b2f00"
    "d339430b80f4de386403d3386030600c885a"
)
PURGE_SUBTRACTION_ENTRY = 0x23054
PURGE_SUBTRACTION_ENTRY_STOCK = bytes.fromhex("c720f608d320d21b")
PURGE_OUTPUT_WRITER = 0xB182
PURGE_DUTY_ADDR = 0xFFFFB6D4
PURGE_MODELED_AIRFLOW_ADDR = 0xFFFFB6D8
PURGE_MODE_ADDR = 0xFFFFB720
PURGE_BANK_SUBTRACTION_ADDRS = (0xFFFFBE60, 0xFFFFBE64)

# Matching base definitions and stock descriptor records identify exactly
# these two purge-circuit switches.  No unrelated EVAP or fan DTC is masked.
DISABLED_PURGE_DTC_SWITCHES = {"P0458": 0x5BD85, "P0459": 0x5BD86}


def build_purge_off_entry() -> bytes:
    """Replacement 1BAF0 leaf; tail-call preserves the original caller PR."""
    a = Asm(PURGE_DISPATCH_ENTRY)
    a.fldi0(4)
    a.movl_pool(1, PURGE_DUTY_ADDR).fmov_store(4, 1)
    a.movl_pool(1, PURGE_MODELED_AIRFLOW_ADDR).fmov_store(4, 1)
    a.mov_imm(0, 0)
    a.movl_pool(1, PURGE_MODE_ADDR).movb_store(0, 1)
    a.movl_pool(1, PURGE_OUTPUT_WRITER).jmp(1).nop()
    result = a.assemble()
    assert len(result) == len(PURGE_DISPATCH_ENTRY_STOCK) == 40
    return result


def build_bank_subtraction_zero_entry() -> bytes:
    """R4 is the stock bank destination; store occurs in the RTS delay slot."""
    result = Asm(PURGE_SUBTRACTION_ENTRY).fldi0(1).rts().fmov_store(1, 4).nop().assemble()
    assert len(result) == len(PURGE_SUBTRACTION_ENTRY_STOCK) == 8
    return result


# Label, flash address, expected stock bytes, replacement bytes.  All ownership
# is explicit; builders/verifiers can include these ranges without allocating
# another code cave or treating stock code as blank flash.
STOCK_PATCHES = (
    ("master_purge_duty_and_airflow_delete", PURGE_DISPATCH_ENTRY,
     PURGE_DISPATCH_ENTRY_STOCK, build_purge_off_entry()),
    ("master_purge_bank_fuel_subtraction_delete", PURGE_SUBTRACTION_ENTRY,
     PURGE_SUBTRACTION_ENTRY_STOCK, build_bank_subtraction_zero_entry()),
    *((f"master_purge_{code}_disable", address, b"\x01", b"\x00")
      for code, address in DISABLED_PURGE_DTC_SWITCHES.items()),
)

# Non-owned stock anchors establish the caller ABI, actual CPC output, both
# bank destinations, preserved clear helper, SSM identity and DTC mapping.
# These bytes are required unchanged before application AND after integration.
STOCK_GUARDS = (
    ("purge dispatch tail caller", 0x1B15A, bytes.fromhex("a4c94f26")),
    ("both bank subtraction call sites", 0x23038,
     bytes.fromhex("92349434b00af42892329432b006f428")),
    ("bank 1 destination literal", 0x230A6, bytes.fromhex("be60")),
    ("bank 2 destination literal", 0x230AA, bytes.fromhex("be64")),
    ("actual CPC output literal", 0x1BBFC, struct.pack(">I", PURGE_OUTPUT_WRITER)),
    ("actual CPC output writer", PURGE_OUTPUT_WRITER, bytes.fromhex(
        "4f22c7167ffcd216f308d513f432f43d035a22322f526551655d"
        "d309430b6422640362f2604381227f044f26000b0009")),
    # The only other AB64 request writer is initialization at B0D8.  It
    # receives the same stock fixed-point scale helper's zero-input result.
    ("CPC initial zero request", 0xB0B4, bytes.fromhex(
        "d3427ff8d2426531655d420be40081f29575d340430b64f3"
        "d53fe60085f26453d23a740c8142")),
    ("stock purge duty/flow clear helper", 0x1BC0A,
     bytes.fromhex("f38d9177f13a9374000bf33a")),
    ("CPC SSM dispatch", 0x4B7C4, struct.pack(">I", 0x318E8)),
    ("CPC SSM RAM literal", 0x319EC, bytes.fromhex("b6d4")),
    ("P0458 descriptor", 0x5C1C4,
     bytes.fromhex("000c400004580200000000000005119401000000")),
    ("P0459 descriptor", 0x5C1D8,
     bytes.fromhex("000c800004590200000000000005119401000000")),
)


def _require_bytes(rom: bytes | bytearray, label: str, address: int, expected: bytes) -> None:
    actual = bytes(rom[address:address + len(expected)])
    if actual != expected:
        raise SystemExit(
            f"REFUSING: {label} @0x{address:05X} is {actual.hex()} "
            f"(expected {expected.hex()})"
        )


def build_blobs() -> list[tuple[str, int, bytes]]:
    """Return replacement ranges, all in-place stock edits, NOT free flash."""
    return [(name, address, replacement)
            for name, address, _, replacement in STOCK_PATCHES]


def verify_rom(rom: bytes | bytearray) -> None:
    """Verify owned bytes and required unchanged stock anchors in an image."""
    if len(rom) != ROM_SIZE:
        raise SystemExit("REFUSING: purge delete requires a 512 KiB ROM")
    for name, address, _, replacement in STOCK_PATCHES:
        _require_bytes(rom, name, address, replacement)
    for name, address, expected in STOCK_GUARDS:
        _require_bytes(rom, name, address, expected)


def apply_to_rom(rom: bytearray) -> list[tuple[str, int, bytes]]:
    """Apply only to a stock-derived in-memory ROM; refusal is all-or-nothing."""
    if not isinstance(rom, bytearray) or len(rom) != ROM_SIZE:
        raise SystemExit("REFUSING: purge delete requires a 512 KiB bytearray")
    occupied: set[int] = set()
    for name, address, expected, replacement in STOCK_PATCHES:
        if len(expected) != len(replacement):
            raise AssertionError(f"Purge delete range length mismatch: {name}")
        region = set(range(address, address + len(replacement)))
        if not region or address < 0 or max(region) >= ROM_SIZE or occupied & region:
            raise AssertionError(f"Purge delete ownership overlap/out-of-range: {name}")
        occupied.update(region)
        _require_bytes(rom, name, address, expected)
    for name, address, expected in STOCK_GUARDS:
        if occupied & set(range(address, address + len(expected))):
            raise AssertionError(f"Purge stock guard overlaps owned bytes: {name}")
        _require_bytes(rom, name, address, expected)
    for _, address, _, replacement in STOCK_PATCHES:
        rom[address:address + len(replacement)] = replacement
    verify_rom(rom)
    return build_blobs()


if __name__ == "__main__":
    raise SystemExit("purge_delete_component.py is a component; run build_master_patch.py")
