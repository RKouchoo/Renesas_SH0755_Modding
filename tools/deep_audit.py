import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.audit_all_tables import parse_all

tables = parse_all()

def analyze_table(t):
    idx = t["idx"]
    name = t["name"]
    cat = t["category"]
    addr = t["addr_hex"]
    sx, sy = t["sizex"], t["sizey"]
    vals = t["scaled"]
    units = t["units"]
    x_ax = t["x_axis"]
    y_ax = t["y_axis"]
    
    # Specific checks
    abnormalities = []
    
    # Check 1: Base Timing
    if "Base Timing" in name and "Idle" not in name:
        # Check high load column timing
        # x_axis is Load, y_axis is RPM
        if x_ax and y_ax:
            # Look at loads >= 1.5 g/rev
            for col_idx, load in enumerate(x_ax["scaled"]):
                if load >= 1.5:
                    col_vals = [vals[row * sx + col_idx] for row in range(sy)]
                    max_t = max(col_vals)
                    if max_t > 18.0:
                        abnormalities.append(f"High timing under boost: {max_t:.1f} deg at {load:.2f} g/rev (dangerously advanced for 10.7:1 turbo on 98 RON)")
    
    # Check 2: Primary Open Loop Fueling
    if "Primary Open Loop Fueling" in name:
        if x_ax and y_ax:
            for col_idx, load in enumerate(x_ax["scaled"]):
                if load >= 1.5:
                    col_vals = [vals[row * sx + col_idx] for row in range(sy)]
                    max_afr = max(col_vals)
                    if max_afr > 12.2:
                        abnormalities.append(f"Lean target under boost: {max_afr:.2f} AFR at {load:.2f} g/rev (turbo should be <= 11.8)")

    # Check 3: Load limit
    if "Engine Load Limit" in name:
        for v in vals:
            if v < 2.5:
                abnormalities.append(f"Engine Load Limit {v:.2f} g/rev is too low for turbo boost (will clip load)")

    # Check 4: Rev limits
    if "Rev Limit" in name:
        for v in vals:
            if v > 7200:
                abnormalities.append(f"Rev limit {v:.0f} RPM exceeds safe EZ30 valvetrain/rod limit for boost")

    # Check 5: Overboost fuel cut
    if "Boost Overboost Fuel Cut" in name:
        for v in vals:
            if v > 15.0:
                abnormalities.append(f"Overboost fuel cut {v:.1f} psi is dangerously high for 10.7:1 stock block on 5 psi spring")

    # Check 6: A/F Learning Airflow Ranges
    if "A/F Learning Airflow Ranges" in name:
        # Check range D threshold
        if vals[-1] < 100.0:
            abnormalities.append(f"A/F Learning Range D upper threshold {vals[-1]:.1f} g/s allows trims to affect boost/WOT")

    # Check 7: Tip-in enrichment
    if "Throttle Tip-in Enrichment" in name:
        max_tip = max(vals)
        if max_tip > 15.0:
            abnormalities.append(f"Excessive tip-in {max_tip:.1f} ms will cause rich stumbling")
        elif max_tip < 1.0:
            abnormalities.append(f"Low tip-in {max_tip:.1f} ms may cause tip-in hesitation on turbo charge piping")

    # Check 8: VE tables
    if "Speed Density VE" in name:
        if min(vals) < 0.2:
            abnormalities.append(f"VE floor {min(vals):.3f} is abnormally low, risks extreme lean cut on decel")
        if max(vals) > 1.8:
            abnormalities.append(f"VE ceiling {max(vals):.3f} is abnormally high")

    # Check 9: Knock correction advance
    if "Knock Correction Advance Max" in name:
        if x_ax and y_ax:
            for col_idx, load in enumerate(x_ax["scaled"]):
                if load >= 1.5:
                    col_vals = [vals[row * sx + col_idx] for row in range(sy)]
                    max_kca = max(col_vals)
                    if max_kca > 8.0:
                        abnormalities.append(f"KCA {max_kca:.1f} deg at {load:.2f} g/rev gives excessive IAM swing under boost")

    # Check 10: Fine correction load range
    if name == "Fine Correction Range (Load)":
        if vals[1] < 2.0:
            abnormalities.append(f"Fine correction load ceiling {vals[1]:.2f} g/rev stops learning below full boost load")

    # Check 11: Rough correction load range
    if name == "Rough Correction Range (Load)":
        if vals[1] < 2.0:
            abnormalities.append(f"Rough correction load ceiling {vals[1]:.2f} g/rev stops IAM learning below full boost load")

    # Check 12: AVCS Target
    if "Intake AVCS Target" in name:
        if x_ax and y_ax:
            for col_idx, load in enumerate(x_ax["scaled"]):
                if load >= 1.5:
                    col_vals = [vals[row * sx + col_idx] for row in range(sy)]
                    max_avcs = max(col_vals)
                    if max_avcs > 25.0:
                        abnormalities.append(f"High intake cam advance {max_avcs:.1f} deg under boost ({load:.2f} g/rev) causes excessive valve overlap and reversion against turbine backpressure")

    return abnormalities

print("Running automated sanity check on all 146 tables...")
issues_found = 0
for t in tables:
    ab = analyze_table(t)
    if ab:
        issues_found += 1
        print(f"[{t['idx']:3d}] {t['name']}:")
        for a in ab:
            print(f"     * ALERT: {a}")

if issues_found == 0:
    print("No immediate out-of-range critical alerts found in initial threshold check.")
else:
    print(f"Total tables with alerts: {issues_found}")
