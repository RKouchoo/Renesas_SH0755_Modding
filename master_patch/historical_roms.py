"""Read immutable log-matching ROMs from Git; the working master keeps rolling.

This module is only for historical analysis and regression fixtures. The
production builder continues to start from canonical stock, without Git input.
"""
from functools import lru_cache
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
MASTER_1030_REVISION = 'c1e81a16af294b7d7786564911b79ae7f55075ce'
MASTER_1030_BLOB = 'eb4d7c317cb69a441d3150f44d5201a0b621b584'
MASTER_1030_SHA256 = '48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0'


@lru_cache(maxsize=1)
def master_1030():
    image = subprocess.run(
        ['git', '-C', str(ROOT), 'cat-file', 'blob', MASTER_1030_BLOB],
        check=True, capture_output=True).stdout
    if len(image) != 0x80000 or hashlib.sha256(image).hexdigest() != MASTER_1030_SHA256:
        raise ValueError('Git ROM does not match the September 8 12:36 capture')
    return image
