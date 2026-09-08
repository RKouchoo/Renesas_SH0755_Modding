#!/usr/bin/env python3
"""Read-only comparison of three evening captures, timing and tip-in boundaries.

Historical user BIN versions are reconstructed in memory and SHA-256 checked
because the same on-disk filename was edited again. No ROM files are written.
Native timing outputs use explicit unlogged cam/flag/correction fixtures.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics as stats
import struct

import analyze_20260908_recovery as recovery
from test_opening_timing_execution import OpeningTimingMachine
from test_tip_in_execution import TipInMachine

ROOT = Path(__file__).resolve().parent.parent
FLASH_LOG = Path('/Users/regan/.config/FastECU/0.1.0-beta.5/syslogs/log_fastecu_2026-09-08_17h59m01s.txt')
CAPTURES = (
    ('18:01', 'romraiderlog_20260908_180131.csv',
     '6fd6a6ecbc03d5d326c265ec8000ed4656666b0f3fb9db287a60f9f1be36c66d', 1112),
    ('18:11', 'romraiderlog_dashpot2_20260908_181118.csv',
     'dd07aeadc3d5c390c2ccb2fdf8514343acf54dfb2b9c83558bfcbcb28d0dc99d', 1813),
    ('18:15', 'romraiderlog_dashpot3_20260908_181505.csv',
     '5150975c8ce9377691a7a7b38e5977aeb796d43c54be24d1debbbb71bddf1739', 498),
)
FIRST_SHA = '7590b6ce79b41caea9d8bb850a31c41318708687120e45a584ad5030c1c47b8f'
SECOND_SHA = '2f80b8e5cb80361cdee170655bc26aa8ed8a41bcf4cd7f7249fe3f8c8eaa1f1c'


def historical_images():
    first = bytearray(recovery.CANDIDATE.read_bytes())
    assert hashlib.sha256(first).hexdigest() == recovery.CANDIDATE_SHA256
    for row, value in enumerate((220, 528, 881, 1101, 1321, 1541), 2):
        struct.pack_into('>H', first, 0x7A738+row*30, value)
    struct.pack_into('>I', first, 0x7FB88, 0x0D556987)
    struct.pack_into('>I', first, 0x7FC4C, 0x26090802)
    assert hashlib.sha256(first).hexdigest() == FIRST_SHA
    second = bytearray(first)
    for row, pair in enumerate(((266, 579), (639, 887), (1066, 1282),
                                (1332, 1676), (1598, 2005), (1865, 2333)), 2):
        struct.pack_into('>HH', second, 0x7A738+row*30, *pair)
    struct.pack_into('>I', second, 0x7FB88, 0x0807644D)
    struct.pack_into('>I', second, 0x7FC4C, 0x26090803)
    assert hashlib.sha256(second).hexdigest() == SECOND_SHA
    return bytes(first), bytes(second)


def read_capture(name, expected, count):
    path = ROOT / 'logs' / name
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected, name
    reader = csv.DictReader(raw.decode().splitlines())
    prefixes = {k: v for k, v in recovery.PREFIXES.items()
                if k not in ('lift', 'factor', 'transient')}
    prefixes.update(baro='Atmospheric Pressure', ready='External Wideband Ready')
    columns = {}
    for key, prefix in prefixes.items():
        matches = [h for h in reader.fieldnames if h.startswith(prefix)]
        assert len(matches) == 1, (name, key)
        columns[key] = matches[0]
    rows = []
    for raw_row in reader:
        assert None not in raw_row and all(v is not None for v in raw_row.values())
        row = {k: float(raw_row[column]) for k, column in columns.items()}
        assert all(math.isfinite(v) for v in row.values())
        row['time'] /= 1000
        row['raw_load_from_flow'] = row['airflow']*60/row['rpm'] if row['rpm'] else None
        rows.append(row)
    assert len(rows) == count and len(reader.fieldnames) == 23
    assert all(b['time'] > a['time'] for a, b in zip(rows, rows[1:]))
    return rows


def events(rows):
    starts = [i for i, row in enumerate(rows) if row['throttle'] >= 15
              and (i == 0 or rows[i-1]['throttle'] < 15)]
    result = []
    for j, index in enumerate(starts):
        start = rows[index]['time']
        end = min(start+6, rows[starts[j+1]]['time']) if j+1 < len(starts) else start+6
        samples = [r for r in rows if start <= r['time'] < end]
        peak = max(samples, key=lambda r: r['rpm'])
        closing = [r for r in samples if r['time'] >= peak['time']]
        result.append(dict(start=start, end=end, peak_rpm=peak,
                           min_rpm_after_peak=min(closing, key=lambda r: r['rpm']),
                           min_timing=min(r['timing'] for r in samples),
                           max_throttle=max(r['throttle'] for r in samples),
                           net_pulse_floor_samples=sum(r['pulse'] == .6 for r in samples),
                           zero_net_pulse=[r for r in samples if r['pulse'] == 0]))
    return result


def analyze():
    first, second = historical_images()
    stock = (ROOT / '2005 BLE MT.bin').read_bytes()
    captures, loaded = [], {}
    for label, name, sha, count in CAPTURES:
        rows = read_capture(name, sha, count)
        loaded[label] = rows
        gaps = [(a['time'], b['time'], b['time']-a['time']) for a, b in zip(rows, rows[1:])
                if b['time']-a['time'] > .25]
        running = [r for r in rows if r['rpm'] > 500 and (label != '18:11' or r['time'] >= 10)]
        captures.append(dict(label=label, file=name, sha256=sha, samples=len(rows),
            duration=rows[-1]['time'], coolant_start_end=[rows[0]['coolant'], rows[-1]['coolant']],
            median_interval_ms=stats.median((b['time']-a['time'])*1000 for a, b in zip(rows, rows[1:])),
            gaps_seconds=gaps, minimum_running_rpm=min(running, key=lambda r: r['rpm']),
            invalid_afr_count=sum(r['afr'] == 0 for r in rows),
            zero_net_pulse_running=[r for r in running if r['pulse'] == 0],
            pulse_consistency_outliers=[r for r in running if r['pulse'] > r['total_pulse']+2],
            events=events(rows)))
    comparisons = []
    for label, times in (('18:01', (79.527, 81.919, 94.607, 94.816, 95.024)),
                         ('18:15', (11.437, 17.677, 22.357, 33.8, 34.008, 35.88))):
        for time in times:
            row = min(loaded[label], key=lambda r: abs(r['time']-time))
            scenarios = []
            for image_label, image in (('stock', stock), ('tested_dashpot', first)):
                for k in (0, .5, 1):
                    cpu = OpeningTimingMachine(image, rpm=row['rpm'], load=row['load'],
                        coolant=row['coolant'], actual_cams=(20*k, 20*k))
                    base = cpu.base_and_idle()
                    final = cpu.final()[0]
                    scenarios.append(dict(image=image_label, cam_tracking_ratio=k,
                        base_A=cpu.get_float(0xFFFFC154), base_D=cpu.get_float(0xFFFFC160),
                        selected_base=base, final_with_neutral_other_corrections=final,
                        final_minimum=cpu.get_float(0xFFFFC124)))
            comparisons.append(dict(capture=label, logged=row, conditional_native_scenarios=scenarios))
    tip_in = []
    for pressure in (330, 482.5, 560.6, 650, 712, 760):
        cpu = TipInMachine(first, map_mmhg=pressure)
        applied = cpu.request()
        tip_in.append(dict(map_mmhg=pressure, baro_minus_map=712-pressure,
            requested=applied, calculated_extra_microseconds=cpu.get_float(0xFFFFBEF0),
            event_boundary=cpu.events))
    record = dict(
        scope='Offline analysis only; no ROM output, ECU connection, flash or engine operation.',
        user_observations='Sluggish pickup predates dashpot changes. More dashpot experimentation did not help. Larger blips worsen recovery; even small throttle movements can leave prolonged rough low RPM.',
        first_user_dashpot=dict(sha256=FIRST_SHA, checksum='0x0D556987', tag='0x26090802',
            flash=recovery.flash_identity(first, FLASH_LOG, verification=0)),
        later_user_dashpot=dict(sha256=SECOND_SHA, checksum='0x0807644D', tag='0x26090803',
            flash=recovery.flash_identity(second, FLASH_LOG, verification=1)),
        chronology='18:00 verification matches first dashpot version. The 18:01, 18:11 and 18:15 captures precede the later 18:18 verification. The 18:17 pre-flash comparison still reads first-version CRC 926036A9. Do not attribute those captures to the later version merely because the filename was reused.',
        captures=captures, timing_comparisons=comparisons, tip_in_fixed_delta20_fixtures=tip_in,
        limitations='No pedal, cam targets/positions, cam-tracking ratio, idle flag, tip-in flag/delta/pulse, fuel-cut reason or B874/B7DC in these evening captures. Calculations use rounded asynchronous channels; short tip-in events cannot be reconstructed from 104-ms sampling. AFR zero is an invalid-input sentinel. Isolated float pulse discrepancies are flagged, not treated as physical injector events. Cold temperatures and different blips preclude controlled dashpot comparisons. Native fixture tests do not predict engine response or validate a calibration.')
    return record, loaded


def plot(rows, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(4, 1, figsize=(11, 9), sharex=True, layout='constrained')
    sample = [r for r in rows if 32.7 <= r['time'] <= 38]
    t = [r['time'] for r in sample]
    for ax, key, label, color in zip(axes, ('rpm', 'timing', 'pulse', 'afr'),
                                   ('RPM', 'Timing (degrees)', 'Net pulse (ms)', 'Wideband AFR'),
                                   ('#2857a4', '#7752a3', '#21826b', '#a94432')):
        ax.plot(t, [math.nan if key == 'afr' and r[key] == 0 else r[key] for r in sample],
                color=color, linewidth=1.6)
        ax.set_ylabel(label)
        ax.grid(alpha=.2)
        ax.axvspan(33.593, 34.008, color='#dbb347', alpha=.17)
    throttle = axes[0].twinx()
    throttle.plot(t, [r['throttle'] for r in sample], color='#777', linestyle='--', linewidth=1)
    throttle.set_ylabel('Logged throttle (%)', color='#777')
    throttle.set_ylim(0, 110)
    axes[2].axvspan(34.217, 34.32, color='#c56049', alpha=.25)
    axes[3].set_ylim(11.5, 20)
    axes[-1].set_xlabel('Seconds from 18:15 log start')
    fig.suptitle('18:15 blip: low opening timing, brief zero net pulse, then low-RPM recovery')
    fig.supxlabel('Shading: throttle-open timing trough; two zero net-pulse samples. AFR gaps are invalid inputs. Channels are asynchronous.', fontsize=9)
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--plot', type=Path)
    args = parser.parse_args()
    record, loaded = analyze()
    args.output.write_text(json.dumps(record, indent=2)+'\n')
    if args.plot:
        plot(loaded['18:15'], args.plot)
    print(json.dumps({c['label']: dict(samples=c['samples'], events=len(c['events']),
          minimum_running_rpm=c['minimum_running_rpm']['rpm'], gaps=c['gaps_seconds'])
          for c in record['captures']}, indent=2))
