import xml.etree.ElementTree as ET
import struct
import math
import sys

def parse_all():
    tree = ET.parse("master_patch_v2/D2WD610H_master_patch_v2.xml")
    root = tree.getroot()
    roms = root.findall("rom")
    base = roms[0]
    target = roms[1]

    base_defs = {t.attrib["name"]: t for t in base.findall("table") if "name" in t.attrib}
    with open("master_patch_v2/D2WD610H_master_patch_v2.bin", "rb") as f:
        rom_data = f.read()

    target_tables = target.findall("table")
    print(f"Total target tables found: {len(target_tables)}")

    results = []

    for idx, t in enumerate(target_tables):
        name = t.attrib.get("name")
        addr_hex = t.attrib.get("storageaddress")
        addr = int(addr_hex, 16) if addr_hex else 0
        bdef = base_defs.get(name)

        category = t.attrib.get("category") or (bdef.attrib.get("category") if bdef is not None else "Uncategorized")
        ttype = t.attrib.get("type") or (bdef.attrib.get("type") if bdef is not None else "2D")
        stype = t.attrib.get("storagetype") or (bdef.attrib.get("storagetype") if bdef is not None else "uint8")
        endian = t.attrib.get("endian") or (bdef.attrib.get("endian") if bdef is not None else "big")

        sizex = int(t.attrib.get("sizex") or (bdef.attrib.get("sizex") if bdef is not None else "1") or "1")
        sizey = int(t.attrib.get("sizey") or (bdef.attrib.get("sizey") if bdef is not None else "1") or "1")

        scaling_elem = t.find("scaling")
        if scaling_elem is None and bdef is not None:
            scaling_elem = bdef.find("scaling")

        units = scaling_elem.attrib.get("units", "") if scaling_elem is not None else ""
        expr = scaling_elem.attrib.get("expression", "x") if scaling_elem is not None else "x"

        # Check for Switch states
        states = t.findall("state")
        if not states and bdef is not None:
            states = bdef.findall("state")

        # Check axes
        x_elem = t.find("./table[@type='X Axis']")
        if x_elem is None and bdef is not None:
            x_elem = bdef.find("./table[@type='X Axis']")
        y_elem = t.find("./table[@type='Y Axis']")
        if y_elem is None and bdef is not None:
            y_elem = bdef.find("./table[@type='Y Axis']")

        # Helper to read values - SH7055 is strictly Big Endian hardware
        def read_data(offset, dtype, end, count):
            # On SH7055 (Subaru 32-bit), ROM storage is ALWAYS Big Endian regardless of XML typos
            fmt_map = {
                "uint8": ("B", 1),
                "int8": ("b", 1),
                "uint16": (">H", 2),
                "int16": (">h", 2),
                "uint32": (">I", 4),
                "int32": (">i", 4),
                "float": (">f", 4),
            }
            if dtype not in fmt_map:
                return [0] * count
            fmt_char, size = fmt_map[dtype]
            vals = []
            for i in range(count):
                pos = offset + i * size
                if pos + size <= len(rom_data):
                    val = struct.unpack(fmt_char, rom_data[pos:pos+size])[0]
                    vals.append(val)
                else:
                    vals.append(0)
            return vals

        def eval_scaling(raw_val, expression):
            x = raw_val
            safe_dict = {"x": x, "math": math}
            try:
                # replace common romraider tokens
                e = expression.replace("TO_HEX", "").replace("[", "").replace("]", "")
                return eval(e, {"__builtins__": None}, safe_dict)
            except Exception:
                return float(x)

        # Parse axis data
        def parse_axis(ax_elem, def_len):
            if ax_elem is None:
                return None
            ax_addr_hex = ax_elem.attrib.get("storageaddress")
            if not ax_addr_hex:
                return None
            ax_addr = int(ax_addr_hex, 16)
            ax_stype = ax_elem.attrib.get("storagetype", "float")
            ax_endian = ax_elem.attrib.get("endian", "little")
            ax_scaling = ax_elem.find("scaling")
            ax_expr = ax_scaling.attrib.get("expression", "x") if ax_scaling is not None else "x"
            ax_units = ax_scaling.attrib.get("units", "") if ax_scaling is not None else ""
            
            raw_vals = read_data(ax_addr, ax_stype, ax_endian, def_len)
            scaled_vals = [eval_scaling(v, ax_expr) for v in raw_vals]
            return {"addr": ax_addr, "units": ax_units, "raw": raw_vals, "scaled": scaled_vals}

        x_axis = parse_axis(x_elem, sizex)
        y_axis = parse_axis(y_elem, sizey)

        # Read main data
        count = sizex * sizey
        raw_vals = read_data(addr, stype, endian, count)
        scaled_vals = [eval_scaling(v, expr) for v in raw_vals]

        results.append({
            "idx": idx + 1,
            "name": name,
            "category": category,
            "addr": addr,
            "addr_hex": f"0x{addr:05X}",
            "type": ttype,
            "stype": stype,
            "endian": endian,
            "sizex": sizex,
            "sizey": sizey,
            "units": units,
            "expr": expr,
            "states": [(s.attrib.get("name"), s.attrib.get("data")) for s in states] if states else [],
            "x_axis": x_axis,
            "y_axis": y_axis,
            "raw": raw_vals,
            "scaled": scaled_vals
        })

    return results

if __name__ == "__main__":
    res = parse_all()
    print(f"Successfully processed {len(res)} tables.")
    for r in res[:10]:
        print(f"Table #{r['idx']}: {r['name']} ({r['category']}) @ {r['addr_hex']} [{r['sizex']}x{r['sizey']}]")
        if r['scaled']:
            print(f"   Values (sample): {r['scaled'][:5]} min={min(r['scaled']):.2f} max={max(r['scaled']):.2f} units={r['units']}")
