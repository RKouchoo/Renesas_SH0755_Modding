#!/usr/bin/env python3
"""Review the cut-trace CSV without modifying input, calibration or firmware.

The optional chart is a standalone diagnostic figure. SD replay holds IAT at
explicit fixtures because this capture does not measure it; only the mode-only
airflow ratio is compared. Lookup interpolation is modeled by the existing
wrapper interpreter, not a whole-engine or hardware timing simulation.
"""
import _analysis_paths
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import statistics
import xml.etree.ElementTree as ET

import test_hook_execution as hook

ROOT = _analysis_paths.ROOT
LOG = ROOT / 'logs/romraiderlog_cuttrace_20260913_143625.csv'
ROM = ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin'
DEFINITION = ROOT / 'logger/D2WD610H_master_logger.xml'
PROFILE = ROOT / 'logger/D2WD610H_cut_trace_profile.xml'
OUT = ROOT / 'logs/20260913_cut_trace_review'
LOG_SHA = '3e62ab07eb7ee184ab43162debd7d97c3f829085399cf87742ca6c8997d85390'
ROM_SHA = 'fabceb54359aca76e6e15835a51aa5cfd008e570dc002e886eaa62a6cb020ce5'
KEYS = ('time pedal aux battery avls ect sync flags timeout rpm afr fbkc flkc '
        'pw iam mode timing inhibit lean airflow_missed crank_missed map spark '
        'throttle speed').split()
STATES = ('aux avls sync flags timeout mode spark inhibit lean airflow_missed '
          'crank_missed iam fbkc flkc').split()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(values):
    return dict(min=min(values), median=statistics.median(values), max=max(values)) if values else None


def summarize(rows):
    return {
        'samples': len(rows),
        'csv_lines': [rows[0]['csv_line'], rows[-1]['csv_line']] if rows else [],
        'range': {k: stats([r[k] for r in rows]) for k in KEYS},
        'state_counts': {k: dict(sorted(Counter(int(r[k]) for r in rows).items())) for k in STATES},
        'valid_afr': stats([r['afr'] for r in rows if r['afr'] > 0]),
        'invalid_afr_samples': sum(r['afr'] == 0 for r in rows),
    }


def read_log():
    assert sha(LOG) == LOG_SHA
    with LOG.open(newline='', encoding='utf-8-sig') as source:
        raw = list(csv.reader(source))
    headings = raw.pop(0)
    params = {p.get('id'): p for p in ET.parse(DEFINITION).iter()
              if p.tag in ('parameter', 'ecuparam')}
    selected = [p for p in ET.parse(PROFILE).iter('parameter') if p.get('livedata') == 'selected']
    expected = sorted(f"{params[p.get('id')].get('name')} ({p.get('units')})" for p in selected)
    assert headings == ['Time (msec)'] + expected, 'Capture differs from saved profile names/units/order'
    assert len(raw) == 1590 and len(headings) == len(KEYS) == 25
    assert all(len(row) == len(KEYS) and all(row) for row in raw)
    rows = [dict(zip(KEYS, map(float, row)), csv_line=i+2) for i, row in enumerate(raw)]
    assert all(math.isfinite(r[k]) for r in rows for k in KEYS)
    for r in rows:
        r['time'] /= 1000
        r['effective_spark_mask'] = int(r['aux']) | (int(r['spark']) if r['mode'] else 65535)
    assert all(a['time'] < b['time'] for a, b in zip(rows, rows[1:]))
    return headings, rows


def replay_entry(row):
    fixtures = []
    for iat in (10, 30, 60):
        flows = [hook.Machine(row['rpm'], row['map'] / .1333223684, iat, mode).run()
                 for mode in (1, 3)]
        fixtures.append({'iat_fixture_c': iat, 'mode1_g_s': flows[0], 'mode3_g_s': flows[1],
                         'mode_only_change_percent': 100 * (flows[1] / flows[0] - 1)})
    return fixtures


