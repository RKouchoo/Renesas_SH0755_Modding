#!/usr/bin/env python3
"""Review the neutral AVLS capture and verify its recorded flash identity.

Reads the source CSV unchanged. Reconstructs the captured images from the
pinned oil-gate repair and subsequent ten-cell v2 VE adjustment evidence.
This is a log summary; the separate native AVLS execution suite tests gates.
"""

import _analysis_paths
from _captured_images import before_pump_scaling
import argparse
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import struct
import sys

from analyze_20260908_recovery import flash_identity

ROOT = _analysis_paths.ROOT
LOG = ROOT / 'logs/romraiderlog_avlslog_20260912_131657.csv'
OUT = ROOT / 'logs/20260912_avls_neutral_review.json'
FLASH = Path('/Users/regan/.config/FastECU/0.1.0-beta.5/syslogs/log_fastecu_2026-09-12_11h31m48s.txt')
LOG_SHA = '77863ac12f459d1092aba57f0d65cded033d1730c600c4ac6d1f550051a42265'
CAPTURED_SHA = 'c6528704472f396cf57c3d18b5e6ef14e46b6da376e9cf19f58f8739ca5c66bc'
CORRECTED_SHA = '4808414b01f3ede952197422f75a791f5325595a27bc810ca610b82d3954d67e'
FOLLOWUP_LOG = ROOT / 'logs/romraiderlog_avlslog2_20260912_133746.csv'
FOLLOWUP_OUT = ROOT / 'logs/20260912_avls_neutral_followup_review.json'
FOLLOWUP_LOG_SHA = 'd7252e1205e2ad8e8c4106dc166747c3ce2ac091de86c1d4428af5969ad57fd0'
KEYS = ('time', 'bank0', 'bank1', 'pedal', 'mode', 'ect', 'rpm', 'afr',
        'fbkc', 'flkc', 'pw', 'iam', 'timing', 'inhibit', 'lean',
        'current_left', 'current_right', 'duty_left', 'duty_right',
        'oil', 'map', 'baro', 'throttle', 'speed')


