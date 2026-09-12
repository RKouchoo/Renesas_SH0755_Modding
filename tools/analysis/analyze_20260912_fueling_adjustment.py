#!/usr/bin/env python3
"""Verify the September 12 v2 idle/high-lift VE adjustment against its warm log.

The first run takes --before with the captured 4808414b image. Subsequent
runs reconstruct that exact image from the saved changed-word evidence.
Only the rolling ROM is produced; the source CSV is never modified.
"""

import _analysis_paths
from _captured_images import before_pump_scaling
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import sys

ROOT = _analysis_paths.ROOT
sys.path.insert(0, str(ROOT / 'tests'))
import test_hook_execution as hook

ROM = ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin'
LOG = ROOT / 'logs/romraiderlog_neutralfuelingtest_20260912_141321.csv'
OUT = ROOT / 'logs/20260912_fueling_adjustment_review.json'
BEFORE_SHA = '4808414b01f3ede952197422f75a791f5325595a27bc810ca610b82d3954d67e'
LOG_SHA = 'fae81a50f56f74c2d6d725db1ec1619e409e1e821324dae6328d817dde226dff'
KEYS = ('time', 'pedal', 'mode', 'ect', 'rpm', 'afr', 'fbkc', 'flkc', 'pw',
        'iam', 'timing', 'map', 'throttle', 'speed', 'state', 'load',
        'factor', 'iat', 'trans')


def sha(image):
    return hashlib.sha256(image).hexdigest()


def stats(values):
    return {'min': min(values), 'median': statistics.median(values), 'max': max(values)}


def verify_changes(before, after):
    """Independent ten-cell scope and checksum check; catch unrelated rebuild drift."""
    assert len(before) == len(after) == 0x80000
    assert sha(before) == BEFORE_SHA, 'Wrong pre-adjustment image'
    allowed, cells = set(), []
    for name, base, rpms, edited_rpms, pressures, factor in (
        ('low', hook.patch.LOW_VE_DATA_ADDR, hook.patch.LOW_RPM_AXIS,
         (800, 1200), (150, 250), 1.05),
        ('high', hook.patch.HIGH_VE_DATA_ADDR, hook.patch.HIGH_RPM_AXIS,
         (3000, 3200, 3500), (250, 350), .88),
    ):
        for rpm in edited_rpms:
            for pressure in pressures:
                addr = base + 4 * (rpms.index(rpm) * len(hook.patch.MAP_AXIS)
                                   + hook.patch.MAP_AXIS.index(pressure))
                old = struct.unpack_from('>f', before, addr)[0]
                new = struct.unpack_from('>f', after, addr)[0]
                assert abs(new / old - factor) < 1e-6, (name, rpm, pressure, old, new)
                allowed.update(range(addr, addr + 4))
                cells.append({'table': name, 'rpm': rpm, 'map_mmhg': pressure,
                              'address': f'{addr:05X}', 'before_ve': old,
                              'after_ve': new, 'change_percent': 100 * (new / old - 1)})
    allowed.update(range(0x7FB88, 0x7FB8C))
    changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
    assert changed and changed <= allowed, 'Changes outside ten VE cells and checksum'
    for image in (before, after):
        total = sum(v[0] for v in struct.iter_unpack('>I', image[0x2000:0x7FAF8]))
        checksum = struct.unpack_from('>I', image, 0x7FB88)[0]
        assert (total + checksum) & 0xFFFFFFFF == 0x5AA5A55A
    words = [{'address': f'{a:05X}', 'before_hex': before[a:a+4].hex(),
              'after_hex': after[a:a+4].hex()} for a in sorted({i & ~3 for i in changed})]
    assert len(words) == 11, 'Expected ten VE words plus checksum'
    return cells, words, len(changed)


def read_log():
    assert sha(LOG.read_bytes()) == LOG_SHA
    with LOG.open(encoding='utf-8-sig', newline='') as source:
        csv_rows = list(csv.reader(source))
    assert all(len(row) == len(KEYS) for row in csv_rows)
    rows = [dict(zip(KEYS, map(float, row))) for row in csv_rows[1:]]
    assert len(rows) == 618 and all(math.isfinite(v) for r in rows for v in r.values())
    for row in rows:
        row['time'] /= 1000
    assert all(a['time'] < b['time'] for a, b in zip(rows, rows[1:]))
    return rows


def flow(image, rpm, pressure, iat, mode):
    previous, hook.IMAGE = hook.IMAGE, image
    try:
        return hook.Machine(rpm, pressure, iat, mode).run()
    finally:
        hook.IMAGE = previous


