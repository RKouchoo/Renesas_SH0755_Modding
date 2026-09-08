#!/usr/bin/env python3
"""Compare two negative-only transient calibration changes in memory.

Fixed recorded engine inputs cannot predict a corrected engine trajectory.
The narrow alternative changes the first slow-negative RPM multiplier from
4 to 2, tapering back to the original calibration at 1600 RPM. No BIN output.
"""

import _analysis_paths  # Locate shared offline interpreters after repository cleanup.
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import statistics
import struct

import analyze_20260908_recovery as recovery
from analyze_transient_components import terms, POINTS
from test_transient_fuel_execution import TransientFuelMachine, TRANSIENT_WRITES

SLOW_NEGATIVE_GAIN = 0x76030
SLOW_NEGATIVE_RPM_DESCRIPTOR = 0x5F6BC
SLOW_NEGATIVE_RPM_DATA = 0x76E7E


def variants(image):
    assert hashlib.sha256(image).hexdigest() == recovery.CANDIDATE_SHA256
    n, kind, axis, data, scale, bias = struct.unpack_from('>HHIIff', image, SLOW_NEGATIVE_RPM_DESCRIPTOR)
    assert (n, kind, data, scale, bias) == (8, 0x800, SLOW_NEGATIVE_RPM_DATA, 1/2048, 0)
    assert struct.unpack_from('>2f', image, axis) == (800, 1600)
    assert struct.unpack_from('>H', image, data)[0] == 8192
    assert abs(struct.unpack_from('>f', image, SLOW_NEGATIVE_GAIN)[0]-.04) < 1e-8
    global_half, low_rpm_half = bytearray(image), bytearray(image)
    struct.pack_into('>f', global_half, SLOW_NEGATIVE_GAIN, .02)
    struct.pack_into('>H', low_rpm_half, data, 4096)
    for changed, address, size in ((global_half, SLOW_NEGATIVE_GAIN, 4),
                                   (low_rpm_half, data, 2)):
        assert all(a == b for i,(a,b) in enumerate(zip(image, changed))
                   if not address <= i < address+size)
    return {'baseline': image, 'global_negative_gain_half': bytes(global_half),
            'low_rpm_negative_multiplier_half': bytes(low_rpm_half)}


def compare_state(reference, changed, label):
    exceptions = {(0xFFFFB874, 4), (0xFFFFB888 if label == 'global_negative_gain_half' else 0xFFFFB8B0, 4)}
    for address, size in TRANSIENT_WRITES-exceptions:
        assert reference.read(address, size) == changed.read(address, size), (label, hex(address))
    if reference.get_float(0xFFFFB87C) >= 0:
        assert reference.read(0xFFFFB874, 4) == changed.read(0xFFFFB874, 4), label
    if label == 'low_rpm_negative_multiplier_half' and reference.get_float(0xFFFFB544) >= 1600:
        assert reference.read(0xFFFFB874, 4) == changed.read(0xFFFFB874, 4), label


def analyze():
    image = recovery.CANDIDATE.read_bytes()
    images = variants(image)
    _, capture = recovery.read_capture()
    rows = [r for r in capture if 130 <= r['time'] < 256]
    times = [r['time'] for r in rows]
    selected_times = {min(rows, key=lambda r: abs(r['time']-point))['time'] for point in POINTS}
    machines = {label: TransientFuelMachine(data, **{k: rows[0][k] for k in ('load','rpm','coolant')})
                for label,data in images.items()}

    def inputs(t):
        i = max(0, min(len(rows)-2, bisect.bisect_right(times,t)-1))
        a,b = rows[i:i+2]
        f = max(0,min(1,(t-a['time'])/(b['time']-a['time'])))
        return {k:a[k]+f*(b[k]-a[k]) for k in ('load','rpm','coolant')}

    selected, errors = [], []
    samples = {label: [] for label in images}
    updates, index, t = 0, 0, times[0]
    while index < len(rows):
        current = inputs(t)
        corrections = {label: cpu.transient(**current) for label,cpu in machines.items()}
        for label,cpu in machines.items():
            if label != 'baseline':
                compare_state(machines['baseline'], cpu, label)
        updates += 1
        while index < len(rows) and t >= times[index]:
            row = rows[index]
            residual = row['factor']-row['transient']
            if row['time'] >= 145:
                errors.append(abs(corrections['baseline']-row['transient']))
                for label, value in corrections.items():
                    samples[label].append(dict(seconds=row['time'], B874=value,
                        net_ms_fixed_residual=max(.6, row['load']*3.2666667*(residual+value))))
            if row['time'] in selected_times:
                selected.append(dict(seconds=row['time'], logged={k:row[k] for k in
                    ('rpm','coolant','load','map','transient','factor','pulse','afr')},
                    alternatives={label:dict(terms(cpu), net_ms_fixed_residual=max(
                        .6,row['load']*3.2666667*(residual+corrections[label])))
                        for label,cpu in machines.items()}))
            index += 1
        t += 20/current['rpm']
    print(f'PASS: {updates} updates per variant; unchanged history/fast/positive controls on every update', flush=True)
    controls = []
    for rpm in (500,800,1200,1600,2400):
        for coolant in (20,45,80):
            for direction,target in (('steady',.75),('opening',.85),('closing',.53)):
                cpus = {label:TransientFuelMachine(data, load=.75, rpm=rpm, coolant=coolant)
                        for label,data in images.items()}
                changes = {label:0 for label in images if label != 'baseline'}
                for _ in range(20):
                    for cpu in cpus.values():
                        cpu.transient(load=target)
                    for label in changes:
                        compare_state(cpus['baseline'], cpus[label], label)
                        changes[label] += (cpus['baseline'].read(0xFFFFB874,4)
                                           != cpus[label].read(0xFFFFB874,4))
                if direction in ('steady','opening'):
                    assert not any(changes.values())
                controls.append(dict(rpm=rpm,coolant=coolant,direction=direction,changed_updates=changes))
    metrics = {label:dict(B874_min=min(r['B874'] for r in values),
        negative_correction_samples=sum(r['B874']<0 for r in values),
        net_floor_samples_fixed_residual=sum(r['net_ms_fixed_residual']==.6 for r in values))
        for label,values in samples.items()}
    return dict(status='OFFLINE COMPARISON ONLY; these values are diagnostic candidates, not engine-validated settings.',
        image_sha256=recovery.CANDIDATE_SHA256,capture_sha256=recovery.LOG_SHA256,
        native_updates_per_variant=updates,baseline_B874_median_absolute_error=statistics.median(errors),
        changes={'global_negative_gain_half':{'address':hex(SLOW_NEGATIVE_GAIN),'old':.04,'new':.02},
                 'low_rpm_negative_multiplier_half':{'address':hex(SLOW_NEGATIVE_RPM_DATA),'old':4,'new':2,
                    'scope':'Slow negative RPM multiplier only; full reduction at/below 800 RPM, linear taper to unchanged 1600 RPM. Applies at all loads, not gated by idle state.'}},
        selected_points=selected,metrics_fixed_trajectory=metrics,controls=controls,
        limitations=['Native transient instructions with mathematical LUT boundaries and supplied normal flags/startup state.',
            'Recorded load/RPM/coolant and B7DC-minus-B874 are held fixed; no AFR, combustion or recovery prediction.',
            'Positive B874 at the deepest dip, opening timing, actual supplemental pulse and zero-pulse cut causes remain unresolved.',
            'No calibration default, logger, checksum or BIN is written.'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.suffix.lower() != '.json':
        parser.error('Only a JSON analysis report may be written')
    report=analyze()
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(args.output)
