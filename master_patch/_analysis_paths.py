"""Locate the shared offline interpreters used by historical replay tools."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
for relative in ("tests", "patches/wideband_o2", "patches/purge_delete"):
    directory = str(ROOT / relative)
    if directory not in sys.path:
        sys.path.append(directory)
