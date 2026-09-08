"""Shared import paths for standalone offline verifiers and execution tests."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
for relative in ("patches/core", "patches/speed_density", "patches/fueling_safety",
                 "patches/wideband_o2", "patches/purge_delete", "master_patch", "tools/analysis", "tests"):
    directory = str(ROOT / relative)
    if directory not in sys.path:
        sys.path.append(directory)
