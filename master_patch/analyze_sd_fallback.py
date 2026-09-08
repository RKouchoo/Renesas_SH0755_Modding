#!/usr/bin/env python3
"""Test logged processed MAP as a proxy and isolate the SD fallback/filter path.

Runs saved ROM instructions, including native SD table helpers. Each CSV row
is a rounded, asynchronous input fixture, not a recovered task invocation.
Crucially E51 records B2A0, whereas SD reads ABC4. These captures do not
establish the SD MAP input or whether its gate was crossed between samples.
The filter fixtures execute retained code with normal flags and mathematical
transient-table lookups. No engine model, ECU connection or BIN output.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct

import analyze_20260908_idle as idle
import analyze_20260908_recovery as recovery
import analyze_20260908_dashpot as dashpot
from audit_fpu_usage import NativeSDMachine, sd, sd_test
from test_load_conditioning_execution import LoadConditioningMachine
from test_primary_fueling_execution import bits, number

ROOT = Path(__file__).resolve().parent.parent
KPA_PER_MMHG = .1333224
BASE_SHA = '48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0'
IDLE_LOG_SHA = '9a1469b3666798d897fdab9f38301a4a8f5961c744be36dc76f175faef782a2b'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run_sd(image, rpm, pressure, iat, mode):
    cpu = NativeSDMachine(image, rpm, pressure, iat, mode)
    value = sd_test.Machine.run(cpu)
    assert (cpu.mach, cpu.macl) == (0x12345678, 0x76543210)
    return value, bool(cpu.reads[sd.FAILSAFE_AIRFLOW_ADDR])


def boundaries(image):
    minimum = struct.unpack_from('>f', image, sd.MAP_MIN_ADDR)[0]
    cases = [
        ('one_float_below_minimum', 1500, number(bits(minimum)-1), 25, True),
        ('at_minimum', 1500, minimum, 25, False),
        ('one_float_above_minimum', 1500, number(bits(minimum)+1), 25, False),
        ('minimum_processed_map_as_proxy', 1494, 16.29/KPA_PER_MMHG, 26, False),
        ('invalid_iat', 1500, 315, float('nan'), True),
        ('stopped_with_invalid_map', 0, float('nan'), 25, False),
    ]
    result = []
    for label, rpm, pressure, iat, expected in cases:
        airflow, fallback = run_sd(image, rpm, pressure, iat, 1)
        assert fallback == expected, label
        assert not fallback or airflow == 500
        result.append(dict(case=label, rpm=rpm,
            map_mmhg=pressure if math.isfinite(pressure) else 'NaN',
            iat=iat if math.isfinite(iat) else 'NaN',
            airflow=airflow, fixed_fallback_read=fallback))
    # Re-enter the same wrapper with intact synthetic history from each prior
    # output. Rapid, valid pressure steps do not activate a delta-rate gate.
    cpu = NativeSDMachine(image, 2000, 712, 25, 1)
    steps = []
    for pressure in (712, minimum, 712, minimum, 315):
        cpu.r, cpu.fr = cpu.original_r.copy(), cpu.original_fr.copy()
        cpu.pc, cpu.pr = sd.WRAPPER_ADDR, cpu.STOP
        cpu.instructions, cpu.min_sp = 0, cpu.STACK
        cpu.writes.clear()
        cpu.reads.clear()
        cpu.trace.clear()
        cpu.put_float(sd.MAP_ADDR, pressure)
        airflow = sd_test.Machine.run(cpu)
        assert not cpu.reads[sd.FAILSAFE_AIRFLOW_ADDR]
        assert math.isfinite(airflow) and 0 < airflow < 500
        steps.append(dict(map_mmhg=pressure, airflow=airflow))
    return dict(edge_cases=result, consecutive_valid_pressure_steps=steps)


def filter_fixtures(image):
    result = []
    for fault_calls in (0, 1, 5):
        rpm, initial = 1500, .30
        cpu = LoadConditioningMachine(image, load=initial, rpm=rpm, coolant=45)
        rows = []
        for call in range(1, 101):
            airflow = 500 if call <= fault_calls else initial*rpm/60
            before = cpu.get_float(0xFFFFB438)
            conditioned = cpu.condition(airflow, rpm, coolant=45)
            raw = cpu.get_float(0xFFFFB428)
            assert abs(conditioned-(before+.06*(raw-before))) < 1e-6
            assert min(before, raw)-1e-6 <= conditioned <= max(before, raw)+1e-6
            correction = cpu.transient()
            assert math.isfinite(correction)
            rows.append(dict(call=call, airflow=airflow, raw_load=raw,
                             conditioned_load=conditioned, B874=correction))
        result.append(dict(fallback_calls=fault_calls,
            fixture='1500 RPM, 45 C, initial steady load 0.30; one transient update per load update; normal flags',
            first_ten_updates=rows[:10], last_update=rows[-1],
            max_conditioned_load=max(r['conditioned_load'] for r in rows),
            B874_range=[min(r['B874'] for r in rows), max(r['B874'] for r in rows)]))
    return result


def analyze():
    baseline = idle.IMAGE.read_bytes()
    candidate = recovery.CANDIDATE.read_bytes()
    first, second = dashpot.historical_images()
    assert sha(baseline) == BASE_SHA
    assert sha(candidate) == recovery.CANDIDATE_SHA256
    assert sha(idle.LOG.read_bytes()) == IDLE_LOG_SHA
    # Check the exact SD wrapper and retained/bypassed paths in every relevant
    # artifact, including the later second dashpot image without a capture.
    images = (baseline, candidate, first, second)
    wrapper = sd.build_wrapper()
    for image in images:
        assert image[sd.WRAPPER_ADDR:sd.WRAPPER_ADDR+len(wrapper)] == wrapper
        for address in (*sd.MAF_CONVERSION_CALL_ADDRS, sd.MAF_LIMIT_UPDATE_CALL_ADDR):
            assert image[address:address+2] == sd.MAF_CONVERSION_CALL_PATCHED
        assert image[sd.LOAD_FILTER_ALPHA_ADDR:sd.LOAD_FILTER_ALPHA_ADDR+4] == sd.LOAD_FILTER_ALPHA_STOCK
        assert struct.unpack_from('>f', image, sd.ENGINE_LOAD_LIMIT_ADDR)[0] == 4
        assert image[sd.FAILSAFE_AIRFLOW_ADDR:sd.MAP_MIN_ADDR+24] == baseline[sd.FAILSAFE_AIRFLOW_ADDR:sd.MAP_MIN_ADDR+24]
    captures = [('12:36', idle.LOG, idle.read_capture()[1], baseline),
                ('14:13', recovery.LOG, recovery.read_capture()[1], candidate)]
    captures += [(label, ROOT/'logs'/name, dashpot.read_capture(name, digest, count), first)
                 for label, name, digest, count in dashpot.CAPTURES]
    results = []
    for label, log, rows, image in captures:
        fallback_rows, capped, calls = [], 0, 0
        outputs = []
        for row in rows:
            # B2A0 is only a proxy for the unlogged ABC4 SD input. Low/high
            # surfaces are both checked when committed AVLS was not
            # logged. These extra fixtures are not claims of actual high lift.
            modes = (int(row['lift']),) if 'lift' in row else (1, 3)
            for mode in modes:
                value, fallback = run_sd(image, row['rpm'], row['map']/KPA_PER_MMHG, row['iat'], mode)
                calls += 1
                outputs.append(value)
                if fallback:
                    fallback_rows.append(dict(seconds=row['time'], mode=mode, airflow=value))
                capped += value == 500 and not fallback
        minimum = min(rows, key=lambda r: r['map'])
        result = dict(label=label, file=log.name, log_sha256=sha(log.read_bytes()),
            image_sha256=sha(image), samples=len(rows), native_invocations=calls,
            map_input_kind='E51/B2A0 processed MAP supplied as proxy for unlogged ABC4',
            fixed_fallback_invocations=fallback_rows, normal_cap_invocations=capped,
            minimum_map_sample={k: minimum[k] for k in ('time','rpm','map','airflow','load','pulse')},
            processed_map_proxy_margin_kpa=minimum['map']-100*KPA_PER_MMHG,
            maximum_logged_airflow=max(r['airflow'] for r in rows),
            logged_airflow_500_samples=sum(r['airflow'] >= 499.99 for r in rows),
            replay_airflow_range=[min(outputs),max(outputs)],
            median_interval_ms=statistics.median(1000*(b['time']-a['time']) for a,b in zip(rows,rows[1:])),
            largest_gap_seconds=max(b['time']-a['time'] for a,b in zip(rows,rows[1:])))
        results.append(result)
        print(f"{label}: {len(rows)} rows / {calls} proxy-input native invocations; {len(fallback_rows)} fixed fallbacks, {capped} normal caps", flush=True)
    constants = {name: struct.unpack_from('>f', baseline, getattr(sd,name))[0]
        for name in ('FAILSAFE_AIRFLOW_ADDR','MAX_AIRFLOW_ADDR','MAP_MIN_ADDR','MAP_MAX_ADDR',
                     'RPM_MIN_ADDR','RPM_MAX_ADDR','IAT_MIN_ADDR','IAT_MAX_ADDR')}
    return dict(scope='Offline B2A0-as-ABC4 proxy fixtures, not exact SD-input replay; no ROM/calibration/logger changes.',
        map_source_correction='Logged E51 is FFFFB2A0. SD reads FFFFABC4, which was not captured. A positive processed-MAP margin does not establish an SD-input margin; zero proxy fallbacks cannot exclude actual fallback events.',
        checked_image_sha256=[sha(image) for image in images], constants=constants,
        captures=results, boundaries=boundaries(candidate), filter_fixtures=filter_fixtures(candidate),
        limitations='Logged MAP is processed B2A0, not the ABC4 SD input. Both normal history processing and diagnostic load-derived MAP substitution can separate them. Channels are rounded and asynchronous, usually 104 ms apart, with longer gaps in some captures. Proxy fixtures cannot exclude an actual input-gate crossing, transient sensor fault, corrupt RAM/ROM, or fallback between samples. This is not a CPU timing or engine/fuel-delivery model. Unlogged AVLS uses both surfaces as fixtures. Filter/transient fixtures use normal flags and mathematical transient LUT boundaries; other fuel factors and cuts are not composed. A 500 g/s numerical result alone cannot distinguish the fixed fallback from the normal cap; the fixture identifies the fixed ROM constant read.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.suffix.lower() != '.json':
        parser.error('Only a .json report may be written')
    report = analyze()
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(args.output)
