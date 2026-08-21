#!/usr/bin/env python3
"""Generate the standalone D2WD610H AVLS-state dual-VE SD definition.

The project keeps the metric D2WD610H AVLS definition as the source template.
This generator removes the now-unused MAF calibration/DTC entries, then adds
only the MAFless speed-density tables and target addresses.  It does not pull
unrelated ROM definitions into the output.
"""

from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "defs" / "D2WD610H_AVLS.xml"
OUTPUT = HERE / "D2WD610H_AVLS_speed_density_patch.xml"

REMOVED_MAF_TABLES = {
    "MAF Limit (Maximum) ",
    "MAF Sensor Scaling",
    "MAF Compensation (IAT)",
    "(P0102) MAF SENSOR LOW INPUT",
    "(P0103) MAF SENSOR HIGH INPUT",
}

HIDDEN_AVLS_TABLES = {
    "AVLS Vehicle Speed Threshold (Normal Oil Temperature)",
    "AVLS Vehicle Speed Threshold (High Oil Temperature)",
    "AVLS Vehicle Speed Hysteresis (Normal Oil Temperature)",
    "AVLS Vehicle Speed Hysteresis (High Oil Temperature)",
    "AVLS Oil Temperature Selector Thresholds",
    "AVLS Actuation Minimum RPM",
}

