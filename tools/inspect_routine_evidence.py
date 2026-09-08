#!/usr/bin/env python3
"""Print retained MCP routine evidence with literal values from pinned stock.

This is an inspection aid, not an instruction interpreter or automatic semantic
review. It never treats a pool value as a proven call/data reference.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs/reference/evidence"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("addresses", nargs="+")
    parser.add_argument("--brief", action="store_true", help="Pool/claim summary instead of full instructions")
    args = parser.parse_args()
    captures = json.loads((EVIDENCE / "ghidra_evidence.json").read_text())
    inventory = json.loads((EVIDENCE / "address_audit.json").read_text())
    stock = (ROOT / "2005 BLE MT.bin").read_bytes()
    assert hashlib.sha256(stock).hexdigest() == inventory["stock_sha256"]
    routines = {r["address"]: r for r in captures["records"] if r["kind"] == "routine_disassembly"}
    addresses = {r["address"]: r for r in inventory["addresses"]}
    for token in args.addresses:
        key = f"{int(token, 16):08X}"
        print("\nROUTINE", key, addresses.get(key, {}).get("ghidra_function_entry"))
        for claim in dict.fromkeys(c["claim"] for c in addresses.get(key, {}).get("claims", [])):
            print("CLAIM", claim)
        if key not in routines:
            print("No retained MCP disassembly at this exact entry")
            continue
        seen = set()
        for line in routines[key]["lines"]:
            annotation = ""
            match = re.match(r"[0-9a-f]{8}: _?(mov\.[wl]|mova) 0x([0-9a-f]+),", line, re.I)
            if match:
                operation, location = match[1], int(match[2], 16)
                if operation == "mova":
                    value = struct.unpack_from(">f", stock, location)[0]
                    annotation = f"[pool@{location:08X}: floatbits {stock[location:location+4].hex()} = {value:g}]"
                else:
                    value = int.from_bytes(stock[location:location+(2 if operation == "mov.w" else 4)], "big")
                    if operation == "mov.w" and value >= 0x8000:
                        value |= 0xFFFF0000
                    known = addresses.get(f"{value:08X}", {})
                    name = known.get("ghidra_function_entry") or known.get("semantic_review", {}).get("meaning", "")
                    annotation = f"[pool@{location:08X} = {value:08X} {name}]"
            if not args.brief:
                print(line, annotation)
            elif annotation and annotation not in seen:
                print(line.split(";", 1)[0], annotation)
                seen.add(annotation)


if __name__ == "__main__":
    main()
