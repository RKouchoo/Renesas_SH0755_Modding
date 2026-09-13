#!/usr/bin/env python3
"""Review the flashed VE-adjustment drive without requesting another capture.

Actual SD wrapper and native cut instructions execute with explicit fixtures;
table helpers are descriptor-based interpolation models. Nothing here models
combustion, hydraulic lift, fuel pressure or actual electrical injector pulses.
"""

import _analysis_paths
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
from _captured_images import before_pump_scaling
from analyze_20260912_fueling_adjustment import KEYS, flow, stats

ROOT = _analysis_paths.ROOT
sys.path.insert(0, str(ROOT / 'tests'))
from test_primary_fueling_execution import PrimaryFuelMachine
from test_dbw_table_execution import DBWMachine
from test_native_fault_cut_execution import FaultCutMachine
from test_idle_air_override_execution import FAULT_WRITES
from test_throttle_link_execution import frame_with_status
from test_wideband_fuel_guard_execution import GuardMachine, safety, boost, wideband

LOG = ROOT / 'logs/romraiderlog_adjustedvedrive_20260912_144204.csv'
LOG_SHA = '347d10ce5e5c70d64f478e4bb6d124453697af07b1e074271ecbe1830d7efb33'
ROM_SHA = 'fd795813febf817c845fc922e81e498539a539efeeb6e4d11822af47098094a2'
OUT = ROOT / 'logs/20260912_adjusted_drive_review.json'
FLASH = Path('/Users/regan/.config/FastECU/0.1.0-beta.5/syslogs/log_fastecu_2026-09-12_11h31m48s.txt')


def replay_other_diagnostic_cuts(image, rows):
    """Hold explicit received faults; do not infer them from a vehicle trace."""
    results = []
    for source, offset, mask in (('C6F7/40', 0, 0x40),
                                  ('C6FA/02', 3, 0x02),
                                  ('C6F8/01', 1, 0x01)):
        cpu = FaultCutMachine(image)
        status = [0] * 7
        status[offset] = mask
        for _ in range(2):
            cpu.receive(frame_with_status(status))
        cpu.invoke(0x64874, FAULT_WRITES)
        selected = []
        for row in rows:
            cpu.put_float(0xFFFFB46C, row['pedal'])
            # P13 getter 316D0 encodes measured B2C4 using 31778
            # (0.31372547 native degrees/count); RR displays count*100/255.
            # Reconstruct the quantization centre, then execute 14CE6 so the
            # imposed TPS fault can select its real 6.375-degree substitute.
            # B2C8 is selected throttle angle, not coolant temperature.
            count = round(row['throttle'] * 255 / 100)
            selected_angle = cpu.select_throttle(
                count * struct.unpack_from('>f', image, 0x31778)[0])
            word = cpu.fault_cut(row['rpm'])
            if 77 <= row['time'] <= 85.25:
                selected.append({'word': word, 'pedal': row['pedal'],
                                 'pw': row['pw'], 'selected_throttle': selected_angle})
        assert selected
        words = {f'{word:04X}': sum(r['word'] == word for r in selected)
                 for word in sorted({r['word'] for r in selected})}
        cut_samples = [r for r in selected if r['word']]
        results.append({
            'received_fault_fixture': source,
            'D271_D272_D273_D274': [f'{cpu.read(a, 1):02X}'
                                    for a in range(0xFFFFD271, 0xFFFFD275)],
            'loaded_77_85_25s_inhibit_words': words,
            'logged_p21_ms_at_fixture_cut_samples': stats([r['pw'] for r in cut_samples])
                if cut_samples else None,
            'above_69_percent_pedal_samples': sum(r['pedal'] > 69 for r in selected),
            'above_69_percent_pedal_cut_samples': sum(r['pedal'] > 69 and bool(r['word'])
                                                       for r in selected),
            'selected_throttle_native_degrees': stats([r['selected_throttle'] for r in selected]),
        })
    return {
        'fixtures': results,
        'throttle_input': 'P13 B2C4 quantization centre followed by native14CE6 '
                          'fault selection into B2C8; previous coolant substitution corrected. '
                          'P13 saturates at255, so displayed100 percent provides only a lower bound.',
        'limit': 'Received faults are held active deliberately, not observed on the vehicle. '
                 'Other diagnostic cuts can outlast the 3000/2500 latch. All nonzero masks '
                 'in these fixtures include the P21 channel, so sustained operation would '
                 'still reduce its scheduled-pulse term after scheduler convergence.',
    }


