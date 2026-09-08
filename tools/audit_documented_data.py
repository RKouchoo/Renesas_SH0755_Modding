#!/usr/bin/env python3
"""Decode reviewed table schemas, never infer a schema from shape alone.

The explicit schemas below were selected from retained MCP caller/callee
instructions. The output is a saved-image data audit, not an execution trace.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs/reference/evidence"

# address, native ABI, caller/consumer, scoped meaning
TABLES = [
    (0x5EA2C, "typed1", "18DDE/209C", "Front lambda atmospheric gain"),
    (0x5EB6C, "typed2", "172A4/2150", "Coolant airflow compensation"),
    (0x5EB88, "typed2", "172A4/2150", "IAT airflow compensation"),
    (0x5ECC8, "typed2", "1BCEA/2150", "CPC requested-flow to duty conversion"),
    (0x5ECE4, "typed2", "1BC78/1BC9C/1BCBA/2150", "CPC inverse duty to flow conversion"),
    (0x5F21C, "raw8", "1E368/20E0", "After-start group A counter increment"),
    (0x5F2E8, "typed1", "20564/209C", "Legacy O2 voltage threshold"),
    (0x5F470, "typed1", "23D34/209C", "Fuel pressure gain from barometric minus MAP pressure"),
    (0x5F564, "typed1", "1E180/209C", "After-start group A initial factor by coolant"),
    (0x5F61C, "typed1", "1E982/209C", "Slow negative transient coolant factor"),
    (0x5F6BC, "typed1", "1E98C/209C", "Slow negative transient RPM factor"),
    (0x5F8FC, "raw16", "22A10/2118", "CL transition atmospheric delay counts"),
    (0x5FA9C, "typed2", "22454/2150", "Primary open-loop target bank A"),
    (0x5FAB8, "typed2", "22454/2150", "Primary open-loop target bank B"),
    (0x5FB78, "typed1", "2777C/209C", "Final timing minimum by RPM"),
    (0x5FB8C, "typed1", "2777C/209C", "Final timing minimum by coolant"),
    (0x5FC18, "typed1", "28776/209C", "Base timing coolant floor"),
    (0x5FFF8, "raw16", "28204/2118", "Timing-map transition delay counts by RPM"),
    *[(a, "typed2", "28418/2150", f"Base timing {letter}") for a, letter in
      zip(range(0x60108, 0x601B0, 0x1C), "ABCDEF")],
    (0x6041C, "typed1", "2BD5C/209C", "First coolant idle-target table"),
    (0x607D4, "typed2", "2AF5C/2150", "DBW target throttle A"),
    (0x607F0, "typed2", "2B35A/2150", "DBW inverse throttle target B"),
    (0x608D8, "raw16", "98D0/2118", "Injector latency counts by battery voltage"),
    (0x60914, "typed1", "7C30/209C", "Stock raw MAF transfer, scheduled calls retired in main/v2"),
    (0x60950, "typed1", "F474/209C", "Oil thermistor voltage to degrees C"),
    (0x609B8, "typed1", "7898/209C", "IAT transfer; installed curve requires physical sensor match"),
    (0x609C4, "typed1", "3FC68/3FCF6/209C", "Radiator fan coolant to percent table"),
    (0x609D8, "typed1", "3FCDC/209C", "Radiator fan alternate coolant to percent table"),
    (0x609EC, "typed1", "3387C/209C", "Startup auxiliary duty by B3B0; physical output identity unresolved"),
    (0x60C34, "typed2", "353B0/2150", "Intake AVCS target in committed AVLS mode 1"),
    (0x60C50, "typed2", "353B0/2150", "Intake AVCS target in committed AVLS mode 3"),
    (0x60F58, "typed1", "40168/209C", "Normal AVLS switch pedal threshold by RPM"),
    (0x60F64, "typed1", "40168/209C", "Hot-oil AVLS switch pedal threshold by RPM"),
    (0x7D7CC, "typed1", "retired boost component/209C", "Retained, inactive boost target descriptor"),
]

# These formats are selected from native access widths or the patch builder.
# Include arrays when adjacent values are part of one reviewed contract.
SCALARS = {
    **{int(a, 16): "f" for a in """
        2A5FC 2A60C 2A610 73984 73B88 73B8C 748AC 76014 760F0 760F4
        7611C 76374 763DC 763E0 77E1C 77EC4 77ED0 7959C 7963C
        7D800 7D804 7D808 7D8C0 7DD0C 7E404 7E408 7E40C 7EAD0
    """.split()},
    **{int(a, 16): "H" for a in """
        72808 72818 737DC 737FA 74D44 75E5E 75E86 75E8E
        77D34 77D44 77D46 794DA 7BE3E 7D468
    """.split()},
    **{int(a, 16): "B" for a in """
        5BD57 5BD58 5BD6C 5BD70 5BDAF 5BDB0 5BDB8 5BDBB
        737D9 75E1B 75E2B 7952C 7952D 7D80C 7D80D 7EACC 7EACD
    """.split()},
    0x73974: "4f", 0x76384: "2f", 0x7644C: "4f", 0x77EBC: "2f",
    0x77EC8: "2f", 0x7828F: "9B", 0x78298: "9B", 0x782AC: "2B",
    0x7B270: "4H", 0x7B284: "2H", 0x7B29C: "2H", 0x7D480: "2f",
    0x7D488: "4f", 0x7D49C: "9f", 0x7D7C4: "8B",
    0x7DB44: "10f", 0x7DB6C: "6f",
}


def decode(blob, address, schema):
    nx = struct.unpack_from(">H", blob, address)[0]
    two_axes = schema == "typed2"
    ny = struct.unpack_from(">H", blob, address + 2)[0] if two_axes else 1
    assert 1 <= nx <= 256 and 1 <= ny <= 256
    axes = [struct.unpack_from(">I", blob, address + 4)[0]]
    if two_axes:
        axes.append(struct.unpack_from(">I", blob, address + 8)[0])
    data_address = struct.unpack_from(">I", blob, address + (12 if two_axes else 8))[0]
    stored_type = blob[address + (16 if two_axes else 2)]
    if schema in ("raw8", "raw16"):
        fmt, scale, offset = ("B" if schema == "raw8" else "H"), 1.0, 0.0
        length = 12
    else:
        fmt = {0: "f", 4: "B", 8: "H", 12: "b", 16: "h"}[stored_type]
        length = (20 if two_axes else 12) + (8 if stored_type else 0)
        scale, offset = (struct.unpack_from(">ff", blob, address + (20 if two_axes else 12))
                         if stored_type else (1.0, 0.0))
    raw = list(struct.unpack_from(f">{nx*ny}{fmt}", blob, data_address))
    axis_values = []
    for location, count in zip(axes, [nx, ny]):
        values = list(struct.unpack_from(f">{count}f", blob, location))
        assert all(a < b for a, b in zip(values, values[1:]))
        axis_values.append({"address": f"{location:08X}", "values": values})
    return {"descriptor_bytes": blob[address:address+length].hex(), "length": length,
            "stored_type_byte": stored_type, "effective_format": fmt,
            "shape": [ny, nx] if two_axes else [nx], "axes": axis_values,
            "data_address": f"{data_address:08X}", "raw_values": raw,
            "scale": scale, "offset": offset,
            "scaled_values": [v * scale + offset for v in raw]}


def main():
    pins = json.loads((EVIDENCE / "image_contracts.json").read_text())["images"]
    images = {name: (ROOT / p["path"]).read_bytes() for name, p in pins.items()}
    for name, blob in images.items():
        assert hashlib.sha256(blob).hexdigest() == pins[name]["sha256"]
    tables = []
    for address, schema, caller, meaning in TABLES:
        tables.append({"address": f"{address:08X}", "schema": schema,
                       "native_caller_or_component": caller, "meaning": meaning,
                       "images": {name: decode(blob, address, schema)
                                  for name, blob in images.items()
                                  if address < 0x7D7CC or name != "stock"}})
    output = {"images": pins, "method": "Explicit reviewed schemas with saved big-endian bytes",
              "limits": ["Raw entry points ignore the stored type byte and have no scale/offset fields.",
                         "Scaled values are host arithmetic, not simulated FPU interpolation.",
                         "Caller claims are scoped to retained instruction reviews, not physical calibration validation."],
              "tables": tables}
    (EVIDENCE / "documented_data.json").write_text(json.dumps(output, indent=2) + "\n")
    scalars = []
    for address, fmt in sorted(SCALARS.items()):
        size = struct.calcsize(">" + fmt)
        scalars.append({"address": f"{address:08X}", "format": fmt,
                        "images": {name: {"bytes": blob[address:address+size].hex(),
                                          "values": list(struct.unpack_from(">"+fmt, blob, address))}
                                   for name, blob in images.items()
                                   if address < 0x7D790 or name != "stock"}})
    (EVIDENCE / "documented_scalars.json").write_text(json.dumps(
        {"images": pins, "scalars": scalars,
         "limits": ["Selected formats are reviewed access widths, not value-shape guesses.",
                    "Stock free-tail bytes are excluded from scalar interpretation.",
                    "Physical sensor and actuator calibration accuracy is not established by these bytes."]},
        indent=2, allow_nan=False) + "\n")
    print(f"Decoded {len(tables)} explicitly reviewed lookup records across three pinned images.")
    print(f"Decoded {len(scalars)} reviewed scalar/array records with exact image bytes.")


if __name__ == "__main__":
    main()
