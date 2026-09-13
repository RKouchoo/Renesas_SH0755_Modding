#!/usr/bin/env python3
"""Connect the native crank-state publisher to injector record refresh flags.

Selected entries execute in their installed task order, with actual lookup
instructions. Other task payload, interrupts, timers and the engine are not
simulated. Forced prior crank state is a positive control, not log evidence.
"""
import _analysis_paths
import hashlib
import json
import struct

from analyze_20260913_cut_trace import ROM, ROM_SHA, LOG_SHA, read_log
from test_ssm_command_process_flow import SSMCommandMachine, RAM
from test_ignition_permission_execution import MODE_WRITES
from test_injector_device_process_flow import InjectorDeviceMachine, DEVICE_WRITES
from test_injector_scheduler_execution import RECORDS, HARDWARE, LAST_PHASE, SCHEDULER_WRITES

ROOT = _analysis_paths.ROOT
OUT = ROOT / 'logs/20260913_crank_refresh_followup_review.json'
CRANK_WRITES = {(RAM+a, 4) for a in (0xB784, 0xB788)} | {
    (RAM+a, 1) for a in (0xB796, 0xB797, 0xB748)}
PHASE_WRITES = {(RAM+a, 1) for a in (0xB528, 0xB529, 0xB52C)} | {
    (RAM+0xB530, 4)}
REFRESH_FLAGS = tuple(RAM+0xBFB8+40*n+6 for n in range(6))
REFRESH_WRITES = {(a, 1) for a in REFRESH_FLAGS}


def prepare(cpu, rpm, ect):
    cpu.put_float(RAM+0xB544, rpm)
    cpu.put_float(RAM+0xB3AC, ect)
    cpu.write(RAM+0xAC04, round(20_000_000/rpm), 4)
    cpu.write(RAM+0xB289, 0x80, 1)
    cpu.write(RAM+0xB51E, 0x10, 1)
    cpu.write(RAM+0x8224, 0x00FF, 2)
    cpu.write(RAM+0xB748, 0xC5, 1)  # Force both start flags plus unrelated bits.
    cpu.write(RAM+0xB797, 1, 1)
    cpu.write(RAM+0xC0AC, 0, 4)  # Worst-case event count for the release gate.
    cpu.write(RAM+0xC0E1, 2, 1)  # Logged running mode; nonzero B529 holds it.
    cpu.write(RAM+0xC0E3, 0x40, 1)


def phase(cpu, value):
    cpu.original_r[4] = value
    # Relative order verified from native11958 and its literal pool.
    cpu.execute(0x19F9C, PHASE_WRITES)
    cpu.execute(0x1C920, CRANK_WRITES)
    cpu.execute(0x2716C, MODE_WRITES)
    for a in REFRESH_FLAGS:
        cpu.write(a, 0xA5, 1)
    cpu.execute(0x26E64, REFRESH_WRITES)
    flags = [cpu.read(a, 1) for a in REFRESH_FLAGS]
    crank = bool(cpu.read(RAM+0xB748, 1) & 0x80)
    assert flags == ([1]*6 if crank else [0xA5]*6)
    assert cpu.read(RAM+0xB748, 1) & 0x3F == 5
    return {'phase': value, 'crank_flag': crank,
            'ignition_mode': cpu.read(RAM+0xC0E1, 1),
            'all_six_refresh_flags_written': crank}


def pending_consumer(image):
    results = []
    for mark in (0, 1):
        cpu = InjectorDeviceMachine(image, rpm=3000)
        cpu.write(LAST_PHASE, 0, 1)
        for n, record in enumerate(RECORDS):
            cpu.enqueue(n, 600, 4000+n*400)
            cpu.write(record+2, 1, 1)
            cpu.write(record+17, 1, 1)
            cpu.write(record+6, mark, 1)
            cpu.put_float(RAM+0xB768+4*n, 2000+n*100)
        cpu.device_calls.clear()
        cpu.cancellations.clear()
        cpu.original_r[4] = 1
        cpu.write(RAM+0xAC17, 1, 1)
        cpu.invoke(0x263EE, SCHEDULER_WRITES | DEVICE_WRITES)
        actual = [cpu.read(hw, 4) for hw in HARDWARE]
        assert actual == [((8000+n*400) if mark else (4000+n*400)) for n in range(6)]
        assert not cpu.cancellations
        assert [call[0] for call in cpu.device_calls] == ([0x90F8]*6 if mark else [])
        assert [cpu.read(r+6, 1) for r in RECORDS] == [0]*6
        results.append({'imposed_refresh_flag': mark,
                        'resulting_effective_counts': actual,
                        'native_update_calls': len(cpu.device_calls), 'cancel_calls': 0})
    return results


