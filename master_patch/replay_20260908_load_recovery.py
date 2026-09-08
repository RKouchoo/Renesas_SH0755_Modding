#!/usr/bin/env python3
"""Native load-filter/B874 sensitivity using the measured 14:13 trajectory.

This is an open-loop calculation on fixed recorded inputs, not an engine
prediction. Alternative filter constants exist only in memory; no BIN output.
"""

import _analysis_paths  # Locate shared offline interpreters after repository cleanup.
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import statistics as stats
import struct

from analyze_20260908_recovery import read_capture, CANDIDATE, LOG_SHA256
from idle_recovery_candidate import CANDIDATE_SHA256
from test_load_conditioning_execution import LoadConditioningMachine
from test_transient_fuel_execution import TransientFuelMachine


def replay():
    image = CANDIDATE.read_bytes()
    assert hashlib.sha256(image).hexdigest() == CANDIDATE_SHA256
    _, capture = read_capture()
    rows = [r for r in capture if 130 <= r['time'] < 256]
    times = [r['time'] for r in rows]
    first = rows[0]
    common = {k: first[k] for k in ('load', 'rpm', 'coolant')}
    observed = TransientFuelMachine(image, **common)
    models = {}
    for alpha in (.06, .2, 1.0):
        variant = bytearray(image)
        struct.pack_into('>f', variant, 0x73968, alpha)
        models[str(alpha)] = LoadConditioningMachine(variant, **common)

    def inputs(t):
        i = max(0, min(len(rows) - 2, bisect.bisect_right(times, t) - 1))
        a, b = rows[i:i + 2]
        q = max(0, min(1, (t - a['time']) / (b['time'] - a['time'])))
        return {k: a[k] + q * (b[k] - a[k]) for k in
                ('load', 'rpm', 'coolant', 'map', 'throttle', 'airflow')}

    result = []
    t, index = times[0], 0
    while index < len(rows):
        current = inputs(t)
        correction = observed.transient(**{k: current[k] for k in ('load', 'rpm', 'coolant')})
        states = {}
        for alpha, cpu in models.items():
            conditioned = cpu.condition(
                airflow=current['airflow'], rpm=current['rpm'], coolant=current['coolant'],
                map_mmhg=current['map'] / .1333224, throttle=current['throttle'] * .84)
            transient = cpu.transient()
            states[alpha] = {'load': conditioned, 'transient': transient}
        while index < len(rows) and t >= times[index]:
            row = rows[index]
            # B7DC already contains B874. Preserve its measured residual only
            # as a sensitivity boundary; changing load can change that residual.
            residual = row['factor'] - row['transient']
            for state in states.values():
                state['factor_with_fixed_residual'] = residual + state['transient']
                state['net_ms_with_fixed_residual'] = max(
                    .6, state['load'] * 3.2666667 * state['factor_with_fixed_residual'])
            result.append(dict(seconds=row['time'], update_time=t, rpm=row['rpm'],
                               logged_load=row['load'], logged_transient=row['transient'],
                               logged_net_ms=row['pulse'], recorded_load_B874=correction,
                               variants={k: dict(v) for k, v in states.items()}))
            index += 1
        t += 20 / current['rpm']

    active = [r for r in result if 145 <= r['seconds'] < 256]
    metrics = {}
    for alpha in models:
        values = [r['variants'][alpha] for r in active]
        metrics[alpha] = dict(
            load_median_absolute_error=stats.median(abs(v['load'] - r['logged_load']) for v, r in zip(values, active)),
            load_mean_absolute_error=stats.mean(abs(v['load'] - r['logged_load']) for v, r in zip(values, active)),
            B874_median_absolute_error=stats.median(abs(v['transient'] - r['logged_transient']) for v, r in zip(values, active)),
            B874_min=min(v['transient'] for v in values), B874_max=max(v['transient'] for v in values),
            net_ms_median_absolute_error=stats.median(abs(v['net_ms_with_fixed_residual'] - r['logged_net_ms']) for v, r in zip(values, active)),
            net_ms_at_floor_samples=sum(v['net_ms_with_fixed_residual'] == .6 for v in values))
    return dict(
        candidate_sha256=CANDIDATE_SHA256, log_sha256=LOG_SHA256,
        source_start_seconds=times[0], evaluated_seconds=[145, 256],
        cadence='172A4 then 1E7E8 on the 11AD0 task-6 route; one normal activation per 120 crank degrees. Interval 20/RPM with arbitrary initial phase.',
        boundaries='1753A..1770A and 1E7E8 native instructions; mathematical table lookups. Interpolated rounded and non-atomic CSV airflow/RPM/ECT/MAP/throttle; supplied startup/runtime and flag states. No sub-sample dynamics or missed tasks. Alternate alpha uses the same measured engine trajectory and holds B7DC-minus-B874 fixed. Primary target, timing, physical airflow, wall-film transport and engine response would also change in a real run.',
        recorded_load_B874_median_absolute_error=stats.median(abs(r['recorded_load_B874'] - r['logged_transient']) for r in active),
        recorded_load_B874_mean_absolute_error=stats.mean(abs(r['recorded_load_B874'] - r['logged_transient']) for r in active),
        metrics=metrics,
        selected_points=[min(active, key=lambda r: abs(r['seconds'] - t)) for t in
                         (192.959, 215.635, 216.571, 216.883, 217.195, 248.188, 248.604, 249.124, 253)],
        rows=result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = replay()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2))
