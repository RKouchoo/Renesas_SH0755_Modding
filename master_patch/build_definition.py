#!/usr/bin/env python3
"""Build the focused, self-contained RomRaider definition for master_patch.

The metric D2WD610H AVLS definition remains the only stock-definition source.
This generator removes stock MAF/O2/diagnostic material that is no longer part
of the master architecture, gives the live timing maps their Ghidra-verified
identities, and adds only the speed-density, boost, AVLS, and external-wideband
calibrations installed by build_master_patch.py.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "defs" / "D2WD610H_AVLS.xml"
SD_SOURCE = ROOT / "speed_density" / "D2WD610H_AVLS_speed_density_patch.xml"
BOOST_SOURCE = ROOT / "defs" / "D2WD610H_AVLS_boost_patch.xml"
OUTPUT = HERE / "D2WD610H_master_patch.xml"

SD_NAMES = (
    "Speed Density Global Airflow Multiplier",
    "Speed Density Engine Displacement",
    "Speed Density Maximum Airflow",
    "Speed Density MAP Valid Range",
    "Speed Density RPM Valid Range",
    "Speed Density IAT Valid Range",
    "Speed Density VE (MAP x RPM)",
    "Speed Density IAT Density Correction",
)

BOOST_NAMES = (
    "Boost Control Patch Enable",
    "Boost Wastegate Duty (RPM)",
    "Boost Target (RPM)",
    "Boost Kp (proportional gain)",
    "Boost Max Duty Ratio",
    "Boost Overboost Cut (Duty, soft)",
    "Boost Minimum Throttle",
    "Boost Overboost Fuel Cut (hard)",
)

WIDEBAND_NAMES = (
    "External Wideband Lambda Transfer",
    "External Wideband Valid Voltage Range",
)

AVLS_NAMES = (
    "AVLS Switchover Load Threshold 1",
    "AVLS Switchover Load Threshold 2",
    "AVLS High Cam Engage RPM",
    "AVLS High Cam Release RPM",
    "AVLS Switchover Load Hysteresis A",
    "AVLS Switchover Load Hysteresis B",
    "AVLS Actuation Minimum RPM",
)

TIMING_RENAMES = {
    "Base Timing A": "Base Timing - Normal Cam (AVCS Tracking Ratio 1.0)",
    "Base Timing C": "Base Timing - AVLS High Cam (AVCS Tracking Ratio 1.0)",
    "Base Timing D": "Base Timing - Normal Cam (AVCS Tracking Ratio 0.0)",
    "Base Timing F": "Base Timing - AVLS High Cam (AVCS Tracking Ratio 0.0)",
    "Knock Correction Advance Max A": "Knock Correction Advance Max - Normal Cam",
    "Knock Correction Advance Max B": "Knock Correction Advance Max - AVLS High Cam",
}

AVCS_RENAMES = {
    "Intake Cam Advance Angle A (AVCS)": "Intake AVCS Target - AVLS Low Cam",
    "Intake Cam Advance Angle B (AVCS)": "Intake AVCS Target - AVLS High Cam",
}

MAP_RENAMES = {
    "Manifold Pressure Sensor Scaling": "Omni Power MAP-SUP-3BR Scaling",
    "Manifold Pressure Sensor Limits (CEL)": "Omni Power MAP-SUP-3BR Input Limits (CEL)",
    "Manifold Pressure Sensor CEL Delays": "Omni Power MAP-SUP-3BR CEL Delays",
}

DROP_NAMES = {
    # The master is permanently MAFless and the former MAF signal is wideband.
    "MAF Limit (Maximum) ",
    "MAF Sensor Scaling",
    "MAF Compensation (IAT)",
    # Both stock front A/F signal paths are replaced by synthetic lambda.
    "Front Oxygen Sensor #1 Scaling",
    "Front Oxygen Sensor #2 Scaling",
    "Front Oxygen Sensor Rich Limit",
    "Front Oxygen Sensor Compensation (Atm. Pressure)",
    # Ghidra proves these two base-timing paths are unreachable in stock:
    # the B/E selector callback at 0x27088 always returns zero.
    "Base Timing B",
    "Base Timing E",
    # Not an engine-tuning control and deliberately excluded from this focus.
    "Fuel Temp Sensor Scaling",
    "Force Pass Readiness Monitors",
}

DROP_CATEGORIES = {"Diagnostic Trouble Codes", "OBD-II"}

TIMING_DESCRIPTIONS = {
    "Base Timing - Normal Cam (AVCS Tracking Ratio 1.0)": (
        "Normal/AVLS-low-cam base timing for an intake-AVCS tracking ratio of "
        "1.0. The stock code calculates selected timing = this table * k + the "
        "paired 0.0 table * (1-k). Live Ghidra shows that k at 0xFFFFC17C is "
        "the clamped ratio of summed measured left/right intake-cam advance to "
        "summed commanded advance; stock status logic can force it to 1.0. "
        "This is AVCS phasing compensation, not an IAM endpoint. Tune it for "
        "the cam angle actually achieved; there is no rule that it must be "
        "more advanced than the paired 0.0 surface. Verified at "
        "ign_avcs_tracking_blend_factor_update @ 0x28354, "
        "ign_base_timing_map_blend @ 0x28418, and ign_base_timing_select @ "
        "0x284B8."
    ),
    "Base Timing - Normal Cam (AVCS Tracking Ratio 0.0)": (
        "Normal/AVLS-low-cam base timing for an intake-AVCS tracking ratio of "
        "0.0. The stock code calculates selected timing = the paired 1.0 table "
        "* k + this table * (1-k). A near-zero summed command produces k=0; "
        "partial cam tracking interpolates between the surfaces. This is not a "
        "knock/IAM fallback and is not required to be more retarded than the "
        "1.0 surface. Tune the pair to match actual intake-cam phasing. Identity "
        "and formula were verified against canonical stock D2WD610H in live "
        "Ghidra."
    ),
    "Base Timing - AVLS High Cam (AVCS Tracking Ratio 1.0)": (
        "AVLS-high-cam base timing for an intake-AVCS tracking ratio of 1.0. It "
        "is selected only in the verified AVLS high-cam state. The stock code "
        "calculates selected timing = this table * k + the paired 0.0 table * "
        "(1-k), where k compares measured with commanded intake-cam advance. "
        "This is AVCS phasing compensation, not an IAM endpoint; tune the pair "
        "for the cam angle actually achieved without assuming a fixed timing "
        "ordering. The cam selection and blend were verified in live Ghidra at "
        "0x28354, 0x28418, and 0x284B8."
    ),
    "Base Timing - AVLS High Cam (AVCS Tracking Ratio 0.0)": (
        "AVLS-high-cam base timing for an intake-AVCS tracking ratio of 0.0. It "
        "is selected only in the verified AVLS high-cam state and is blended "
        "with the paired 1.0 surface as selected timing = 1.0 table * k + this "
        "table * (1-k). A near-zero summed AVCS command produces k=0. This is "
        "not a knock/IAM fallback and is not required to be more retarded than "
        "the 1.0 surface. The cam selection and blend were verified in live "
        "Ghidra at 0x28354, 0x28418, and 0x284B8."
    ),
    "Knock Correction Advance Max - Normal Cam": (
        "Normal-cam maximum positive knock-correction advance. Ghidra-verified "
        "knock_correction_advance_max_select @ 0x3EB68 selects this surface "
        "outside the AVLS-high-cam state."
    ),
    "Knock Correction Advance Max - AVLS High Cam": (
        "AVLS-high-cam maximum positive knock-correction advance. "
        "Ghidra-verified knock_correction_advance_max_select @ 0x3EB68 selects "
        "this surface in the same high-cam state used by the timing selector."
    ),
}

AVCS_DESCRIPTIONS = {
    "Intake AVCS Target - AVLS Low Cam": (
        "Intake-cam advance target, in degrees, selected while committed AVLS "
        "cam mode 0xFFFFCD86 is 1 (low lift). Live Ghidra at "
        "intake_avcs_target_by_avls_mode_update @ 0x353B0 selects descriptor "
        "0x60C34 and data 0x7C5B0 in this state. Legacy table A is an AVLS-mode "
        "map, not a left/right-bank map, and it is selected rather than blended "
        "with the high-cam target. The load axis ends at 2.00 g/rev, so the "
        "stock lookup uses its last column above that breakpoint."
    ),
    "Intake AVCS Target - AVLS High Cam": (
        "Intake-cam advance target, in degrees, selected while committed AVLS "
        "cam mode 0xFFFFCD86 is 3 (high lift). Live Ghidra at "
        "intake_avcs_target_by_avls_mode_update @ 0x353B0 selects descriptor "
        "0x60C50 and data 0x7C764 in this state. Legacy table B is an AVLS-mode "
        "map, not a left/right-bank map, and it is selected rather than blended "
        "with the low-cam target. The load axis ends at 2.00 g/rev, so the stock "
        "lookup uses its last column above that breakpoint."
    ),
}

BOOST_DESCRIPTIONS = {
    "Boost Control Patch Enable": (
        "Exact 01 enables the EVAP-output EBCS controller and added hard MAP "
        "fuel cut. Any other value forces zero EBCS duty and runs only the "
        "stock RPM limiter. This does not restore the removed MAF/O2 logic or "
        "the stock MAP scaling. The master prerequisite guard still forces "
        "zero duty unless the AEM input is ready, MAP/RPM/IAT are inside their "
        "speed-density validity windows, RPM is at least the first shared "
        "boost-axis breakpoint, and modeled airflow is not the 500 g/s fault "
        "sentinel."
    ),
    "Boost Wastegate Duty (RPM)": (
        "Feed-forward EBCS duty versus RPM. The master commissioning image is "
        "zero at every breakpoint, so the 5 psi mechanical spring alone sets "
        "boost. Do not add duty until plumbing/polarity, spring boost, lambda, "
        "and both overboost actions have been physically proven."
    ),
    "Boost Target (RPM)": (
        "Controller target stored in native mmHg absolute and displayed as psi "
        "relative to 760 mmHg. The commissioning curve rises to 5.0 psi. This "
        "target alone cannot raise boost while Kp, feed-forward duty, and the "
        "maximum-duty ratio remain zero. The first shared RPM-axis breakpoint "
        "also acts as the minimum electronic-control speed."
    ),
    "Boost Kp (proportional gain)": (
        "Proportional EBCS gain. Default is 0.0 for spring-only commissioning. "
        "There is no integral term. Tune only after the zero-duty system and "
        "overboost protections have been proven on the installed hardware."
    ),
    "Boost Max Duty Ratio": (
        "Final EBCS duty clamp, where 1.0 is 100 percent. Default is 0.0, which "
        "independently guarantees spring-only boost even if another duty or "
        "gain table is edited."
    ),
    "Boost Overboost Cut (Duty, soft)": (
        "Soft MAP limit. Above the default 5.5 psi relative-to-760-mmHg value, "
        "the controller commands zero EBCS duty. Keep below the hard cut and "
        "bench/dyno-prove the transition."
    ),
    "Boost Minimum Throttle": (
        "Driver-demand gate. At or below this processed-throttle value the "
        "controller commands zero EBCS duty. Default native value is 30.0."
    ),
    "Boost Overboost Fuel Cut (hard)": (
        "Last-resort MAP fuel cut through the verified rev-limiter flag path. "
        "Default is 6.5 psi relative to 760 mmHg. It has no hysteresis and must "
        "be safely proven before positive-load tuning."
    ),
}


def roms_from(path: Path) -> tuple[ET.Element, ET.Element]:
    root = ET.parse(path).getroot()
    roms = root.findall("rom")
    if len(roms) != 2 or roms[0].get("base") is not None or roms[1].get("base") != "32BITBASE":
        raise SystemExit(f"unexpected two-ROM definition structure in {path}")
    return roms[0], roms[1]


def table_by_name(rom: ET.Element, name: str) -> ET.Element:
    matches = [table for table in rom.findall("table") if table.get("name") == name]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one table {name!r}, found {len(matches)}")
    return matches[0]


def set_description(table: ET.Element, text: str) -> None:
    descriptions = table.findall("description")
    for old in descriptions:
        table.remove(old)
    ET.SubElement(table, "description").text = text


def should_drop(table: ET.Element) -> bool:
    return table.get("name") in DROP_NAMES or table.get("category") in DROP_CATEGORIES


def prune_and_rename(rom: ET.Element, inherited_drop_names: set[str] | None = None) -> None:
    inherited_drop_names = inherited_drop_names or set()
    for table in list(rom.findall("table")):
        if should_drop(table) or table.get("name") in inherited_drop_names:
            rom.remove(table)
            continue
        original = table.get("name")
        replacement = TIMING_RENAMES.get(
            original, AVCS_RENAMES.get(original, MAP_RENAMES.get(original))
        )
        if replacement:
            table.set("name", replacement)
            if replacement in TIMING_DESCRIPTIONS:
                set_description(table, TIMING_DESCRIPTIONS[replacement])
            elif replacement in AVCS_DESCRIPTIONS:
                set_description(table, AVCS_DESCRIPTIONS[replacement])


def add_wideband_templates(parent: ET.Element, target: ET.Element) -> None:
    transfer = ET.SubElement(
        parent,
        "table",
        {
            "type": "2D",
            "name": WIDEBAND_NAMES[0],
            "category": "External Wideband Input (patch)",
            "storagetype": "float",
            "endian": "big",
            "sizey": "2",
            "userlevel": "3",
        },
    )
    ET.SubElement(
        transfer,
        "scaling",
        {
            "units": "lambda transfer",
            "expression": "x",
            "to_byte": "x",
            "format": "0.000000",
            "fineincrement": ".0001",
            "coarseincrement": ".001",
        },
    )
    axis = ET.SubElement(
        transfer, "table", {"type": "Static Y Axis", "name": "Transfer", "sizey": "2"}
    )
    ET.SubElement(axis, "data").text = "Slope (lambda per volt)"
    ET.SubElement(axis, "data").text = "Offset (lambda)"
    set_description(
        transfer,
        "Former-MAF-input conversion: lambda = slope * input volts + offset. "
        "Defaults 0.1621 and 0.4990 match the AEM X-Series 30-0300 analog "
        "output. A different controller requires both its verified transfer "
        "and valid-voltage window; do not enter AFR-domain coefficients here.",
    )

    valid_range = ET.SubElement(
        parent,
        "table",
        {
            "type": "2D",
            "name": WIDEBAND_NAMES[1],
            "category": "External Wideband Input (patch)",
            "storagetype": "float",
            "endian": "big",
            "sizey": "2",
            "userlevel": "3",
        },
    )
    ET.SubElement(
        valid_range,
        "scaling",
        {
            "units": "Volts",
            "expression": "x",
            "to_byte": "x",
            "format": "0.00",
            "fineincrement": ".01",
            "coarseincrement": ".10",
        },
    )
    axis = ET.SubElement(
        valid_range, "table", {"type": "Static Y Axis", "name": "Gate", "sizey": "2"}
    )
    ET.SubElement(axis, "data").text = "Minimum valid voltage"
    ET.SubElement(axis, "data").text = "Maximum valid voltage"
    set_description(
        valid_range,
        "Inclusive input-validity window. Default is 0.50 to 4.50 V. Outside "
        "this window the ECU marks the synthetic front feedback unavailable, "
        "publishes a zero logger sentinel, inhibits closed-loop feedback, and "
        "forces EBCS duty to zero. Valid wideband voltage is necessary but not "
        "sufficient for duty; the separate MAP/RPM/IAT, minimum-RPM, and SD "
        "fault-sentinel prerequisites must also pass.",
    )

    ET.SubElement(target, "table", {"name": WIDEBAND_NAMES[0], "storageaddress": "0x7E404"})
    ET.SubElement(target, "table", {"name": WIDEBAND_NAMES[1], "storageaddress": "0x7E40C"})


def update_patch_descriptions(target: ET.Element) -> None:
    for name, description in BOOST_DESCRIPTIONS.items():
        set_description(table_by_name(target, name), description)


def validate(root: ET.Element) -> None:
    roms = root.findall("rom")
    if len(roms) != 2:
        raise SystemExit("master definition must contain exactly two ROM blocks")
    parent, target = roms
    xmlid = target.findtext("romid/xmlid")
    if xmlid != "D2WD610H_MASTER_PATCH":
        raise SystemExit(f"unexpected target XMLID {xmlid!r}")

    for label, rom in (("parent", parent), ("target", target)):
        names = [table.get("name") for table in rom.findall("table")]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise SystemExit(f"duplicate {label} table names: {duplicates}")

    parent_names = {table.get("name") for table in parent.findall("table")}
    for table in target.findall("table"):
        if table.get("type") is None and table.get("name") not in parent_names:
            raise SystemExit(f"target table has no parent template: {table.get('name')!r}")

    target_names = {table.get("name") for table in target.findall("table")}
    expected_custom = set(SD_NAMES + BOOST_NAMES + WIDEBAND_NAMES + AVLS_NAMES)
    missing = sorted(expected_custom - target_names)
    if missing:
        raise SystemExit(f"master definition is missing custom tables: {missing}")

    forbidden = (
        DROP_NAMES
        | set(TIMING_RENAMES)
        | set(AVCS_RENAMES)
        | {"Base Timing B", "Base Timing E"}
    )
    present_forbidden = sorted(forbidden & (parent_names | target_names))
    if present_forbidden:
        raise SystemExit(f"obsolete tables survived master pruning: {present_forbidden}")
    if any(table.get("category") in DROP_CATEGORIES for table in parent.findall("table")):
        raise SystemExit("diagnostic/readiness category survived parent pruning")

    expected_addresses = {
        "Base Timing - Normal Cam (AVCS Tracking Ratio 1.0)": "0x78AA0",
        "Base Timing - AVLS High Cam (AVCS Tracking Ratio 1.0)": "0x78CD0",
        "Base Timing - Normal Cam (AVCS Tracking Ratio 0.0)": "0x78E34",
        "Base Timing - AVLS High Cam (AVCS Tracking Ratio 0.0)": "0x79064",
        "Knock Correction Advance Max - Normal Cam": "0x7924C",
        "Knock Correction Advance Max - AVLS High Cam": "0x793AC",
        "Intake AVCS Target - AVLS Low Cam": "0x7C5B0",
        "Intake AVCS Target - AVLS High Cam": "0x7C764",
        "Omni Power MAP-SUP-3BR Scaling": "0x72810",
        "External Wideband Lambda Transfer": "0x7E404",
        "External Wideband Valid Voltage Range": "0x7E40C",
    }
    for name, address in expected_addresses.items():
        if table_by_name(target, name).get("storageaddress") != address:
            raise SystemExit(f"wrong address for {name}")


def build_tree() -> ET.ElementTree:
    source_parent, source_target = roms_from(SOURCE)
    parent = deepcopy(source_parent)
    target = deepcopy(source_target)
    inherited_drop_names = {
        table.get("name") for table in source_parent.findall("table") if should_drop(table)
    }
    prune_and_rename(parent, inherited_drop_names)
    prune_and_rename(target, inherited_drop_names)

    target.find("romid/xmlid").text = "D2WD610H_MASTER_PATCH"
    target.find("romid/author").text = "Renesas_SH0755_modding master_patch"

    sd_parent, sd_target = roms_from(SD_SOURCE)
    for name in SD_NAMES:
        parent.append(deepcopy(table_by_name(sd_parent, name)))
        target.append(deepcopy(table_by_name(sd_target, name)))

    _, boost_target = roms_from(BOOST_SOURCE)
    for name in BOOST_NAMES:
        target.append(deepcopy(table_by_name(boost_target, name)))
    update_patch_descriptions(target)
    add_wideband_templates(parent, target)

    root = ET.Element("roms")
    root.append(
        ET.Comment(
            " D2WD610H master-only metric definition; generated by "
            "master_patch/build_definition.py from the project AVLS source. "
        )
    )
    root.append(parent)
    root.append(target)
    validate(root)
    return ET.ElementTree(root)


def main() -> None:
    tree = build_tree()
    ET.indent(tree, space=" ")
    tree.write(OUTPUT, encoding="utf-8", xml_declaration=True)
    # Parse the serialized artifact too, so a writer/encoding regression fails.
    serialized = ET.parse(OUTPUT).getroot()
    validate(serialized)
    parent, target = serialized.findall("rom")
    print(f"Wrote {OUTPUT}")
    print(f"  inherited tuning templates : {len(parent.findall('table'))}")
    print(f"  D2WD610H target tables      : {len(target.findall('table'))}")
    print("  timing paths                : normal/high cam x AVCS tracking ratio 1.0/0.0; dormant pair omitted")
    print("  removed                     : stock MAF/O2 scalings, DTC/readiness switches")


if __name__ == "__main__":
    main()
