#!/usr/bin/env python3
"""Build the combined D2WD610H boost + single-front-A/F ROM.

Both component patch sets are applied in memory to a fresh, hash-pinned copy of
the canonical root stock ROM.  Generated standalone images are never inputs.
The original EcuFlash SRF is also parsed and its MEMD payload must match the
canonical stock bytes before the combined image can be written.

Usage: python3 patch/patch_combined.py [out.bin]
"""

from pathlib import Path
import hashlib
import os
import sys

import extract_srf
import patch_boost as boost
import patch_single_front_af as front


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STOCK = ROOT / "2005 BLE MT.bin"
BASE_STOCK = ROOT / "base_roms/2005 BLE MT.bin"
SOURCE_SRF = ROOT / "base_roms/2005 BLE MT.srf"
DEFAULT_OUT = HERE / "D2WD610H_boost_single_front_af.bin"
STOCK_SHA256 = boost.STOCK_SHA256


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def changed_offsets(before, after):
    return {index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]}


def merge_ranges(addresses):
    return front.merge_ranges(sorted(addresses))


def refuse_stock_alias(output):
    output_real = Path(os.path.realpath(output))
    protected = [STOCK, BASE_STOCK, SOURCE_SRF]
    for path in protected:
        if output_real == Path(os.path.realpath(path)):
            raise SystemExit("REFUSING: output aliases protected stock source: %s" % path)
        if output.exists() and path.exists() and os.path.samefile(output, path):
            raise SystemExit("REFUSING: output is a hard link to protected stock source: %s" % path)


def build_combined(stock_bytes):
    """Return a combined image plus independently derived change sets."""
    if len(stock_bytes) != 0x80000 or sha256(stock_bytes) != STOCK_SHA256:
        raise SystemExit("REFUSING: combined build input is not the pinned D2WD610H stock ROM")

    # Independent dry builds prove that the two component patch sets have no
    # overlapping byte ownership before they are composed into one stock copy.
    boost_only = bytearray(stock_bytes)
    boost.apply_to_rom(boost_only)
    boost_changed = changed_offsets(stock_bytes, boost_only)

    front_only = bytearray(stock_bytes)
    front.apply_to_rom(front_only)
    front_changed = changed_offsets(stock_bytes, front_only)

    overlap = boost_changed & front_changed
    if overlap:
        raise SystemExit("REFUSING: component patches overlap at %s"
                         % ", ".join("0x%05X" % address for address in sorted(overlap)[:32]))

    combined = bytearray(stock_bytes)
    boost_blobs = boost.apply_to_rom(combined)
    front_blobs = front.apply_to_rom(combined)

    combined_changed = changed_offsets(stock_bytes, combined)
    expected_changed = boost_changed | front_changed
    if combined_changed != expected_changed:
        raise SystemExit("FAIL: combined change set is not the exact union of both patches")
    for address in boost_changed:
        if combined[address] != boost_only[address]:
            raise SystemExit("FAIL: combined boost byte differs at 0x%05X" % address)
    for address in front_changed:
        if combined[address] != front_only[address]:
            raise SystemExit("FAIL: combined front-A/F byte differs at 0x%05X" % address)

    return combined, boost_blobs, front_blobs, boost_changed, front_changed


def main():
    if len(sys.argv) > 2:
        raise SystemExit("usage: python3 patch/patch_combined.py [out.bin]")
    output = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else DEFAULT_OUT.resolve()
    refuse_stock_alias(output)

    stock_bytes = STOCK.read_bytes()
    stock_hash = sha256(stock_bytes)
    if stock_hash != STOCK_SHA256:
        raise SystemExit("REFUSING: canonical stock ROM hash is %s (expected %s)"
                         % (stock_hash, STOCK_SHA256))

    try:
        srf_payload, chunks, srf_hash, payload_offset = extract_srf.extract_memd(SOURCE_SRF)
    except (OSError, ValueError) as exc:
        raise SystemExit("REFUSING: SRF provenance check failed: %s" % exc)
    if srf_payload != stock_bytes:
        raise SystemExit("REFUSING: original SRF MEMD payload differs from canonical stock ROM")
    if BASE_STOCK.read_bytes() != stock_bytes:
        raise SystemExit("REFUSING: base_roms stock BIN differs from canonical root stock ROM")

    combined, boost_blobs, front_blobs, boost_changed, front_changed = build_combined(stock_bytes)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        handle.write(combined)

    # Re-read every protected source after output generation.
    if STOCK.read_bytes() != stock_bytes:
        raise RuntimeError("canonical root stock ROM changed during combined build")
    if BASE_STOCK.read_bytes() != stock_bytes or extract_srf.extract_memd(SOURCE_SRF)[0] != stock_bytes:
        raise RuntimeError("base stock provenance changed during combined build")

    all_changed = boost_changed | front_changed
    print("Combined boost + single-front-A/F patch written: %s" % output)
    print("  stock source    : %s (UNCHANGED)" % STOCK)
    print("  stock SHA-256   : %s" % stock_hash)
    print("  SRF SHA-256     : %s" % srf_hash)
    print("  SRF MEMD        : offset 0x%X, %d bytes, byte-identical to stock"
          % (payload_offset, len(srf_payload)))
    print("  SRF chunks      : %s" % ", ".join(tag for tag, _, _ in chunks))
    print("  output SHA-256  : %s" % sha256(combined))
    print("  changed bytes   : %d = boost %d + front-A/F %d (zero overlap)"
          % (len(all_changed), len(boost_changed), len(front_changed)))
    print("  changed ranges  : %s" % ", ".join(
        "0x%05X..0x%05X" % pair for pair in merge_ranges(all_changed)))
    print("  boost blocks    : %d; enable 0x%05X=01" %
          (len(boost_blobs), boost.BOOST_ENABLE_ADDR))
    print("  front-A/F blocks: %d; enable 0x%05X=01" %
          (len(front_blobs), front.FRONT_AF_ENABLE_ADDR))
    print("  input policy    : fresh root stock only; no generated image was used as input")
    print("\n*** DEVELOPMENT IMAGE: complete both standalone commissioning plans before flashing combined. ***")


if __name__ == "__main__":
    main()
