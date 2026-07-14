#!/usr/bin/env python3
"""Add the D2WD610H AEM-lambda parameter to a RomRaider logger definition.

The source logger is never modified.  The output defaults to a sibling file with
"_D2WD610H_AEM" appended to its stem.

Usage:  python3 install_aem_logger.py source_logger.xml [output_logger.xml]
"""
import os
import re
import sys
import xml.etree.ElementTree as ET


HERE = os.path.dirname(os.path.abspath(__file__))
FRAGMENT = os.path.abspath(os.path.join(
    HERE, "..", "defs", "D2WD610H_AEM_logger_ecuparam.xml"))
ECU_ID = "3C5A387116"
PARAMETERS = {
    "E500": "AEM Post-Turbo Lambda (D2WD610H)*",
    "E501": "AEM Input Raw ADC (D2WD610H)*",
}


def default_output(source):
    stem, extension = os.path.splitext(source)
    return stem + "_D2WD610H_AEM" + (extension or ".xml")


def fail(message):
    raise SystemExit("REFUSING: " + message)


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: python3 install_aem_logger.py source_logger.xml "
                         "[output_logger.xml]")
    source = os.path.abspath(sys.argv[1])
    output = os.path.abspath(sys.argv[2]) if len(sys.argv) == 3 else default_output(source)
    if not os.path.isfile(source):
        fail("source logger does not exist: %s" % source)
    if os.path.realpath(source) == os.path.realpath(output):
        fail("output must be a new file; the source logger is preserved")
    if os.path.exists(output) and os.path.samefile(source, output):
        fail("output is a hard link to the source logger")

    with open(source, "r", encoding="utf-8-sig") as handle:
        text = handle.read()
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        fail("source logger XML does not parse: %s" % exc)
    if root.tag != "logger":
        fail("source root is <%s>, expected <logger>" % root.tag)
    existing_ids = {element.get("id") for element in root.iter()}
    existing_names = {element.get("name") for element in root.iter()}
    for parameter_id, parameter_name in PARAMETERS.items():
        if parameter_id in existing_ids:
            fail("parameter ID %s already exists; choose/review the logger definition manually"
                 % parameter_id)
        if parameter_name in existing_names:
            fail("the D2WD610H AEM parameters are already installed")

    with open(FRAGMENT, "r", encoding="utf-8") as handle:
        fragment_text = handle.read()
    try:
        fragment = ET.fromstring(fragment_text)
    except ET.ParseError as exc:
        fail("project logger fragment does not parse: %s" % exc)
    fragment_parameters = list(fragment.findall("ecuparam"))
    if (fragment.tag != "ecuparams"
            or {element.get("id") for element in fragment_parameters} != set(PARAMETERS)):
        fail("project logger fragment has an unexpected root or parameter IDs")

    protocol_match = re.search(r'<protocol\b[^>]*\bid=["\']SSM["\'][^>]*>', text)
    if not protocol_match:
        fail("could not find the SSM protocol block")
    protocol_end = text.find("</protocol>", protocol_match.end())
    if protocol_end < 0:
        fail("could not find the SSM </protocol> closing tag")
    if ECU_ID not in text[protocol_match.start():protocol_end]:
        fail("the SSM protocol has no existing support for ECU ID %s" % ECU_ID)
    ecuparams_start = text.find("<ecuparams", protocol_match.end(), protocol_end)
    if ecuparams_start < 0:
        fail("could not find the SSM <ecuparams> block")
    insert_at = text.find("</ecuparams>", ecuparams_start, protocol_end)
    if insert_at < 0:
        fail("could not find the SSM </ecuparams> closing tag")

    element_blocks = []
    search_at = 0
    for _ in fragment_parameters:
        element_start = fragment_text.index("<ecuparam ", search_at)
        element_end = fragment_text.index("</ecuparam>", element_start) + len("</ecuparam>")
        element_blocks.append(fragment_text[element_start:element_end])
        search_at = element_end
    element_text = "\n".join(element_blocks)
    indented = "\n".join("                " + line for line in element_text.splitlines())
    closing_line_start = text.rfind("\n", 0, insert_at) + 1
    patched_text = text[:closing_line_start] + indented + "\n" + text[closing_line_start:]
    try:
        patched_root = ET.fromstring(patched_text)
    except ET.ParseError as exc:
        fail("generated logger XML does not parse: %s" % exc)
    installed_ids = [element.get("id") for element in patched_root.iter("ecuparam")
                     if element.get("id") in PARAMETERS]
    if sorted(installed_ids) != sorted(PARAMETERS):
        fail("generated logger does not contain exactly one copy of each project parameter")

    with open(output, "w", encoding="utf-8", newline="") as handle:
        handle.write(patched_text)
    print("D2WD610H AEM logger definition written: %s" % output)
    print("  source preserved : %s" % source)
    print("  ECU ID           : %s" % ECU_ID)
    print("  parameters       : E500 AEM lambda / E501 raw conditioner ADC")
    print("  RAM sources      : 0xFFFFB098 float lambda / 0xFFFFAB20 uint16 raw")
    print("Select the new output under RomRaider Logger -> Settings -> Logger Definition Location.")


if __name__ == "__main__":
    main()