TEMPLATE_INSERT = """  <table type="2D" name="Speed Density Global Airflow Multiplier" category="Speed Density (patch)" storagetype="float" endian="little" sizey="1" userlevel="3">
   <scaling units="multiplier" expression="x" to_byte="x" format="0.000" fineincrement=".005" coarseincrement=".02" />
   <table type="Static Y Axis" name="Global correction" sizey="1"><data>Multiplier</data></table>
   <description>Final multiplier applied to modeled mass airflow. A non-positive or non-finite value invokes the fixed 500 g/s rich/high-load fail-safe.</description>
  </table>
  <table type="2D" name="Speed Density Engine Displacement" category="Speed Density (patch)" storagetype="float" endian="little" sizey="1" userlevel="3">
   <scaling units="litres" expression="x" to_byte="x" format="0.000" fineincrement=".001" coarseincrement=".01" />
   <table type="Static Y Axis" name="Engine" sizey="1"><data>Displacement</data></table>
   <description>Engine displacement used by the ideal-gas mass-flow model. Default is 2.999 litres for the EZ30R.</description>
  </table>
  <table type="2D" name="Speed Density Maximum Airflow" category="Speed Density (patch)" storagetype="float" endian="little" sizey="1" userlevel="3">
   <scaling units="g/s" expression="x" to_byte="x" format="0.0" fineincrement="1" coarseincrement="10" />
   <table type="Static Y Axis" name="Safety cap" sizey="1"><data>Maximum</data></table>
   <description>Maximum normal speed-density airflow. A non-positive or non-finite value invokes the fixed 500 g/s rich/high-load fail-safe.</description>
  </table>
  <table type="2D" name="Speed Density MAP Valid Range" category="Speed Density (patch)" storagetype="float" endian="little" sizey="2" userlevel="4">
   <scaling units="mmHg absolute" expression="x" to_byte="x" format="0.0" fineincrement="1" coarseincrement="10" />
   <table type="Static Y Axis" name="Gate" sizey="2"><data>Minimum</data><data>Maximum</data></table>
   <description>Native absolute-MAP validity window. Outside it the task writes the fixed 500 g/s rich/high-load fail-safe.</description>
  </table>
  <table type="2D" name="Speed Density RPM Valid Range" category="Speed Density (patch)" storagetype="float" endian="little" sizey="2" userlevel="4">
   <scaling units="RPM" expression="x" to_byte="x" format="#" fineincrement="10" coarseincrement="100" />
   <table type="Static Y Axis" name="Gate" sizey="2"><data>Minimum</data><data>Maximum</data></table>
   <description>RPM validity window. Exact zero RPM writes zero airflow; other invalid values invoke the fixed 500 g/s rich/high-load fail-safe.</description>
  </table>
  <table type="2D" name="Speed Density IAT Valid Range" category="Speed Density (patch)" storagetype="float" endian="little" sizey="2" userlevel="4">
   <scaling units="Degrees C" expression="x" to_byte="x" format="0.0" fineincrement="1" coarseincrement="5" />
   <table type="Static Y Axis" name="Gate" sizey="2"><data>Minimum</data><data>Maximum</data></table>
   <description>Intake-air-temperature validity window. Outside it the task writes the fixed 500 g/s rich/high-load fail-safe.</description>
  </table>
  <table type="3D" name="Speed Density VE - AVLS Low Lift" category="Speed Density - AVLS VE (patch)" storagetype="float" endian="little" sizex="13" sizey="9" userlevel="2">
   <scaling units="VE fraction" expression="x" to_byte="x" format="0.000" fineincrement=".005" coarseincrement=".02" />
   <table type="X Axis" name="Manifold Pressure" storagetype="float" endian="little" logparam="E52">
    <scaling units="mmHg absolute" expression="x" to_byte="x" format="0.0" fineincrement="1" coarseincrement="10" />
   </table>
   <table type="Y Axis" name="Engine Speed" storagetype="float" endian="little" logparam="P8">
    <scaling units="RPM" expression="x" to_byte="x" format="#" fineincrement="50" coarseincrement="100" />
   </table>
   <description>VE fraction used while committed AVLS mode 0xFFFFCD86 is not 3. The RPM axis stops at the 3200 RPM high-lift engage threshold. The 3000-3200 overlap is selected by committed state.</description>
  </table>
  <table type="3D" name="Speed Density VE - AVLS High Lift" category="Speed Density - AVLS VE (patch)" storagetype="float" endian="little" sizex="13" sizey="11" userlevel="2">
   <scaling units="VE fraction" expression="x" to_byte="x" format="0.000" fineincrement=".005" coarseincrement=".02" />
   <table type="X Axis" name="Manifold Pressure" storagetype="float" endian="little" logparam="E52">
    <scaling units="mmHg absolute" expression="x" to_byte="x" format="0.0" fineincrement="1" coarseincrement="10" />
   </table>
   <table type="Y Axis" name="Engine Speed" storagetype="float" endian="little" logparam="P8">
    <scaling units="RPM" expression="x" to_byte="x" format="#" fineincrement="50" coarseincrement="100" />
   </table>
   <description>VE fraction used only while committed AVLS mode 0xFFFFCD86 is 3. The RPM axis starts at the 3000 RPM release threshold and extends through 7500 RPM. Values are conservative seeds requiring log calibration.</description>
  </table>
  <table type="2D" name="Speed Density IAT Density Correction" category="Speed Density (patch)" storagetype="float" endian="little" sizey="10" userlevel="2">
   <scaling units="multiplier" expression="x" to_byte="x" format="0.000" fineincrement=".005" coarseincrement=".02" />
   <table type="Y Axis" name="Intake Temperature" storagetype="float" endian="little" logparam="P11">
    <scaling units="Degrees C" expression="x" to_byte="x" format="0.0" fineincrement="1" coarseincrement="5" />
   </table>
   <description>Density multiplier applied after the VE calculation. Defaults to 293.15/(IAT C + 273.15), referenced to 20 C.</description>
  </table>
"""

TARGET_INSERT = """  <table name="Speed Density Global Airflow Multiplier" storageaddress="0x7DD04" />
  <table name="Speed Density Engine Displacement" storageaddress="0x7DD08" />
  <table name="Speed Density Maximum Airflow" storageaddress="0x7DD0C" />
  <table name="Speed Density MAP Valid Range" storageaddress="0x7DD10" />
  <table name="Speed Density RPM Valid Range" storageaddress="0x7DD18" />
  <table name="Speed Density IAT Valid Range" storageaddress="0x7DD20" />
  <table name="Speed Density VE - AVLS Low Lift" storageaddress="0x7E6B8" sizex="13" sizey="9">
   <table type="X Axis" storageaddress="0x7DD4C" />
   <table type="Y Axis" storageaddress="0x7E668" />
  </table>
  <table name="Speed Density VE - AVLS High Lift" storageaddress="0x7E88C" sizex="13" sizey="11">
   <table type="X Axis" storageaddress="0x7DD4C" />
   <table type="Y Axis" storageaddress="0x7E68C" />
  </table>
  <table name="Speed Density IAT Density Correction" storageaddress="0x7E160" sizey="10">
   <table type="Y Axis" storageaddress="0x7E138" />
  </table>
"""


