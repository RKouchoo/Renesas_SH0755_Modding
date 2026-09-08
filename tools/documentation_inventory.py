#!/usr/bin/env python3
"""Inventory historical documentation claims without equating a label with proof.

Reads the Ghidra MCP snapshot and saved stock ROM; never connects to an ECU.
The semantic review ledger is maintained separately from mechanical evidence.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "docs/reference"
SNAPSHOT = REFERENCE / "evidence/ghidra_snapshot.json"
BASELINE = "2d95301"
MOVES = {
    "patch": "patches/core",
    "speed_density": "patches/speed_density",
    "fueling_safety": "patches/fueling_safety",
    "wideband_o2": "patches/wideband_o2",
}
EXPLICIT = re.compile(r"\b(?:0[xX][0-9a-fA-F]{4,8}|[fF]{4}[0-9a-fA-F]{4})\b")
SHORT = re.compile(r"(?<![\w])(?:[0-9a-fA-F]{4,5}|[fF]{2}[0-9a-fA-F]{4})(?![\w])")


def current_path(name: str) -> Path:
    path = Path(name)
    if path.parts[0] in MOVES:
        return Path(MOVES[path.parts[0]]).joinpath(*path.parts[1:])
    return path


def address_tokens(line: str, function_addresses=()):
    """Keep ambiguous abbreviated hex separate from explicit addresses."""
    for match in EXPLICIT.finditer(line):
        yield match.group(), int(match.group(), 16), "explicit_hex"
    # Expand explicitly RAM-qualified slash lists, including BE14/16/18.
    for group in re.finditer(r"0xFFFF[0-9A-Fa-f]{4}(?:(?:/|\s*/\s*|–|\.\.)[0-9A-Fa-f]{2,4})+", line):
        base = int(group.group()[:10], 16)
        for token in re.findall(r"(?:/|–|\.\.)\s*([0-9A-Fa-f]{2,4})", group.group()[10:]):
            value = (base & (0xFFFFFF00 if len(token) == 2 else 0xFFFF0000)) | int(token, 16)
            yield token, value, "ram_qualified_continuation"
    for code in re.findall(r"`([^`]+)`", line):
        if re.search(r"\bB13[4-6]-\d", code) or re.fullmatch(r"(?:[0-9A-F]{4}\s*){2,}", code):
            continue  # Connector names and raw-word dumps are not RAM addresses.
        for match in SHORT.finditer(code):
            token = match.group()
            # Plain decimal numbers, dates and units are not address claims.
            if not re.search(r"[a-fA-F]", token):
                continue
            value = int(token, 16)
            if token.lower().startswith("ff") and len(token) == 6:
                yield token, value | 0xFF000000, "ssm_24_bit_or_abbreviated"
            elif token.upper() == "B45C":
                yield token, value | 0xFFFF0000, "abbreviated_ram_candidate"
            elif len(token) == 4 and value in function_addresses:
                yield token, value, "abbreviated_rom_function_candidate"
            elif len(token) == 4 and token.upper() == "D390" and "CMT1" in line:
                yield token, value, "abbreviated_rom_internal_entry"
            elif len(token) == 4 and 0x8000 <= value <= 0xDFFF:
                yield token, value | 0xFFFF0000, "abbreviated_ram_candidate"
            elif len(token) == 5 and value < 0x80000:
                yield token, value, "abbreviated_rom_candidate"
            elif len(token) == 4 and value < 0x8000:
                yield token, value, "abbreviated_rom_or_constant"


def region(address: int) -> str:
    if 0 <= address < 0x80000:
        return "saved_flash"
    if 0xFFFF6000 <= address <= 0xFFFFDFFF:
        return "on_chip_ram"
    if 0xFFFFE000 <= address <= 0xFFFFFFFF:
        return "peripheral_or_reserved_check_register_map"
    return "outside_verified_flash_and_ram_or_literal_constant"


def main() -> None:
    snapshot = json.loads(SNAPSHOT.read_text())
    stock = (ROOT / "2005 BLE MT.bin").read_bytes()
    assert hashlib.sha256(stock).hexdigest() == snapshot["stock_sha256"]
    functions = {}
    for line in snapshot["functions"]:
        match = re.fullmatch(r"(.+) at ([0-9a-fA-F]{8})", line)
        if match:
            functions[int(match[2], 16)] = match[1]
    data = defaultdict(list)
    for line in snapshot["data"]:
        match = re.match(r"([0-9a-fA-F]{8}): (.*)", line)
        if match:
            data[int(match[1], 16)].append(match[2])

    document_names = [name for name in subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", BASELINE], cwd=ROOT, text=True
    ).splitlines() if name.endswith(".md")]
    documents = []
    claims = defaultdict(list)
    for old in document_names:
        if old.startswith(("pico_kline_adapter/", "docs/reference/")) or old in (
            "patches/README.md", "tests/README.md"
        ):
            continue
        path = current_path(old)
        raw = (ROOT / path).read_bytes()
        lines = raw.decode("utf-8").splitlines()
        baseline_raw = subprocess.check_output(
            ["git", "show", f"{BASELINE}:{old}"], cwd=ROOT
        )
        documents.append({
            "original_path": old, "current_path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(), "lines": len(lines),
            "baseline_sha256": hashlib.sha256(baseline_raw).hexdigest(),
        })
        current_claims = set()
        for revision, source_lines in (("working_tree", lines),
                                       (BASELINE, baseline_raw.decode("utf-8").splitlines())):
            section = ""
            for number, line in enumerate(source_lines, 1):
                if line.startswith("#"):
                    section = line.lstrip("# ")
                seen = set()
                for token, address, notation in address_tokens(line, functions):
                    key = (address, notation)
                    identity = (address, notation, line.strip())
                    if key in seen or (revision == BASELINE and identity in current_claims):
                        continue
                    seen.add(key)
                    if revision == "working_tree":
                        current_claims.add(identity)
                    claims[address].append({
                        "document": str(path), "line": number, "section": section,
                        "token": token, "notation": notation, "claim": line.strip(),
                        "source_revision": revision,
                    })

    literal32 = defaultdict(list)
    literal16 = defaultdict(list)
    for offset in range(0, len(stock) - 3, 2):
        word = struct.unpack_from(">I", stock, offset)[0]
        if word in claims:
            literal32[word].append(f"{offset:08X}")
        short = struct.unpack_from(">H", stock, offset)[0]
        if short >= 0x8000 and (short | 0xFFFF0000) in claims:
            literal16[short | 0xFFFF0000].append(f"{offset:08X}")

    reviewed_path = REFERENCE / "evidence/reviewed_addresses.json"
    reviewed = json.loads(reviewed_path.read_text()) if reviewed_path.exists() else {}
    records = []
    for address, occurrences in sorted(claims.items()):
        key = f"{address:08X}"
        records.append({
            "address": key, "region": region(address),
            "ghidra_function_entry": functions.get(address),
            "ghidra_data": data[address],
            "stock_bytes": stock[address:address + 16].hex() if address < len(stock) else None,
            "possible_32bit_literal_offsets": literal32[address],
            "possible_sign_extended_16bit_literal_offsets": literal16[address],
            "claims": occurrences,
            "semantic_review": reviewed.get(key, {"status": "pending", "note":
                "An address, literal match or existing Ghidra name alone does not verify its meaning."}),
        })
    output = REFERENCE / "evidence/documentation_inventory.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "stock_sha256": snapshot["stock_sha256"],
        "baseline_commit": BASELINE,
        "documents": documents,
        "addresses": records,
        "limits": [
            "Candidate extraction covers explicit hex, selected inline abbreviations and RAM-qualified continuations; implicit prose and unqualified short numbers need separate review.",
            "Abbreviated hex may be a constant or opcode; its notation is retained for review.",
            "Literal matches are candidates, not executable cross-references.",
            "Existing Ghidra symbols may themselves reflect a historical misidentification.",
            "Every occurrence remains linked to its source; contradictions must be resolved per image and context.",
            "Claims changed or removed during this audit are retained from the pinned baseline with baseline line numbers; other source locations refer to the working-tree document hash.",
        ],
    }, indent=2) + "\n")
    print(f"Inventoried {len(documents)} documents, {len(records)} address candidates, "
          f"{sum(len(v) for v in claims.values())} occurrences")
    print(output)


if __name__ == "__main__":
    main()
