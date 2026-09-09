import csv
import math
import sys
from collections import defaultdict

def analyze_log(filename):
    with open(filename, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} rows from {filename}")
    if not rows:
        return

    # Columns
    # 'Time (msec)', 'Accelerator Pedal Angle (%)', 'Engine Speed (rpm)',
    # 'External Wideband AFR (D2WD610H master)* (estimated AFR (14.64 stoich))',
    # 'Final Fueling Base (4-byte)* (fuel-air equivalence ratio)',
    # 'Fuel Injector #1 Pulse Width (4-byte)* (ms)',
    # 'Manifold Absolute Pressure (kPa)', 'Coolant Temperature (C)',
    # 'Transient Load Fuel Correction (D2WD610H diagnostic)* (raw additive factor)'

    ve_map_bins = [150, 250, 350, 450, 550, 650, 760, 850, 1000, 1150, 1300, 1400, 1500] # mmHg
    ve_map_kpa = [round(m / 7.5006168, 1) for m in ve_map_bins]
    low_rpm_bins = [400, 800, 1200, 1600, 2000, 2400, 2800, 3200, 3600]
    high_rpm_bins = [1200, 1600, 2000, 2400, 2800, 3200, 3600, 4000, 4800, 5600, 6400]

    # Collect steady-state points
    low_cam_cells = defaultdict(list)
    high_cam_cells = defaultdict(list)

    valid_points = 0
    dfco_points = 0
    transient_points = 0

    prev_time = 0
    prev_pedal = 0.0

    for r in rows:
        try:
            t_ms = float(r.get('Time (msec)', 0))
            rpm = float(r.get('Engine Speed (rpm)', 0))
            pedal = float(r.get('Accelerator Pedal Angle (%)', 0))
            wb_afr = float(r.get('External Wideband AFR (D2WD610H master)* (estimated AFR (14.64 stoich))', 0))
            eq_ratio = float(r.get('Final Fueling Base (4-byte)* (fuel-air equivalence ratio)', 0))
            pw = float(r.get('Fuel Injector #1 Pulse Width (4-byte)* (ms)', 0))
            map_kpa = float(r.get('Manifold Absolute Pressure (kPa)', 0))
            ect = float(r.get('Coolant Temperature (C)', 0))
            trans = float(r.get('Transient Load Fuel Correction (D2WD610H diagnostic)* (raw additive factor)', 0))
        except (ValueError, TypeError):
            continue

        # Filters
        if rpm < 500:
            continue
        if pw < 0.5 or eq_ratio <= 0.0:
            dfco_points += 1
            continue
        if wb_afr < 9.5 or wb_afr > 19.5:
            continue
        
        # dPedal / dt
        dt = (t_ms - prev_time) / 1000.0 if prev_time > 0 else 0.1
        dpedal = abs(pedal - prev_pedal) / dt if dt > 0 else 0.0
        prev_time = t_ms
        prev_pedal = pedal

        if dpedal > 20.0 or abs(trans) > 0.03:
            transient_points += 1
            continue

        valid_points += 1
        target_afr = 14.64 / eq_ratio if eq_ratio > 0 else 14.64
        afr_error_pct = ((wb_afr - target_afr) / target_afr) * 100.0

        # Convert MAP to nearest bin
        map_mmhg = map_kpa * 7.5006168
        nearest_map_bin = min(ve_map_bins, key=lambda b: abs(b - map_mmhg))

        # Check cam mode (AVLS switches at 3200 RPM in patch v2)
        if rpm < 3200:
            nearest_rpm_bin = min(low_rpm_bins, key=lambda b: abs(b - rpm))
            low_cam_cells[(nearest_map_bin, nearest_rpm_bin)].append((wb_afr, target_afr, afr_error_pct, map_kpa, rpm))
        else:
            nearest_rpm_bin = min(high_rpm_bins, key=lambda b: abs(b - rpm))
            high_cam_cells[(nearest_map_bin, nearest_rpm_bin)].append((wb_afr, target_afr, afr_error_pct, map_kpa, rpm))

    print(f"Total valid steady-state samples: {valid_points} (Filtered out {dfco_points} DFCO, {transient_points} transients)")

    print("\n================== LOW-CAM VE ANALYSIS (< 3200 RPM) ==================")
    print("Cells with >= 5 repeat samples:")
    print(f"{'MAP bin':<10} {'RPM bin':<10} {'Samples':<8} {'Avg AFR':<10} {'Target AFR':<12} {'AFR Error %':<14} {'Recommended VE Adj'}")
    print("-" * 80)
    for (m_bin, r_bin), samples in sorted(low_cam_cells.items(), key=lambda x: (x[0][1], x[0][0])):
        if len(samples) >= 5:
            avg_afr = sum(s[0] for s in samples) / len(samples)
            avg_tgt = sum(s[1] for s in samples) / len(samples)
            avg_err = sum(s[2] for s in samples) / len(samples)
            # If AFR is leaner than target (avg_err > 0), VE must be INCREASED
            adj_str = f"+{avg_err:.1f}%" if avg_err > 0 else f"{avg_err:.1f}%"
            print(f"{m_bin} mmHg   {r_bin} RPM    {len(samples):<8} {avg_afr:<10.2f} {avg_tgt:<12.2f} {avg_err:<+13.2f}% {adj_str}")

    print("\n================== HIGH-CAM VE ANALYSIS (>= 3200 RPM) ==================")
    print("Cells with >= 5 repeat samples:")
    print(f"{'MAP bin':<10} {'RPM bin':<10} {'Samples':<8} {'Avg AFR':<10} {'Target AFR':<12} {'AFR Error %':<14} {'Recommended VE Adj'}")
    print("-" * 80)
    high_count = 0
    for (m_bin, r_bin), samples in sorted(high_cam_cells.items(), key=lambda x: (x[0][1], x[0][0])):
        if len(samples) >= 5:
            high_count += 1
            avg_afr = sum(s[0] for s in samples) / len(samples)
            avg_tgt = sum(s[1] for s in samples) / len(samples)
            avg_err = sum(s[2] for s in samples) / len(samples)
            adj_str = f"+{avg_err:.1f}%" if avg_err > 0 else f"{avg_err:.1f}%"
            print(f"{m_bin} mmHg   {r_bin} RPM    {len(samples):<8} {avg_afr:<10.2f} {avg_tgt:<12.2f} {avg_err:<+13.2f}% {adj_str}")
    if high_count == 0:
        print("No cells with >= 5 samples (check if log stayed mostly < 3200 RPM). Listing cells with >= 1 sample:")
        for (m_bin, r_bin), samples in sorted(high_cam_cells.items(), key=lambda x: (x[0][1], x[0][0])):
            avg_afr = sum(s[0] for s in samples) / len(samples)
            avg_tgt = sum(s[1] for s in samples) / len(samples)
            avg_err = sum(s[2] for s in samples) / len(samples)
            adj_str = f"+{avg_err:.1f}%" if avg_err > 0 else f"{avg_err:.1f}%"
            print(f"{m_bin} mmHg   {r_bin} RPM    {len(samples):<8} {avg_afr:<10.2f} {avg_tgt:<12.2f} {avg_err:<+13.2f}% {adj_str}")

if __name__ == "__main__":
    fn = "logs/romraiderlog_patchv2_5_20260909_182732.csv"
    if len(sys.argv) > 1:
        fn = sys.argv[1]
    analyze_log(fn)