def analyze(headings, rows):
    assert sha(ROM) == ROM_SHA
    image = ROM.read_bytes()
    stock = (ROOT / '2005 BLE MT.bin').read_bytes()
    ranges = ((0x405B2, 0x40714), (0x2A262, 0x2A2E8), (0xD156, 0xD18C),
              (0xD22E, 0xD232), (0xD240, 0xD24C))
    for a, b in ranges:
        assert image[a:b] == stock[a:b], (hex(a), hex(b))
    windows = {name: [r for r in rows if a <= r['time'] <= b] for name, a, b in (
        ('low_lift_full_throttle', 63.148, 64.086),
        ('entry_57s', 57.211, 58.044),
        ('entry_105s', 104.899, 105.525),
        ('entry_110s', 110.215, 111.777),
        ('already_high_116s', 116.146, 117.813),
        ('already_high_120s', 119.896, 121.148),
        ('already_high_123s', 122.813, 124.584),
        ('final_engine_stop', 161.718, 165.357),
    )}
    demand = [r for r in rows if r['speed'] > 5 and r['pedal'] >= 30 and r['rpm'] >= 2500]
    open_plate = [r for r in demand if r['throttle'] >= 80]
    assert len(demand) == 247
    assert sum(r['inhibit'] != 0 for r in demand) == 1
    assert all(r['inhibit'] == 0 for r in open_plate)
    for r in demand:
        assert (r['spark'], r['mode'], r['aux'], r['sync'], r['flags'], r['timeout']) == (0, 2, 4032, 1, 0, 0)
        assert (r['iam'], r['fbkc'], r['flkc'], r['lean']) == (1, 0, 0, 0)
    assert all(r['airflow_missed'] == r['crank_missed'] == 0 for r in rows)
    entries = []
    previous, hook.IMAGE = hook.IMAGE, image
    try:
        for i, r in enumerate(rows):
            if i and r['avls'] == 3 and rows[i-1]['avls'] == 1:
                entries.append({'previous': rows[i-1], 'sample': r,
                                'loaded_entry': r['pedal'] >= 50 and r['throttle'] >= 70,
                                'mode_only_wrapper_replay': replay_entry(r)})
    finally:
        hook.IMAGE = previous
    loaded_entries = [e for e in entries if e['loaded_entry']]
    assert len(loaded_entries) == 3
    assert all(abs(f['mode_only_change_percent']) < .1 for e in loaded_entries
               for f in e['mode_only_wrapper_replay'])
    return {
        'source_log': str(LOG.relative_to(ROOT)), 'source_log_sha256': LOG_SHA,
        'review_rom': str(ROM.relative_to(ROOT)), 'review_rom_sha256': ROM_SHA,
        'rom_identity_limit': 'Same saved repaired v2 as latest recorded 13:28 flash verification; '
                              'this CSV contains no fresh ROM identity or ECU readback.',
        'definition_sha256': sha(DEFINITION), 'profile_sha256': sha(PROFILE),
        'headings': dict(zip(KEYS, headings)),
        'user_observations': ['Same hard cut repeated several times.',
            'Feels like hitting a brick wall, with only one or two cylinders firing while held. '
            'The number of firing cylinders is a sensation, not measured cylinder attribution.',
            'User challenged a fueling explanation based on the logged AFR.'],
        'whole_capture': summarize(rows),
        'sample_interval_ms': stats([round((b['time']-a['time'])*1000) for a, b in zip(rows, rows[1:])]),
        'high_demand': summarize(demand), 'high_demand_plate_at_least_80': summarize(open_plate),
        'high_demand_inhibit_exceptions': [r for r in demand if r['inhibit']],
        'windows': {name: summarize(group) for name, group in windows.items()},
        'window_rows': windows,
        'state_transitions': {k: [r for i, r in enumerate(rows) if not i or r[k] != rows[i-1][k]]
                              for k in STATES if k not in ('inhibit', 'avls')},
        'avls_entries': entries,
        'native_stock_byte_ranges': [{'start': f'{a:05X}', 'end_exclusive': f'{b:05X}'} for a, b in ranges],
        'limits': [
            '100–108ms non-atomic SSM samples can miss brief state changes.',
            'Counters start and remain at zero; capture begins with engine already running at944RPM. '
            'No missed task5/task6 activations are recorded, but this is not proof of every deadline.',
            'Normal auxiliary mask0FC0 suppresses the secondary six slots; primary slots remain enabled.',
            'P21 and timing are software publications, not actual injector/coil waveforms.',
            'AVLS committed software state is not hydraulic lift or bank electrical feedback.',
            'AFR zero means rejected wideband input; AFR during failed combustion does not establish cause.',
            'IAT, fuel pressure, individual-cylinder combustion and current coil/injector outputs are absent.',
            'The mode-only replay uses supplied IAT and modeled lookups; it isolates table selection '
            'but does not reconstruct the unlogged full fuel/ignition calculation or transient physical airflow.',
            'The final engine-stop sequence changes masks and sync; the CSV does not identify key position.',
        ],
        'conclusions': [
            'At110.319–110.424s RPM falls3249to3016 while AFR stays11.57 and published pulse '
            'increases11.01to11.52ms. The later lean excursion does not establish fuel starvation; '
            'no further fuel adjustment is justified by this observation.',
            'Repeated loaded loss of acceleration occurs without sustained sampled ignition inhibition, '
            'engine-signal timeout, synchronization loss, lean guard or knock retard.',
            'No native task5/task6 activation losses are recorded anywhere in the capture.',
            'Three loaded lift transitions correlate with disturbance but their mode-only airflow changes '
            'are below0.1%; there is no large VE-table selection step at those points.',
            'Another plateau occurs at3600–3800RPM with high mode already committed; low-lift '
            'full-throttle acceleration is also weak. A single3200RPM table-switch explanation is insufficient.',
            'No vehicle cause or software cure is established. Downstream scheduling, physical ignition, '
            'injection, fuel pressure and lift response are not cleared by normal software gates.',
        ],
        'changes': 'Offline analysis and documentation only. No firmware, calibration, logger or CSV edits.',
    }


