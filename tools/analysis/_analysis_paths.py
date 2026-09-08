"""Locate master artifacts and shared interpreters for offline analysis tools."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "master_patch"
for relative in ("master_patch", "tests", "patches/core", "patches/speed_density",
                 "patches/fueling_safety", "patches/wideband_o2", "patches/purge_delete"):
    directory = str(ROOT / relative)
    if directory not in sys.path:
        sys.path.append(directory)
