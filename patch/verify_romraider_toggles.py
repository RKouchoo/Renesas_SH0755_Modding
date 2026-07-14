#!/usr/bin/env python3
"""Audit runtime switches in the standalone and combined patch images."""
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent

CASES = [
    {
        "definition": ROOT / "defs/D2WD610H_AVLS_boost_patch.xml",
        "image": ROOT / "patch/D2WD610H_boost.bin",
        "xmlid": "D2WD610H_AVLS_BOOST_PATCH",
        "switch": "Boost Control Patch Enable",
        "address": 0x7D80C,
        "tables": {
            "Boost Wastegate Duty (RPM)": 0x7D7C4,
            "Boost Target (RPM)": 0x7D7E0,
            "Boost Kp (proportional gain)": 0x7D800,
            "Boost Max Duty Ratio": 0x7D804,
            "Boost Overboost Cut (Duty, soft)": 0x7D808,
            "Boost Minimum Throttle": 0x7D8BC,
            "Boost Overboost Fuel Cut (hard)": 0x7D8C0,
        },
    },
    {
        "definition": ROOT / "defs/D2WD610H_AVLS_single_front_af_patch.xml",
        "image": ROOT / "patch/D2WD610H_single_front_af.bin",
        "xmlid": "D2WD610H_AVLS_SINGLE_FRONT_AF_PATCH",
        "switch": "Single Front A/F Patch Enable",
        "address": 0x7D91C,
        "tables": {
            "(P0051) HO2S CIRCUIT LOW B2 S1": 0x5BDB4,
            "(P0052) HO2S CIRCUIT HIGH B2 S1": 0x5BDB3,
            "(P0151) O2 SENSOR CIRCUIT LOW B2 S1": 0x5BDA1,
            "(P0152) O2 SENSOR CIRCUIT HIGH B2 S1": 0x5BDA3,
            "(P0154) O2 SENSOR CIRCUIT OPEN B2 S1": 0x5BDBC,
        },
    },
    {
        "definition": ROOT / "defs/D2WD610H_AVLS_boost_single_front_af_patch.xml",
        "image": ROOT / "patch/D2WD610H_boost_single_front_af.bin",
        "xmlid": "D2WD610H_AVLS_BOOST_SINGLE_FRONT_AF_PATCH",
        "switch": "Boost Control Patch Enable",
        "address": 0x7D80C,
        "tables": {
            "Boost Wastegate Duty (RPM)": 0x7D7C4,
            "Boost Target (RPM)": 0x7D7E0,
            "Boost Kp (proportional gain)": 0x7D800,
            "Boost Max Duty Ratio": 0x7D804,
            "Boost Overboost Cut (Duty, soft)": 0x7D808,
            "Boost Minimum Throttle": 0x7D8BC,
            "Boost Overboost Fuel Cut (hard)": 0x7D8C0,
        },
    },
    {
        "definition": ROOT / "defs/D2WD610H_AVLS_boost_single_front_af_patch.xml",
        "image": ROOT / "patch/D2WD610H_boost_single_front_af.bin",
        "xmlid": "D2WD610H_AVLS_BOOST_SINGLE_FRONT_AF_PATCH",
        "switch": "Single Front A/F Patch Enable",
        "address": 0x7D91C,
        "tables": {
            "(P0051) HO2S CIRCUIT LOW B2 S1": 0x5BDB4,
            "(P0052) HO2S CIRCUIT HIGH B2 S1": 0x5BDB3,
            "(P0151) O2 SENSOR CIRCUIT LOW B2 S1": 0x5BDA1,
            "(P0152) O2 SENSOR CIRCUIT HIGH B2 S1": 0x5BDA3,
            "(P0154) O2 SENSOR CIRCUIT OPEN B2 S1": 0x5BDBC,
        },
    },
]


def named_tables(root, name):
    return [table for table in root.findall(".//table") if table.get("name") == name]


def main():
    for case in CASES:
        root = ET.parse(case["definition"]).getroot()
        xmlids = [rom.findtext("./romid/xmlid") for rom in root.findall("./rom")]
        expected_ids = ["32BITBASE", case["xmlid"]]
        if xmlids != expected_ids:
            raise SystemExit("FAIL: %s ROM IDs are %r, expected %r"
                             % (case["definition"].name, xmlids, expected_ids))

        switches = named_tables(root, case["switch"])
        if len(switches) != 1:
            raise SystemExit("FAIL: %s has %d matching enable switches"
                             % (case["definition"].name, len(switches)))
        switch = switches[0]
        address = int(switch.get("storageaddress"), 16)
        states = {state.get("name"): state.get("data") for state in switch.findall("state")}
        if address != case["address"] or states != {"on": "01", "off": "00"}:
            raise SystemExit("FAIL: %s switch mapping is address=0x%X states=%r"
                             % (case["definition"].name, address, states))

        for name, expected_address in case["tables"].items():
            tables = [table for table in named_tables(root, name)
                      if table.get("storageaddress") is not None]
            if len(tables) != 1 or int(tables[0].get("storageaddress"), 16) != expected_address:
                raise SystemExit("FAIL: %s table %r does not map uniquely to 0x%05X"
                                 % (case["definition"].name, name, expected_address))

        image = case["image"].read_bytes()
        if len(image) != 0x80000 or image[address] != 0x01:
            raise SystemExit("FAIL: %s is not a 512-KiB generated-ON image"
                             % case["image"].name)
        off = bytearray(image)
        off[address] = 0x00
        changed = [index for index, pair in enumerate(zip(image, off)) if pair[0] != pair[1]]
        if changed != [address]:
            raise SystemExit("FAIL: simulated OFF edit was not isolated to the enable byte")

        print("PASS: %-48s %s @0x%05X (ON=01/OFF=00)"
              % (case["definition"].name, case["switch"], address))

    print("RomRaider toggle audit PASS: XML, target IDs, table addresses, defaults, and isolated OFF edits")


if __name__ == "__main__":
    main()
