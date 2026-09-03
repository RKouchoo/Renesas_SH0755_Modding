#!/usr/bin/env python3
"""Build the complete D2WD610H master RomRaider logger definition.

The input must be a complete RomRaider ``<logger>`` definition. The source is
never modified. The generated definition keeps the SSM transports, standard
parameters, switches and DTCs, but removes protocols and ECU-specific address
records unrelated to D2WD610H before adding the master-patch parameters.

Usage:
    python3 master_patch/install_master_logger.py source_logger.xml [output.xml]
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
FRAGMENT = HERE / "D2WD610H_master_logger_ecuparams.xml"
ECU_ID = "3C5A387116"
PARAMETER_IDS = {"E500", "E501", "E502", "E503", "E504", "E505", "E506"}

# The upstream logger contains a global catalogue for many Subaru ECUs, TCMs,
# diesel engines, and DCCD controllers.  Standard SSM parameters do not carry
# an ECU ID, so RomRaider can display irrelevant entries even after it has
# identified D2WD610H.  Keep a deliberately small H6-MT commissioning set.
STANDARD_PARAMETER_IDS = {
    "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10",
    "P11", "P12", "P13", "P17", "P19", "P21", "P22", "P23", "P24",
    "P25", "P29", "P30", "P35", "P38", "P46", "P47", "P48", "P49",
    "P50", "P51", "P52", "P53", "P60", "P63", "P64", "P69", "P70",
    "P71", "P72", "P73", "P74", "P75", "P76", "P82", "P90", "P91",
    "P92", "P115", "P122", "P123", "P124", "P125", "P126", "P127",
    "P151", "P152", "P153", "P200", "P201", "P202", "P239", "P240",
    "P241",
}

STANDARD_SWITCH_IDS = {
    "S2", "S4", "S5", "S7", "S9", "S11", "S15", "S16", "S17",
    "S18", "S19", "S20", "S21", "S22", "S23", "S24", "S25", "S26",
    "S27", "S28", "S29", "S30", "S32", "S62", "S63", "S64", "S65",
    "S66", "S67", "S68", "S70", "S71", "S73", "S74", "S130", "S131",
    "S132", "S133", "S148", "S149", "S154", "S155", "S158", "S169",
    "S170", "S171",
}

# Prefer one high-resolution representation where the v370 source supplies
# duplicates.  Both banks are retained because the master writes the same
# external-wideband result into two independent stock feedback paths.
STOCK_ECU_PARAMETER_IDS = {
    "E31", "E32", "E33", "E39", "E40", "E41", "E44", "E45", "E46",
    "E47", "E48", "E50", "E51", "E53", "E54", "E55", "E56", "E57",
    "E58", "E59", "E60", "E61", "E62", "E63", "E64", "E65", "E66",
    "E81", "E84", "E91", "E105", "E109", "E113", "E121", "E123",
}


def default_output(source: Path) -> Path:
    extension = source.suffix or ".xml"
    return source.with_name(source.stem + "_D2WD610H_master" + extension)


def fail(message: str) -> None:
    raise SystemExit("REFUSING: " + message)


def parse_xml(text: str, description: str) -> ET.Element:
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        fail(f"{description} does not parse: {exc}")


def ecu_ids(element: ET.Element) -> set[str]:
    return {
        value.strip()
        for value in (element.get("id") or "").split(",")
        if value.strip()
    }


def load_fragment() -> list[ET.Element]:
    fragment = parse_xml(
        FRAGMENT.read_text(encoding="utf-8-sig"), "project fragment"
    )
    parameters = list(fragment.findall("ecuparam"))
    ids = [parameter.get("id") for parameter in parameters]
    if (
        fragment.tag != "ecuparams"
        or len(ids) != len(set(ids))
        or set(ids) != PARAMETER_IDS
    ):
        fail("project fragment has duplicate, missing, or unrelated parameter IDs")
    for parameter in parameters:
        ecus = list(parameter.findall("ecu"))
        if len(ecus) != 1 or ecu_ids(ecus[0]) != {ECU_ID}:
            fail(f"fragment parameter {parameter.get('id')} is not D2WD610H-only")
    return parameters


def find_xml_preamble(text: str) -> str:
    """Retain the declaration, disclaimer and internal/external DTD verbatim."""
    matches = list(re.finditer(r"(?m)^[ \t]*<logger(?:\s|>)", text))
    if len(matches) != 1:
        fail(f"source contains {len(matches)} <logger> opening tags")
    return text[: matches[0].start()]


def build_definition(source_text: str) -> tuple[str, int]:
    source_root = parse_xml(source_text, "source logger XML")
    if source_root.tag != "logger":
        fail(f"source root is <{source_root.tag}>, expected <logger>")

    protocols = list(source_root.findall("./protocols/protocol"))
    ssm_protocols = [
        protocol
        for protocol in protocols
        if (protocol.get("id") or "").upper() == "SSM"
    ]
    if len(ssm_protocols) != 1:
        fail(f"source contains {len(ssm_protocols)} SSM protocol blocks")

    protocol = deepcopy(ssm_protocols[0])

    standard_parameters = protocol.find("parameters")
    if standard_parameters is None:
        fail("SSM protocol has no standard <parameters> block")
    for parameter in list(standard_parameters.findall("parameter")):
        if parameter.get("id") not in STANDARD_PARAMETER_IDS:
            standard_parameters.remove(parameter)

    standard_switches = protocol.find("switches")
    if standard_switches is None:
        fail("SSM protocol has no standard <switches> block")
    for switch in list(standard_switches.findall("switch")):
        if switch.get("id") not in STANDARD_SWITCH_IDS:
            standard_switches.remove(switch)

    containers = list(protocol.findall("ecuparams"))
    if len(containers) != 1:
        fail("SSM protocol must contain exactly one <ecuparams> block")
    container = containers[0]

    # Accept a previously generated master file as regeneration input without
    # duplicating the custom block.  Normal upstream sources have no E500-E506.
    for parameter in list(container.findall("ecuparam")):
        if parameter.get("id") in PARAMETER_IDS:
            container.remove(parameter)

    retained = 0
    target_was_supported = False
    for parameter in list(container.findall("ecuparam")):
        if parameter.get("id") not in STOCK_ECU_PARAMETER_IDS:
            container.remove(parameter)
            continue
        matching_ecus: list[ET.Element] = []
        for ecu in parameter.findall("ecu"):
            if ECU_ID in ecu_ids(ecu):
                target_was_supported = True
                ecu.set("id", ECU_ID)
                matching_ecus.append(ecu)
            else:
                parameter.remove(ecu)
        if not matching_ecus:
            container.remove(parameter)
        else:
            if len(matching_ecus) != 1:
                fail(
                    f"source parameter {parameter.get('id')} has multiple "
                    f"address records for {ECU_ID}"
                )
            retained += 1

    if not target_was_supported:
        fail(f"the source SSM definition has no ECU-specific support for {ECU_ID}")
    if retained != len(STOCK_ECU_PARAMETER_IDS):
        fail(
            "source is missing focused D2WD610H extended parameters: "
            + ", ".join(
                sorted(
                    STOCK_ECU_PARAMETER_IDS
                    - {
                        parameter.get("id")
                        for parameter in container.findall("ecuparam")
                    }
                )
            )
        )

    for parameter in load_fragment():
        container.append(deepcopy(parameter))

    output_root = ET.Element("logger", source_root.attrib)
    output_root.append(
        ET.Comment(
            " D2WD610H-only master logger generated by install_master_logger.py; "
            "standard SSM data retained, unrelated ECU address records removed. "
        )
    )
    output_protocols = ET.SubElement(output_root, "protocols")
    output_protocols.append(protocol)
    ET.indent(output_root, space="    ")

    body = ET.tostring(output_root, encoding="unicode", short_empty_elements=True)
    output_text = find_xml_preamble(source_text) + body + "\n"
    validate_generated(output_text, retained)
    return output_text, retained


def validate_generated(text: str, retained: int | None = None) -> None:
    root = parse_xml(text, "generated logger XML")
    if root.tag != "logger":
        fail("generated logger is not a complete <logger> definition")
    protocols = root.findall("./protocols/protocol")
    if len(protocols) != 1 or (protocols[0].get("id") or "").upper() != "SSM":
        fail("generated logger must contain only the SSM protocol")
    container = protocols[0].find("ecuparams")
    if container is None:
        fail("generated SSM protocol has no <ecuparams> block")

    parameters = list(container.findall("ecuparam"))
    ids = [parameter.get("id") for parameter in parameters]
    if len(ids) != len(set(ids)):
        fail("generated logger has duplicate ecuparam IDs")
    if sum(parameter_id in PARAMETER_IDS for parameter_id in ids) != len(PARAMETER_IDS):
        fail("generated logger does not contain exactly one master parameter set")
    if retained is not None and len(parameters) != retained + len(PARAMETER_IDS):
        fail("generated logger lost or gained an ECU-specific parameter")

    standard_parameters = {
        item.get("id") for item in protocols[0].findall("parameters/parameter")
    }
    if standard_parameters != STANDARD_PARAMETER_IDS:
        fail("generated logger has missing or unrelated standard parameters")
    standard_switches = {
        item.get("id") for item in protocols[0].findall("switches/switch")
    }
    if standard_switches != STANDARD_SWITCH_IDS:
        fail("generated logger has missing or unrelated standard switches")
    stock_extended = set(ids) - PARAMETER_IDS
    if stock_extended != STOCK_ECU_PARAMETER_IDS:
        fail("generated logger has missing or unrelated stock extended parameters")

    for parameter in parameters:
        ecus = list(parameter.findall("ecu"))
        if len(ecus) != 1 or ecu_ids(ecus[0]) != {ECU_ID}:
            fail(
                f"generated parameter {parameter.get('id')} contains "
                "anything other than one D2WD610H address record"
            )


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv if argv is None else argv
    if len(argv) not in (2, 3):
        raise SystemExit(
            "usage: python3 master_patch/install_master_logger.py "
            "source_logger.xml [output_logger.xml]"
        )
    source = Path(argv[1]).resolve()
    output = Path(argv[2]).resolve() if len(argv) == 3 else default_output(source)
    if not source.is_file():
        fail(f"source logger does not exist: {source}")
    if source == output:
        fail("output must be a new file; the source logger is preserved")
    if output.exists() and output.samefile(source):
        fail("output is a hard link to the source logger")

    source_text = source.read_text(encoding="utf-8-sig")
    output_text, retained = build_definition(source_text)
    output.write_text(output_text, encoding="utf-8", newline="\n")
    validate_generated(output.read_text(encoding="utf-8"), retained)

    print(f"D2WD610H master logger definition written: {output}")
    print(f"  source preserved       : {source}")
    print("  complete XML root      : <logger>")
    print("  protocols              : SSM only")
    print(f"  stock extended params  : {retained}")
    print("  master params          : E500 through E506")
    print(f"  ECU-specific records   : {ECU_ID} only")


if __name__ == "__main__":
    main()
