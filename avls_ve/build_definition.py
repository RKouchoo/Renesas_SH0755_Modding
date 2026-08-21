#!/usr/bin/env python3
"""Generate the D2WD610H committed-AVLS dual-VE RomRaider definition."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import patch_avls_ve as avls_ve  # noqa: E402


SOURCE = ROOT / "speed_density" / "D2WD610H_AVLS_speed_density_patch.xml"
OUTPUT = HERE / "D2WD610H_AVLS_dual_ve_patch.xml"
OLD_VE_NAME = "Speed Density VE (MAP x RPM)"
LOW_VE_NAME = "Speed Density VE - AVLS Low Lift"
HIGH_VE_NAME = "Speed Density VE - AVLS High Lift"

# These inputs no longer participate in the predictable AVLS policy and are
# omitted instead of inviting a tune edit that silently reintroduces the old
# vehicle-speed/oil-temperature state behavior.
HIDDEN_AVLS_TABLES = {
    "AVLS Vehicle Speed Threshold (Normal Oil Temperature)",
    "AVLS Vehicle Speed Threshold (High Oil Temperature)",
    "AVLS Vehicle Speed Hysteresis (Normal Oil Temperature)",
    "AVLS Vehicle Speed Hysteresis (High Oil Temperature)",
    "AVLS Oil Temperature Selector Thresholds",
    "AVLS Actuation Minimum RPM",
}


def table_by_name(rom: ET.Element, name: str) -> ET.Element:
    matches = [table for table in rom.findall("table") if table.get("name") == name]
    if len(matches) != 1:
        raise SystemExit(f"expected one table {name!r}, found {len(matches)}")
    return matches[0]


def remove_named(rom: ET.Element, names: set[str]) -> None:
    for table in list(rom.findall("table")):
        if table.get("name") in names:
            rom.remove(table)


def set_description(table: ET.Element, value: str) -> None:
    for element in table.findall("description"):
        table.remove(element)
    ET.SubElement(table, "description").text = value


def add_ve_template(parent: ET.Element, name: str, rows: int, low: bool) -> None:
    table = ET.SubElement(
        parent,
        "table",
        {
            "type": "3D",
            "name": name,
            "category": "Speed Density - AVLS VE (patch)",
            "storagetype": "float",
            "endian": "little",
            "sizex": str(len(avls_ve.speed_density.MAP_AXIS)),
            "sizey": str(rows),
            "userlevel": "2",
        },
    )
    ET.SubElement(
        table,
        "scaling",
        {
            "units": "VE fraction",
            "expression": "x",
            "to_byte": "x",
            "format": "0.000",
            "fineincrement": ".005",
            "coarseincrement": ".02",
        },
    )
    x_axis = ET.SubElement(
        table,
        "table",
        {
            "type": "X Axis",
            "name": "Manifold Pressure",
            "storagetype": "float",
            "endian": "little",
            "logparam": "E52",
        },
    )
    ET.SubElement(
        x_axis,
        "scaling",
        {
            "units": "mmHg absolute",
            "expression": "x",
            "to_byte": "x",
            "format": "0.0",
            "fineincrement": "1",
            "coarseincrement": "10",
        },
    )
    y_axis = ET.SubElement(
        table,
        "table",
        {
            "type": "Y Axis",
            "name": "Engine Speed",
            "storagetype": "float",
            "endian": "little",
            "logparam": "P8",
        },
    )
    ET.SubElement(
        y_axis,
        "scaling",
        {
            "units": "RPM",
            "expression": "x",
            "to_byte": "x",
            "format": "#",
            "fineincrement": "50",
            "coarseincrement": "100",
        },
    )
    if low:
        description = (
            "VE fraction used only while committed AVLS mode 0xFFFFCD86 is not "
            "3. Its RPM axis deliberately stops at the 3200 RPM high-lift engage "
            "threshold. High lift releases at 3000 RPM, so 3000-3200 is a real "
            "hysteresis overlap selected by committed state."
        )
    else:
        description = (
            "VE fraction used only while committed AVLS mode 0xFFFFCD86 is 3. "
            "Its RPM axis deliberately starts at the 3000 RPM high-lift release "
            "threshold and extends through 7500 RPM. The supplied values clone "
            "the original conservative VE surface and require log calibration."
        )
    set_description(table, description)


def add_ve_target(
    target: ET.Element, name: str, rows: int, data: int, rpm_axis: int
) -> None:
    table = ET.SubElement(
        target,
        "table",
        {
            "name": name,
            "storageaddress": f"0x{data:X}",
            "sizex": str(len(avls_ve.speed_density.MAP_AXIS)),
            "sizey": str(rows),
        },
    )
    ET.SubElement(
        table,
        "table",
        {"type": "X Axis", "storageaddress": f"0x{avls_ve.speed_density.MAP_AXIS_ADDR:X}"},
    )
    ET.SubElement(
        table,
        "table",
        {"type": "Y Axis", "storageaddress": f"0x{rpm_axis:X}"},
    )


def build_tree() -> ET.ElementTree:
    source = ET.parse(SOURCE).getroot()
    roms = source.findall("rom")
    if len(roms) != 2:
        raise SystemExit("unexpected source definition structure")
    parent, target = deepcopy(roms[0]), deepcopy(roms[1])
    remove_named(parent, {OLD_VE_NAME} | HIDDEN_AVLS_TABLES)
    remove_named(target, {OLD_VE_NAME} | HIDDEN_AVLS_TABLES)

    add_ve_template(parent, LOW_VE_NAME, len(avls_ve.LOW_RPM_AXIS), True)
    add_ve_template(parent, HIGH_VE_NAME, len(avls_ve.HIGH_RPM_AXIS), False)
    add_ve_target(
        target, LOW_VE_NAME, len(avls_ve.LOW_RPM_AXIS),
        avls_ve.LOW_VE_DATA_ADDR, avls_ve.LOW_RPM_AXIS_ADDR,
    )
    add_ve_target(
        target, HIGH_VE_NAME, len(avls_ve.HIGH_RPM_AXIS),
        avls_ve.HIGH_VE_DATA_ADDR, avls_ve.HIGH_RPM_AXIS_ADDR,
    )

    target.find("romid/xmlid").text = "D2WD610H_AVLS_DUAL_VE_ONLY"
    target.find("romid/author").text = "Renesas_SH0755_modding AVLS dual-VE patch"
    set_description(
        table_by_name(target, "AVLS High Cam Engage RPM"),
        "Predictable high-lift engagement threshold. Default 3200 RPM. The "
        "vehicle-speed request path is fixed unreachable in this patch; keep "
        "this value above the release threshold.",
    )
    set_description(
        table_by_name(target, "AVLS High Cam Release RPM"),
        "Predictable high-lift release threshold. Default 3000 RPM, providing "
        "200 RPM hysteresis. The two VE tables both cover the resulting overlap.",
    )

    root = ET.Element("roms")
    root.append(ET.Comment(" D2WD610H-only AVLS committed-state dual-VE definition. "))
    root.extend((parent, target))
    tree = ET.ElementTree(root)
    validate(root)
    return tree


def validate(root: ET.Element) -> None:
    parent, target = root.findall("rom")
    names_parent = [table.get("name") for table in parent.findall("table")]
    names_target = [table.get("name") for table in target.findall("table")]
    for names, label in ((names_parent, "parent"), (names_target, "target")):
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise SystemExit(f"duplicate {label} tables: {sorted(duplicates)}")
    forbidden = {OLD_VE_NAME} | HIDDEN_AVLS_TABLES
    if forbidden & (set(names_parent) | set(names_target)):
        raise SystemExit("obsolete single-VE or variable-switch tables survived")
    if target.findtext("romid/xmlid") != "D2WD610H_AVLS_DUAL_VE_ONLY":
        raise SystemExit("wrong XMLID")
    low = table_by_name(target, LOW_VE_NAME)
    high = table_by_name(target, HIGH_VE_NAME)
    for name in (LOW_VE_NAME, HIGH_VE_NAME):
        template = table_by_name(parent, name)
        if template.get("endian") != "little":
            raise SystemExit(f"wrong RomRaider float endianness for {name}")
        if any(axis.get("endian") != "little" for axis in template.findall("table")):
            raise SystemExit(f"wrong RomRaider axis endianness for {name}")
    if (low.get("storageaddress"), low.get("sizey")) != (
        f"0x{avls_ve.LOW_VE_DATA_ADDR:X}", str(len(avls_ve.LOW_RPM_AXIS))
    ):
        raise SystemExit("wrong low-lift VE definition")
    if (high.get("storageaddress"), high.get("sizey")) != (
        f"0x{avls_ve.HIGH_VE_DATA_ADDR:X}", str(len(avls_ve.HIGH_RPM_AXIS))
    ):
        raise SystemExit("wrong high-lift VE definition")


def main() -> None:
    tree = build_tree()
    ET.indent(tree, space=" ")
    tree.write(OUTPUT, encoding="utf-8", xml_declaration=True)
    serialized = ET.parse(OUTPUT).getroot()
    validate(serialized)
    print(f"Wrote {OUTPUT}")
    print(f"  low-lift VE  : 13x{len(avls_ve.LOW_RPM_AXIS)}, 0..3200 RPM")
    print(f"  high-lift VE : 13x{len(avls_ve.HIGH_RPM_AXIS)}, 3000..7500 RPM")
    print("  hidden       : obsolete vehicle-speed/oil-band AVLS switching controls")


if __name__ == "__main__":
    main()
