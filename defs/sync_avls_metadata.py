#!/usr/bin/env python3
"""Synchronize Ghidra-verified AVLS metadata into retained component inputs.

The metric D2WD610H_AVLS.xml definition is authoritative.  Only the boost
component definition remains as a generator input; the focused master
definition is rebuilt by master_patch/build_definition.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "D2WD610H_AVLS.xml"
TARGETS = (
    HERE / "D2WD610H_AVLS_boost_patch.xml",
)

OIL_TABLE = "Engine Oil Temperature Sensor Scaling"
FUEL_TABLE = "Fuel Temp Sensor Scaling"
AVLS_MARKER = "<!-- D2WD610H AVLS tables -->"
OLD_AVLS_NAME = "AVLS Switchover Load Threshold 1"
NEW_AVLS_NAME = "AVLS Vehicle Speed Threshold (Normal Oil Temperature)"
TABLE_TAGS = re.compile(r"</?table\b[^>]*>")


def depth_delta(line: str) -> int:
    delta = 0
    for tag in TABLE_TAGS.findall(line):
        if tag.startswith("</"):
            delta -= 1
        elif not tag.rstrip().endswith("/>"):
            delta += 1
    return delta


def table_ranges(lines: list[str], name: str) -> list[tuple[int, int]]:
    needle = f'name="{name}"'
    found: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        if "<table" not in lines[index] or needle not in lines[index]:
            index += 1
            continue
        start = index
        depth = depth_delta(lines[index])
        index += 1
        while depth > 0 and index < len(lines):
            depth += depth_delta(lines[index])
            index += 1
        if depth != 0:
            raise SystemExit(f"unterminated {name!r} table")
        found.append((start, index))
    return found


def avls_range(lines: list[str]) -> tuple[int, int]:
    starts = [i for i, line in enumerate(lines) if line.strip() == AVLS_MARKER]
    if len(starts) != 1:
        raise SystemExit(f"expected one AVLS marker, found {len(starts)}")
    start = starts[0]
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped == "</rom>" or (
            stripped.startswith("<!-- D2WD610H ") and stripped != AVLS_MARKER
        ):
            return start, index
    raise SystemExit("could not find end of AVLS table block")


def render(source_lines: list[str], target_text: str) -> str:
    source_oil = table_ranges(source_lines, OIL_TABLE)
    if len(source_oil) != 2:
        raise SystemExit(f"source must contain two {OIL_TABLE!r} tables")
    source_avls_start, source_avls_end = avls_range(source_lines)
    source_avls = source_lines[source_avls_start:source_avls_end]

    lines = target_text.splitlines(keepends=True)
    oil_ranges = table_ranges(lines, OIL_TABLE)
    if not oil_ranges:
        fuel_ranges = table_ranges(lines, FUEL_TABLE)
        if len(fuel_ranges) != 2:
            raise SystemExit(f"target must contain two {FUEL_TABLE!r} tables")
        insertions = (
            (fuel_ranges[0][1], source_lines[source_oil[0][0]:source_oil[0][1]]),
            (fuel_ranges[1][1], source_lines[source_oil[1][0]:source_oil[1][1]]),
        )
        for index, block in reversed(insertions):
            lines[index:index] = block
    elif len(oil_ranges) != 2:
        raise SystemExit(f"target has an incomplete {OIL_TABLE!r} definition")

    target_avls_start, target_avls_end = avls_range(lines)
    lines[target_avls_start:target_avls_end] = source_avls
    result = "".join(lines)

    if OLD_AVLS_NAME in result:
        raise SystemExit("stale load-labelled AVLS metadata remains")
    if result.count(f'name="{NEW_AVLS_NAME}"') != 1:
        raise SystemExit("synchronized AVLS table is missing or duplicated")
    if result.count(f'name="{OIL_TABLE}"') != 2:
        raise SystemExit("engine-oil-temperature scaling is missing or duplicated")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if a derived definition is not synchronized",
    )
    args = parser.parse_args()

    source_lines = SOURCE.read_text(encoding="utf-8").splitlines(keepends=True)
    changed: list[Path] = []
    for path in TARGETS:
        old = path.read_text(encoding="utf-8")
        new = render(source_lines, old)
        if new == old:
            continue
        changed.append(path)
        if not args.check:
            path.write_text(new, encoding="utf-8")

    if args.check and changed:
        names = ", ".join(path.name for path in changed)
        raise SystemExit(f"AVLS metadata is out of sync: {names}")
    if changed:
        print("Synchronized AVLS metadata: " + ", ".join(path.name for path in changed))
    else:
        print("AVLS metadata already synchronized")


if __name__ == "__main__":
    main()
