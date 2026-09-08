"""Read the exact files used by the completed audit as rolling artifacts change."""
from functools import lru_cache
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
AUDIT_COMMIT = "2d95301"


@lru_cache(maxsize=None)
def read_audit_file(path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{AUDIT_COMMIT}:{path}"],
        check=True, capture_output=True,
    ).stdout


def read_audit_image(record: dict) -> bytes:
    image = read_audit_file(record["path"])
    if len(image) != 0x80000 or hashlib.sha256(image).hexdigest() != record["sha256"]:
        raise ValueError(f"Audit image hash/size mismatch: {record['path']} at {AUDIT_COMMIT}")
    return image
