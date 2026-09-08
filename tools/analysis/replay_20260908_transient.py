#!/usr/bin/env python3
"""Replay stock B874 load-change compensation against the 12:36 capture.

B438/RPM/ECT are linearly interpolated between 104-ms CSV samples. The stock
crank-slot map gives one fuel-task update per 120 degrees (interval 20/RPM).
Phase, sub-sample input variation, other fuel factors, and injector scheduling
are unrecorded. This is a scoped attribution model, not an engine simulation.
"""

import _analysis_paths  # Shared repository, artifact and interpreter paths.
import bisect
import hashlib
import json
import statistics

from analyze_20260908_idle import read_capture, LOG, read_image
from test_transient_fuel_execution import TransientFuelMachine
from idle_recovery_candidate import BASELINE_SHA256


def replay():
    image = read_image()
    if hashlib.sha256(image).hexdigest() != BASELINE_SHA256:
        raise ValueError('This replay requires the 10:30 image used in the capture')
    _, rows = read_capture()
    rows = [r for r in rows if 135 <= r['time'] < 180]
    times = [r['time'] for r in rows]
    cpu = TransientFuelMachine(image, rows[0]['load'], rows[0]['rpm'], rows[0]['coolant'])

    def interpolate(t):
        i = max(0, min(len(rows)-2, bisect.bisect_right(times, t)-1))
        a, b = rows[i:i+2]
        q = max(0, min(1, (t-a['time'])/(b['time']-a['time'])))
        return {k: a[k]+q*(b[k]-a[k]) for k in ('load', 'rpm', 'coolant')}

    output = []
    t, index = times[0], 0
    while index < len(rows):
        inputs = interpolate(t)
        correction = cpu.transient(**inputs)
        if t >= times[index]:
            row = rows[index]
            cpu.seed_composer()  # All unlogged corrections explicitly neutral.
            cpu.put_float(0xFFFFB874, correction)
            cpu.invoke(0x1E0C8, {(0xFFFFB82C, 4)})
            cpu.compose()
            output.append(dict(
                seconds=row['time'], rpm=row['rpm'], logged_load=row['load'],
                logged_net_ms=row['pulse'], modeled_composed_ms=cpu.get_float(0xFFFFB7F4)/1000,
                modeled_B874=correction, modeled_slow_delta=cpu.get_float(0xFFFFB87C),
                modeled_fast_delta=cpu.get_float(0xFFFFB880)))
            index += 1
        t += 20 / inputs['rpm']

    blips = [r for r in output if 151 < r['seconds'] < 165.5]
    differences = [abs(r['modeled_composed_ms'] - r['logged_net_ms']) for r in blips]
    return dict(
        baseline_sha256=BASELINE_SHA256, log_sha256=hashlib.sha256(LOG.read_bytes()).hexdigest(),
        cadence='Six evenly spaced task-6 activations per 720-degree cycle; 20/RPM-second interval model.',
        assumptions='Interpolated CSV load/RPM/ECT; arbitrary initial crank phase; neutral unlogged fuel factors; no output-scheduler delay or physical engine model.',
        median_absolute_error_ms=statistics.median(differences),
        mean_absolute_error_ms=statistics.mean(differences),
        selected_points=[min(output, key=lambda r: abs(r['seconds']-second))
                         for second in (140, 153.873, 154.185, 155.538, 157.621, 160.95, 161.471, 162.717, 166, 175)],
        rows=output)


if __name__ == '__main__':
    print(json.dumps(replay(), indent=2))
