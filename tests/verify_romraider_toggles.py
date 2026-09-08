#!/usr/bin/env python3
"""Audit current master switches and reject retired actuator controls."""

import _test_paths  # Shared offline-test imports and repository root.
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = _test_paths.ROOT
DEFINITION = ROOT / "master_patch/D2WD610H_master_patch.xml"
IMAGE = ROOT / "master_patch/D2WD610H_master_patch.bin"
XMLIDS = ["32BITBASE", "D2WD610H_MASTER_PATCH"]

CASES = (
    {
        "switch": "Overboost Fuel Cut Enable",
        "address": 0x7D80D,
        "default": 0x01,
        "alternate": 0x00,
        "tables": {"Boost Overboost Fuel Cut (hard)": 0x7D8C0},
    },
    {
        "switch": "Rotational Idle Enable",
        "address": 0x7DB40,
        "default": 0x00,
        "alternate": 0x01,
        "tables": {
            "Rotational Idle Minimum Coolant Temperature": 0x7DB44,
            "Rotational Idle Maximum Coolant Temperature": 0x7DB48,
            "Rotational Idle Minimum Engine Speed": 0x7DB4C,
            "Rotational Idle Maximum Engine Speed": 0x7DB50,
            "Rotational Idle Maximum Throttle": 0x7DB54,
            "Rotational Idle Maximum Vehicle Speed": 0x7DB58,
            "Rotational Idle Minimum Manifold Pressure": 0x7DB5C,
            "Rotational Idle Maximum Manifold Pressure": 0x7DB60,
            "Rotational Idle Maximum Retard": 0x7DB64,
            "Rotational Idle Minimum Final Timing": 0x7DB68,
            "Rotational Idle Cylinder Timing Offsets": 0x7DB6C,
        },
    },
)

RETIRED_ACTUATOR_TABLES = {
    "Electronic Boost Control Enable": 0x7D80C,
    "Boost Wastegate Duty (RPM)": 0x7D7C4,
    "Boost Target (RPM)": 0x7D7E0,
    "Boost Kp (proportional gain)": 0x7D800,
    "Boost Max Duty Ratio": 0x7D804,
    "Boost Overboost Cut (Duty, soft)": 0x7D808,
    "Boost Minimum Throttle": 0x7D8BC,
}


def named_tables(root, name):
    return [table for table in root.findall(".//table") if table.get("name") == name]


def verify_definition_toggles(root, image):
    xmlids = [rom.findtext("./romid/xmlid") for rom in root.findall("./rom")]
    if xmlids != XMLIDS:
        raise SystemExit(f"FAIL: {DEFINITION.name} ROM IDs are {xmlids!r}, expected {XMLIDS!r}")

    if len(image) != 0x80000:
        raise SystemExit(f"FAIL: {IMAGE.name} is not a 512-KiB image")

    for table in root.findall(".//table"):
        address = table.get("storageaddress")
        if (table.get("name") in RETIRED_ACTUATOR_TABLES or
            (address is not None and int(address, 16) in RETIRED_ACTUATOR_TABLES.values())):
            raise SystemExit(f"FAIL: retired actuator control remains exposed: {table.get('name')!r}")
    if image[0x3FD8C:0x3FD90] != bytes.fromhex("0000e8c4"):
        raise SystemExit("FAIL: stock radiator-fan output pointer is not preserved")
    for start, size in ((0x7D810, 172), (0x7E560, 224)):
        if image[start:start + size] != bytes.fromhex("000b0009") + b"\xff" * (size - 4):
            raise SystemExit(f"FAIL: retired actuator allocation at 0x{start:05X} contains executable code")
    print("PASS: retired actuator controls absent; fan pointer stock; old actuator code inert")

    for case in CASES:
        switches = [table for table in named_tables(root, case["switch"])
                    if table.get("storageaddress") is not None]
        if len(switches) != 1:
            raise SystemExit(f"FAIL: {DEFINITION.name} has {len(switches)} matching switches")
        switch = switches[0]
        address = int(switch.get("storageaddress"), 16)
        states = {state.get("name"): state.get("data") for state in switch.findall("state")}
        if address != case["address"] or states != {"on": "01", "off": "00"}:
            raise SystemExit(
                f"FAIL: {case['switch']} maps to 0x{address:X} with states {states!r}"
            )

        for name, expected_address in case["tables"].items():
            tables = [table for table in named_tables(root, name)
                      if table.get("storageaddress") is not None]
            if len(tables) != 1 or int(tables[0].get("storageaddress"), 16) != expected_address:
                raise SystemExit(
                    f"FAIL: table {name!r} does not map uniquely to 0x{expected_address:05X}"
                )

        default = case["default"]
        alternate = case["alternate"]
        if image[address] != default:
            raise SystemExit(
                f"FAIL: {case['switch']} generated {image[address]:02X}, expected {default:02X}"
            )
        edited = bytearray(image)
        edited[address] = alternate
        changed = [index for index, pair in enumerate(zip(image, edited)) if pair[0] != pair[1]]
        if changed != [address]:
            raise SystemExit("FAIL: simulated switch edit was not isolated to its enable byte")

        print(
            f"PASS: {case['switch']:<36} @0x{address:05X} "
            f"(default={default:02X}, alternate={alternate:02X})"
        )

    print("Master RomRaider switch audit PASS")


def main():
    verify_definition_toggles(ET.parse(DEFINITION).getroot(), IMAGE.read_bytes())


if __name__ == "__main__":
    main()
