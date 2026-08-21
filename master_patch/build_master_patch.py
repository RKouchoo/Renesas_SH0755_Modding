#!/usr/bin/env python3
"""Build the D2WD610H mafless turbo master patch from canonical stock.

Order is deliberate and deterministic:

1. verify the root stock BIN, base_roms copy, and original SRF payload;
2. install the existing Ghidra-verified boost-control component;
3. replace its donor MAP transfer with the exact Omni Power MAP-SUP-3BR data;
4. install the bounded, default-off rotational-idle timing post-processor;
5. install always-on mafless speed density with committed-state dual VE;
6. install the permanent four-stock-O2 delete / former-MAF wideband component;
7. install barometrically referenced forced-open-loop and latched lean-cut safety;
8. apply the conservative 5 psi / 98 RON / STI-pink / 6800-RPM calibration;
9. apply the speed-density component's predictable 3200/3000-RPM AVLS policy
   and write/verify the Subaru checksum.

Generated ROMs are never accepted as input.  The root stock ROM is never
opened for writing.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import os
import struct
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PATCH_DIR = ROOT / "patch"
SD_DIR = ROOT / "speed_density"
BASE_TURBO_DIR = ROOT / "base_turbo_map"
FUEL_SAFETY_DIR = ROOT / "fueling_safety"
for directory in (PATCH_DIR, SD_DIR, BASE_TURBO_DIR, FUEL_SAFETY_DIR, HERE):
    sys.path.insert(0, str(directory))

import extract_srf  # noqa: E402
import patch_boost as boost  # noqa: E402
import patch_speed_density as speed_density  # noqa: E402
import patch_rotational_idle as rotational_idle  # noqa: E402
import build_base_turbo_map as base_turbo  # noqa: E402
import wideband_component as wideband  # noqa: E402
import fueling_safety_component as fueling_safety  # noqa: E402


STOCK = (ROOT / "2005 BLE MT.bin").resolve()
BASE_STOCK = (ROOT / "base_roms" / "2005 BLE MT.bin").resolve()
SOURCE_SRF = (ROOT / "base_roms" / "2005 BLE MT.srf").resolve()
DEFAULT_OUT = (HERE / "D2WD610H_master_patch.bin").resolve()
ROM_SIZE = 0x80000
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"

# Exact sensor selected by the user:
# Omni Power MAP-SUP-3BR, direct-fit Subaru/Toyota housing.
# Supplied product data: 0.60 V at 30 kPa absolute, 4.75 V at 300 kPa.
# The product page also states Vout = 5*(0.003074074*P + 0.027777778),
# multiplier 9.436 psi/V, offset -1.311 psi.  Endpoint arithmetic is used
# here because it is clearer and avoids rounding the printed coefficients.
OMNI_PRODUCT_URL = (
    "https://www.prospeedracing.com.au/products/"
    "omni-power-3-bar-map-sensor-subaru-wrx-sti-97-00-wrx-08-14-"
    "lgt-04-09-toyota-supra-93-02-map-sup-3br"
)
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
STOCK_MAP_LOW_CEL_RAW = 0x1D08  # 0.5670 V; too high for deep-vacuum use of this sensor
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
        base_turbo.PINK_INJECTOR_DONOR.resolve(),
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
    component_blobs["rotational_idle"] = rotational_idle.apply_to_rom(rom)
    component_blobs["speed_density"] = speed_density.apply_to_rom(rom)
    component_blobs["wideband_O2_delete"] = wideband.apply_to_rom(rom)
    component_blobs["fueling_safety"] = fueling_safety.apply_to_rom(rom)

    # Pin the exact firmware-component stage before applying any tune tables.
    component_reference = bytes(rom)
    calibration_writes = base_turbo.apply_calibration(rom, component_reference)

    # The legacy base-turbo calibration predates committed-state dual VE and
    # intentionally requested early AVLS through vehicle speed.  Master now
    # replaces those values with the deterministic 3200/3000 RPM policy.  The
    # component's standalone image uses the same helper.
    predictable_avls = speed_density.apply_predictable_avls_calibration(rom)
    calibration_writes.update(predictable_avls)
    _, calculated, _ = base_turbo.checksum_value(rom)
    checksum_data = struct.pack(">I", calculated)
    rom[
        base_turbo.CHECKSUM_TABLE_ADDR + 8 : base_turbo.CHECKSUM_TABLE_ADDR + 12
    ] = checksum_data
    calibration_writes["Subaru checksum"] = (
        base_turbo.CHECKSUM_TABLE_ADDR + 8,
        checksum_data,
    )
    output = bytes(rom)

    stored, calculated, _ = base_turbo.checksum_value(output)
    if stored != calculated:
        raise AssertionError("master image Subaru checksum is invalid")
    if STOCK.read_bytes() != stock or BASE_STOCK.read_bytes() != stock:
        raise RuntimeError("protected stock ROM changed during master build")
    if extract_srf.extract_memd(SOURCE_SRF)[0] != stock:
        raise RuntimeError("protected SRF payload changed during master build")
    base_turbo.pink_injector_calibration()  # repeat donor hash/CALID/value checks
    return stock, output, component_blobs, calibration_writes


def resolve_output(argv: list[str]) -> Path:
    if len(argv) > 2:
        raise SystemExit("usage: python3 master_patch/build_master_patch.py [out.bin]")
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
    stored, calculated, _ = base_turbo.checksum_value(output)
    pink_raw, _, pink_display = base_turbo.pink_injector_calibration()

    print("D2WD610H master patch written: %s" % output_path)
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
    print("  speed density     : always-on MAFless, committed-state dual VE, 2.999 L")
    print("  AVLS VE ranges    : low 0..3200 RPM; high 3000..7500 RPM")
    print("  AVLS switch       : fixed 3200 engage / 3000 release RPM")
    print("  primary OL RPM    : 1000..6800 RPM, conservative stock-surface resample")
    print("  boost             : EVAP PWM + throttle/SD-input/wideband/soft/hard gates")
    print("  boost switches    : EBCS OFF; independent hard overboost cut ON")
    print("  default boost cmd : spring-only (WGDC/Kp/max duty all zero), 5 psi targets")
    print("  oxygen sensors    : four stock paths removed; former MAF ADC -> 50-4110 P0/P1")
    print("  rotational idle   : installed, bounded retard-only, default OFF")
    print("  pressure OL guard : ON; baro-referenced, 0.5 psi pre-boost margin")
    print("  lean fuel cut     : ON; 13.0 AFR, delayed/confirmed, boost-release latched")
    print(
        "  injectors         : pinned STI-pink factory donor, %.2f cc/min estimate "
        "(D2WD raw %.6f)" % (pink_display, pink_raw)
    )
    print("  rev limit         : 6800 cut / 6770 resume RPM")
    print("  calibration writes: %d tables/regions" % len(calibration_writes))
    print("  checksum          : 0x%08X (valid=%s)" % (stored, stored == calculated))
    for component, blobs in component_blobs.items():
        print("  %-18s: %d free-space blobs" % (component, len(blobs)))
    print("\n*** DEVELOPMENT IMAGE: bench, continuity, pressure, and load-dyno validation required. ***")


if __name__ == "__main__":
    main()
