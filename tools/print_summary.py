import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.audit_all_tables import parse_all

tables = parse_all()
for t in tables:
    idx = t["idx"]
    name = t["name"]
    cat = t["category"]
    addr = t["addr_hex"]
    sx, sy = t["sizex"], t["sizey"]
    dim = f"{sx}x{sy}"
    vals = t["scaled"]
    units = t["units"]
    if t["states"]:
        val_str = f"Switch: states={t['states']}, raw=0x{t['raw'][0]:02X}"
    elif vals:
        val_str = f"min={min(vals):.3g}, max={max(vals):.3g} {units}"
    else:
        val_str = "no data"
    print(f"[{idx:3d}] {addr} | {cat:<36} | {dim:<6} | {name:<46} | {val_str}")
