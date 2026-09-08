#!/usr/bin/env python3
"""Attribute retained B874 fuel correction on the measured 14:13 trajectory.

Native history/compensation instructions run on fixed recorded load/RPM/ECT.
Table lookups remain mathematical boundaries. At selected points, clone the
pre-update state and alter only the slow negative gain in memory. This tests
software sensitivity, not wall-film physics, combustion or a calibration fix.
No BIN is written.
"""
import argparse
import bisect
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import statistics
import struct

from analyze_20260908_recovery import read_capture, CANDIDATE, LOG_SHA256
from idle_recovery_candidate import CANDIDATE_SHA256
from test_transient_fuel_execution import TransientFuelMachine, TRANSIENT_WRITES
from test_primary_fueling_execution import number
import sh2e_test_fpu as fpu

NEGATIVE_SLOW_GAIN = 0x76030
POINTS = (192.959, 248.188, 248.604, 249.124)


def terms(cpu):
    def raw(short):
        return cpu.read(0xFFFF0000 | short, 4)

    fast = fpu.binary('mul', raw(0xB884), raw(0xB8A4))
    slow = fpu.binary('mul', raw(0xB888), raw(0xB8A8))
    slow = fpu.binary('mul', slow, raw(0xB8B0))
    combined = fpu.multiply_accumulate(raw(0xB8AC), fast, slow)
    combined = fpu.binary('mul', combined, raw(0xB890))
    assert combined == raw(0xB874), 'Component attribution differs from native result'
    return {'history_load': cpu.get_float(0xFFFFB878),
            'fast_load_delta': cpu.get_float(0xFFFFB880),
            'slow_load_delta': cpu.get_float(0xFFFFB87C),
            'fast_before_final_gains': cpu.get_float(0xFFFFB884),
            'slow_before_final_gains': cpu.get_float(0xFFFFB888),
            'fast_coolant_gain': cpu.get_float(0xFFFFB8A4),
            'fast_rpm_gain': cpu.get_float(0xFFFFB8AC),
            'slow_coolant_gain': cpu.get_float(0xFFFFB8A8),
            'slow_rpm_gain': cpu.get_float(0xFFFFB8B0),
            'startup_gain': cpu.get_float(0xFFFFB890),
            'fast_term_before_startup_gain': number(fpu.binary('mul', fast, raw(0xB8AC))),
            'slow_term_before_startup_gain': number(slow),
            'native_B874': cpu.get_float(0xFFFFB874)}