def main():
    image = ROM.read_bytes()
    assert hashlib.sha256(image).hexdigest() == ROM_SHA
    stock = (ROOT/'2005 BLE MT.bin').read_bytes()
    # Native instructions, task pointers, lookup descriptors and gate data.
    ranges = ((0x11958, 0x119DC), (0x11A7C, 0x11AD0),
              (0x19F9C, 0x1A02C), (0x1A082, 0x1A0A8),
              (0x1C920, 0x1CA38), (0x1D228, 0x1D23C),
              (0x1D296, 0x1D298), (0x26E64, 0x26E80),
              (0x26EF4, 0x26EF8), (0x2705E, 0x27080),
              (0x2716C, 0x27294), (0x5F134, 0x5F140),
              (0x5F498, 0x5F4C0), (0x76AE0, 0x76AF8),
              (0x76648, 0x76658))
    for a, b in ranges:
        assert image[a:b] == stock[a:b], hex(a)
    for a, b in ((0x263EE, 0x2687C), (0x26C50, 0x26D44),
                 (0x26E9A, 0x26F78), (0x90F8, 0x915C), (0x92DA, 0x9350)):
        assert image[a:b] == stock[a:b], hex(a)
    for pointer, target in ((0x11A7C, 0x19F9C), (0x11A88, 0x1C920),
                            (0x11AA8, 0x2716C), (0x11AB0, 0x26E64)):
        assert struct.unpack_from('>I', image, pointer)[0] == target
    _, rows = read_log()
    demand = [r for r in rows if r['speed'] > 5 and r['pedal'] >= 30
              and r['rpm'] >= 2500 and r['throttle'] >= 80]
    assert len(demand) == 125
    cpu = SSMCommandMachine(image)
    points, fixtures = [], 0
    for row in demand:
        counts = []
        for start in range(4):
            prepare(cpu, row['rpm'], row['ect'])
            history = [phase(cpu, (start+n) % 24) for n in range(8)]
            until_release = (-start) % 4
            assert [s['crank_flag'] for s in history] == [
                n < until_release for n in range(8)]
            assert all(s['ignition_mode'] == 2 for s in history)
            assert cpu.read(RAM+0xB796, 1) == 0
            assert cpu.get_float(RAM+0xB784) == 500
            assert cpu.get_float(RAM+0xB788) == 300
            counts.append(sum(s['all_six_refresh_flags_written'] for s in history))
            fixtures += 1
        points.append({'csv_line': row['csv_line'], 'seconds': row['time'],
                       'rpm': row['rpm'], 'ect_c': row['ect'],
                       'event_delay': 0,
                       'refresh_calls_from_forced_crank_by_start_mod4': counts})

    prepare(cpu, 3152, 20)
    controls = []
    for events in (0, 9, 10):
        cpu.write(RAM+0xC0AC, events, 4)
        result = phase(cpu, 0)
        assert result['ignition_mode'] == 2
        assert result['crank_flag'] == (events < 10)
        assert cpu.read(RAM+0xB796, 1) == 10
        controls.append({'imposed_ect_c': 20, 'events': events, **result})

    consumer = pending_consumer(image)
    report = {
        'source_log_sha256': LOG_SHA, 'rom_sha256': ROM_SHA,
        'user_confirmation': 'Stock EZ30R coils, wiring and plugs; measured gap not supplied.',
        'scope': 'Bounded native producer-to-refresh follow-up; no ECU I/O or ROM edits.',
        'native_order': ['19F9C', '1C920 ->1C972', '2716C', '26E64 ->1D228 ->2705E'],
        'stock_identical_ranges': [[hex(a), hex(b)] for a, b in ranges],
        'sampled_points': points, 'starting_phase_fixtures': fixtures,
        'supplied_phase_calls': fixtures*8, 'cold_positive_controls': controls,
        'pending_duration_consumer_controls': consumer,
        'conclusions': [
            'Record+06 requests duration refresh, not scheduler reset or cylinder inhibition: '
            '263EE ->26E9A ->26C50 ->90F8 updates all six pending durations in the positive control '
            'without cancellation, then clears the requests.',
            'Ignition mode2 can coexist with B748/80 and all-six injector refresh requests.',
            'At all125 recorded open-plate demand RPM/ECT points, native delay is zero '
            'even with C0AC=0; the next phase divisible by4 clears both start flags.',
            'Forced stale crank state persists for at most three supplied phase calls '
            'before that clearing; it does not reassert over the remaining supplied phases.',
            'This path does not reproduce the sustained cut with those inputs.',
        ],
        'limits': [
            'B748, C0AC, refresh flags and actual per-phase execution are not captured.',
            'Recorded RPM/ECT are quantized samples, not simultaneous per-phase RAM values.',
            'Selected native entries execute in installed relative order; this is not '
            'the complete11958 payload, real dispatch, elapsed-time or electrical simulation.',
            'Setting a refresh request is not itself proof of a missed delivered pulse.',
            'The pending-consumer controls use the existing bounded integer-division model; '
            'enqueue/update routines execute native instructions, but timer completion and '
            'electrical fuel delivery are not simulated.',
            'The already documented native crank producer is reused; the additional '
            'connection here is to26E64 and its six computed record stores.',
            'No new registered regression groups; cumulative355-group total unchanged.',
        ],
    }
    OUT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'output': str(OUT), 'points': len(points), 'fixtures': fixtures,
                      'phase_calls': fixtures*8, 'cut_reproduced': False}, indent=2))


if __name__ == '__main__':
    main()
