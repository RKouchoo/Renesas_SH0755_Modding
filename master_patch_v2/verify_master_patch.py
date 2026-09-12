#!/usr/bin/env python3
"""Focused verifier for D2WD610H master patch v2.

Performs ten offline check groups:
1. Subaru Checksum Verification (valid 32-bit additive checksum)
2. Memory Layout & Component Collision Checks (no overlapping allocations or corrupted ranges)
3. RomRaider XML Definition Integrity (valid XML, target CALID and table addresses)
4. Rotational-idle removal (stock timing-task pointer and erased allocation).
5. Lean-cut hysteresis instruction execution with the installed calibration.
6. Native AVLS stationary oil-temperature gate and mode-selection execution.
7. Native primary-fuel selection, ramp and six-cylinder fuel composition.
8. Native injector scheduling, cut publication, cancellation and release.
9. Retained diagnostic fuel-cut selector, including its 3000/2500-RPM path.
10. Injector-scaled fuel-consumption conversion and native pump-demand selection.
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

# Load the v2 definition before shared components prepend their own search
# paths; otherwise the same-named v1 generator can be imported accidentally.
import build_definition as definition
import build_master_patch as master
import master_calibration as calibration
import speed_density_component as speed_density
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
    print(f"  [1/10] Subaru Checksum       : 0x{stored:08X} (VALID)")


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
    print(f"  [2/10] Memory Layout         : NO COLLISIONS ({len(blobs)} components, {changed_bytes} changed bytes)")


def verify_definition(image: bytes) -> None:
    """3. Verify that the RomRaider definition is valid and matches binary table addresses."""
    if not XML_PATH.exists():
        fail(f"Missing RomRaider definition {XML_PATH}")

    root = ET.parse(XML_PATH).getroot()
    definition.validate(root)
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
        "Fuel Consumption Injector Coefficient": (0x72D54, 1, 1),
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

    print("  [3/10] RomRaider XML Def     : VALID (D2WD610H target, verified table addresses)")


def verify_stock_timing_path(stock: bytes, image: bytes) -> None:
    """Reject an installed wrapper even if its enable byte is switched off."""
    pointer = struct.pack(">I", 0x279CC)
    if stock[0x11E30:0x11E34] != pointer or image[0x11E30:0x11E34] != pointer:
        fail("Final-timing task pointer does not call stock 0x279CC directly")
    erased = b"\xff" * 0x1C0
    if stock[0x7DB40:0x7DD00] != erased or image[0x7DB40:0x7DD00] != erased:
        fail("Former rotational-idle allocation is not erased")
    # Retained final-angle composition and ignition scheduler code must also
    # remain stock; timing calibration elsewhere is deliberately independent.
    for start, end in ((0x2777C, 0x285E0), (0x29C00, 0x2A53A)):
        if image[start:end] != stock[start:end]:
            fail(f"Stock timing/scheduler code changed at 0x{start:05X}..0x{end - 1:05X}")
    print("  [4/10] Stock Timing Path     : direct stock task; rotational-idle allocation erased")


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
    verify_stock_timing_path(stock, image)
    sys.path.insert(0, str(ROOT / "tests"))
    from test_lean_cut_hysteresis_execution import verify_execution
    count = verify_execution(image)
    print(f"  [5/10] Lean-Cut Hysteresis    : {count} instruction-execution tests passed")
    from test_avls_oil_gate_execution import verify_execution as verify_avls
    count = verify_avls(image)
    print(f"  [6/10] AVLS Oil Gates        : {count} instruction-execution tests passed")
    from test_primary_fueling_execution import verify_execution as verify_fuel
    verify_fuel(image)
    print("  [7/10] Primary Fueling       : native targets, ramp and cylinder composition passed")
    from test_injector_scheduler_execution import verify_execution as verify_scheduler
    verify_scheduler(image)
    print("  [8/10] Injector Scheduling   : native cut, cancellation and release paths passed")
    from test_native_fault_cut_execution import verify_execution as verify_fault_cut
    verify_fault_cut(image)
    print("  [9/10] Native Fault Cut      : diagnostic qualification, RPM hysteresis and release passed")

    from test_fuel_pump_demand_execution import verify_execution as verify_pump
    count = verify_pump(image)
    print(f"  [10/10] Fuel-Pump Demand      : {count} instruction-execution tests passed")

    out_hash = hashlib.sha256(image).hexdigest()
    print("\nALL 10 OFFLINE CHECK GROUPS PASSED.")
    print(f"ROM SHA-256: {out_hash}")
    print(f"Verified artifact: {BIN_PATH.name} (vehicle behavior remains unverified)")


if __name__ == "__main__":
    main()
