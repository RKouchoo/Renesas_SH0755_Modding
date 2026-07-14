#!/usr/bin/env python3
"""Extract and verify the raw ROM payload from the original EcuFlash SRF.

The D2WD610H SRF is a sequence of big-endian chunks.  Its MEMD chunk contains
the complete 512-KiB flash image; no byte scanning or guessed offset is used.

Usage: python3 patch/extract_srf.py [input.srf] [output.bin]

The default output is base_roms/2005 BLE MT.bin.  If that file already contains
the exact MEMD payload it is left untouched.  A different existing file is
never overwritten.
"""

from pathlib import Path
import hashlib
import struct
import sys


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRF = ROOT / "base_roms/2005 BLE MT.srf"
DEFAULT_OUT = ROOT / "base_roms/2005 BLE MT.bin"
CANONICAL_STOCK = ROOT / "2005 BLE MT.bin"

EXPECTED_SRF_SHA256 = "05eae5322072449d90e20e20125d5333738675168d623a320735958bfc7619aa"
EXPECTED_ROM_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"
EXPECTED_ROM_SIZE = 0x80000


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_chunks(container):
    """Return (tag, payload_offset, payload) tuples for an SRF container."""
    chunks = []
    offset = 0
    while offset < len(container):
        if len(container) - offset < 8:
            raise ValueError("truncated SRF chunk header at 0x%X" % offset)
        tag_bytes = container[offset:offset + 4]
        try:
            tag = tag_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("non-ASCII SRF chunk tag at 0x%X" % offset) from exc
        length = struct.unpack_from(">I", container, offset + 4)[0]
        payload_offset = offset + 8
        end = payload_offset + length
        if end > len(container):
            raise ValueError("SRF chunk %s at 0x%X extends past EOF" % (tag, offset))
        chunks.append((tag, payload_offset, container[payload_offset:end]))
        offset = end
    return chunks


def extract_memd(path=DEFAULT_SRF, verify_known_container=True):
    path = Path(path)
    container = path.read_bytes()
    container_hash = sha256(container)
    if verify_known_container and path.resolve() == DEFAULT_SRF.resolve():
        if container_hash != EXPECTED_SRF_SHA256:
            raise ValueError("original SRF hash is %s, expected %s"
                             % (container_hash, EXPECTED_SRF_SHA256))

    chunks = parse_chunks(container)
    memd = [(offset, payload) for tag, offset, payload in chunks if tag == "MEMD"]
    if len(memd) != 1:
        raise ValueError("expected exactly one MEMD chunk, found %d" % len(memd))
    payload_offset, payload = memd[0]
    if len(payload) != EXPECTED_ROM_SIZE:
        raise ValueError("MEMD payload is %d bytes, expected %d"
                         % (len(payload), EXPECTED_ROM_SIZE))
    if payload[0x2000:0x2008] != b"D2WD610H":
        raise ValueError("MEMD payload does not contain CALID D2WD610H at 0x2000")
    return payload, chunks, container_hash, payload_offset


def main():
    if len(sys.argv) > 3:
        raise SystemExit("usage: python3 patch/extract_srf.py [input.srf] [output.bin]")
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_SRF.resolve()
    output = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DEFAULT_OUT.resolve()

    if output == CANONICAL_STOCK.resolve():
        raise SystemExit("REFUSING: extraction output may not be the canonical root stock ROM")

    try:
        payload, chunks, container_hash, payload_offset = extract_memd(source)
    except (OSError, ValueError) as exc:
        raise SystemExit("REFUSING: %s" % exc)

    payload_hash = sha256(payload)
    if payload_hash != EXPECTED_ROM_SHA256:
        raise SystemExit("REFUSING: MEMD payload SHA-256 is %s, expected %s"
                         % (payload_hash, EXPECTED_ROM_SHA256))

    if output.exists():
        existing = output.read_bytes()
        if existing != payload:
            raise SystemExit("REFUSING: existing output differs from the SRF MEMD payload: %s"
                             % output)
        disposition = "already exact; left unchanged"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as handle:
            handle.write(payload)
        disposition = "extracted"

    canonical = CANONICAL_STOCK.read_bytes()
    if canonical != payload:
        raise SystemExit("FAIL: SRF MEMD payload differs from canonical root stock ROM")

    print("SRF extraction verification PASS")
    print("  source SHA-256 : %s" % container_hash)
    print("  chunks         : %s" % ", ".join(
        "%s@0x%X+0x%X" % (tag, offset, len(data)) for tag, offset, data in chunks))
    print("  MEMD payload   : offset 0x%X, %d bytes" % (payload_offset, len(payload)))
    print("  ROM SHA-256    : %s" % payload_hash)
    print("  output         : %s (%s)" % (output, disposition))
    print("  canonical root : byte-identical and unchanged")


if __name__ == "__main__":
    main()