def plot(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    fig, axes = plt.subplots(5, 3, figsize=(13, 8), sharex='col')
    for col, (start, end, edge, title) in enumerate((
            (55.2, 58.4, 57.211, 'First loaded transition'),
            (108.6, 112.2, 110.215, 'Repeated loaded transition'),
            (119.7, 121.5, None, 'High lift already selected'))):
        subset = [r for r in rows if start <= r['time'] <= end]
        xs = [r['time'] for r in subset]
        for j, (key, label) in enumerate((('rpm', 'RPM'), ('throttle', 'Throttle / pedal (%)'),
                                        ('afr', 'Wideband AFR'), ('pw', 'Injector pulse (ms)'),
                                        ('timing', 'Timing (deg)'))):
            ax = axes[j, col]
            ax.plot(xs, [r[key] if key != 'afr' or r[key] > 0 else math.nan for r in subset],
                    '.-', color='#17649b', lw=1.3, ms=3)
            if key == 'throttle':
                ax.plot(xs, [r['pedal'] for r in subset], color='#ac541d', lw=1.1, label='Pedal')
                ax.set_ylim(0, 105)
                if col == 0:
                    ax.legend(loc='lower left', fontsize=8)
            if key == 'afr':
                ax.set_ylim(10.8, 17.2)
            if edge is not None:
                ax.axvline(edge, color='#aa2929', ls='--', lw=1)
            ax.grid(alpha=.2)
            ax.set_xlim(start, end)
            ax.xaxis.set_major_locator(MaxNLocator(5))
            if col == 0:
                ax.set_ylabel(label)
            if j == 0:
                ax.set_title(title, fontsize=11)
            if j == 4:
                ax.set_xlabel('Seconds into capture')
    fig.suptitle('Cut trace: repeated acceleration plateaus\n'
                 'Red dashed line: software AVLS 1 → 3; neither waveform delivery nor hydraulic lift is measured', fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .93))
    fig.savefig(OUT.with_suffix('.png'), dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plot', action='store_true')
    args = parser.parse_args()
    headings, rows = read_log()
    report = analyze(headings, rows)
    OUT.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    if args.plot:
        plot(rows)
    print(json.dumps({
        'samples': len(rows), 'high_demand': report['high_demand']['samples'],
        'high_demand_plate80': report['high_demand_plate_at_least_80']['samples'],
        'interval_ms': report['sample_interval_ms'],
        'mode_only_percent_at_30C_fixture': [(e['sample']['time'], e['mode_only_wrapper_replay'][1]['mode_only_change_percent'])
                                           for e in report['avls_entries'] if e['loaded_entry']],
        'output': str(OUT.with_suffix('.json'))}, indent=2))


if __name__ == '__main__':
    main()
