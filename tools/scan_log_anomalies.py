import csv
import math

def scan_anomalies(log_file):
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        rows = list(csv.DictReader(f))

    print(f"Loaded {len(rows)} rows from {log_file}")

    anomalies = []
    
    # Track statistics
    min_volt = 99.0
    max_volt = 0.0
    low_volt_frames = 0
    
    min_ect = 999.0
    max_ect = -999.0
    
    max_rpm = 0
    max_map_kpa = 0
    min_map_kpa = 999
    
    max_pw = 0.0
    max_duty = 0.0
    
    timing_pulls = 0
    min_timing = 99.0
    
    throttle_lag_frames = 0
    dbw_mismatch = 0
    
    idle_rpm_diffs = []
    idle_hunting_frames = 0
    
    transient_spikes = 0

    for idx, r in enumerate(rows):
        try:
            t_ms = float(r.get('Time (msec)', 0))
            rpm = float(r.get('Engine Speed (rpm)', 0))
            pedal = float(r.get('Accelerator Pedal Angle (%)', 0))
            req_thr = float(r.get('Combined Throttle Request (D2WD610H diagnostic)* (%)', 0))
            thr = float(r.get('Throttle Opening Angle (%)', 0))
            wb_afr = float(r.get('External Wideband AFR (D2WD610H master)* (estimated AFR (14.64 stoich))', 0))
            pw = float(r.get('Fuel Injector #1 Pulse Width (4-byte)* (ms)', 0))
            map_kpa = float(r.get('Manifold Absolute Pressure (kPa)', 0))
            ect = float(r.get('Coolant Temperature (C)', 0))
            iat = float(r.get('Intake Air Temperature (C)', 0))
            volt = float(r.get('Battery Voltage (V)', 0))
            timing = float(r.get('Ignition Total Timing (degrees)', 0))
            idle_tgt = float(r.get('Effective Idle Speed Target (D2WD610H diagnostic)* (rpm)', 0))
            trans = float(r.get('Transient Load Fuel Correction (D2WD610H diagnostic)* (raw additive factor)', 0))
        except (ValueError, TypeError):
            continue

        if volt > 0:
            min_volt = min(min_volt, volt)
            max_volt = max(max_volt, volt)
            if volt < 12.0 and rpm > 600:
                low_volt_frames += 1

        min_ect = min(min_ect, ect)
        max_ect = max(max_ect, ect)
        max_rpm = max(max_rpm, rpm)
        max_map_kpa = max(max_map_kpa, map_kpa)
        if map_kpa > 0:
            min_map_kpa = min(min_map_kpa, map_kpa)

        # Pulse width & duty cycle: for 4-stroke, injector fires once per 2 revs
        # Period for 2 revs (ms) = (120 / rpm) * 1000 = 120,000 / rpm
        if rpm > 600 and pw > 0:
            duty = (pw / (120000.0 / rpm)) * 100.0
            max_pw = max(max_pw, pw)
            max_duty = max(max_duty, duty)

        # Timing
        if rpm > 600:
            min_timing = min(min_timing, timing)
            # Check for sudden timing dips under load
            if timing < 5.0 and map_kpa > 50:
                timing_pulls += 1

        # DBW tracking
        if pedal > 2.0:
            # If throttle plate lags pedal by > 15% in steady-state
            if abs(pedal - thr) > 25.0:
                dbw_mismatch += 1

        # Idle tracking
        if pedal == 0.0 and rpm > 500 and rpm < 1500 and idle_tgt > 500:
            diff = abs(rpm - idle_tgt)
            idle_rpm_diffs.append(diff)
            if diff > 150:
                idle_hunting_frames += 1

        # Transient spikes
        if abs(trans) > 0.40:
            transient_spikes += 1

    print("\n=== SYSTEM OVERVIEW ===")
    print(f"Battery Voltage: Min = {min_volt:.2f} V, Max = {max_volt:.2f} V (Low voltage frames < 12V running: {low_volt_frames})")
    print(f"Coolant Temp: Min = {min_ect:.1f} C, Max = {max_ect:.1f} C")
    print(f"Max Engine Speed: {max_rpm:.0f} RPM")
    print(f"Manifold Pressure Range: Min = {min_map_kpa:.1f} kPa ({min_map_kpa*7.5006:.0f} mmHg), Max = {max_map_kpa:.1f} kPa ({max_map_kpa*7.5006:.0f} mmHg)")
    print(f"Max Injector Pulse Width: {max_pw:.2f} ms (Max calculated Duty: {max_duty:.1f}%)")
    print(f"Min Running Ignition Timing: {min_timing:.2f} deg (Suspicious low timing under load: {timing_pulls} frames)")
    print(f"DBW Mismatch frames (pedal vs plate > 25%): {dbw_mismatch}")
    if idle_rpm_diffs:
        avg_idle_err = sum(idle_rpm_diffs) / len(idle_rpm_diffs)
        print(f"Idle RPM Tracking: Avg error from target = {avg_idle_err:.1f} RPM (Frames with error > 150 RPM: {idle_hunting_frames} / {len(idle_rpm_diffs)})")
    print(f"Large Transient Fuel Correction spikes (>0.40): {transient_spikes}")

if __name__ == "__main__":
    scan_anomalies("logs/romraiderlog_patchv2_5_20260909_182732.csv")
