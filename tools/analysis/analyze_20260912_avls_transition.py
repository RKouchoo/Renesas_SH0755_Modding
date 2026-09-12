#!/usr/bin/env python3
"""Review the rotational-delete capture without changing its CSV or calibration.

Reconstructs the captured ROM from its Git baseline and the verified rotational
removal, then checks its exact hash. SD wrapper execution changes only the
software lift mode at each logged operating point; it is not an engine model.
Use --plot with matplotlib to render the three loaded lift transitions.
"""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / 'logs/romraiderlog_rotationaldelete_20260912_122651.csv'
OUT = ROOT / 'logs/20260912_rotationaldelete_review'
LOG_SHA = '3c167a4ce61a7d503232a490157b47c4283385ec06268551ed125b1803080142'
ROM_SHA = 'ca4516f5a3737cffc172e9f1771a78a1a4ee966703136281d65d275d77dad7ef'
KEYS = ('time', 'state', 'ect', 'rpm', 'afr', 'factor', 'iat', 'trans', 'pw',
        'avls', 'load', 'timing', 'throttle', 'pedal', 'fbkc', 'flkc', 'iam',
        'map', 'speed')


def captured_rom():
    image = bytearray(subprocess.check_output([
        'git', 'show', '5f0ba2a:master_patch_v2/D2WD610H_master_patch_v2.bin'], cwd=ROOT))
    struct.pack_into('>I', image, 0x11E30, 0x279CC)
    image[0x7DB40:0x7DD00] = b'\xff' * 0x1C0
    total = sum(word[0] for word in struct.iter_unpack('>I', image[0x2000:0x7FAF8]))
    struct.pack_into('>I', image, 0x7FB88, (0x5AA5A55A - total) & 0xFFFFFFFF)
    assert hashlib.sha256(image).hexdigest() == ROM_SHA
    return bytes(image)


def read_log():
    assert hashlib.sha256(LOG.read_bytes()).hexdigest() == LOG_SHA
    with LOG.open(newline='') as f:
        reader = csv.reader(f)
        headings = next(reader)
        assert len(headings) == len(KEYS) == 19
        rows = []
        for raw in reader:
            assert len(raw) == len(KEYS)
            row = dict(zip(KEYS, map(float, raw)))
            assert all(math.isfinite(v) for v in row.values())
            row['time'] /= 1000
            rows.append(row)
    assert all(b['time'] > a['time'] for a, b in zip(rows, rows[1:]))
    return rows


def analyze(rows, image):
    sys.path.insert(0, str(ROOT / 'tests'))
    import test_hook_execution as hook
    hook.IMAGE = image
    entries = []
    for i, row in enumerate(rows):
        if not i or row['avls'] != 3 or rows[i - 1]['avls'] != 1:
            continue
        flow = [hook.Machine(row['rpm'], row['map'] / .1333223684,
                            row['iat'], mode).run() for mode in (1, 3)]
        following = [r for r in rows[i:] if r['time'] <= row['time'] + 1.1]
        entries.append({
            'sample': row,
            'loaded_entry': row['pedal'] > 50,
            'sd_airflow_low_g_s': flow[0],
            'sd_airflow_high_g_s': flow[1],
            'mode_only_airflow_change_percent': 100 * (flow[1] / flow[0] - 1),
            'first_second_samples': following,
        })
    baro = statistics.median(r['map'] for r in rows if r['time'] < 2 and r['rpm'] == 0)
    arm = struct.unpack_from('>f', image, 0x7EAD4)[0] * .1333223684
    pressure_qualified = [r for r in rows if r['rpm'] > 0 and r['map'] >= baro + arm]
    return {
        'log': str(LOG.relative_to(ROOT)), 'log_sha256': LOG_SHA,
        'captured_rom_sha256': ROM_SHA, 'samples': len(rows),
        'duration_seconds': rows[-1]['time'],
        'median_interval_seconds': statistics.median(
            b['time'] - a['time'] for a, b in zip(rows, rows[1:])),
        'avls_entries': entries,
        'conditional_cut_check': {
            'assumption': 'Hold baro at KOEO MAP; runtime CFBC was not logged.',
            'koeo_map_kpa': baro, 'arm_absolute_kpa': baro + arm,
            'pressure_qualified_samples': len(pressure_qualified),
            'afr_range': [min(r['afr'] for r in pressure_qualified),
                          max(r['afr'] for r in pressure_qualified)],
            'simultaneous_lean_or_invalid_samples': [r['time'] for r in pressure_qualified
                                                    if r['afr'] == 0 or r['afr'] > 12.8],
        },
        'limits': [
            'SSM channels are sampled across a request, not atomically.',
            'CD86 is software mode, not measured valve lift.',
            'P21 is gross calculated duration, not proof of injector delivery.',
            'AFR zero is an invalid-input sentinel.',
            'No cut state, injector inhibit word, runtime baro or bank lift feedback captured.',
        ],
    }


def plot(rows, report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    events = [e for e in report['avls_entries'] if e['loaded_entry']]
    fig, axes = plt.subplots(5, len(events), figsize=(13, 9), sharex='col')
    specs = [('rpm', 'RPM'), ('pedal', 'Pedal / throttle (%)'),
             ('afr', 'Wideband AFR'), ('pw', 'Injector #1 (ms)'), ('timing', 'Timing (deg)')]
    for col, event in enumerate(events):
        t = event['sample']['time']
        data = [r for r in rows if t - .65 <= r['time'] <= t + 1.1]
        xs = [r['time'] - t for r in data]
        release = next((r['time'] - t for r in data if r['time'] >= t
                        and r['pedal'] < event['sample']['pedal'] - 5), None)
        for j, (key, ylabel) in enumerate(specs):
            ax = axes[j, col]
            ys = [r[key] if key != 'afr' or r[key] > 0 else math.nan for r in data]
            ax.plot(xs, ys, '.-', color='#175c99', lw=1.5, ms=3, label=key)
            if key == 'pedal':
                ax.plot(xs, [r['throttle'] for r in data], color='#a55315', label='throttle')
                if col == 0:
                    ax.legend(fontsize=8, loc='lower left')
            if key == 'afr':
                ax.set_ylim(10.5, 17.5)
            ax.axvline(0, color='#ba2929', lw=1, ls='--')
            if release is not None:
                ax.axvspan(release, 1.1, color='#999999', alpha=.15)
            ax.grid(alpha=.2)
            ax.set_xlim(-.65, 1.1)
            if col == 0:
                ax.set_ylabel(ylabel)
            if j == 0:
                ax.set_title(f"AVLS 1 → 3 at {t:.3f} s")
            if j == 4:
                ax.set_xlabel('Seconds relative to software lift switch')
    fig.suptitle('Repeated RPM disturbance after high-lift selection\n'
                 'Red line: CD86 selects high lift · Gray: driver begins lifting off', fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, .94))
    fig.savefig(OUT.with_suffix('.png'), dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plot', action='store_true')
    args = parser.parse_args()
    rows = read_log()
    report = analyze(rows, captured_rom())
    OUT.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    if args.plot:
        plot(rows, report)
    for event in report['avls_entries']:
        if event['loaded_entry']:
            print(f"{event['sample']['time']:.3f} s: mode-only airflow change "
                  f"{event['mode_only_airflow_change_percent']:+.3f}%")
    print('Wrote', OUT.with_suffix('.json'))


if __name__ == '__main__':
    main()
