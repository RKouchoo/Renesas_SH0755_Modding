#!/usr/bin/env python3
"""Read-only review of the first rollback driving capture; no ECU actions.

The optional --write flag saves derived JSON/PNG beside the capture. It never
changes the original CSV, ROM, or calibration. Table lookups are conditional
comparisons; they do not reconstruct unlogged control or physical state.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics as stats
import struct

from analyze_20260908_recovery import flash_identity

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / 'logs' / 'romraiderlog_rollbackdrive1\\_20260911_180013.csv'
ROM = ROOT / 'rollback' / 'D2WD610H_master_patch_v2.bin'
FLASH = Path('/Users/regan/.config/FastECU/0.1.0-beta.5/syslogs/log_fastecu_2026-09-11_17h09m54s.txt')
LOG_HASH = '9ab91bcba3cf19aece029f817730be5080e7db292ac554f35597161daff77551'
ROM_HASH = '5a1ad588dc620f6a4bb9ee3a464fa9eefc173cc107b8e5cc4a3c918a59004755'
KEYS = ('time', 'pedal', 'battery', 'state', 'request', 'coolant', 'target',
        'load', 'rpm', 'afr', 'adc', 'factor', 'pulse', 'idle_flags', 'timing',
        'iat', 'map', 'airflow', 'throttle', 'transient')


def read_inputs():
    assert hashlib.sha256(LOG.read_bytes()).hexdigest() == LOG_HASH
    image = ROM.read_bytes()
    assert hashlib.sha256(image).hexdigest() == ROM_HASH
    with LOG.open() as source:
        reader = csv.reader(source)
        headings = next(reader)
        raw = list(reader)
    assert len(headings) == 20 and len(raw) == 4184
    assert all(len(row) == 20 for row in raw)
    rows = [dict(zip(KEYS, map(float, row))) for row in raw]
    assert all(math.isfinite(value) for row in rows for value in row.values())
    for row in rows:
        row['time'] /= 1000
    assert all(b['time'] > a['time'] for a, b in zip(rows, rows[1:]))
    return rows, image


def summarize(rows):
    result = {'samples': len(rows), 'invalid_afr': sum(r['afr'] <= 0 for r in rows)}
    for key in ('rpm', 'pedal', 'throttle', 'load', 'map', 'afr', 'factor',
                'pulse', 'timing', 'transient', 'battery', 'coolant'):
        values = [r[key] for r in rows if key != 'afr' or r[key] > 0]
        result[key] = [min(values), stats.median(values), max(values)] if values else None
    return result


def build_review(rows, image):
    intervals = [(b['time'] - a['time']) * 1000 for a, b in zip(rows, rows[1:])]
    loaded = [r for r in rows if r['pedal'] > 5 and r['rpm'] > 500 and r['map'] >= 85]
    points = [min(rows, key=lambda r: abs(r['time'] - t))
              for t in (239.213, 242.852, 355.484, 364.851)]
    # Expose the exact primary OL axes for review. The final selected/ramped
    # target is not logged; table comparisons remain conditional.
    load_axis = struct.unpack_from('>14f', image, 0x7771C)
    rpm_axis = struct.unpack_from('>10f', image, 0x77754)
    proof = flash_identity(image, FLASH, verification=1)
    assert len(proof['blocks']) == 16
    # Native checksum descriptor's end is the final byte, not a word boundary.
    start, end, stored = struct.unpack_from('>III', image, 0x7FB80)
    checksum = (sum(struct.unpack_from('>I', image, a)[0]
                    for a in range(start, end, 4)) + stored) & 0xFFFFFFFF
    assert checksum == 0x5AA5A55A
    return {
        'log': str(LOG.relative_to(ROOT)), 'log_sha256': LOG_HASH,
        'rom': str(ROM.relative_to(ROOT)), 'rom_sha256': ROM_HASH,
        'flash_verification': proof, 'native_checksum_pass': True,
        'duration_seconds': rows[-1]['time'] - rows[0]['time'],
        'interval_ms_min_median_max': [min(intervals), stats.median(intervals), max(intervals)],
        'whole_capture': summarize(rows), 'loaded': summarize(loaded),
        'loaded_small_transient': summarize([r for r in loaded if abs(r['transient']) < .03]),
        'zero_net_pulse_with_pedal_over5_and_rpm_over500':
            sum(r['pedal'] > 5 and r['rpm'] > 500 and r['pulse'] == 0 for r in rows),
        'windows': {f'{lo}..{hi}': summarize([r for r in rows if lo <= r['time'] <= hi])
                    for lo, hi in ((238.1, 241.5), (242, 243.6), (354.5, 356.3), (364.7, 365.1))},
        'example_rows': points, 'primary_ol_axes': {'load': load_axis, 'rpm': rpm_axis},
        'user_observations': [
            'Revs normally in neutral; very little torque when moving or climbing a slight hill.',
            'These September 11 captures are the first movement under own power since the turbo conversion.',
        ],
        'limits': 'One-channel net pulse is not measured injector delivery. P7 MAP is not direct ABC4. '
                  'Gear, vehicle speed, clutch position, actual cam angles, IAM and knock corrections are absent. '
                  'The wideband has exhaust transport delay and channels are not a simultaneous snapshot. '
                  'Single-sample pulse anomalies remain unmodified; their byte patterns are consistent with torn reads.',
    }


def plot(rows, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(6, 2, figsize=(13, 11), sharex='col', layout='constrained')
    panels = (
        (('rpm', 'RPM', '#2857a4'),),
        (('pedal', 'Pedal %', '#68717c'), ('throttle', 'Plate %', '#2857a4')),
        (('afr', 'Indicated AFR', '#b64529'),),
        (('pulse', 'Net pulse ms', '#2857a4'),),
        (('timing', 'Spark degrees', '#70479c'),),
        (('transient', 'B874 additive', '#22775a'),),
    )
    for col, (lo, hi) in enumerate(((236, 244), (353.7, 357.8))):
        subset = [r for r in rows if lo <= r['time'] <= hi]
        for ax, panel in zip(axes[:, col], panels):
            for key, label, colour in panel:
                ax.plot([r['time'] for r in subset],
                        [r[key] if key != 'afr' or r[key] > 0 else float('nan') for r in subset],
                        label=label, color=colour, linewidth=1.6)
            ax.grid(alpha=.18)
            ax.legend(loc='upper right', fontsize=8, frameon=False)
        axes[2, col].set_ylim(10.5, 18)
        axes[3, col].set_ylim(0, 10)
        axes[5, col].axhline(0, color='#777', linewidth=.7)
        axes[-1, col].set_xlabel('Seconds from capture start')
        axes[0, col].set_xlim(lo, hi)
    axes[0, 0].set_title('Sustained bog: more throttle, little RPM response')
    axes[0, 1].set_title('Near-stall with throttle still open')
    fig.suptitle('September 11 rollback: recorded engine commands during loss of torque', weight='bold')
    fig.savefig(output, dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Save derived JSON and PNG; raw inputs unchanged.')
    args = parser.parse_args()
    rows, image = read_inputs()
    result = build_review(rows, image)
    if args.write:
        destination = ROOT / 'logs' / '20260911_rollback_review'
        destination.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n')
        plot(rows, destination.with_suffix('.png'))
        print('Saved rollback review JSON/PNG; original log and ROM unchanged.')
    else:
        print(json.dumps(result, indent=2))
