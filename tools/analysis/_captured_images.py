"""Recover pinned captures across the recorded September 12 pump-scaling edit.

Only reverse an exact recognized after-hash and exact changed words. The
calling analysis must still check its own captured-image hash. This keeps
old logs tied to their flashed image as the rolling binaries advance.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def before_pump_scaling(image):
    digest = hashlib.sha256(image).hexdigest()
    evidence = json.loads((ROOT / 'docs/reference/evidence/fuel_pump_scaling_20260912.json').read_text())
    for record in evidence['images']:
        if digest != record['after_sha256']:
            continue
        restored = bytearray(image)
        for word in record['changed_words']:
            address = int(word['address'], 16)
            assert restored[address:address+4] == bytes.fromhex(word['after_hex'])
            restored[address:address+4] = bytes.fromhex(word['before_hex'])
        assert hashlib.sha256(restored).hexdigest() == record['before_sha256']
        return bytes(restored)
    return image
