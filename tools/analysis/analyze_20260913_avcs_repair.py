#!/usr/bin/env python3
"""Read the first repaired-v2 vehicle capture; do not write an ECU or ROM.

Log channels are sampled publications, not a trace of every injection/spark.
The saved definition supplies Right/Left labels: bank 0 is Right, bank 1 Left.
"""
import _analysis_paths
import csv
import hashlib
import json
from pathlib import Path
import statistics
import struct
import xml.etree.ElementTree as ET

from analyze_20260908_recovery import flash_identity

ROOT = _analysis_paths.ROOT
LOG = ROOT / 'logs/romraiderlog_AVCSREPAIR1_20260913_132958.csv'
ROM = ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin'
FLASH = Path('/Users/regan/.config/FastECU/0.1.0-beta.5/syslogs/'
             'log_fastecu_2026-09-13_13h00m52s.txt')
OUT = ROOT / 'logs/20260913_avcs_repair_review.json'
KEYS = ('time', 'duty_right', 'duty_left', 'pedal', 'ect', 'rpm', 'afr',
        'fbkc', 'flkc', 'pw', 'iam', 'timing', 'inhibit', 'current_left',
        'current_right', 'angle_left', 'angle_right', 'lean_state', 'map',
        'throttle', 'speed')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(values):
    return {'min': min(values), 'median': statistics.median(values),
            'max': max(values)} if values else None


def summarize(rows):
    return {
        'samples': len(rows),
        'csv_lines': [rows[0]['csv_line'], rows[-1]['csv_line']] if rows else [],
        'range': {k: stats([r[k] for r in rows]) for k in KEYS},
        'valid_afr': stats([r['afr'] for r in rows if r['afr'] > 0]),
        'invalid_afr_samples': sum(r['afr'] == 0 for r in rows),
        'inhibit_counts': {f'{v:04X}': sum(r['inhibit'] == v for r in rows)
                           for v in sorted({int(r['inhibit']) for r in rows})},
        'lean_state_counts': {str(v): sum(r['lean_state'] == v for r in rows)
                             for v in sorted({int(r['lean_state']) for r in rows})},
    }


