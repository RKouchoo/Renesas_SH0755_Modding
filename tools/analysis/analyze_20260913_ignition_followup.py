#!/usr/bin/env python3
"""Bounded, no-ECU ignition checks following the cut-trace capture.

Native lookup/correction/logger helpers execute actual ROM instructions.
Device checks supply crank/timer snapshots and use native-derived dwell;
they do not model electrical outputs, asynchronous timing or engine response.
"""
import _analysis_paths
import hashlib
import json
import struct

from analyze_20260913_cut_trace import read_log, ROM, ROM_SHA, LOG_SHA
from test_ssm_command_process_flow import SSMCommandMachine, RAM
from test_ignition_device_process_flow import IgnitionDeviceMachine

ROOT = _analysis_paths.ROOT
OUT = ROOT / 'logs/20260913_ignition_followup_review.json'


def main():
    _, rows = read_log()
    image = ROM.read_bytes()
    assert hashlib.sha256(image).hexdigest() == ROM_SHA
    stock = (ROOT / '2005 BLE MT.bin').read_bytes()
    for a, b in ((0x3D7E4, 0x3D8E2), (0x3D980, 0x3D9B0),
                 (0x77F74, 0x77F84), (0x31684, 0x31694),
                 (0x3174E, 0x31750), (0x21B0, 0x21CC),
                 (0x9D3A, 0xA034), (0x60998, 0x609A8), (0x7BBE0, 0x7BCC6)):
        assert image[a:b] == stock[a:b], (hex(a), hex(b))
    assert struct.unpack_from('>I', image, 0x11E20)[0] == 0x3D824
    assert struct.unpack_from('>I', image, 0x11E30)[0] == 0x279CC
    assert struct.unpack_from('>I', image, 0x4B6FC+4*0x11)[0] == 0x31684
    assert image[0x3174E:0x31750] == b'\xc0\xec'
    cpu = SSMCommandMachine(image)

    # Actual SSM callback and conversion: vary other five cylinder angles,
    # then vary element0. No write is allowed outside the interpreter stack.
    visibility = []
    for values in ((15, 20, 25, 30, 35, 40), (15, -20, -10, 0, 5, 60),
                   (16, -20, -10, 0, 5, 60)):
        for n, value in enumerate(values):
            cpu.put_float(RAM+0xC0EC+4*n, value)
        cpu.execute(0x31684, set())
        assert (cpu.r[0]-128)/2 == values[0]
        visibility.append({'supplied_angles': values, 'P10_degrees': (cpu.r[0]-128)/2})

    # Exercise the producer directly with enable forced on, so a disabled
    # low-RPM latch cannot accidentally explain a passing high-RPM check.
    correction = []
    writes = {(RAM+0xCCC8+4*n, 4) for n in range(6)}
    for rpm in (1999, 2000, 2500, 2800, 3016, 3152, 3500, 3800):
        cpu.put_float(RAM+0xB544, rpm)
        cpu.write(RAM+0xCCE0, 0x40, 1)
        for n, value in enumerate((-30, -20, -10, 0, 10, 20)):
            cpu.put_float(RAM+0x82EC+8*n, value)
            cpu.put_float(RAM+0xCCC8+4*n, 99)
        cpu.execute(0x3D824, writes)
        result = [cpu.get_float(RAM+0xCCC8+4*n) for n in range(6)]
        assert result == ([-5, -5, -5, 0, 5, 5] if rpm < 2000 else [0]*6)
        correction.append({'rpm_fixture': rpm, 'output_offsets': result})

    # Native 21B0/27D0/26B0 lookup executes here rather than the earlier
    # dwell test's modeled interpolation. Hold each recorded point; do not
    # pretend the ~104ms log supplies per-tooth timing or all final angles.
    demand = [r for r in rows if r['speed'] > 5 and r['pedal'] >= 30
              and r['rpm'] >= 2500 and r['throttle'] >= 80]
    assert len(demand) == 125
    points, checks = [], 0
    for r in demand:
        cpu.put_float(RAM+0xAC00, r['rpm'])
        cpu.put_float(RAM+0xABB4, r['battery'])
        cpu.execute(0x9FEC, {(RAM+0xAD5C, 2)})
        dwell = cpu.read(RAM+0xAD5C, 2)
        assert dwell > 0
        widths = []
        for snapshot in (1000, 65500):
            device = IgnitionDeviceMachine(image, r['rpm'], r['timing'], snapshot)
            device.put_float(RAM+0xABB4, r['battery'])
            device.write(RAM+0xAD5C, dwell, 2)
            device.write(RAM+0xC290, 0x0FC0, 2)
            for n in range(6):
                # Explicit late-start angle10deg ahead of snapshot. This
                # invokes native997A ->9D3A ->9F9C/9E58, not a phase-cycle replay.
                device.enqueue(n, 10)
                start = device.read(RAM+0xF614+2*n, 2)
                end = device.read(RAM+0xF604+2*n, 2)
                width = (end-start) & 65535
                assert start == (snapshot+3) & 65535
                assert width >= dwell//2
                assert device.read(RAM+0xF650+2*n, 2) > 0
                widths.append(width)
                checks += 1
        points.append({'csv_line': r['csv_line'], 'seconds': r['time'], 'rpm': r['rpm'],
                       'logged_battery_v': r['battery'], 'native_dwell_counts': dwell,
                       'late_fixture_min_compare_width_counts': min(widths)})
    assert checks == 1500
    report = {
        'source_log_sha256': LOG_SHA, 'rom_sha256': ROM_SHA,
        'scope': 'No-cost offline ignition follow-up; no ECU I/O or ROM/calibration changes.',
        'native_lookup': '9FEC ->21B0 ->27D0/26B0 executes without lookup stand-ins.',
        'P10_visibility': visibility, 'per_cylinder_correction': correction,
        'sampled_operating_points': points, 'device_cases': checks,
        'dwell_count_range': [min(p['native_dwell_counts'] for p in points),
                              max(p['native_dwell_counts'] for p in points)],
        'conclusions': [
            'P10 encodes only final timing element0 atC0EC; it is not an average or six-cylinder trace.',
            'Installed3D824 clears the ordinary six correction offsets atRPM>=2000 '
            'even with its enable bit set; below threshold the forced records clamp to-5..+5deg.',
            'Native requested dwell stays nonzero at all125 recorded open-plate/high-demand points.',
            'All1500 held-point late-start/channel/wrap fixtures program nonzero down-counters '
            'and at least half-dwell compare spans; none establishes a new software cut.',
        ],
        'limits': [
            'Logged battery/RPM are quantized samples, not the exact simultaneous native inputs.',
            'No actual coil current, coil voltage, spark energy or hardware waveform is simulated.',
            'A programmed nonzero compare span does not prove an electrical firing event.',
            'No full-task dispatch, real interrupt delays or live phase/timer snapshots are recovered.',
            'Correction clearing requires the installed producer to execute; actual offsets remain unlogged.',
            'This is bounded instruction analysis, not new registered regression-test groups; '
            'the historical355-group cumulative report is unchanged.',
        ],
    }
    OUT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'output': str(OUT), 'points': len(points), 'device_cases': checks,
                      'dwell_count_range': report['dwell_count_range'], 'cut_reproduced': False}, indent=2))


if __name__ == '__main__':
    main()
