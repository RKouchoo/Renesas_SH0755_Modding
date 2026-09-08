#!/usr/bin/env python3
"""Compatibility entry point; the master verifier now lives in tests/."""
from pathlib import Path
import runpy
import sys

TESTS = Path(__file__).resolve().parent.parent / "tests"
sys.path.insert(0, str(TESTS))

if __name__ == "__main__":
    runpy.run_path(str(TESTS / "verify_master_patch.py"), run_name="__main__")
else:
    # Preserve imports used by older offline investigation commands.
    namespace = runpy.run_path(str(TESTS / "verify_master_patch.py"))
    globals().update({key: value for key, value in namespace.items()
                      if not key.startswith("__")})