def compare_dbw_maps(image, rows):
    """Compare both native lookup callers with driver torque passed through.

    This isolates the two calibration maps. Intervening torque arbitration,
    final request composition and actual throttle tracking are not replayed.
    """
    cpus = [DBWMachine((ROOT / '2005 BLE MT.bin').read_bytes()), DBWMachine(image)]

    def mapped(rpm, pedal):
        values = []
        for cpu in cpus:
            cpu.put_float(0xFFFFB544, rpm)
            cpu.put_float(0xFFFFB46C, pedal)
            cpu.invoke(0x2B35A, {(0xFFFFC3DC, 4)})
            torque = cpu.get_float(0xFFFFC3DC)
            cpu.put_float(0xFFFFC3D4, torque)  # Explicit arbitration boundary.
            cpu.invoke(0x2AF5C, {(0xFFFFC3D0, 4)})
            values.append((torque, cpu.get_float(0xFFFFC3D0)))
        return values

    windows = []
    for name, predicate in (
            ('first_event_70_5_72_32s', lambda r: 70.5 <= r['time'] <= 72.32),
            ('long_bog_77_85_25s', lambda r: 77 <= r['time'] <= 85.25),
            ('moving_2500_3500_rpm_pedal_at_least_25',
             lambda r: r['speed'] > 0 and 2500 <= r['rpm'] <= 3500 and r['pedal'] >= 25)):
        points = []
        for row in filter(predicate, rows):
            stock, captured = mapped(row['rpm'], row['pedal'])
            points.append((stock, captured))
        windows.append({
            'window': name, 'samples': len(points),
            'different_map_output_samples': sum(a != b for a, b in points),
            'captured_minus_stock_mapped_angle_degrees': stats([b[1] - a[1] for a, b in points]),
            'captured_mapped_angle_degrees': stats([b[1] for _, b in points]),
        })
    # Verify that the comparison detects the installed light-pedal edits.
    stock, captured = mapped(1000, 1)
    assert stock != captured
    return {
        'windows': windows,
        'changed_calibration_positive_control': {
            'rpm': 1000, 'pedal_percent': 1,
            'stock_torque_and_angle': stock, 'captured_torque_and_angle': captured},
        'limit': 'Native 2B35A and 2AF5C callers execute with mathematical table interpolation. '
                 'C3DC is copied into C3D4 as an explicit driver-only arbitration fixture. '
                 'Outputs are mapped requests, not the unlogged final C2B4 request or a '
                 'measurement of throttle-tracking error. Matching outputs in a window '
                 'do not exclude faults or effects of earlier state.',
    }