def main():
    assert sha(LOG) == '190ede240179e3560e12f7cafe7fffd1f9d88d872648504d58748f6c4d18918b'
    assert sha(ROM) == 'fabceb54359aca76e6e15835a51aa5cfd008e570dc002e886eaa62a6cb020ce5'
    with LOG.open(newline='', encoding='utf-8-sig') as source:
        raw = list(csv.reader(source))
    headings = raw.pop(0)
    assert len(headings) == len(KEYS) == 21
    assert all(len(row) == len(KEYS) and all(row) for row in raw)
    rows = [dict(zip(KEYS, map(float, row)), csv_line=i+2)
            for i, row in enumerate(raw)]
    for row in rows:
        row['time'] /= 1000
    assert len(rows) == 7697
    assert all(b['time'] > a['time'] for a, b in zip(rows, rows[1:]))

    definition = ROOT / 'logger/D2WD610H_master_logger.xml'
    params = {p.get('id'): p for p in ET.parse(definition).iter('parameter')}
    bank_map = []
    image = ROM.read_bytes()
    for bank, side, ids, indices, callbacks in (
            (0, 'right', ('P48', 'P52'), (0x3C, 0x40), (0x3192A, 0x31962)),
            (1, 'left', ('P49', 'P53'), (0x3D, 0x41), (0x31938, 0x31978))):
        for pid, index, callback in zip(ids, indices, callbacks):
            assert int(params[pid].findtext('address'), 16) == index
            assert params[pid].get('name').endswith(side.title())
            assert struct.unpack_from('>I', image, 0x4B6FC+index*4)[0] == callback
        assert params[ids[0]].get('name') in headings[KEYS.index('angle_'+side)]
        assert params[ids[1]].get('name') in headings[KEYS.index('current_'+side)]
        assert f'Bank {bank}' in headings[KEYS.index('duty_'+side)]
        bank_map.append({'software_bank': bank, 'definition_label': side.title(),
                         'angle_id': ids[0], 'current_id': ids[1],
                         'angle_ram': f'FFFF{0xC8C8+4*bank:04X}',
                         'current_ram': f'FFFF{0xB098+4*bank:04X}',
                         'normal_duty_ram': f'FFFF{0xC91C+4*bank:04X}'})

    identity = flash_identity(image, FLASH)
    identity['matches_saved_v2'] = identity.pop('matches_candidate')
    identity['syslog_sha256'] = sha(FLASH)
    identity['post_flash_completed_local'] = '2026-09-13 13:28:58.243'
    selectors = {
        'moving': lambda r: r['speed'] > 0,
        'high_demand_2500_3500': lambda r: r['speed'] > 5 and r['pedal'] >= 30
            and 2500 <= r['rpm'] <= 3500,
        'high_demand_2800_3500': lambda r: r['speed'] > 5 and r['pedal'] >= 30
            and 2800 <= r['rpm'] <= 3500,
        'loaded_760_720_to_765_721': lambda r: 760.720 <= r['time'] <= 765.721,
        'normal_output_withdrawal': lambda r: 731.991 <= r['time'] <= 733.657,
        'inhibit_before_shutdown': lambda r: r['inhibit'] != 0 and r['time'] < 804.543,
        'idle_iam_zero': lambda r: r['iam'] == 0,
    }
    windows = {name: summarize([r for r in rows if predicate(r)])
               for name, predicate in selectors.items()}
    assert windows['high_demand_2500_3500']['samples'] == 268
    assert windows['high_demand_2500_3500']['inhibit_counts'] == {'0000': 268}
    assert windows['high_demand_2800_3500']['samples'] == 109
    assert windows['high_demand_2800_3500']['range']['angle_right']['max'] == 0
    assert max(r['lean_state'] for r in rows) == 1
    assert sum(r['afr'] == 0 and r['speed'] > 0 for r in rows) == 42

    intervals = [b['time']-a['time'] for a, b in zip(rows, rows[1:])]
    report = {
        'source_log': str(LOG.relative_to(ROOT)), 'source_log_sha256': sha(LOG),
        'rom': str(ROM.relative_to(ROOT)), 'rom_sha256': sha(ROM),
        'definition_sha256': sha(definition), 'flash_identity': identity,
        'user_observations': ['Test connectors disconnected.', 'No DTCs reported.',
            'Cruise light flashing.', 'User confirms the over-3000 RPM cut persists.'],
        'headings': dict(zip(KEYS, headings)), 'bank_mapping': bank_map,
        'whole_capture': summarize(rows), 'windows': windows,
        'sample_interval_ms': stats([round(v*1000, 3) for v in intervals]),
        'gaps_over_200ms': [{'from': a['time'], 'to': b['time'],
                             'ms': round((b['time']-a['time'])*1000, 3)}
                            for a, b in zip(rows, rows[1:]) if b['time']-a['time'] > .2],
        'invalid_wb_moving': [r for r in rows if r['afr'] == 0 and r['speed'] > 0],
        'inhibit_with_pedal_above_10': [r for r in rows if r['inhibit'] and r['pedal'] > 10],
        'selected_event_rows': [min(rows, key=lambda r: abs(r['time']-t)) for t in
            (711.996, 731.991, 732.095, 732.303, 733.449,
             763.640, 763.848, 764.472, 764.576, 765.512, 780.407, 780.512)],
        'conclusions': [
            'The AVCS repair did not cure the cut, per the user and loaded capture.',
            'Both normal OCV output publications and current channels are active. '
            'Left reported advance changes; Right is zero throughout all selected high-demand samples.',
            'No sustained sampled B744 inhibition, lean-cut state3, IAM drop or knock retard '
            'coincides with the selected high-demand event.',
            'The recorded AFR becomes lean during part of the approximately3100RPM event. '
            'It does not establish whether fuel delivery or failed combustion caused the excursion.',
            'Rejected WB input can revoke cruise permission via the documented native path '
            'despite disabled O2 DTC enables. Actual lamp cause is not logged.',
        ],
        'limits': [
            'About104ms between samples cannot exclude brief firing/inhibit events between reads.',
            'C0DC spark mask, C0E1 mode, C290 auxiliary mask, synchronization, queue losses, '
            'and actual injector/coil hardware outputs are not logged.',
            'Right/Left follow the saved definition; physical harness assignment is not established.',
            'Actual-angle publication is clamped after subtracting learned offsets. Targets, '
            'raw captures, learned offsets and capture validity are absent, so zero does not prove a stuck solenoid.',
            'Normal OCV duty can differ from temporary diagnostic output. Overrides are not logged.',
            'Zero AFR is an invalid-input sentinel, not a measured zero air/fuel ratio. '
            'Raw WB ADC and cruise-fault flags are absent.',
            'The CSV contains no DTC response. No reported DTC is not proof that native fault latches are clear.',
            'ECT reaches69C. No direct before/after torque measurement or fully matched route exists.',
        ],
        'changes': 'Offline review only; source CSV, ROMs, calibrations and logger profiles unchanged.',
    }
    OUT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'output': str(OUT), 'samples': len(rows),
                      'flash_blocks_matched': len(identity['blocks']),
                      'high_demand_samples': windows['high_demand_2500_3500']['samples'],
                      'high_demand_inhibits': windows['high_demand_2500_3500']['inhibit_counts'],
                      'cut_cured': False}, indent=2))


if __name__ == '__main__':
    main()
