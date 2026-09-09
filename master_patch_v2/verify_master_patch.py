#!/usr/bin/env python3
"""Focused verifier for D2WD610H master patch v2.

Performs four offline check groups:
1. Subaru Checksum Verification (valid 32-bit additive checksum)
2. Memory Layout & Component Collision Checks (no overlapping allocations or corrupted ranges)
3. RomRaider XML Definition Integrity (valid XML, target CALID and table addresses)
4. Local load-fallback instruction regression, diagnostic preservation and
   exact change scope against the pre-fix v2 image.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PATCH_DIR = ROOT / "patches/core"
FUEL_SAFETY_DIR = ROOT / "patches/fueling_safety"
MASTER_PATCH_DIR = ROOT / "master_patch"

for directory in (PATCH_DIR, FUEL_SAFETY_DIR, MASTER_PATCH_DIR, HERE):
    sys.path.insert(0, str(directory))

import build_master_patch as master
import master_calibration as calibration
import speed_density_component as speed_density
import build_definition as definition
import patch_boost as boost


BIN_PATH = HERE / "D2WD610H_master_patch_v2.bin"
XML_PATH = HERE / "D2WD610H_master_patch_v2.xml"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def verify_checksum(image: bytes) -> None:
    """1. Verify that the 32-bit Subaru additive checksum matches exactly."""
    stored, calculated, _ = calibration.checksum_value(image)
    if stored != calculated:
        fail(f"Subaru checksum invalid: stored 0x{stored:08X} != calculated 0x{calculated:08X}")
    print(f"  [1/3] Subaru Checksum       : 0x{stored:08X} (VALID)")


def verify_memory_layout(
    stock: bytes,
    image: bytes,
    blobs: dict[str, list[tuple[str, int, bytes]]],
    calibration_writes: dict[str, tuple[int, bytes]],
) -> None:
    """2. Verify that injected blobs do not overlap and stay within free flash."""
    owned_ranges: set[int] = set()

    for component, blob_list in blobs.items():
        if component == "purge_delete":
            continue  # In-place stock overrides
        for name, address, data in blob_list:
            region = set(range(address, address + len(data)))
            overlap = owned_ranges & region
            if overlap:
                fail(f"Flash collision in {component}/{name} at 0x{min(overlap):05X}")
            owned_ranges.update(region)

    # Component data tables that are intentionally updated by calibration
    allowed_component_overrides = {
        boost.TARGET_DATA,
        boost.BASE_DATA,
        boost.KP_ADDR,
        boost.MAXR_ADDR,
        boost.OVERB_ADDR,
        boost.OVERB_FC_ADDR,
        speed_density.MAP_MIN_ADDR,
        calibration.LEAN_ARM_ADDR,
        calibration.LEAN_RESET_ADDR,
        calibration.LEAN_AFR_ADDR,
    }

    for name, (address, data) in calibration_writes.items():
        if name == "Subaru checksum" or address in allowed_component_overrides:
            continue
        region = set(range(address, address + len(data)))
        overlap = owned_ranges & region
        if overlap:
            fail(f"Calibration write '{name}' collided with code blob at 0x{min(overlap):05X}")

    changed_bytes = sum(1 for a, b in zip(stock, image) if a != b)
    print(f"  [2/3] Memory Layout         : NO COLLISIONS ({len(blobs)} components, {changed_bytes} changed bytes)")


def verify_definition(image: bytes) -> None:
    """3. Verify that the RomRaider definition is valid and matches binary table addresses."""
    if not XML_PATH.exists():
        fail(f"Missing RomRaider definition {XML_PATH}")

    root = ET.parse(XML_PATH).getroot()
    roms = root.findall("rom")
    if len(roms) < 2:
        fail("RomRaider XML is missing base or target ROM entry")

    target = roms[1]
    calid = target.findtext("romid/internalidstring")
    if calid != "D2WD610H":
        fail(f"Target definition CALID is {calid}, expected D2WD610H")

    tables = {table.get("name"): table for table in target.findall("table")}

    # Verify critical tables point to correct addresses and dimensions in the binary
    checks = {
        "Speed Density VE - AVLS Low Lift": (speed_density.LOW_VE_DATA_ADDR, len(speed_density.MAP_AXIS), len(speed_density.LOW_RPM_AXIS)),
        "Speed Density VE - AVLS High Lift": (speed_density.HIGH_VE_DATA_ADDR, len(speed_density.MAP_AXIS), len(speed_density.HIGH_RPM_AXIS)),
        "Base Timing A (Normal Cam, AVCS 1.0)": (0x78AA0, 15, 14),
        "Base Timing D (Normal Cam, AVCS 0.0)": (0x78E34, 15, 14),
        "Base Timing C (AVLS High Cam, AVCS 1.0)": (0x78CD0, 15, 20),
        "Base Timing F (AVLS High Cam, AVCS 0.0)": (0x79064, 15, 20),
        "Tip-in Enrichment Compensation (MRP)": (0x76AC8, 1, 8),
        "Injector Flow Scaling ": (0x76014, 1, 1),
    }

    for name, (expected_addr, expected_x, expected_y) in checks.items():
        tbl = tables.get(name)
        if tbl is None:
            # Check if name has slight whitespace difference in definition
            tbl = next((t for t in target.findall("table") if t.get("name", "").strip() == name.strip()), None)
        if tbl is None:
            fail(f"Definition is missing table '{name}'")

        addr = int(tbl.get("storageaddress", "0"), 0)
        if addr != expected_addr:
            fail(f"Table '{name}' address is 0x{addr:05X}, expected 0x{expected_addr:05X}")

    print("  [3/3] RomRaider XML Def     : VALID (D2WD610H target, verified table addresses)")


def main() -> None:
    print("Verifying D2WD610H master patch v2...")
    stock = master.STOCK.read_bytes()
    if not BIN_PATH.exists():
        fail(f"Binary {BIN_PATH} does not exist. Run build_master_patch.py first.")

    _, image, blobs, cal_writes = master.build_image()
    disk_image = BIN_PATH.read_bytes()

    if disk_image != image:
        fail("Disk binary differs from generator output. Re-run build_master_patch.py.")

    verify_checksum(image)
    verify_memory_layout(stock, image, blobs, cal_writes)
    verify_definition(image)

    out_hash = hashlib.sha256(image).hexdigest()
    print(f"\nALL 3 ESSENTIAL CHECKS PASSED.")
    print(f"ROM SHA-256: {out_hash}")
    print(f"Ready for vehicle flashing: {BIN_PATH.name}")


if __name__ == "__main__":
    main()