def replay(before, after, rows):
    summaries = []
    for label, start, end, mode in (
        ('initial_idle', 0, 11, 1), ('high_hold_1', 28, 31.85, 3),
        ('high_hold_2', 49, 52.15, 3), ('settled_final_idle', 60, 63.05, 1),
    ):
        samples = [r for r in rows if start <= r['time'] <= end]
        assert samples and all(r['mode'] == mode and r['afr'] > 0 and r['speed'] == 0 for r in samples)
        ratios, estimated_afrs, old_load, new_load = [], [], [], []
        for r in samples:
            point = (r['rpm'], r['map'] / .1333224, r['iat'], mode)
            a, b = flow(before, *point), flow(after, *point)
            ratio = b / a
            assert 1.04999 <= ratio <= 1.05001 if mode == 1 else .87999 <= ratio <= .90001
            ratios.append(ratio)
            estimated_afrs.append(r['afr'] / ratio)
            old_load.append(a * 60 / r['rpm'])
            new_load.append(b * 60 / r['rpm'])
        summaries.append({
            'window': label, 'time_start': samples[0]['time'], 'time_end': samples[-1]['time'],
            'samples': len(samples),
            'logged': {key: stats([r[key] for r in samples]) for key in KEYS[1:]},
            'replayed_airflow_ratio_after_over_before': stats(ratios),
            'replayed_raw_load_before_g_rev': stats(old_load),
            'replayed_raw_load_after_g_rev': stats(new_load),
            'estimated_afr_if_physical_air_and_other_fuel_factors_unchanged': stats(estimated_afrs),
        })
    # Table interpolation and wrapper output at unaffected controls. These
    # include the earlier loaded-fault pressure region, not only cell centres.
    controls = 0
    for mode in (1, 3):
        for rpm in (500, 850, 1200, 1600, 2500, 3200, 3400, 4000, 6000):
            for pressure in (450, 650, 760, 850, 1100):
                assert flow(before, rpm, pressure, 39, mode) == flow(after, rpm, pressure, 39, mode)
                controls += 1
    for rpm in (2000, 3000, 3200):
        for pressure in (150, 220, 300, 400):
            assert flow(before, rpm, pressure, 39, 1) == flow(after, rpm, pressure, 39, 1)
            controls += 1
    # The vacuum trim leaves the artificially floored 150-mmHg knot intact.
    # Verify modeled airflow still rises with MAP through that blend.
    for rpm in (3000, 3200, 3500):
        outputs = [flow(after, rpm, p, 39, 3) for p in range(150, 451, 25)]
        assert all(a < b for a, b in zip(outputs, outputs[1:])), 'Nonmonotonic MAP/airflow blend'
    return summaries, controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, help='Exact captured 4808414b image, needed only on first run')
    args = parser.parse_args()
    if args.before:
        before = args.before.read_bytes()
    else:
        from analyze_20260912_avls_neutral import corrected_image
        before = corrected_image()
    after = before_pump_scaling(ROM.read_bytes())
    cells, words, count = verify_changes(before, after)
    rows = read_log()
    windows, controls = replay(before, after, rows)
    report = {
        'source_log': str(LOG.relative_to(ROOT)), 'source_log_sha256': LOG_SHA,
        'before_sha256': sha(before), 'after_sha256': sha(after),
        'before_checksum': before[0x7FB88:0x7FB8C].hex().upper(),
        'after_checksum': after[0x7FB88:0x7FB8C].hex().upper(),
        'changed_byte_count': count, 'cells': cells, 'changed_words': words,
        'replay_windows': windows, 'unchanged_airflow_control_points': controls,
        'limits': [
            'Actual SD-wrapper instructions; native lookup bodies are replaced by descriptor-based interpolation models.',
            'AFR estimates hold physical air and other fuel factors fixed; this is not an engine simulation or measured new AFR.',
            'SD load changes also move downstream load-indexed operating points; no timing or target-AFR table bytes change.',
            'Native interpolation spreads the idle adjustment between 500 and 1600 RPM below 350 mmHg, and the high-lift adjustment below 4000 RPM between 150 and 450 mmHg.',
            'No altered boost cells, no new physical test, and no claim that the earlier loaded misfire is fixed.',
        ],
    }
    OUT.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Verified {len(cells)} VE cells, {count} changed bytes including checksum; {controls} unaffected airflow controls.')
    for window in windows:
        print(window['window'], 'airflow ratio', window['replayed_airflow_ratio_after_over_before'],
              'conditional AFR', window['estimated_afr_if_physical_air_and_other_fuel_factors_unchanged'])
    print('SHA-256:', report['after_sha256'], 'checksum:', report['after_checksum'])
    print('Wrote', OUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