def analyze():
    image = CANDIDATE.read_bytes()
    assert hashlib.sha256(image).hexdigest() == CANDIDATE_SHA256
    # Actual negative branch: 1EAC0 loads the pointer at 1EBC0, then multiplies
    # B87C by that scalar. This branch is separate from the positive gain.
    assert image[0x1EAC0:0x1EAC8] == bytes.fromhex('d33ff238f422f44a')
    assert struct.unpack_from('>I', image, 0x1EBC0)[0] == NEGATIVE_SLOW_GAIN
    gain = struct.unpack_from('>f', image, NEGATIVE_SLOW_GAIN)[0]
    assert abs(gain-.04) < 1e-8
    images = {}
    for label, multiplier in (('half_negative_slow_gain', .5), ('zero_negative_slow_gain', 0)):
        variant = bytearray(image)
        struct.pack_into('>f', variant, NEGATIVE_SLOW_GAIN, gain*multiplier)
        assert all(a == b for i, (a, b) in enumerate(zip(image, variant))
                   if not NEGATIVE_SLOW_GAIN <= i < NEGATIVE_SLOW_GAIN+4)
        images[label] = bytes(variant)

    _, capture = read_capture()
    rows = [r for r in capture if 130 <= r['time'] < 256]
    selected_times = {min(rows, key=lambda r: abs(r['time']-point))['time'] for point in POINTS}
    times = [r['time'] for r in rows]
    cpu = TransientFuelMachine(image, **{k: rows[0][k] for k in ('load', 'rpm', 'coolant')})

    def inputs(t):
        index = max(0, min(len(rows)-2, bisect.bisect_right(times, t)-1))
        a, b = rows[index:index+2]
        fraction = max(0, min(1, (t-a['time'])/(b['time']-a['time'])))
        return {k: a[k]+fraction*(b[k]-a[k]) for k in ('load', 'rpm', 'coolant')}

    selected, errors = [], []
    t, index, updates = times[0], 0, 0
    while index < len(rows):
        current = inputs(t)
        end = bisect.bisect_right(times, t)
        needs_variant = any(r['time'] in selected_times for r in rows[index:end])
        snapshot = deepcopy(cpu) if needs_variant else None
        correction = cpu.transient(**current)
        updates += 1
        while index < len(rows) and t >= times[index]:
            row = rows[index]
            if row['time'] >= 145:
                errors.append(abs(correction-row['transient']))
            if row['time'] in selected_times:
                record = {'seconds': row['time'], 'update_seconds': t,
                          'logged': {k: row[k] for k in ('rpm', 'coolant', 'load', 'map',
                                     'throttle', 'afr', 'transient', 'factor', 'pulse')},
                          'baseline': terms(cpu), 'variants': {}}
                residual = row['factor']-row['transient']
                for label, variant in images.items():
                    alternative = deepcopy(snapshot)
                    alternative.image = variant
                    alternative.transient(**current)
                    for address, size in TRANSIENT_WRITES - {(0xFFFFB874, 4), (0xFFFFB888, 4)}:
                        assert cpu.read(address, size) == alternative.read(address, size), (label, hex(address))
                    state = terms(alternative)
                    state['net_ms_at_fixed_logged_load_and_residual'] = max(
                        .6, row['load']*3.2666667*(residual+state['native_B874']))
                    record['variants'][label] = state
                selected.append(record)
            index += 1
        t += 20/current['rpm']

    # Direction/steady-state controls: only the negative slow term may change.
    controls = []
    for label, loads in (('steady', [.75]*100), ('opening', [.85]*100), ('closing', [.53]*100)):
        reference = TransientFuelMachine(image)
        variants = {name: TransientFuelMachine(data) for name, data in images.items()}
        changed = {name: 0 for name in variants}
        for load in loads:
            original = reference.transient(load)
            for name, alternative in variants.items():
                value = alternative.transient(load)
                changed[name] += value != original
                if reference.get_float(0xFFFFB87C) >= 0:
                    assert reference.read(0xFFFFB874, 4) == alternative.read(0xFFFFB874, 4)
        controls.append({'trajectory': label, 'changed_updates': changed})
    assert len(selected) == len(POINTS)
    return {'candidate_sha256': CANDIDATE_SHA256, 'capture_sha256': LOG_SHA256,
            'negative_slow_gain_address': hex(NEGATIVE_SLOW_GAIN), 'original_gain': gain,
            'native_updates': updates, 'B874_median_absolute_error': statistics.median(errors),
            'selected_points': selected, 'direction_controls': controls,
            'limits': ['Fixed recorded conditioned load/RPM/ECT; arbitrary initial crank phase and settled startup/flag fixtures.',
                       'Stock table interpolation is mathematical; native routine and component arithmetic execute SH-2E operations.',
                       'Alternative gain values exist only in memory and are sensitivity controls, not recommended calibrations.',
                       'Pulse sensitivity holds logged load and B7DC-minus-B874 fixed; no engine/AFR, injector-event or wall-film prediction.',
                       'Latest evening captures do not contain B874; their zero-pulse cause is unlogged.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assert args.output.suffix.lower() == '.json'
    result = analyze()
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(f"PASS: {result['native_updates']} native updates; median B874 error "
          f"{result['B874_median_absolute_error']:.6f}; report {args.output}")