def remove_named_table_blocks(text: str, names: set[str]) -> str:
    """Remove complete top-level table blocks while preserving source formatting."""
    table_tags = re.compile(r"</?table\b[^>]*>")

    def depth_delta(line: str) -> int:
        delta = 0
        for tag in table_tags.findall(line):
            if tag.startswith("</"):
                delta -= 1
            elif not tag.rstrip().endswith("/>"):
                delta += 1
        return delta

    lines = text.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        matched = next(
            (name for name in names if ('name="%s"' % name) in line and "<table" in line),
            None,
        )
        if matched is None:
            output.append(line)
            index += 1
            continue

        depth = depth_delta(line)
        index += 1
        while depth > 0 and index < len(lines):
            depth += depth_delta(lines[index])
            index += 1
        if depth != 0:
            raise SystemExit("unterminated table block while removing %s" % matched)
    return "".join(output)


def replace_target_description(text: str, name: str, description: str) -> str:
    start = text.find('<table type="1D" name="%s"' % name)
    if start < 0:
        raise SystemExit("could not find target table %s" % name)
    end = text.find("</table>", start)
    if end < 0:
        raise SystemExit("unterminated target table %s" % name)
    block = text[start : end + len("</table>")]
    updated, count = re.subn(
        r"<description>.*?</description>",
        "<description>%s</description>" % description,
        block,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise SystemExit("could not replace description for %s" % name)
    return text[:start] + updated + text[end + len("</table>") :]


def render_definition() -> str:
    text = SOURCE.read_text(encoding="utf-8")
    if "Speed Density Global Airflow Multiplier" in text:
        raise SystemExit("source definition already contains speed-density entries")
    removed = REMOVED_MAF_TABLES | HIDDEN_AVLS_TABLES
    text = remove_named_table_blocks(text, removed)
    for name in removed:
        if ('name="%s"' % name) in text:
            raise SystemExit("failed to remove inherited obsolete table %s" % name)

    target_marker = ' <rom base="32BITBASE">\n'
    target_start = text.find(target_marker)
    if target_start < 0:
        raise SystemExit("could not find D2WD610H target ROM block")

    template_close = text.rfind(" </rom>\n", 0, target_start)
    if template_close < 0:
        raise SystemExit("could not find metric 32BITBASE template close")
    text = text[:template_close] + TEMPLATE_INSERT + text[template_close:]

    target_start = text.find(target_marker, template_close + len(TEMPLATE_INSERT))
    target_close = text.find(" </rom>\n", target_start)
    if target_close < 0:
        raise SystemExit("could not find D2WD610H target ROM close")
    text = text[:target_close] + TARGET_INSERT + text[target_close:]

    text = text.replace(
        "<xmlid>D2WD610H_AVLS</xmlid>",
        "<xmlid>D2WD610H_AVLS_SPEED_DENSITY_ONLY</xmlid>",
        1,
    )
    text = replace_target_description(
        text,
        "AVLS High Cam Engage RPM",
        "Predictable high-lift engagement threshold. Default 3200 RPM. The "
        "vehicle-speed request path is fixed unreachable in this patch; keep "
        "this value above the release threshold.",
    )
    text = replace_target_description(
        text,
        "AVLS High Cam Release RPM",
        "Predictable high-lift release threshold. Default 3000 RPM, providing "
        "200 RPM hysteresis. Both VE tables cover the resulting overlap.",
    )
    return text


def main() -> None:
    OUTPUT.write_text(render_definition(), encoding="utf-8")
    print("Wrote %s from %s" % (OUTPUT, SOURCE))


if __name__ == "__main__":
    main()
