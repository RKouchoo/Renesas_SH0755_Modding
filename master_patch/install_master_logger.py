#!/usr/bin/env python3
"""Install the D2WD610H master parameters into a RomRaider logger XML.

The source logger definition is never modified.  The output defaults to a
sibling file with ``_D2WD610H_master`` appended to its stem.

Usage:
    python3 master_patch/install_master_logger.py source_logger.xml [output.xml]
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
FRAGMENT = HERE / "D2WD610H_master_logger_ecuparams.xml"
ECU_ID = "3C5A387116"
PARAMETERS = {
    "E500": "External Wideband AFR (D2WD610H master)*",
    "E501": "External Wideband Input ADC (D2WD610H master)*",
    "E502": "External Wideband Ready Metric (D2WD610H master)*",
    "E503": "Committed AVLS VE State (D2WD610H master)*",
    "E504": "Lean Fuel Cut State (D2WD610H master)*",
    "E505": "Lean Fuel Cut Counter (D2WD610H master)*",
    "E506": "CL/OL State Flags (D2WD610H master)*",
}


def default_output(source: Path) -> Path:
    extension = source.suffix or ".xml"
    return source.with_name(source.stem + "_D2WD610H_master" + extension)


def fail(message: str) -> None:
    raise SystemExit("REFUSING: " + message)


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
    if output.exists() and source.samefile(output):
        fail("output is a hard link to the source logger")

    text = source.read_text(encoding="utf-8-sig")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        fail(f"source logger XML does not parse: {exc}")
    if root.tag != "logger":
        fail(f"source root is <{root.tag}>, expected <logger>")
    existing_ids = {element.get("id") for element in root.iter()}
    existing_names = {element.get("name") for element in root.iter()}
    for parameter_id, parameter_name in PARAMETERS.items():
        if parameter_id in existing_ids:
            fail(
                f"parameter ID {parameter_id} already exists; "
                "review the logger definition manually"
            )
        if parameter_name in existing_names:
            fail("the D2WD610H master parameters are already installed")

    fragment_text = FRAGMENT.read_text(encoding="utf-8")
    try:
        fragment = ET.fromstring(fragment_text)
    except ET.ParseError as exc:
        fail(f"project logger fragment does not parse: {exc}")
    fragment_parameters = list(fragment.findall("ecuparam"))
    if fragment.tag != "ecuparams" or {
        element.get("id") for element in fragment_parameters
    } != set(PARAMETERS):
        fail("project logger fragment has an unexpected root or parameter IDs")

    protocol_match = re.search(r'<protocol\b[^>]*\bid=["\']SSM["\'][^>]*>', text)
    if not protocol_match:
        fail("could not find the SSM protocol block")
    protocol_end = text.find("</protocol>", protocol_match.end())
    if protocol_end < 0:
        fail("could not find the SSM </protocol> closing tag")
    if ECU_ID not in text[protocol_match.start() : protocol_end]:
        fail(f"the SSM protocol has no existing support for ECU ID {ECU_ID}")
    ecuparams_start = text.find("<ecuparams", protocol_match.end(), protocol_end)
    if ecuparams_start < 0:
        fail("could not find the SSM <ecuparams> block")
    insert_at = text.find("</ecuparams>", ecuparams_start, protocol_end)
    if insert_at < 0:
        fail("could not find the SSM </ecuparams> closing tag")

    element_blocks: list[str] = []
    search_at = 0
    for _ in fragment_parameters:
        element_start = fragment_text.index("<ecuparam ", search_at)
        element_end = fragment_text.index("</ecuparam>", element_start) + len(
            "</ecuparam>"
        )
        element_blocks.append(fragment_text[element_start:element_end])
        search_at = element_end
    element_text = "\n".join(element_blocks)
    indented = "\n".join("                " + line for line in element_text.splitlines())
    closing_line_start = text.rfind("\n", 0, insert_at) + 1
    patched_text = (
        text[:closing_line_start] + indented + "\n" + text[closing_line_start:]
    )
    try:
        patched_root = ET.fromstring(patched_text)
    except ET.ParseError as exc:
        fail(f"generated logger XML does not parse: {exc}")
    installed_ids = [
        element.get("id")
        for element in patched_root.iter("ecuparam")
        if element.get("id") in PARAMETERS
    ]
    if sorted(installed_ids) != sorted(PARAMETERS):
        fail("generated logger does not contain exactly one copy of each parameter")

    output.write_text(patched_text, encoding="utf-8", newline="")
    print(f"D2WD610H master logger definition written: {output}")
    print(f"  source preserved : {source}")
    print(f"  ECU ID           : {ECU_ID}")
    print("  E500              : external-wideband AFR / raw lambda")
    print("  E501              : former-MAF raw ADC / input volts")
    print("  E502              : wideband readiness / one boost-duty prerequisite")
    print("  E503              : committed AVLS mode used by the dual-VE selector")
    print("  E504 / E505       : lean-cut state / task-call counter")
    print("  E506              : raw stock CL/OL state flags")
    print(
        "Select the new output under RomRaider Logger -> Settings -> "
        "Logger Definition Location."
    )


if __name__ == "__main__":
    main()
