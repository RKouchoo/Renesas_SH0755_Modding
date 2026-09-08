#!/usr/bin/env python3
"""Build the evidence index and retirement register without certifying labels.

Structural observations are deliberately separate from reviewed meanings.
The generated JSON retains all original claims, including contradictions.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "docs/reference"
EVIDENCE = REF / "evidence"


def escaped(text):
    return str(text).replace("|", "&#124;").replace("\n", " ")


def descriptor(blob, address):
    """Recognize only well-formed finite ascending-axis descriptor candidates."""
    result = []
    for dimensions in (1, 2):
        size = 20 if dimensions == 1 else 28
        if address + size > len(blob):
            continue
        nx = struct.unpack_from(">H", blob, address)[0]
        ny = 1 if dimensions == 1 else struct.unpack_from(">H", blob, address+2)[0]
        kind = blob[address + (2 if dimensions == 1 else 16)]
        if not (2 <= nx <= 256 and 1 <= ny <= 256 and kind in (0, 4, 8, 12, 16)):
            continue
        axis_addresses = [struct.unpack_from(">I", blob, address+4)[0]]
        lengths = [nx]
        if dimensions == 2:
            if ny < 2:
                continue
            axis_addresses.append(struct.unpack_from(">I", blob, address+8)[0])
            lengths.append(ny)
        data_address = struct.unpack_from(">I", blob, address+(8 if dimensions == 1 else 12))[0]
        width = {0: 4, 4: 1, 8: 2, 12: 1, 16: 2}[kind]
        if data_address < 0x2000 or data_address + nx*ny*width > len(blob):
            continue
        axes = []
        for location, count in zip(axis_addresses, lengths):
            if location < 0x2000 or location % 4 or location + count*4 > len(blob):
                break
            values = struct.unpack_from(f">{count}f", blob, location)
            if not all(math.isfinite(v) for v in values) or not all(a < b for a, b in zip(values, values[1:])):
                break
            axes.append({"address": f"{location:08X}", "count": count,
                         "first": values[0], "last": values[-1]})
        if len(axes) != dimensions:
            continue
        scale_offset = None
        if kind:
            values = struct.unpack_from(">ff", blob, address+(12 if dimensions == 1 else 20))
            if not all(math.isfinite(v) for v in values):
                continue
            scale_offset = list(values)
        result.append({"dimensions": dimensions, "type_byte": kind,
                       "axes": axes, "data_address": f"{data_address:08X}",
                       "data_bytes": nx*ny*width, "scale_offset": scale_offset})
    return result


def replacement(path):
    if path in ("readme.md", "master_patch/README.md") or path.endswith("/COMMISSIONING.md"):
        return "Keep operational entry point", "README.md"
    if path.startswith("logs/"):
        return "Keep capture provenance unchanged", "LOGGER.md"
    if path.startswith("patches/") and path.endswith("README.md"):
        return "Keep component contract", "IMAGES.md"
    if "WIRING" in path or "direct_attach" in path or "boost_donor" in path:
        return "Keep specialist source; physical limits apply", "MEMORY_AND_IO.md"
    if "romraider_query_fix" in path:
        return "Keep implementation/reproduction guide", "LOGGER.md"
    if "candidates" in path:
        return "Keep historical image provenance", "PATCH_STORY.md"
    if path.endswith("CALIBRATION.md") or path.endswith("MEMORY_LAYOUT.md"):
        return "Keep detailed current build contract", "IMAGES.md"
    if any(word in path.lower() for word in ("logger", "map_source")):
        return "Review for archival after consolidation", "LOGGER.md"
    if any(word in path.lower() for word in ("fpu", "execution", "scheduler", "retained")):
        return "Keep detailed proof until replacement reviewed", "METHODS.md"
    if any(word in path.lower() for word in ("hardware", "ram_map", "solenoid", "boost")):
        return "Review for archival; old identities corrected", "MEMORY_AND_IO.md"
    return "Review for archival after consolidation", "PATCH_STORY.md"


def main():
    inventory = json.loads((EVIDENCE / "documentation_inventory.json").read_text())
    captures = json.loads((EVIDENCE / "ghidra_evidence.json").read_text())
    fixtures = json.loads((EVIDENCE / "fixture_accesses.json").read_text())
    contracts = json.loads((EVIDENCE / "image_contracts.json").read_text())
    main_sha = contracts["images"]["main"]["sha256"]
    images = {name: (ROOT / record["path"]).read_bytes()
              for name, record in contracts["images"].items()}
    for name, blob in images.items():
        assert hashlib.sha256(blob).hexdigest() == contracts["images"][name]["sha256"], name
    assert contracts["images"]["stock"]["sha256"] == inventory["stock_sha256"]
    xml_references = defaultdict(list)
    for name in ("main", "v2"):
        path = Path(contracts["images"][name]["path"]).with_suffix(".xml")
        root = ET.parse(ROOT / path).getroot()

        def collect(element, parent_name=""):
            label = element.get("name", parent_name)
            if element.get("storageaddress"):
                address = int(element.get("storageaddress"), 16)
                assert 0 <= address < len(images[name]), (path, address)
                xml_references[f"{address:08X}"].append({
                    "image": name, "path": str(path), "parent_table": parent_name,
                    "label": label, "attributes": element.attrib,
                    "limit": "Address declaration only; inherited type, size and scaling are not resolved here.",
                })
            for child in element:
                collect(child, label)

        collect(root)
    by_address = defaultdict(list)
    instructions = {}
    routine_pcs = defaultdict(set)
    for record in captures["records"]:
        by_address[record["address"]].append(record)
        if record["kind"] != "routine_disassembly":
            continue
        for line in record["lines"]:
            match = re.match(r"([0-9a-fA-F]{8}):\s*(.*)", line)
            if match:
                pc = int(match[1], 16)
                instructions[pc] = {"entry": record["address"], "text": match[2]}
                routine_pcs[record["address"]].add(pc)
    fixture_accesses = defaultdict(list)
    for record in fixtures["accesses"]:
        if record["image"] == main_sha:
            fixture_accesses[record["address"]].append(record)
    visited = set(int(pc, 16) for pc in fixtures["visited_pcs"].get(main_sha, []))
    rows = []
    for record in inventory["addresses"]:
        address = int(record["address"], 16)
        references = []
        direct_accesses = []
        for capture in by_address[record["address"]]:
            if "xref" in capture["kind"]:
                references += [line for line in capture["lines"] if line.startswith("From ")]
        for line in references:
            match = re.match(r"From ([0-9a-fA-F]{8}).*\[(READ|WRITE)\]", line)
            if not match:
                continue
            insn = instructions.get(int(match[1], 16))
            if insn:
                direct_accesses.append({"pc": match[1].upper(), "operation": match[2], **insn})
        candidates = {name: descriptor(blob, address) for name, blob in images.items()
                      if 0x50000 <= address < len(blob)}
        candidates = {name: value for name, value in candidates.items() if value}
        if 0x80000 < address < 0x100000:
            classification = "donor_image_address"
        elif address == 0x80000:
            classification = "image_size_or_exclusive_end"
        elif address > 0x100000 and not 0xFFFF0000 <= address <= 0xFFFFFFFF:
            classification = "numeric_constant_or_checksum"
        elif record["ghidra_function_entry"]:
            classification = "ghidra_routine_entry"
        elif address in instructions:
            classification = "instruction_within_captured_routine"
        elif candidates:
            classification = "well_formed_lookup_descriptor_candidate"
        elif record["region"] == "saved_flash":
            classification = "rom_location_or_numeric_literal"
        else:
            classification = record["region"]
        semantic = record["semantic_review"]
        if semantic["status"] == "pending":
            semantic = {"status": "unresolved_meaning", "note":
                        "Structural evidence reviewed below; historical semantic claims are not certified by this index."}
        pcs = routine_pcs[record["address"]]
        rows.append({**record, "semantic_review": semantic,
                     "structural_class": classification,
                     "definition_address_declarations": xml_references[record["address"]],
                     "mcp_references": references,
                     "mcp_direct_access_instructions": direct_accesses,
                     "lookup_descriptor_candidates": candidates,
                     "main_fixture_accesses": fixture_accesses[record["address"]],
                     "captured_routine_instruction_addresses": len(pcs),
                     "main_fixture_visited_addresses_in_routine": len(pcs & visited),
                     "main_bytes": images["main"][address:address+16].hex() if address < 0x80000 else None,
                     "v2_bytes": images["v2"][address:address+16].hex() if address < 0x80000 else None})
    counts = Counter(row["structural_class"] for row in rows)
    semantics = Counter(row["semantic_review"]["status"] for row in rows)
    output = {"stock_sha256": inventory["stock_sha256"], "baseline_commit": inventory["baseline_commit"],
              "documents": inventory["documents"],
              "structural_counts": dict(counts), "semantic_counts": dict(semantics),
              "addresses": rows, "limits": inventory["limits"] + captures["limits"] + fixtures["limits"]}
    (EVIDENCE / "address_audit.json").write_text(json.dumps(output, indent=2) + "\n")
    md = ["# Complete documentation address index", "", "[Reference home](README.md) · [Findings](FINDINGS.md)", "",
          f"The inventory contains **{len(inventory['documents'])} documents, {len(rows)} address candidates and "
          f"{sum(len(r['claims']) for r in rows)} source occurrences**. It includes abbreviations, range endpoints, "
          "instruction sites and numeric constants; this is not a count of verified variables.", "",
          "Every candidate has saved-byte/region checks and available MCP/fixture evidence in "
          "[address_audit.json](evidence/address_audit.json). The original claims and line numbers are retained. "
          "[reviewed_addresses.json](evidence/reviewed_addresses.json) holds the separately reviewed meanings.", "",
          "Claims removed or rewritten during this audit are retained from commit `2d95301` with that revision's "
          "line numbers. Other source locations refer to the hashed working-tree document. The JSON records "
          "the distinction and matching main/v2 XML address declarations; those declarations do not by themselves verify runtime use.", "",
          "**Unresolved means unresolved.** A routine entry, descriptor-shaped record, literal match or fixture "
          "access does not certify every historical description. No-xref results do not establish unused RAM. "
          "The source column is a historical claim, not an endorsed label.", "", "## Structural coverage", "",
          "| Classification | Candidates |", "|---|---:|"]
    md += [f"| {key.replace('_',' ')} | {value} |" for key, value in sorted(counts.items())]
    md += ["", "## Review status", "", "| Status | Candidates |", "|---|---:|"]
    md += [f"| {key.replace('_',' ')} | {value} |" for key, value in sorted(semantics.items())]
    for title, predicate in (("RAM and peripheral candidates", lambda a: a >= 0xFFFF0000),
                             ("ROM, donor and numeric candidates", lambda a: a < 0xFFFF0000)):
        md += ["", "## " + title, "", "| Address | Structural evidence | Reviewed meaning / status | Source |", "|---|---|---|---|"]
        for row in rows:
            if not predicate(int(row["address"], 16)):
                continue
            review = row["semantic_review"]
            evidence = row["structural_class"].replace("_", " ")
            if row["mcp_references"]:
                evidence += f"; {len(row['mcp_references'])} xrefs"
            if row["captured_routine_instruction_addresses"]:
                evidence += (f"; {row['captured_routine_instruction_addresses']} instruction addresses; "
                             f"{row['main_fixture_visited_addresses_in_routine']} fixture visits")
            if row["main_fixture_accesses"]:
                widths = sorted({r["size"] for r in row["main_fixture_accesses"]})
                evidence += "; fixture sizes " + "/".join(map(str, widths))
            if row["definition_address_declarations"]:
                evidence += "; XML address declaration"
            meaning = review.get("meaning", row["ghidra_function_entry"] or "Meaning unresolved")
            source = row["claims"][0]
            link = "../../" + source["document"]
            revision = " at " + source["source_revision"] if source["source_revision"] != "working_tree" else ""
            md.append(f"| `{row['address']}` | {escaped(evidence)} | {escaped(meaning)} — "
                      f"{review['status'].replace('_',' ')} | [{escaped(source['document'])}]({link}) "
                      f"line {source['line']}{revision} |")
    (REF / "ADDRESS_INDEX.md").write_text("\n".join(md) + "\n")
    register = ["# Document retirement register", "", "[Reference home](README.md)", "",
                "**No document is approved for deletion.** The user must review the central replacement first. "
                "This register covers the original 44 Markdown documents outside the excluded adapter. "
                "Detailed execution proofs, wiring, source provenance and historical captures may remain useful even "
                "after their summary moves here. Any later removal must first check code links and retained unique evidence.", "",
                "Paths reflect the repository cleanup. Old component roots map to `patches/core`, "
                "`patches/speed_density`, `patches/fueling_safety` and `patches/wideband_o2`. The adapter tree is "
                "excluded and unchanged. V2 had no tracked Markdown documents at this baseline.", "",
                "| Existing document | Central destination | Proposed disposition | User review |", "|---|---|---|---|"]
    for doc in inventory["documents"]:
        path = doc["current_path"]
        disposition, destination = replacement(path)
        register.append(f"| [{path}](../../{path}) | [{destination}]({destination}) | {disposition} | Pending; retain |")
    register += ["", "The machine-readable inventory preserves each document's content hash and every extracted claim. "
                 "Historical errors are retained as history with retractions; central pages supply the corrected current "
                 "interpretation. Preservation does not mean those old claims remain valid."]
    (REF / "DOCUMENT_REGISTER.md").write_text("\n".join(register) + "\n")
    print(f"Reference index: {len(rows)} candidates; {dict(semantics)}")


if __name__ == "__main__":
    main()
