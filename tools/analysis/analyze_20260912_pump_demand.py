#!/usr/bin/env python3
"""Replay pump-demand calibration against existing loaded samples and fixtures.

No pump-duty or rail-pressure observation is invented. Each point is held
settled through the native mode selector, with explicit voltage/latency,
processed-relative-pressure and P21 quantization fixtures. Operating gates
permit normal running selection, and BE40 is zero. No ECU or ROM is written.
"""

import _analysis_paths
import csv
import hashlib
from itertools import product
import json
from pathlib import Path
import statistics

from _captured_images import before_pump_scaling
from analyze_20260912_fueling_adjustment import KEYS
from test_fuel_pump_demand_execution import PumpDemandMachine

ROOT = _analysis_paths.ROOT
LOG = ROOT / 'logs/romraiderlog_adjustedvedrive_20260912_144204.csv'
OUT = ROOT / 'logs/20260912_pump_demand_review.json'
VOLTAGE_LATENCY = ((11.5, .980), (14, .684), (16.5, .380))


def main():
    after = (ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
    before = before_pump_scaling(after)
    assert hashlib.sha256(before).hexdigest() == 'fd795813febf817c845fc922e81e498539a539efeeb6e4d11822af47098094a2'
    assert hashlib.sha256(after).hexdigest() == '8ab70f32dce51857652fc2ab24e340dea9399f12d7042cf8f9afab851e0df6d5'
    assert hashlib.sha256(LOG.read_bytes()).hexdigest() == '347d10ce5e5c70d64f478e4bb6d124453697af07b1e074271ecbe1830d7efb33'
    with LOG.open(encoding='utf-8-sig', newline='') as source:
        raw = list(csv.reader(source))
    assert all(len(r) == len(KEYS) for r in raw)
    rows = [dict(zip(KEYS, map(float, r))) for r in raw[1:]]
    for r in rows:
        r['time'] /= 1000
    windows = []
    for start, end in ((70.5, 72.3), (77, 85.25), (130.6, 132), (177, 181)):
        selected = [r for r in rows if start <= r['time'] <= end and r['pedal'] >= 25]
        comparisons = []
        for row, (voltage, latency), pressure, quantization in product(
                selected, VOLTAGE_LATENCY, (-400, 0), (-.128, 0, .128)):
            pulse = max(0, (row['pw'] + quantization - latency) * 1000)
            values = []
            for image in (before, after):
                cpu = PumpDemandMachine(image)
                consumption = cpu.consumption(row['rpm'], pulse)
                command = cpu.select(pressure, voltage, settled=True)
                values.append({'consumption': consumption,
                               'demand': cpu.get_float(0xFFFFC2A4),
                               'pump_command': round(command, 1)})
            comparisons.append({'time': row['time'], 'voltage_fixture': voltage,
                'relative_pressure_fixture_mmhg': pressure,
                'p21_quantization_offset_ms': quantization,
                'before': values[0], 'after': values[1]})
        pairs = {}
        pairs_by_pressure = {}
        for r in comparisons:
            key = f"{r['before']['pump_command']} -> {r['after']['pump_command']}"
            pairs[key] = pairs.get(key, 0) + 1
            group = pairs_by_pressure.setdefault(str(r['relative_pressure_fixture_mmhg']), {})
            group[key] = group.get(key, 0) + 1
        entry = {'window_seconds': [start, end], 'recorded_samples': len(selected),
            'fixture_pairs': len(comparisons), 'settled_pump_command_pairs_percent': pairs,
            'command_pairs_by_relative_pressure_fixture_mmhg': pairs_by_pressure,
            'afr_recorded': {'min': min(r['afr'] for r in selected),
                'median': statistics.median(r['afr'] for r in selected),
                'max': max(r['afr'] for r in selected)},
            'demand_ranges': {which: [min(r[which]['demand'] for r in comparisons),
                max(r[which]['demand'] for r in comparisons)] for which in ('before', 'after')},
            'changed_command_times': sorted({r['time'] for r in comparisons
                if r['before']['pump_command'] != r['after']['pump_command']})}
        if start == 77:
            assert pairs_by_pressure['0'] == {'66.7 -> 66.7': len(comparisons)//2}
            assert all(r['after']['pump_command'] == 66.7 for r in comparisons)
        windows.append(entry)
        print(f'{start}–{end}s: {len(selected)} samples, {len(comparisons)} fixture pairs; {pairs_by_pressure}')
    report = {'source_log': str(LOG.relative_to(ROOT)),
        'source_log_sha256': hashlib.sha256(LOG.read_bytes()).hexdigest(),
        'captured_rom_sha256': hashlib.sha256(before).hexdigest(),
        'repaired_rom_sha256': hashlib.sha256(after).hexdigest(),
        'voltage_latency_fixtures_v_ms': VOLTAGE_LATENCY,
        'relative_pressure_fixtures_mmhg': [-400, 0],
        'p21_quantization_fixture_offsets_ms': [-.128, 0, .128],
        'windows': windows,
        'conclusion': 'At relative-pressure fixture 0 mmHg, the sustained 77–85.25 s bog points select 66.7 percent before and after. At -400 mmHg some old points select 33.3 instead of 66.7. The drive does not log this pressure or pump state, so the correction is not a demonstrated cure for the rich bog.',
        'limits': [
            'Pump command, voltage, B2A4, BE40 and rail pressure are not recorded in the drive.',
            'Voltage fixtures pair with the installed latency curve; P21 offsets bracket half its 0.256-ms quantum.',
            'B2A4 pressure fixtures span both table endpoints; no gauge boost is inferred from ABC4.',
            'Each point is held settled. This is not a timed reconstruction of the vehicle state machine.',
            'Native arithmetic, mode branches and publisher execute; table interpolation and physical DEAA output are modeled boundaries.',
        ]}
    OUT.write_text(json.dumps(report, indent=2) + '\n')
    print('Wrote', OUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
