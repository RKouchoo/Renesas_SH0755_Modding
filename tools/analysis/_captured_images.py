"""Recover pinned captures across recorded repairs to the rolling images.

Only reverse an exact recognized after-hash and exact changed words. The
calling analysis must still check its own captured-image hash. This keeps
old logs tied to their flashed image as the rolling binaries advance.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def before_pump_scaling(image):
    # Reverse the later OCV repair first, checking both endpoint hashes and
    # every replacement byte. No source-generated historical ROM is accepted.
    path = ROOT / 'docs/reference/evidence/avcs_ocv_repair_20260913.json'
    if path.exists():
        for record in json.loads(path.read_text())['images']:
            if hashlib.sha256(image).hexdigest() != record['after_sha256']:
                continue
            restored = bytearray(image)
            for item in record['changed_ranges']:
                address = int(item['address'], 16)
                after, before = bytes.fromhex(item['after_hex']), bytes.fromhex(item['before_hex'])
                assert len(after) == len(before)
                assert restored[address:address+len(after)] == after
                restored[address:address+len(after)] = before
            assert hashlib.sha256(restored).hexdigest() == record['before_sha256']
            image = bytes(restored)
            break
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
