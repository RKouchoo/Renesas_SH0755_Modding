import os
import sys
import struct
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.audit_all_tables import parse_all

tables = parse_all()

# Table documentation database mapping table names or indices to specific analysis
# Let us structure this systematically.

def format_grid(t):
    sx = t["sizex"]
    sy = t["sizey"]
    vals = t["scaled"]
    x_ax = t["x_axis"]
    y_ax = t["y_axis"]
    
    if sx == 1 and sy == 1:
        return f"`{vals[0]:.4g} {t['units']}`"
    
    if sx > 1 and sy == 1:
        s = "[" + ", ".join([f"{v:.4g}" for v in vals]) + f"] {t['units']}"
        if x_ax:
            s += "\n  * X Axis (" + x_ax['units'] + "): [" + ", ".join([f"{v:.4g}" for v in x_ax['scaled']]) + "]"
        return s

    if sx == 1 and sy > 1:
        # 1D vector (often 1xN)
        s = "[" + ", ".join([f"{v:.4g}" for v in vals]) + f"] {t['units']}"
        if y_ax:
            s += "\n  * Y Axis (" + y_ax['units'] + "): [" + ", ".join([f"{v:.4g}" for v in y_ax['scaled']]) + "]"
        return s
        
    # 2D table (sx cols x sy rows)
    out = []
    if x_ax and y_ax:
        header = "| RPM \\ Load | " + " | ".join([f"{v:.2f}" for v in x_ax["scaled"][:10]])
        if sx > 10:
            header += " | ... |"
        else:
            header += " |"
        sep = "|:---| " + " | ".join([":---:" for _ in range(min(sx, 10))])
        if sx > 10:
            sep += " |:---:|"
        else:
            sep += " |"
        out.append(header)
        out.append(sep)
        for r_i in range(min(sy, 12)):
            row_y = y_ax["scaled"][r_i]
            row_str = f"| **{row_y:.0f}** | " + " | ".join([f"{vals[r_i * sx + c_i]:.2f}" for c_i in range(min(sx, 10))])
            if sx > 10:
                row_str += " | ... |"
            else:
                row_str += " |"
            out.append(row_str)
        if sy > 12:
            out.append(f"| ... ({sy} rows total) | ... |")
        return "\n" + "\n".join(out)
    else:
        return f"{sx}x{sy} matrix, min={min(vals):.3g}, max={max(vals):.3g} {t['units']}"

print("Helper format_grid ready.")
