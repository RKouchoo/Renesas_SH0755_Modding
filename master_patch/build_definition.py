#!/usr/bin/env python3
"""Build the focused, self-contained RomRaider definition for master_patch.

The metric D2WD610H AVLS definition remains the only stock-definition source.
This generator removes stock MAF/O2/diagnostic material that is no longer part
of the master architecture, gives the live timing maps their Ghidra-verified
identities, groups the flat RomRaider menu by tuning workflow, and adds only the
speed-density, boost, AVLS, external-wideband, pressure-open-loop, and lean-cut
calibrations installed by build_master_patch.py.
The generated target also exposes the integrated default-OFF rotational-idle
switch, gates, limits, and six cylinder offsets.
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
    "Speed Density VE - AVLS Low Lift",
    "Speed Density VE - AVLS High Lift",
    "Speed Density IAT Density Correction",
)

BOOST_NAMES = (
    "Electronic Boost Control Enable",
    "Overboost Fuel Cut Enable",
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

FUELING_SAFETY_NAMES = (
    "Pressure-Based Open Loop Failsafe Enable",
    "Pressure-Based Open Loop Margin",
    "Lean Fuel Cut Enable",
    "Lean Fuel Cut Arm Pressure",
    "Lean Fuel Cut Reset Pressure",
    "Lean Fuel Cut AFR Threshold",
    "Lean Fuel Cut Sensor Transport Delay",
    "Lean Fuel Cut Confirmation Count",
)

FUEL_PUMP_NAMES = (
    "Fuel Pump Low-Speed Command",
    "Fuel Pump Medium-Speed Command",
)

ROTATIONAL_IDLE_NAMES = (
    "Rotational Idle Enable",
    "Rotational Idle Minimum Coolant Temperature",
    "Rotational Idle Maximum Coolant Temperature",
    "Rotational Idle Minimum Engine Speed",
    "Rotational Idle Maximum Engine Speed",
    "Rotational Idle Maximum Throttle",
    "Rotational Idle Maximum Vehicle Speed",
    "Rotational Idle Minimum Manifold Pressure",
    "Rotational Idle Maximum Manifold Pressure",
    "Rotational Idle Maximum Retard",
    "Rotational Idle Minimum Final Timing",
    "Rotational Idle Cylinder Timing Offsets",
)

AVLS_NAMES = (
    "AVLS High Cam Engage RPM",
    "AVLS High Cam Release RPM",
)

# RomRaider presents categories as a flat, alphabetically sorted list.  Keep a
# numbered tuning workflow here so inherited stock tables and installed patch
# tables appear together by purpose instead of as unrelated stock/patch groups.
CAT_AIR_MAP = "01.1 - Air Model - MAP Sensor"
CAT_AIR_IAT = "01.2 - Air Model - IAT Sensor"
CAT_AIR_SD = "01.3 - Air Model - Speed Density"
CAT_AIR_VE = "01.4 - Air Model - VE Tables"
CAT_AIR_LOAD = "01.5 - Air Model - Load Calculation"
CAT_FUEL_INJECTORS = "02.1 - Fueling - Injectors"
CAT_FUEL_OL = "02.2 - Fueling - Primary Open Loop"
CAT_FUEL_CL = "02.3 - Fueling - Closed Loop"
CAT_FUEL_TRANSITION = "02.4 - Fueling - CL/OL Transition"
CAT_FUEL_CRANKING = "02.5 - Fueling - Cranking"
CAT_FUEL_TIPIN = "02.6 - Fueling - Tip-in Enrichment"
CAT_FUEL_LEARNING = "02.7 - Fueling - Correction and Learning"
CAT_FUEL_PUMP = "02.8 - Fueling - Fuel Pump Control"
CAT_WIDEBAND = "03 - Wideband - Input Calibration"
CAT_IGN_BASE = "04.1 - Ignition - Base Timing"
CAT_IGN_COMP = "04.2 - Ignition - Compensations"
CAT_IGN_KNOCK = "04.3 - Ignition - Knock Control"
CAT_CAM_AVLS = "05.1 - Cam Control - AVLS Switching"
CAT_CAM_AVCS = "05.2 - Cam Control - Intake AVCS Targets"
CAT_BOOST_CONTROL = "06.1 - Boost - Electronic Control"
CAT_BOOST_PROTECTION = "06.2 - Boost - Overboost Protection"
CAT_PROTECTION_FUEL = "07.1 - Protection - Open Loop and Lean Cut"
CAT_PROTECTION_RPM = "07.2 - Protection - RPM Limit"
CAT_THROTTLE = "08 - Throttle - Drive-by-Wire"
CAT_IDLE_TARGET = "09.1 - Idle - Speed Targets"
CAT_IDLE_IGNITION = "09.2 - Idle - Ignition Timing"
CAT_IDLE_ROTATIONAL = "09.3 - Idle - Rotational Idle"
CAT_SENSOR_TEMPERATURE = "10.1 - Sensors - Temperature Scaling"
CAT_COOLING_FANS = "10.2 - Cooling - Radiator Fans"
CAT_CHECKSUM = "99 - ROM - Checksum"

CATEGORY_ORDER = (
    CAT_AIR_MAP,
    CAT_AIR_IAT,
    CAT_AIR_SD,
    CAT_AIR_VE,
    CAT_AIR_LOAD,
    CAT_FUEL_INJECTORS,
    CAT_FUEL_OL,
    CAT_FUEL_CL,
    CAT_FUEL_TRANSITION,
    CAT_FUEL_CRANKING,
    CAT_FUEL_TIPIN,
    CAT_FUEL_LEARNING,
    CAT_FUEL_PUMP,
    CAT_WIDEBAND,
    CAT_IGN_BASE,
    CAT_IGN_COMP,
    CAT_IGN_KNOCK,
    CAT_CAM_AVLS,
    CAT_CAM_AVCS,
    CAT_BOOST_CONTROL,
    CAT_BOOST_PROTECTION,
    CAT_PROTECTION_FUEL,
    CAT_PROTECTION_RPM,
    CAT_THROTTLE,
    CAT_IDLE_TARGET,
    CAT_IDLE_IGNITION,
    CAT_IDLE_ROTATIONAL,
    CAT_SENSOR_TEMPERATURE,
    CAT_COOLING_FANS,
    CAT_CHECKSUM,
)

CATEGORY_RENAMES = {
    "Manifold Pressure Sensor": CAT_AIR_MAP,
    "Mass Airflow / Engine Load": CAT_AIR_LOAD,
    "Speed Density (patch)": CAT_AIR_SD,
    "Speed Density - AVLS VE (patch)": CAT_AIR_VE,
    "Fueling - Injectors": CAT_FUEL_INJECTORS,
    "Fueling - Primary Open Loop": CAT_FUEL_OL,
    "Fueling - Closed Loop": CAT_FUEL_CL,
    "Fueling - CL/OL Transition": CAT_FUEL_TRANSITION,
    "Fueling - Cranking": CAT_FUEL_CRANKING,
    "Fueling - Tip-in Enrichment": CAT_FUEL_TIPIN,
    "Fueling - AF Correction / Learning": CAT_FUEL_LEARNING,
    "External Wideband Input (patch)": CAT_WIDEBAND,
    "Ignition Timing - Advance": CAT_IGN_BASE,
    "Ignition Timing - Compensation": CAT_IGN_COMP,
    "Ignition Timing - Knock Control": CAT_IGN_KNOCK,
    "AVLS": CAT_CAM_AVLS,
    "Variable Valve Timing (AVCS)": CAT_CAM_AVCS,
    "Boost Control (patch)": CAT_BOOST_CONTROL,
    "Fueling - Pressure/Lean Safety (patch)": CAT_PROTECTION_FUEL,
    "Miscellaneous - Limits": CAT_PROTECTION_RPM,
    "Drive-by-Wire Throttle (DBW)": CAT_THROTTLE,
    "Idle Control": CAT_IDLE_TARGET,
    "Rotational Idle (master patch)": CAT_IDLE_ROTATIONAL,
    "Miscellaneous - Sensor Scalings": CAT_SENSOR_TEMPERATURE,
    "Miscellaneous - Thresholds": CAT_COOLING_FANS,
    "Checksum Fix": CAT_CHECKSUM,
}

TABLE_CATEGORY_OVERRIDES = {
    "Intake Temp Sensor Scaling": CAT_AIR_IAT,
    "Speed Density IAT Density Correction": CAT_AIR_IAT,
    "Knock Correction Advance Max - Normal Cam": CAT_IGN_KNOCK,
    "Knock Correction Advance Max - AVLS High Cam": CAT_IGN_KNOCK,
    "Base Timing Idle": CAT_IDLE_IGNITION,
    "Base Timing Idle (Below Speed Threshold) ": CAT_IDLE_IGNITION,
    "Base Timing Idle (Above Speed Threshold)": CAT_IDLE_IGNITION,
    "Base Timing Idle Vehicle Speed Threshold": CAT_IDLE_IGNITION,
    "Overboost Fuel Cut Enable": CAT_BOOST_PROTECTION,
    "Boost Overboost Cut (Duty, soft)": CAT_BOOST_PROTECTION,
    "Boost Overboost Fuel Cut (hard)": CAT_BOOST_PROTECTION,
}

HIDDEN_AVLS_NAMES = {
    "AVLS Vehicle Speed Threshold (Normal Oil Temperature)",
    "AVLS Vehicle Speed Threshold (High Oil Temperature)",
    "AVLS Vehicle Speed Hysteresis (Normal Oil Temperature)",
    "AVLS Vehicle Speed Hysteresis (High Oil Temperature)",
    "AVLS Oil Temperature Selector Thresholds",
    "AVLS Actuation Minimum RPM",
}

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

IAT_SENSOR_DESCRIPTION = (
    "Provisional Haltech HT-010206 intake-air-temperature transfer for the "
    "retained B3-4/B136-13 signal and B3-5/B136-35 sensor ground. The 30-point "
    "voltage axis converts Haltech's published 1.00-kohm/5-V calibration to an "
    "assumed 2.49-kohm ECU pull-up. Points below -10 C are extrapolated. Treat "
    "this as a commissioning base reference: verify the ECU pull-up on the "
    "installed circuit and compare logged temperature against a trusted "
    "reference before tuning VE or entering boost. This table converts sensor "
    "voltage to degrees C; the separate Speed Density IAT Density Correction "
    "table applies the air-density multiplier."
)

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
} | HIDDEN_AVLS_NAMES

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
        "with the high-cam target. The master load axis is resampled through "
        "the stock 2.00 g/rev range and extended to 4.00 g/rev; higher-load "
        "columns retain the stock final-column target as a safe starting point."
    ),
    "Intake AVCS Target - AVLS High Cam": (
        "Intake-cam advance target, in degrees, selected while committed AVLS "
        "cam mode 0xFFFFCD86 is 3 (high lift). Live Ghidra at "
        "intake_avcs_target_by_avls_mode_update @ 0x353B0 selects descriptor "
        "0x60C50 and data 0x7C764 in this state. Legacy table B is an AVLS-mode "
        "map, not a left/right-bank map, and it is selected rather than blended "
        "with the low-cam target. The master load axis is resampled through "
        "the stock 2.00 g/rev range and extended to 4.00 g/rev; higher-load "
        "columns retain the stock final-column target as a safe starting point."
    ),
}

PREDICTABLE_AVLS_DESCRIPTIONS = {
    "AVLS High Cam Engage RPM": (
        "Predictable committed-state high-lift engagement threshold. Master "
        "defaults to 3200 RPM. The former vehicle-speed/oil-band request tables "
        "are fixed unreachable and omitted; keep engage above release."
    ),
    "AVLS High Cam Release RPM": (
        "Predictable high-lift release threshold. Master defaults to 3000 RPM, "
        "creating a 200 RPM hysteresis band. Low- and high-lift VE tables both "
        "cover this 3000-3200 RPM committed-state overlap."
    ),
}

BOOST_DESCRIPTIONS = {
    "Electronic Boost Control Enable": (
        "Exact 01 permits the EVAP-output EBCS controller to command duty. "
        "Default 00 forces zero EBCS duty for direct wastegate-spring control "
        "without disabling the independent hard overboost cut. This does not "
        "restore the removed MAF/O2 logic or stock MAP scaling. The master "
        "prerequisite guard still forces "
        "zero duty unless the external-wideband input is ready, MAP/RPM/IAT "
        "are inside their speed-density validity windows, RPM is at least the first shared "
        "boost-axis breakpoint, and modeled airflow is not the 500 g/s fault "
        "sentinel."
    ),
    "Overboost Fuel Cut Enable": (
        "Exact 01 independently enables the added hard MAP fuel cut through "
        "the verified stock rev-limiter flag path. Default is ON even while "
        "electronic boost control is OFF. Any other value retains the stock "
        "RPM limiter but bypasses only the added MAP cut. This is a last-resort "
        "software protection and cannot replace correct wastegate plumbing."
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
            "category": CAT_WIDEBAND,
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
        "Defaults 2/14.64 (0.136612...) and 10/14.64 (0.683060...) match the "
        "supplied seller-labelled AEM 50-4110 P0/P1 table: gasoline AFR = "
        "2*V + 10. P2/P3 are incompatible. Do not enter AFR-domain "
        "coefficients here.",
    )

    valid_range = ET.SubElement(
        parent,
        "table",
        {
            "type": "2D",
            "name": WIDEBAND_NAMES[1],
            "category": CAT_WIDEBAND,
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
        "Inclusive operating-plausibility window. Default 0.50 to 4.50 V "
        "corresponds to 11.00 to 19.00 gasoline AFR on the supplied P0/P1 "
        "curve. Outside it the ECU publishes a zero logger sentinel, inhibits "
        "closed-loop feedback, and forces EBCS duty to zero. In-range voltage "
        "does not prove controller or sensor health; a warm-up/disconnected "
        "output may remain in range. MAP/RPM/IAT, minimum-RPM, and SD-result "
        "prerequisites must also pass.",
    )

    ET.SubElement(target, "table", {"name": WIDEBAND_NAMES[0], "storageaddress": "0x7E404"})
    ET.SubElement(target, "table", {"name": WIDEBAND_NAMES[1], "storageaddress": "0x7E40C"})


def add_scalar_template(
    parent: ET.Element,
    target: ET.Element,
    name: str,
    address: str,
    storagetype: str,
    units: str,
    expression: str,
    to_byte: str,
    axis_label: str,
    description: str,
    fmt: str = "0.00",
    fine: str = ".01",
    coarse: str = ".10",
) -> None:
    table = ET.SubElement(
        parent,
        "table",
        {
            "type": "2D",
            "name": name,
            "category": CAT_PROTECTION_FUEL,
            "storagetype": storagetype,
            "endian": "big",
            "sizey": "1",
            "userlevel": "3",
        },
    )
    ET.SubElement(
        table,
        "scaling",
        {
            "units": units,
            "expression": expression,
            "to_byte": to_byte,
            "format": fmt,
            "fineincrement": fine,
            "coarseincrement": coarse,
        },
    )
    axis = ET.SubElement(
        table, "table", {"type": "Static Y Axis", "name": "Setting", "sizey": "1"}
    )
    ET.SubElement(axis, "data").text = axis_label
    set_description(table, description)
    ET.SubElement(target, "table", {"name": name, "storageaddress": address})


def add_rotational_idle_tables(target: ET.Element) -> None:
    category = CAT_IDLE_ROTATIONAL
    switch = ET.SubElement(
        target,
        "table",
        {
            "type": "Switch",
            "name": ROTATIONAL_IDLE_NAMES[0],
            "category": category,
            "sizey": "1",
            "userlevel": "1",
            "storageaddress": "0x7DB40",
        },
    )
    set_description(
        switch,
        "Exact 01 enables the bounded timing post-processor; 00 or any other "
        "value leaves all six stock final ignition angles unchanged. Master "
        "defaults OFF. Enable only after confirming a stable warm idle and log "
        "final ignition timing while commissioning.",
    )
    ET.SubElement(switch, "state", {"name": "on", "data": "01"})
    ET.SubElement(switch, "state", {"name": "off", "data": "00"})

    scalar_specs = (
        (ROTATIONAL_IDLE_NAMES[1], "0x7DB44", "Coolant Temp (Degrees C)", "x", "x", "0.0", "Inclusive warm-idle lower gate; default 80 C."),
        (ROTATIONAL_IDLE_NAMES[2], "0x7DB48", "Coolant Temp (Degrees C)", "x", "x", "0.0", "Inclusive over-temperature exit; default 105 C."),
        (ROTATIONAL_IDLE_NAMES[3], "0x7DB4C", "RPM", "x", "x", "#", "Inclusive idle-speed lower gate; default 600 RPM."),
        (ROTATIONAL_IDLE_NAMES[4], "0x7DB50", "RPM", "x", "x", "#", "Inclusive idle-speed upper gate; default 1050 RPM."),
        (ROTATIONAL_IDLE_NAMES[5], "0x7DB54", "Throttle Plate Opening Angle (%)", "x/.84", "x*.84", "0.0", "Inclusive processed-throttle gate; default native 1.68 displays as 2.0 percent."),
        (ROTATIONAL_IDLE_NAMES[6], "0x7DB58", "km/h", "x", "x", "0.0", "Inclusive stationary-vehicle gate; default 1.0 km/h."),
        (ROTATIONAL_IDLE_NAMES[7], "0x7DB5C", "kPa absolute", "x*.1333223684", "x/.1333223684", "0.0", "Inclusive MAP lower gate; default 150 mmHg or about 20.0 kPa absolute."),
        (ROTATIONAL_IDLE_NAMES[8], "0x7DB60", "kPa absolute", "x*.1333223684", "x/.1333223684", "0.0", "Inclusive high-vacuum upper gate; default 550 mmHg or about 73.3 kPa absolute."),
        (ROTATIONAL_IDLE_NAMES[9], "0x7DB64", "degrees", "x", "x", "0.0", "Maximum retard magnitude; default 8 degrees. Invalid or non-positive values apply no offset."),
        (ROTATIONAL_IDLE_NAMES[10], "0x7DB68", "degrees BTDC", "x", "x", "0.0", "Post-retard timing floor; default 5 degrees BTDC. The stock-angle ceiling prevents this floor adding advance."),
    )
    for name, address, units, expression, to_byte, fmt, description in scalar_specs:
        table = ET.SubElement(
            target,
            "table",
            {
                "type": "1D",
                "name": name,
                "category": category,
                "storagetype": "float",
                "endian": "big",
                "sizey": "1",
                "userlevel": "2",
                "storageaddress": address,
            },
        )
        ET.SubElement(
            table,
            "scaling",
            {
                "units": units,
                "expression": expression,
                "to_byte": to_byte,
                "format": fmt,
                "fineincrement": "0.5",
                "coarseincrement": "1",
            },
        )
        set_description(table, description)

    offsets = ET.SubElement(
        target,
        "table",
        {
            "type": "2D",
            "name": ROTATIONAL_IDLE_NAMES[11],
            "category": category,
            "storagetype": "float",
            "endian": "big",
            "sizey": "6",
            "userlevel": "1",
            "storageaddress": "0x7DB6C",
        },
    )
    ET.SubElement(
        offsets,
        "scaling",
        {
            "units": "degrees",
            "expression": "x",
            "to_byte": "x",
            "format": "0.0",
            "fineincrement": "0.5",
            "coarseincrement": "1",
        },
    )
    axis = ET.SubElement(
        offsets, "table", {"type": "Static Y Axis", "name": "Cylinder", "sizey": "6"}
    )
    for cylinder in range(1, 7):
        ET.SubElement(axis, "data").text = f"Cylinder {cylinder}"
    set_description(
        offsets,
        "Retard-only offsets in ECU final-angle array order. Defaults are "
        "{-6, 0, -6, 0, -6, 0} degrees. Positive values are forced to zero; "
        "Maximum Retard, Minimum Final Timing, and the original stock angle "
        "bound every output.",
    )


def add_fuel_pump_tables(target: ET.Element) -> None:
    """Expose the three verified discrete FPCU commands used by stock code."""
    specs = (
        (
            FUEL_PUMP_NAMES[0],
            "0x2A610",
            "Stock 33.3 percent low-speed command. P47 reports the selected "
            "command and fuel_pump_pwm_command_output_update @ 0x2A53A sends "
            "the same value to fuel_pump_pwm_output_write @ 0xDEAA. For a "
            "stationary full-speed diagnostic, set this and Medium-Speed "
            "Command to 100.0; the shared high-mode/PWM-scale constant remains "
            "fixed at 100.0. "
            "This does not override the ECU's pump-off state. Restore the "
            "stock value after the test unless wiring, fuel temperature, "
            "current draw, pressure and regulator capacity have been proven.",
        ),
        (
            FUEL_PUMP_NAMES[1],
            "0x2A60C",
            "Stock 66.7 percent medium-speed command. The Ghidra-verified "
            "selector at 0x2A53A copies this exact float to P47 RAM "
            "0xFFFFC298 and to the fuel-pump PWM output. Set Low- and "
            "Medium-Speed Command to 100.0 together for the stationary "
            "full-speed diagnostic; changing only one leaves another reduced "
            "mode available.",
        ),
    )
    for name, address, description in specs:
        table = ET.SubElement(
            target,
            "table",
            {
                "type": "1D",
                "name": name,
                "category": CAT_FUEL_PUMP,
                "storagetype": "float",
                "endian": "big",
                "sizey": "1",
                "userlevel": "2",
                "storageaddress": address,
            },
        )
        ET.SubElement(
            table,
            "scaling",
            {
                "units": "%",
                "expression": "x",
                "to_byte": "x",
                "format": "0.0",
                "fineincrement": "0.1",
                "coarseincrement": "1.0",
            },
        )
        set_description(table, description)


def add_fueling_safety_templates(parent: ET.Element, target: ET.Element) -> None:
    exact_switch = (
        "Exact 01 enables this guard; any other value disables only this guard. "
    )
    add_scalar_template(
        parent, target, FUELING_SAFETY_NAMES[0], "0x7EACC", "uint8", "switch",
        "x", "x", "01 = enabled", exact_switch
        + "Default is ON. The stock primary-open-loop target routine still runs first; "
        "the wrapper then clears only its Ghidra-verified closed-loop-permission bit "
        "when MAP reaches barometric pressure minus the configured margin.",
        "0", "1", "1",
    )
    add_scalar_template(
        parent, target, FUELING_SAFETY_NAMES[1], "0x7EAD0", "float", "psi below baro",
        "x/51.71493257", "x*51.71493257", "Force OL this far below barometric pressure",
        "Default 0.50 psi. A larger value requests open loop earlier in vacuum. The "
        "comparison uses live MAP minus live atmospheric pressure, not a fixed sea-level value.",
    )
    add_scalar_template(
        parent, target, FUELING_SAFETY_NAMES[2], "0x7EACD", "uint8", "switch",
        "x", "x", "01 = enabled", exact_switch
        + "Default is ON. It adds a latched cut through the verified stock rev-limiter "
        "fuel-cut path and cannot suppress the existing RPM or hard-overboost cuts.",
        "0", "1", "1",
    )
    add_scalar_template(
        parent, target, FUELING_SAFETY_NAMES[3], "0x7EAD4", "float", "psi gauge",
        "x/51.71493257", "x*51.71493257", "Begin sensor-delay state above",
        "Default +0.50 psi relative to live barometric pressure. Below this pressure "
        "the non-latched state and counter are cleared.",
    )
    add_scalar_template(
        parent, target, FUELING_SAFETY_NAMES[4], "0x7EAD8", "float", "psi gauge",
        "x/51.71493257", "x*51.71493257", "Release a latched cut below",
        "Default -0.50 psi relative to live barometric pressure. AFR is deliberately "
        "ignored after a trip because fuel cut itself makes the sensor read lean.",
    )
    add_scalar_template(
        parent, target, FUELING_SAFETY_NAMES[5], "0x7EADC", "float", "gasoline AFR",
        "x*14.64", "x/14.64", "Trip when measured AFR is leaner than",
        "Default 13.00 AFR using the project's verified 14.64 stoichiometric reference. "
        "An invalid or not-ready former-MAF wideband sample counts as lean after the "
        "transport delay. This is displayed as AFR although firmware stores lambda.",
    )
    add_scalar_template(
        parent, target, FUELING_SAFETY_NAMES[6], "0x7EAE8", "uint16", "task calls",
        "x", "x", "Post-turbo sensor delay", "Default 50 periodic task calls before "
        "AFR is evaluated. This is not milliseconds; measure and calibrate it from logs.",
        "0", "1", "10",
    )
    add_scalar_template(
        parent, target, FUELING_SAFETY_NAMES[7], "0x7EAEA", "uint16", "task calls",
        "x", "x", "Consecutive lean samples to trip", "Default 8 consecutive lean, "
        "invalid, or not-ready samples. A valid sample at or richer than the AFR "
        "threshold resets this counter.",
        "0", "1", "5",
    )


def update_patch_descriptions(target: ET.Element) -> None:
    for name, description in BOOST_DESCRIPTIONS.items():
        set_description(table_by_name(target, name), description)
    for name, description in PREDICTABLE_AVLS_DESCRIPTIONS.items():
        set_description(table_by_name(target, name), description)


def apply_master_categories(parent: ET.Element, target: ET.Element) -> None:
    """Assign and order the flat RomRaider menu categories by tuning workflow."""
    for rom in (parent, target):
        for table in rom.findall("table"):
            current = table.get("category")
            category = TABLE_CATEGORY_OVERRIDES.get(
                table.get("name"), CATEGORY_RENAMES.get(current)
            )
            if category is not None:
                table.set("category", category)

    parent_categories = {
        table.get("name"): table.get("category") for table in parent.findall("table")
    }
    rank = {category: index for index, category in enumerate(CATEGORY_ORDER)}

    def resolved_category(table: ET.Element) -> str:
        category = table.get("category") or parent_categories.get(table.get("name"))
        if category not in rank:
            raise SystemExit(
                f"table {table.get('name')!r} has ungrouped category {category!r}"
            )
        return category

    for rom in (parent, target):
        tables = list(rom.findall("table"))
        indexed = list(enumerate(tables))
        indexed.sort(key=lambda item: (rank[resolved_category(item[1])], item[0]))
        for table in tables:
            rom.remove(table)
        for _, table in indexed:
            rom.append(table)


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
    expected_custom = set(
        SD_NAMES
        + BOOST_NAMES
        + WIDEBAND_NAMES
        + FUELING_SAFETY_NAMES
        + FUEL_PUMP_NAMES
        + ROTATIONAL_IDLE_NAMES
        + AVLS_NAMES
    )
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

    allowed_categories = set(CATEGORY_ORDER)
    parent_categories = {
        table.get("name"): table.get("category") for table in parent.findall("table")
    }
    category_rank = {category: index for index, category in enumerate(CATEGORY_ORDER)}
    for label, rom in (("parent", parent), ("target", target)):
        resolved = [
            table.get("category") or parent_categories.get(table.get("name"))
            for table in rom.findall("table")
        ]
        unexpected = sorted({category for category in resolved if category not in allowed_categories})
        if unexpected:
            raise SystemExit(f"ungrouped {label} categories: {unexpected}")
        ranks = [category_rank[category] for category in resolved]
        if ranks != sorted(ranks):
            raise SystemExit(f"{label} tables are not ordered by tuning workflow")

    expected_categories = {
        "Omni Power MAP-SUP-3BR Scaling": CAT_AIR_MAP,
        "Intake Temp Sensor Scaling": CAT_AIR_IAT,
        "Speed Density Global Airflow Multiplier": CAT_AIR_SD,
        "Speed Density VE - AVLS Low Lift": CAT_AIR_VE,
        "Engine Load Compensation (MP)": CAT_AIR_LOAD,
        "Injector Flow Scaling ": CAT_FUEL_INJECTORS,
        "Primary Open Loop Fueling A ": CAT_FUEL_OL,
        "Fuel Pump Low-Speed Command": CAT_FUEL_PUMP,
        "External Wideband Lambda Transfer": CAT_WIDEBAND,
        "Base Timing - Normal Cam (AVCS Tracking Ratio 1.0)": CAT_IGN_BASE,
        "Knock Correction Advance Max - Normal Cam": CAT_IGN_KNOCK,
        "AVLS High Cam Engage RPM": CAT_CAM_AVLS,
        "Intake AVCS Target - AVLS Low Cam": CAT_CAM_AVCS,
        "Electronic Boost Control Enable": CAT_BOOST_CONTROL,
        "Overboost Fuel Cut Enable": CAT_BOOST_PROTECTION,
        "Lean Fuel Cut Enable": CAT_PROTECTION_FUEL,
        "Rev Limit A": CAT_PROTECTION_RPM,
        "Requested Torque (Accelerator Pedal)": CAT_THROTTLE,
        "Idle Speed Target A": CAT_IDLE_TARGET,
        "Base Timing Idle": CAT_IDLE_IGNITION,
        "Rotational Idle Enable": CAT_IDLE_ROTATIONAL,
        "Engine Oil Temperature Sensor Scaling": CAT_SENSOR_TEMPERATURE,
        "Radiator Fan Modes A (ECT)": CAT_COOLING_FANS,
        "Checksum Fix": CAT_CHECKSUM,
    }
    for name, expected_category in expected_categories.items():
        table = table_by_name(target, name)
        actual_category = table.get("category") or parent_categories.get(name)
        if actual_category != expected_category:
            raise SystemExit(
                f"wrong category for {name}: {actual_category!r}, expected {expected_category!r}"
            )

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
        "Electronic Boost Control Enable": "0x7D80C",
        "Overboost Fuel Cut Enable": "0x7D80D",
        "External Wideband Lambda Transfer": "0x7E404",
        "External Wideband Valid Voltage Range": "0x7E40C",
        "Pressure-Based Open Loop Failsafe Enable": "0x7EACC",
        "Pressure-Based Open Loop Margin": "0x7EAD0",
        "Lean Fuel Cut Enable": "0x7EACD",
        "Lean Fuel Cut Arm Pressure": "0x7EAD4",
        "Lean Fuel Cut Reset Pressure": "0x7EAD8",
        "Lean Fuel Cut AFR Threshold": "0x7EADC",
        "Lean Fuel Cut Sensor Transport Delay": "0x7EAE8",
        "Lean Fuel Cut Confirmation Count": "0x7EAEA",
        "Fuel Pump Low-Speed Command": "0x2A610",
        "Fuel Pump Medium-Speed Command": "0x2A60C",
        "Rotational Idle Enable": "0x7DB40",
        "Rotational Idle Minimum Coolant Temperature": "0x7DB44",
        "Rotational Idle Maximum Coolant Temperature": "0x7DB48",
        "Rotational Idle Minimum Engine Speed": "0x7DB4C",
        "Rotational Idle Maximum Engine Speed": "0x7DB50",
        "Rotational Idle Maximum Throttle": "0x7DB54",
        "Rotational Idle Maximum Vehicle Speed": "0x7DB58",
        "Rotational Idle Minimum Manifold Pressure": "0x7DB5C",
        "Rotational Idle Maximum Manifold Pressure": "0x7DB60",
        "Rotational Idle Maximum Retard": "0x7DB64",
        "Rotational Idle Minimum Final Timing": "0x7DB68",
        "Rotational Idle Cylinder Timing Offsets": "0x7DB6C",
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
    set_description(
        table_by_name(parent, "Intake Temp Sensor Scaling"), IAT_SENSOR_DESCRIPTION
    )

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
    add_fueling_safety_templates(parent, target)
    add_fuel_pump_tables(target)
    add_rotational_idle_tables(target)
    apply_master_categories(parent, target)

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