def corrected_image():
    """Restore the captured oil-gate image after the rolling VE calibration edit."""
    image = bytearray(before_pump_scaling((ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()))
    digest = hashlib.sha256(image).hexdigest()
    if digest != CORRECTED_SHA:
        review = json.loads((ROOT / 'logs/20260912_fueling_adjustment_review.json').read_text())
        assert digest == review['after_sha256'], 'Unrecognized rolling image'
        assert review['before_sha256'] == CORRECTED_SHA
        for word in review['changed_words']:
            addr = int(word['address'], 16)
            assert image[addr:addr+4] == bytes.fromhex(word['after_hex'])
            image[addr:addr+4] = bytes.fromhex(word['before_hex'])
    assert hashlib.sha256(image).hexdigest() == CORRECTED_SHA, 'Captured oil-gate image unavailable'
    return bytes(image)


def captured_image():
    current = (ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
    if hashlib.sha256(current).hexdigest() == CAPTURED_SHA:
        return current
    image = bytearray(corrected_image())
    struct.pack_into('>2f', image, 0x7D4B0, 110, 110)
    total = sum(w[0] for w in struct.iter_unpack('>I', image[0x2000:0x7FAF8]))
    struct.pack_into('>I', image, 0x7FB88, (0x5AA5A55A - total) & 0xFFFFFFFF)
    assert hashlib.sha256(image).hexdigest() == CAPTURED_SHA, 'Unrecognized image; use the pinned capture or oil-gate repair'
    return bytes(image)


def read_log(path=LOG, digest=LOG_SHA, expected_rows=1278):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    source = list(csv.reader(path.open(encoding='utf-8-sig', newline='')))
    assert all(len(r) == len(KEYS) for r in source)
    with LOG.open(encoding='utf-8-sig', newline='') as baseline:
        assert source[0] == next(csv.reader(baseline)), 'Unexpected channel order'
    rows = [dict(zip(KEYS, map(float, r))) for r in source[1:]]
    assert all(math.isfinite(v) for r in rows for v in r.values())
    for row in rows:
        row['time'] /= 1000
    assert len(rows) == expected_rows
    assert all(b['time'] > a['time'] for a, b in zip(rows, rows[1:]))
    return rows


def summarize(rows):
    running = [r for r in rows if r['rpm'] > 500]
    high = [r for r in rows if r['rpm'] >= 3200]
    pedal_high = [r for r in high if r['pedal'] >= 6]
    cuts = []
    for i, r in enumerate(rows):
        if r['inhibit'] == 0:
            continue
        if not cuts or cuts[-1]['last_index'] != i - 1 or cuts[-1]['word'] != r['inhibit']:
            cuts.append({'word': int(r['inhibit']), 'first_index': i, 'last_index': i,
                         'start': r['time'], 'end': r['time'], 'samples': []})
        cuts[-1]['last_index'] = i
        cuts[-1]['end'] = r['time']
        cuts[-1]['samples'].append(r)
    return {
        'samples': len(rows), 'duration_seconds': rows[-1]['time'],
        'interval_median_seconds': statistics.median(b['time'] - a['time'] for a, b in zip(rows, rows[1:])),
        'mode_values': {k: sorted({r[k] for r in rows}) for k in ('mode', 'bank0', 'bank1')},
        'peak_rpm_sample': max(rows, key=lambda r: r['rpm']),
        'samples_at_or_above_3200': len(high),
        'high_rpm_time_range': [high[0]['time'], high[-1]['time']],
        'high_rpm_pedal_applied_ranges': {k: [min(r[k] for r in pedal_high), max(r[k] for r in pedal_high)]
            for k in ('rpm', 'pedal', 'map', 'afr', 'iam', 'fbkc', 'flkc',
                      'inhibit', 'lean', 'current_left', 'current_right', 'duty_left', 'duty_right')},
        'temperatures': {k: [min(r[k] for r in running), max(r[k] for r in running)] for k in ('ect', 'oil')},
        'baro_values_kpa': sorted({r['baro'] for r in rows}),
        'minimum_map_sample': min(rows, key=lambda r: r['map']),
        'cut_windows': cuts,
        'iam_changes': [r for i, r in enumerate(rows) if not i or r['iam'] != rows[i-1]['iam']],
    }


def followup_summary(rows):
    summary = summarize(rows)
    summary['vehicle_speed_values'] = sorted({r['speed'] for r in rows})
    summary['bank_mismatch_samples'] = [r for r in rows
        if not r['mode'] == r['bank0'] == r['bank1']]
    summary['all_lean_state_values'] = sorted({r['lean'] for r in rows})
    summary['pedal_applied_inhibit_samples'] = [r for r in rows
        if r['pedal'] > 0 and r['inhibit'] != 0]

    def ranges(samples, keys=KEYS[1:]):
        return {k: {'min': min(r[k] for r in samples),
                    'median': statistics.median(r[k] for r in samples),
                    'max': max(r[k] for r in samples)} for k in keys}

    high_windows = []
    for i, entry in enumerate(rows):
        if entry['mode'] != 3 or (i and rows[i-1]['mode'] == 3):
            continue
        end = next(j for j in range(i+1, len(rows)) if rows[j]['mode'] != 3)
        samples = rows[i:end]
        bank_follow = next(r for r in samples if r['bank0'] == r['bank1'] == 3)
        hold_end = next((j for j in range(i+1, end)
            if abs(rows[j]['pedal']-entry['pedal']) > .5
            or abs(rows[j]['throttle']-entry['throttle']) > .5), end)
        held = [r for r in rows[i:hold_end] if r['time'] >= entry['time']+1]
        before = [r for r in rows[:i] if r['time'] >= entry['time']-.6]
        high_windows.append({
            'entry': entry, 'last_high': rows[end-1], 'first_low': rows[end],
            'samples': len(samples), 'ranges': ranges(samples),
            'both_banks_high_first_sample': bank_follow['time'],
            'observed_bank_follow_interval_seconds': bank_follow['time']-entry['time'],
            'before_entry_time_range': [before[0]['time'], before[-1]['time']],
            'before_entry_ranges': ranges(before),
            'held_high_definition': 'At least one second after entry, until pedal or plate differs by more than 0.5 percentage points from the entry sample.',
            'held_high_time_range': [held[0]['time'], held[-1]['time']],
            'held_high_ranges': ranges(held),
        })
    summary['high_lift_windows'] = high_windows

    invalid_windows = []
    for i, r in enumerate(rows):
        if r['afr'] != 0:
            continue
        if not invalid_windows or invalid_windows[-1]['last_index'] != i-1:
            invalid_windows.append({'first_index': i, 'last_index': i,
                                    'start': r['time'], 'end': r['time'], 'samples': []})
        invalid_windows[-1]['last_index'] = i
        invalid_windows[-1]['end'] = r['time']
        invalid_windows[-1]['samples'].append(r)
    summary['wideband_invalid_zero_windows'] = invalid_windows
    last_exit = high_windows[-1]['first_low']['time']
    shutdown = next(r['time'] for r in rows
                    if r['time'] > last_exit and r['inhibit'] == 65535)
    recovery = [r for r in rows if last_exit <= r['time'] < shutdown]
    summary['final_recovery_before_shutdown'] = {
        'time_range': [recovery[0]['time'], recovery[-1]['time']],
        'minimum_rpm_sample': min(recovery, key=lambda r: r['rpm']),
        'first_sample_below_1000_rpm': next(r for r in recovery if r['rpm'] < 1000),
    }
    return summary


def followup_airflow_replay(rows, image):
    """Conditional SD/table comparison; IAT and conditioned load were not logged."""
    sys.path.insert(0, str(ROOT / 'tests'))
    import test_hook_execution as hook
    from test_primary_fueling_execution import PrimaryFuelMachine

    hook.IMAGE = image
    target = PrimaryFuelMachine(image)
    pairs = []
    for i, entry in enumerate(rows):
        if not i or entry['mode'] != 3 or rows[i-1]['mode'] != 1:
            continue
        before = rows[i-1]
        after = next(r for r in rows[i:] if r['time'] >= entry['time']+2)
        sweeps = []
        for iat in (0, 25, 60):
            points = []
            for r in (before, after):
                flows = [hook.Machine(r['rpm'], r['map']/.1333224, iat, m).run()
                         for m in (1, 3)]
                load = flows[(int(r['mode'])-1)//2] * 60 / r['rpm']
                points.append({
                    'time': r['time'], 'sd_g_s_low_mode': flows[0],
                    'sd_g_s_high_mode': flows[1], 'raw_load_g_rev': load,
                    'mode_only_airflow_change_percent': 100*(flows[1]/flows[0]-1),
                    'primary_table_only_afr': {
                        f'{a:05X}': 14.64/(1+target.table(0x2150, a, load, r['rpm']))
                        for a in (0x5FA9C, 0x5FAB8)},
                })
            sweeps.append({'fixed_iat_fixture_c': iat, 'points': points,
                           'raw_load_change_percent': 100*(points[1]['raw_load_g_rev']/points[0]['raw_load_g_rev']-1)})
        pairs.append({'before': before, 'two_seconds_after_entry': after, 'sweeps': sweeps})
    margin = struct.unpack_from('>f', image, 0x7EAD0)[0] * .1333224
    return {
        'method': 'Actual SD-wrapper opcodes with descriptor-based lookup models, using recorded RPM/MAP/mode. IAT is held at three explicit fixtures, not inferred from the capture.',
        'primary_table_comparison_limit': 'Raw modeled load is used for illustration. Native primary fueling consumes conditioned B438 and other corrections; this is not a reconstruction of the commanded target.',
        'pairs': pairs,
        'pressure_forced_ol_absolute_kpa': sorted({r['baro']-margin for r in rows}),
        'high_lift_map_peak_kpa': max(r['map'] for r in rows if r['mode'] == 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--followup', action='store_true',
                        help='Review the 13:37 capture on the corrected oil-gate image.')
    args = parser.parse_args()
    if args.followup:
        log, out, log_sha, rom_sha = FOLLOWUP_LOG, FOLLOWUP_OUT, FOLLOWUP_LOG_SHA, CORRECTED_SHA
        image = corrected_image()
        assert hashlib.sha256(image).hexdigest() == rom_sha, 'Captured image unavailable'
        captured_at = datetime(2026, 9, 12, 13, 37, 46)
        rows = read_log(log, log_sha, 1676)
        summary = followup_summary(rows)
        summary['conditional_airflow_replay'] = followup_airflow_replay(rows, image)
        limits = [
            'Two stationary high-lift command/electrical transitions; no loaded samples.',
            'Both bank software modes and solenoid currents respond, but these do not measure hydraulic lift or valve motion.',
            'Driver subsequently reports the run felt fine.',
            'Oil reaches 56 C and coolant 61 C; this is not a fully warmed loaded validation.',
            'High-lift richening is measured; target/composed fuel factor, CL/OL status, load and AVCS are absent, so its cause is not identified.',
            'No sampled added lean cut; pressure stays below the arming threshold and does not test latch release.',
            'Word 63 after final pedal release is consistent with native overrun cut; its source flags are absent.',
            'AFR zero is the invalid-data sentinel, not a measured zero AFR or proof of a serial dropout.',
            'Final global inhibition accompanies shutdown; the key switch was not logged.',
            'SSM values are quantized and not atomic; one-row bank differences are not measured hydraulic delays.',
        ]
    else:
        log, out, log_sha, rom_sha = LOG, OUT, LOG_SHA, CAPTURED_SHA
        image = captured_image()
        captured_at = datetime(2026, 9, 12, 13, 16, 57)
        rows = read_log()
        summary = summarize(rows)
        limits = ['No high-lift samples; no physical lift validation.',
                  'Oil channel P122 precedes selected CF94; stationary qualifier flags were not logged.',
                  'No sampled added lean cut; this capture does not test latch release or cuts under load.',
                  'Word 63 after throttle release is consistent with native overrun cut; retained source flags were not captured.',
                  'Final word 65535 coincides with engine shutdown; key-off is inferred from sequence, not a logged key channel.',
                  'SSM values are quantized and not atomic.']
    text = FLASH.read_text()
    marks = list(re.finditer(r'\[([^\]]+)\] \(II\) --- Comparing ECU flash memory pages to image file after reflash ---', text))
    prior = [(i, m.group(1)) for i, m in enumerate(marks)
             if datetime.fromisoformat(m.group(1)) < captured_at]
    verification, flashed_at = prior[-1]
    report = {'log': str(log.relative_to(ROOT)), 'log_sha256': log_sha,
              'captured_rom_sha256': rom_sha, 'flash_verified_at': flashed_at,
              'flash_identity': flash_identity(image, FLASH, verification),
              'summary': summary, 'limits': limits}
    assert report['flash_identity']['matches_candidate']
    out.write_text(json.dumps(report, indent=2) + '\n')
    s = report['summary']
    print('Flash:', flashed_at, 'all 16 blocks match', rom_sha)
    print('Rows:', s['samples'], 'high-RPM rows:', s['samples_at_or_above_3200'], 'lift modes:', s['mode_values'])
    print('High-RPM ranges:', s['high_rpm_pedal_applied_ranges'])
    print('Wrote', out)


if __name__ == '__main__':
    main()
