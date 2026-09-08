#!/usr/bin/env python3
"""Read-only replay and summary of the September 8 12:36 idle/rev capture.

The selected comparison windows avoid the fast transients and zero AFR fault
sentinels. SD replay executes the saved BIN's wrapper instructions with modeled
table lookups; CSV columns are not an atomic ECU state snapshot. Neither the
replay nor gauge agreement proves physical fuel delivery or sensor accuracy.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics as stats
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT / "speed_density"), str(ROOT / "patch")]
import patch_speed_density as sd
import test_hook_execution as hook

LOG = ROOT / "logs/romraiderlog_idle_diagnostic_20260908_123651.csv"
IMAGE = HERE / "D2WD610H_master_patch.bin"
PREFIXES = {
    "time": "Time", "rpm": "Engine Speed", "afr": "External Wideband AFR",
    "adc": "External Wideband Input ADC", "ready": "External Wideband Ready",
    "pulse": "Fuel Injector #1 Pulse Width (4-byte)",
    "latency": "Fuel Injector #1 Latency", "load": "Engine Load",
    "airflow": "Mass Airflow", "map": "Manifold Absolute",
    "battery": "Battery", "pump": "Fuel Pump", "throttle": "Throttle",
    "coolant": "Coolant", "iat": "Intake Air Temperature", "state": "CL/OL",
}


def read_capture():
    with LOG.open(newline="") as handle:
        reader = csv.reader(handle)
        headings = next(reader)
        raw = list(reader)
    if not raw or any(len(row) != len(headings) for row in raw):
        raise ValueError("Capture has no samples or incomplete rows")
    values = [[float(value) for value in row] for row in raw]
    if any(not math.isfinite(value) for row in values for value in row):
        raise ValueError("Capture contains non-finite samples")
    indices = {}
    for key, prefix in PREFIXES.items():
        matches = [i for i, name in enumerate(headings) if name.startswith(prefix)]
        if len(matches) != 1:
            raise ValueError(f"Missing/ambiguous column: {prefix}")
        indices[key] = matches[0]
    rows = [{key: row[index] for key, index in indices.items()} for row in values]
    for row in rows:
        row["time"] /= 1000
        row["volts"] = row["adc"] * 5 / 65536
    return headings, rows


def ve_from_bin(image, rpm, map_kpa):
    def array(address, length):
        return struct.unpack_from(">" + str(length) + "f", image, address)
    maps = array(sd.MAP_AXIS_ADDR, len(sd.MAP_AXIS))
    rpms = array(sd.LOW_RPM_AXIS_ADDR, len(sd.LOW_RPM_AXIS))
    data = array(sd.LOW_VE_DATA_ADDR, len(maps) * len(rpms))
    rows = tuple(sd.interpolate(maps, data[i * len(maps):(i + 1) * len(maps)],
                                map_kpa / 0.1333224) for i in range(len(rpms)))
    return sd.interpolate(rpms, rows, rpm)


def summary(headings, rows, image):
    intervals = [1000 * (b["time"] - a["time"]) for a, b in zip(rows, rows[1:])]
    windows = []
    for start, end in ((12, 30), (30, 40), (40, 60), (80, 130),
                       (135, 150), (151, 165.5), (166, 180)):
        samples = [r for r in rows if start <= r["time"] < end and r["rpm"] > 500]
        valid = [r for r in samples if r["afr"] > 0 and r["ready"] == 50]
        item = {key: stats.median(r[key] for r in samples) for key in
                ("rpm", "pulse", "latency", "load", "airflow", "map", "battery", "pump", "coolant")}
        invalid = [r for r in samples if r["afr"] == 0]
        item.update(seconds=[start, end], samples=len(samples),
                    valid_afr_median=stats.median(r["afr"] for r in valid),
                    invalid_afr=len(invalid),
                    invalid_with_high_adc=sum(r["volts"] > 4.5 for r in invalid),
                    invalid_with_low_adc=sum(r["volts"] < .5 for r in invalid),
                    pulse_per_logged_load=stats.median(r["pulse"] / r["load"] for r in samples),
                    ve_from_bin=ve_from_bin(image, item["rpm"], item["map"]))
        windows.append(item)
    replays = []
    hook.IMAGE = image
    for second in (100, 140, 150, 153.9, 154.2, 157.6, 161, 166, 170, 175):
        row = min(rows, key=lambda r: abs(r["time"] - second))
        flow = hook.Machine(rpm=row["rpm"], map_mmhg=row["map"] / .1333224,
                            iat=row["iat"], mode=1).run()
        replays.append({"seconds": row["time"], "logged_airflow": row["airflow"],
                        "replayed_airflow": flow})
    return {
        "log_sha256": hashlib.sha256(LOG.read_bytes()).hexdigest(),
        "bin_sha256": hashlib.sha256(image).hexdigest(),
        "samples": len(rows), "channels": len(headings) - 1,
        "duration_seconds": rows[-1]["time"] - rows[0]["time"],
        "interval_ms_min_median_max": [min(intervals), stats.median(intervals), max(intervals)],
        "fuel_states": sorted({r["state"] for r in rows}),
        "rpm_min_during_revs": min(r["rpm"] for r in rows if 151 <= r["time"] < 165.5),
        "windows": windows,
        "ve_at_fixed_41_32_kpa": {str(rpm): ve_from_bin(image, rpm, 41.32)
                                  for rpm in (1252, 1200, 1069, 950, 800, 734)},
        "sd_opcode_replays_low_lift_assumption": replays,
    }


def plot(rows, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(4, 2, figsize=(13, 9), sharex="col", layout="constrained")
    panels = (("rpm", "RPM", "#2458a6"), ("afr", "Wideband AFR", "#a33a2c"),
              ("pulse", "Net pulse (ms)", "#26745d"), ("volts", "Wideband input (V)", "#815a9b"))
    for column, (start, end) in enumerate(((0, 186), (148, 181))):
        sample = [r for r in rows if start <= r["time"] <= end]
        time = [r["time"] for r in sample]
        for row_index, (key, label, color) in enumerate(panels):
            ax = axes[row_index, column]
            value = [r[key] if key != "afr" or r["afr"] > 0 else math.nan for r in sample]
            ax.plot(time, value, color=color, linewidth=1.1)
            ax.set_ylabel(label)
            ax.grid(alpha=.18)
            ax.set_xlim(start, end)
            ax.axvspan(151, 165.5, color="#cf9b40", alpha=.11)
            if key == "afr":
                ax.axhline(14.64, color="#777777", linestyle="--", linewidth=.8)
                ax.set_ylim(11, 20)
            elif key == "volts":
                for threshold in (.5, 4.5):
                    ax.axhline(threshold, color="#777777", linestyle="--", linewidth=.8)
                ax.set_ylim(-.1, 5.2)
            elif key == "pulse":
                ax.set_ylim(0, 15 if column == 0 else 8.5)
        axes[0, column].set_title("Complete capture" if column == 0 else "Throttle blips and recovery")
        axes[-1, column].set_xlabel("Seconds from log start")
    fig.suptitle("September 8 idle log — complete data; lean recovery after throttle blips", fontsize=14)
    fig.supxlabel("AFR gaps are the firmware's invalid-input sentinel; dashed voltage lines mark its acceptance window.", fontsize=9)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plot", type=Path, help="Optional output PNG (requires matplotlib)")
    args = parser.parse_args()
    headings, rows = read_capture()
    print(json.dumps(summary(headings, rows, IMAGE.read_bytes()), indent=2))
    if args.plot:
        plot(rows, args.plot)