def main():
    image = before_pump_scaling((ROOT / 'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes())
    assert hashlib.sha256(image).hexdigest() == ROM_SHA, 'Use the exact captured image'
    assert hashlib.sha256(LOG.read_bytes()).hexdigest() == LOG_SHA
    with LOG.open(encoding='utf-8-sig', newline='') as source:
        records = list(csv.reader(source))
    assert len(records) == 2748 and all(len(r) == len(KEYS) for r in records)
    rows = [dict(zip(KEYS, map(float, row))) for row in records[1:]]
    assert all(math.isfinite(v) for r in rows for v in r.values())
    for row in rows:
        row['time'] /= 1000
    assert all(a['time'] < b['time'] for a, b in zip(rows, rows[1:]))
    marks = list(re.finditer(r'\[([^\]]+)\] \(II\) --- Comparing ECU flash memory pages to image file after reflash ---', FLASH.read_text()))
    index, flashed_at = [(i, m.group(1)) for i, m in enumerate(marks)
                         if datetime.fromisoformat(m.group(1)) < datetime(2026, 9, 12, 14, 42, 4)][-1]
    identity = flash_identity(image, FLASH, index)
    assert identity['matches_candidate']
    primary = PrimaryFuelMachine(image)
    scalar = struct.unpack_from('>f', image, 0x76014)[0] / 1000
    windows = []
    for start, end in ((68, 72.3), (77, 85.8), (107, 111), (115, 117.8),
                       (133.5, 137.3), (177, 181), (185, 198), (230, 233.7), (247, 252)):
        selected = [r for r in rows if start <= r['time'] <= end
                    and r['pedal'] >= 25 and abs(r['trans']) < .03]
        derived = []
        for r in selected:
            raw = flow(image, r['rpm'], r['map'] / .1333224, r['iat'], int(r['mode'])) * 60 / r['rpm']
            target = primary.table(0x2150, 0x5FA9C, r['load'], r['rpm'])
            derived.append({
                'raw_sd_load_g_rev': raw,
                'load_error_g_rev': raw - r['load'],
                'factor_minus_primary_and_transient': r['factor'] - 1 - target - r['trans'],
                'gross_pulse_residual_ms': r['pw'] - r['load'] * scalar * r['factor'],
                'afr_equivalent_of_additive_factor': 14.64 / r['factor'],
            })
        windows.append({'requested_time_range': [start, end], 'samples': len(selected),
                        'logged': {k: stats([r[k] for r in selected]) for k in KEYS},
                        'derived': {k: stats([r[k] for r in derived]) for k in derived[0]}})
    # Hold each low-lift bog sample through all transport/confirmation counts.
    # This identifies fresh cuts on these steady inputs, not unlogged live cuts.
    cut_samples = [r for r in rows if 77 <= r['time'] <= 85.25 and r['pedal'] >= 25]
    cut_count = 0
    for baro in (90, 94.6855, 100):
        for r in cut_samples:
            cpu = GuardMachine(image)
            cpu.put_float(safety.ATMOSPHERIC_PRESSURE, baro / .1333224)
            cpu.put_float(safety.MAP_PRESSURE, r['map'] / .1333224)
            cpu.put_float(boost.RPM_ADDR, r['rpm'])
            cpu.put_float(wideband.FRONT_READY_METRIC_BANK1, 50 if r['afr'] > 0 else 0)
            cpu.put_float(cpu.wideband_outputs[2], r['afr'] / 14.64)
            calls = (cpu.read(safety.LEAN_TRANSPORT_COUNT_ADDR, 2)
                     + cpu.read(safety.LEAN_CONFIRM_COUNT_ADDR, 2) + 4)
            for _ in range(calls):
                result = cpu.cut_step()
            cut_count += bool(result[-1])
    assert cut_count == 0
    # The newly traced 3000/2500 diagnostic cut is a separate native path.
    # Deliberately hold its diagnostic request active, execute each sampled
    # RPM in order and expose why it cannot explain all of the long bog.
    # This is not a reconstruction of the unlogged diagnostic request.
    fault_cpu = FaultCutMachine(image)
    fault_cpu.write(0xFFFFD273, 2, 1)
    native_cut_history = []
    for r in rows:
        inhibit = fault_cpu.fault_cut(r['rpm'])
        native_cut_history.append({'time': r['time'], 'rpm': r['rpm'],
                                   'inhibit_word': inhibit})
    native_bog = [r for r in native_cut_history if 77 <= r['time'] <= 85.25]
    assert native_bog and all(r['inhibit_word'] == 0 for r in native_bog)
    spikes = []
    for i, r in enumerate(rows):
        if r['map'] > 140:
            spikes.append({'sample': r, 'previous': rows[i-1], 'next': rows[i+1],
                           'quarter_of_reported_map_kpa': r['map'] / 4,
                           'interpretation': 'Compatible with mixed bytes across a float exponent boundary; not established as a physical pressure spike.'})
    idle = [r for r in rows if 10 <= r['time'] <= 30 and r['pedal'] == 0 and r['speed'] == 0]
    report = {
        'log': str(LOG.relative_to(ROOT)), 'log_sha256': LOG_SHA,
        'captured_rom_sha256': ROM_SHA, 'flash_verified_at': flashed_at,
        'flash_identity': identity, 'samples': len(rows), 'duration_seconds': rows[-1]['time'],
        'idle_10_30s': {k: stats([r[k] for r in idle]) for k in KEYS},
        'fueling_status_values': sorted({r['state'] for r in rows}),
        'loaded_windows': windows,
        'avls_transitions': [{'previous': rows[i-1], 'sample': r} for i, r in enumerate(rows)
                             if i and rows[i-1]['mode'] != r['mode']],
        'isolated_map_outliers': spikes,
        'fresh_cut_sweep': {'fixtures': len(cut_samples)*3, 'baro_fixtures_kpa': [90, 94.6855, 100],
                            'fresh_cuts': cut_count, 'stock_fault_flags': 'clear fixtures'},
        'native_3000_rpm_cut_replay': {
            'routine': '000253A8', 'request': 'FFFFD273 mask 02 forced active fixture',
            'trip_rpm': 3000, 'release_below_rpm': 2500,
            'all_six_inhibit_word': '003F',
            'loaded_77_85_25s_samples': len(native_bog),
            'loaded_77_85_25s_cut_samples': sum(bool(r['inhibit_word']) for r in native_bog),
            'release_near_73s': [r for r in native_cut_history if 73 <= r['time'] <= 73.3],
            'limit': 'Observed RPM samples cannot establish the live cut history; unlogged faults and between-sample excursions remain unobserved.',
        },
        'other_native_diagnostic_cut_replays': replay_other_diagnostic_cuts(image, rows),
        'dbw_map_comparison': compare_dbw_maps(image, rows),
        'limits': [
            'User reports persistent loaded misfire/bog and requests no more logs until a cause is fixed.',
            'Recorded commands and code explain fuel duration; they do not identify the physical cause of poor combustion/torque.',
            'B7DC is an additive factor, not all bank corrections; pulse residual is not independently measured latency.',
            'No runtime baro, actual cut state, measured cam lift, fuel pressure or electrical ignition capture.',
            'Fresh-cut sweep holds sampled values; it cannot rule out faults or excursions between samples, or a previously latched cut.',
            'An arbitrary boost VE reduction is not proven corrective; VE need not be constant with boost, and lowering load also changes the primary table target.',
        ],
    }
    OUT.write_text(json.dumps(report, indent=2) + '\n')
    print('Flash identity: all 16 blocks match', ROM_SHA)
    print('Rows:', len(rows), 'duration:', rows[-1]['time'], 'seconds')
    print('Fresh-cut fixtures:', report['fresh_cut_sweep'])
    print('Wrote', OUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
