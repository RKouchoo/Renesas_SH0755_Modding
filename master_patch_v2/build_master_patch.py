#!/usr/bin/env python3
"""Build the D2WD610H mafless turbo master patch v2 from canonical stock.

Fixes:
- Base Timing D & A low-RPM timing floor to eliminate off-idle stumble/bog.
- Full boost timing cap at 2000 RPM raised from -2.0 deg to +10.0 deg.
- Local obsolete MAF-fault load substitution bypassed, matching rolling main.
- Tip-in Enrichment Compensation (MRP) zero-multiplier defect fixed near atmospheric/boost.
- Smoothed low-lift VE table (no 1200-1600 RPM spike, flattened idle vacuum cells).
- Deceleration dashpot air decrement softened from 0.6 to 0.15 for gentle return to idle.
- Transient load-change falling-load filter speed increased from 0.01 to 0.08.
- Hardcoded 550cc (Subaru 16611AA510) injector scaling and latencies (no external donor ROM check).
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import os
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PATCH_DIR = ROOT / "patches/core"
FUEL_SAFETY_DIR = ROOT / "patches/fueling_safety"
MASTER_PATCH_DIR = ROOT / "master_patch"

for directory in (PATCH_DIR, FUEL_SAFETY_DIR, MASTER_PATCH_DIR,
                  ROOT / "patches/wideband_o2", ROOT / "patches/purge_delete", HERE):
    sys.path.insert(0, str(directory))

import extract_srf  # noqa: E402
import patch_boost as boost  # noqa: E402
import speed_density_component as speed_density  # noqa: E402
import master_calibration as calibration  # noqa: E402
import wideband_component as wideband  # noqa: E402
import fueling_safety_component as fueling_safety  # noqa: E402
import purge_delete_component as purge_delete  # noqa: E402


STOCK = (ROOT / "2005 BLE MT.bin").resolve()
BASE_STOCK = (ROOT / "base_roms" / "2005 BLE MT.bin").resolve()
SOURCE_SRF = (ROOT / "base_roms" / "2005 BLE MT.srf").resolve()
DEFAULT_OUT = (HERE / "D2WD610H_master_patch_v2.bin").resolve()
ROM_SIZE = 0x80000
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"

OMNI_MIN_VOLTS = 0.60
OMNI_MIN_KPA = 30.0
OMNI_MAX_VOLTS = 4.75
OMNI_MAX_KPA = 300.0
KPA_TO_MMHG = 7.500616827041698
OMNI_KPA_PER_VOLT = (OMNI_MAX_KPA - OMNI_MIN_KPA) / (
    OMNI_MAX_VOLTS - OMNI_MIN_VOLTS
)
OMNI_KPA_OFFSET = OMNI_MIN_KPA - OMNI_KPA_PER_VOLT * OMNI_MIN_VOLTS
OMNI_MAP_MULTIPLIER = OMNI_KPA_PER_VOLT * KPA_TO_MMHG
OMNI_MAP_OFFSET = OMNI_KPA_OFFSET * KPA_TO_MMHG

MAP_SCALING_ADDR = boost.MAP_SCALING_ADDR
MAP_LOW_CEL_RAW_ADDR = 0x0007B286
STOCK_MAP_LOW_CEL_RAW = 0x1D08
MASTER_MAP_LOW_CEL_VOLTS = 0.30
MASTER_MAP_LOW_CEL_RAW = round(MASTER_MAP_LOW_CEL_VOLTS * 65536.0 / 5.0)


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def f32(value: float) -> bytes:
    return struct.pack(">f", value)


def merge_ranges(addresses: set[int]) -> list[tuple[int, int]]:
    if not addresses:
        return []
    ordered = sorted(addresses)
    result: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for address in ordered[1:]:
        if address != previous + 1:
            result.append((start, previous))
            start = address
        previous = address
    result.append((start, previous))
    return result


def checked_write(
    rom: bytearray,
    address: int,
    expected: bytes,
    replacement: bytes,
    label: str,
) -> None:
    current = bytes(rom[address : address + len(expected)])
    if current != expected:
        raise SystemExit(
            "REFUSING: %s @0x%05X is %s (expected %s)"
            % (label, address, current.hex(), expected.hex())
        )
    rom[address : address + len(replacement)] = replacement


def verify_provenance() -> bytes:
    stock = STOCK.read_bytes()
    if len(stock) != ROM_SIZE or sha256(stock) != STOCK_SHA256:
        raise SystemExit("REFUSING: root stock ROM is not the pinned D2WD610H image")
    if BASE_STOCK.read_bytes() != stock:
        raise SystemExit("REFUSING: base_roms stock copy differs from canonical root stock")
    try:
        payload, _, _, _ = extract_srf.extract_memd(SOURCE_SRF)
    except (OSError, ValueError) as exc:
        raise SystemExit("REFUSING: original SRF provenance check failed: %s" % exc) from exc
    if payload != stock:
        raise SystemExit("REFUSING: original SRF payload differs from canonical stock")
    return stock


def apply_omni_map_calibration(rom: bytearray) -> None:
    donor_scaling = f32(boost.MAP_SENSOR_OFFSET) + f32(boost.MAP_SENSOR_MULTIPLIER)
    omni_scaling = f32(OMNI_MAP_OFFSET) + f32(OMNI_MAP_MULTIPLIER)
    checked_write(
        rom,
        MAP_SCALING_ADDR,
        donor_scaling,
        omni_scaling,
        "boost component's temporary donor MAP transfer",
    )
    checked_write(
        rom,
        MAP_LOW_CEL_RAW_ADDR,
        struct.pack(">H", STOCK_MAP_LOW_CEL_RAW),
        struct.pack(">H", MASTER_MAP_LOW_CEL_RAW),
        "MAP raw low-input CEL threshold",
    )


def refuse_output_alias(output: Path) -> None:
    protected = (
        STOCK,
        BASE_STOCK,
        SOURCE_SRF,
    )
    output_real = Path(os.path.realpath(output))
    for source in protected:
        source_real = Path(os.path.realpath(source))
        if output_real == source_real:
            raise SystemExit("REFUSING: output aliases protected source: %s" % source)
        if output.exists() and source.exists() and os.path.samefile(output, source):
            raise SystemExit("REFUSING: output is a hard link to protected source: %s" % source)


def build_image() -> tuple[
    bytes,
    bytes,
    dict[str, list[tuple[str, int, bytes]]],
    dict[str, tuple[int, bytes]],
]:
    stock = verify_provenance()
    rom = bytearray(stock)

    component_blobs: dict[str, list[tuple[str, int, bytes]]] = {}
    component_blobs["boost"] = boost.apply_to_rom(rom)
    apply_omni_map_calibration(rom)
    # Rotational idle is excluded from v2. Starting from stock retains the
    # direct final-timing task pointer and erased former component allocation.
    component_blobs["speed_density"] = speed_density.apply_to_rom(rom)
    component_blobs["wideband_O2_delete"] = wideband.apply_to_rom(rom)
    component_blobs["purge_delete"] = purge_delete.apply_to_rom(rom)
    component_blobs["fueling_safety"] = fueling_safety.apply_to_rom(rom)

    component_reference = bytes(rom)
    calibration_writes = calibration.apply_calibration(rom, component_reference)

    predictable_avls = speed_density.apply_predictable_avls_calibration(rom)
    calibration_writes.update(predictable_avls)
    _, calculated, _ = calibration.checksum_value(rom)
    checksum_data = struct.pack(">I", calculated)
    rom[
        calibration.CHECKSUM_TABLE_ADDR + 8 : calibration.CHECKSUM_TABLE_ADDR + 12
    ] = checksum_data
    calibration_writes["Subaru checksum"] = (
        calibration.CHECKSUM_TABLE_ADDR + 8,
        checksum_data,
    )
    output = bytes(rom)

    if output[0x11E30:0x11E34] != struct.pack(">I", 0x279CC):
        raise AssertionError("v2 final-timing task must call the stock routine directly")
    if output[0x7DB40:0x7DD00] != b"\xff" * 0x1C0:
        raise AssertionError("v2 former rotational-idle allocation must remain erased")
    stored, calculated, _ = calibration.checksum_value(output)
    if stored != calculated:
        raise AssertionError("master image Subaru checksum is invalid")
    if STOCK.read_bytes() != stock or BASE_STOCK.read_bytes() != stock:
        raise RuntimeError("protected stock ROM changed during master build")
    if extract_srf.extract_memd(SOURCE_SRF)[0] != stock:
        raise RuntimeError("protected SRF payload changed during master build")
    return stock, output, component_blobs, calibration_writes


def resolve_output(argv: list[str]) -> Path:
    if len(argv) > 2:
        raise SystemExit("usage: python3 master_patch_v2/build_master_patch.py [out.bin]")
    return Path(argv[1]).resolve() if len(argv) == 2 else DEFAULT_OUT


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv if argv is None else argv
    output_path = resolve_output(argv)
    refuse_output_alias(output_path)
    stock, output, component_blobs, calibration_writes = build_image()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output)

    changed = {
        index
        for index, (before, after) in enumerate(zip(stock, output))
        if before != after
    }
    stored, calculated, _ = calibration.checksum_value(output)
    flow_raw, _, flow_disp = calibration.sti_550cc_injector_calibration()

    print("D2WD610H master patch v2 written: %s" % output_path)
    print("  stock source      : %s (UNCHANGED, SHA-256 %s)" % (STOCK, sha256(stock)))
    print("  output SHA-256    : %s" % sha256(output))
    print("  changed bytes     : %d" % len(changed))
    print(
        "  changed ranges    : %s"
        % ", ".join("0x%05X..0x%05X" % pair for pair in merge_ranges(changed))
    )
    print(
        "  Omni MAP transfer : %.9f mmHg/V %+.9f mmHg; low CEL %.3f V"
        % (OMNI_MAP_MULTIPLIER, OMNI_MAP_OFFSET, MASTER_MAP_LOW_CEL_VOLTS)
    )
    print("  speed density     : always-on MAFless, smoothed dual VE, 2.999 L")
    print("  load source       : local obsolete MAF-fault substitution bypassed")
    print("  rotational idle   : removed; final-timing task calls stock 0x279CC directly")
    print("  AVLS switch       : fixed 3200 engage / 3000 release RPM")
    print("  timing fixes      : Base Timing D/A low-RPM floor >=9-15 deg; 2000 RPM full boost cap %+.1f deg"
          % calibration.interpolate(calibration.FULL_BOOST_TIMING_CAP, 2000))
    print("  tip-in fix        : Tip-in MRP table neutral (128) across vacuum/boost (no zero multiplier)")
    print("  idle/decel fixes  : Dashpot decel air decrement 0.15; transient load filter 0.08")
    print("  injectors         : 550cc (Subaru 16611AA510), %.2f cc/min (raw %.6f)" % (flow_disp, flow_raw))
    print("  boost             : spring-only; hard MAP cut retained")
    print("  fan / purge       : stock fan PWM retained; actual CPC + fuel subtraction deleted")
    print("  oxygen sensors    : former MAF ADC -> wideband lambda; stock O2 terms neutralized")
    print("  checksum          : 0x%08X (valid=%s)" % (stored, stored == calculated))
    for component, blobs in component_blobs.items():
        location = "in-place stock ranges" if component == "purge_delete" else "reserved flash blobs"
        print("  %-18s: %d %s" % (component, len(blobs), location))


if __name__ == "__main__":
    main()
