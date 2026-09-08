#!/usr/bin/env python3
"""Read-only analysis of the September 8 14:13 candidate idle/blip capture.

The original CSV has an unquoted comma in one units label. Normalize that
specific header in memory; never rewrite recorded samples. Table values are
conditional lookups, not measurements of AVCS blend or final spark timing.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics as stats
import struct

import master_calibration as calibration
from analyze_20260908_idle import sd, hook
from idle_recovery_candidate import CANDIDATE_SHA256, OUTPUT as CANDIDATE

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / 'logs/romraiderlog_idle_diagnostic2_20260908_141335.csv'
FLASH_LOG = Path('/Users/regan/.config/FastECU/0.1.0-beta.5/syslogs/log_fastecu_2026-09-08_14h10m06s.txt')
LOG_SHA256 = '7b5c3fda47a64d97ee0761333bff9b1b53516d4239565681049159b2bef6d855'
PREFIXES = {
    'time': 'Time', 'battery': 'Battery Voltage', 'state': 'CL/OL',
    'coolant': 'Coolant', 'load': 'Engine Load', 'rpm': 'Engine Speed',
    'afr': 'External Wideband AFR', 'adc': 'External Wideband Input ADC',
    'latency': 'Fuel Injector #1 Latency',
    'total_pulse': 'Fuel Injector #1 Pulse Width (ms)',
    'pulse': 'Fuel Injector #1 Pulse Width (4-byte)', 'pump': 'Fuel Pump',
    'timing': 'Ignition Total Timing', 'iat': 'Intake Air Temperature',
    'map': 'Manifold Absolute', 'airflow': 'Mass Airflow', 'throttle': 'Throttle',
    'lift': 'Committed AVLS', 'factor': 'Final Fueling Base',
    'transient': 'Transient Load Fuel Correction',
}
WINDOWS = ((100, 130), (140, 148), (154, 159), (200, 210),
           (221, 234), (253, 256))
EVENT_WINDOWS = ((159.8, 167), (177.5, 186), (187.4, 191.3), (191.3, 197),
                 (215, 220), (234.8, 239.5), (239.5, 245), (245.8, 253))


def read_capture():
    data = LOG.read_bytes()
    if hashlib.sha256(data).hexdigest() != LOG_SHA256:
        raise ValueError('Capture changed: inspect provenance before reusing fixed windows')
    header, remaining = data.decode().split('\n', 1)
    old = '(AVLS mode (1 low, 3 high))'
    assert header.count(old) == 1
    header = header.replace(old, '(AVLS mode (1 low; 3 high))')
    reader = csv.reader(io.StringIO(header + '\n' + remaining))
    headings = next(reader)
    raw = [[float(value) for value in row] for row in reader]
    assert len(headings) == 20 and len(raw) == 2510
    assert all(len(row) == len(headings) for row in raw)
    assert all(math.isfinite(value) for row in raw for value in row)
    indices = {}
    for key, prefix in PREFIXES.items():
        matches = [i for i, name in enumerate(headings) if name.startswith(prefix)]
        assert len(matches) == 1, prefix
        indices[key] = matches[0]
    rows = [{key: row[i] for key, i in indices.items()} for row in raw]
    for row in rows:
        row['time'] /= 1000
        row['volts'] = row['adc'] * 5 / 65536
        row['flow_derived_load'] = row['airflow'] * 60 / row['rpm'] if row['rpm'] else None
    assert all(b['time'] > a['time'] for a, b in zip(rows, rows[1:]))
    return headings, rows


def flash_identity(image, flash_log=None, verification=-1):
    path = FLASH_LOG if flash_log is None else Path(flash_log)
    if not path.exists():
        return {'available': False, 'path': str(path)}
    sessions = path.read_text(errors='replace').split('after reflash ---')[1:]
    if not sessions:
        raise ValueError('No recorded post-flash verification in ' + str(path))
    text = sessions[verification]
    entries = re.findall(
        r'FB(\d+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+).*?'
        r'ROM CRC: 0x([0-9a-fA-F]+) IMG CRC: 0x([0-9a-fA-F]+)', text, re.S)[:16]
    # A subsequent pre-flash comparison may share this section. Only the first
    # complete 16-block set belongs to the selected post-flash verification.
    # FastECU custom reflected CRC, not zlib's polynomial. Source:
    # modules/ecu/flash_ecu_subaru_denso_sh705x_kline.cpp crc32/init_crc32_tab.
    table = []
    for value in range(256):
        for _ in range(8):
            value = (value >> 1) ^ (0x5AA5A55A if value & 1 else 0)
        table.append(value)
    blocks = []
    for number, start, length, ecu_crc, image_crc in entries:
        start, length, ecu_crc, image_crc = (int(v, 16) for v in (start, length, ecu_crc, image_crc))
        value = 0xFFFFFFFF
        for byte in image[start:start + length]:
            value = table[(value ^ byte) & 255] ^ (value >> 8)
        value ^= 0xFFFFFFFF
        assert value == ecu_crc == image_crc
        blocks.append(dict(block=int(number), start=start, length=length, crc=f'0x{value:08X}'))
    assert len(blocks) == 16
    assert blocks[0]['start'] == 0
    assert all(a['start'] + a['length'] == b['start'] for a, b in zip(blocks, blocks[1:]))
    assert blocks[-1]['start'] + blocks[-1]['length'] == len(image)
    return dict(available=True, path=str(path), matches_candidate=True, blocks=blocks)


def timing_endpoint(image, map_index, rpm, load):
    _, address, rpm_axis_address, ny = calibration.TIMING_MAPS[map_index]
    x = struct.unpack_from('>15f', image, calibration.TIMING_LOAD_AXIS_ADDR)
    y = struct.unpack_from('>' + str(ny) + 'f', image, rpm_axis_address)
    values = [sd.interpolate(x, [v * .3515625 - 20 for v in
              image[address + i * 15:address + (i + 1) * 15]], load) for i in range(ny)]
    return sd.interpolate(y, values, rpm)


def timing_floor(image, coolant):
    # 284B8 uses 5FC18 through 209C, then native max helper 24A0 at 28784.
    n, kind, axis, data, scale, bias = struct.unpack_from('>HHIIff', image, 0x5FC18)
    assert n == 3 and kind == 0x400
    return sd.interpolate(struct.unpack_from('>3f', image, axis),
                          [v * scale + bias for v in image[data:data + n]], coolant)


def summarize_window(rows, start, end):
    samples = [r for r in rows if start <= r['time'] < end and r['rpm'] > 500]
    assert samples
    result = {'seconds': [start, end], 'samples': len(samples)}
    for key in ('rpm', 'afr', 'timing', 'transient', 'factor', 'pulse', 'load',
                'map', 'airflow', 'throttle', 'coolant', 'iat', 'battery', 'pump'):
        values = [r[key] for r in samples if key != 'afr' or r['afr'] > 0]
        result[key] = dict(min=min(values), median=stats.median(values), max=max(values)) if values else None
    result['invalid_afr_samples'] = sum(r['afr'] == 0 for r in samples)
    return result


def summary(headings, rows, image):
    if hashlib.sha256(image).hexdigest() != CANDIDATE_SHA256:
        raise ValueError('This analysis requires the tested 6af0d1 candidate')
    running = [r for r in rows if 145 <= r['time'] < 256 and r['rpm'] > 500]
    intervals = [(b['time'] - a['time']) * 1000 for a, b in zip(rows, rows[1:])]
    points = []
    for second in (187.864, 187.969, 188.072, 188.176, 188.904,
                   215.531, 215.635, 216.571, 246.729, 246.834, 249.124):
        row = min(rows, key=lambda r: abs(r['time'] - second))
        a = timing_endpoint(image, 0, row['rpm'], row['load'])
        d = timing_endpoint(image, 3, row['rpm'], row['load'])
        floor = timing_floor(image, row['coolant'])
        points.append(dict(row, modeled_A=a, modeled_D=d,
                           modeled_D_with_base_floor=max(d, floor)))
    # E123/B7DC is already the composed factor: never multiply it by 1+B874 again.
    errors = [abs(max(.6, r['load'] * 3.2666667 * r['factor']) - r['pulse']) for r in running]
    invalid = [r for r in running if r['afr'] == 0]
    airflow_replays = []
    previous = hook.IMAGE
    try:
        hook.IMAGE = image
        for second in (145, 154.5, 187.864, 188.904, 189.423, 200,
                       215.635, 216.571, 217.195, 248.604, 249.124, 253):
            row = min(rows, key=lambda r: abs(r['time'] - second))
            flow = hook.Machine(rpm=row['rpm'], map_mmhg=row['map'] / .1333224,
                                iat=row['iat'], mode=int(row['lift'])).run()
            airflow_replays.append(dict(seconds=row['time'], logged_g_s=row['airflow'],
                                        replayed_g_s=flow, replayed_raw_load=flow * 60 / row['rpm'],
                                        logged_conditioned_load=row['load']))
    finally:
        hook.IMAGE = previous
    return dict(
        log_sha256=LOG_SHA256, candidate_sha256=CANDIDATE_SHA256,
        samples=len(rows), channels=len(headings) - 1,
        header_repair='One unquoted comma in the AVLS units label normalized in memory; source CSV unchanged.',
        duration_seconds=rows[-1]['time'] - rows[0]['time'],
        interval_ms_min_median_max=[min(intervals), stats.median(intervals), max(intervals)],
        flash_identity=flash_identity(image),
        fuel_states=sorted({r['state'] for r in rows}), lift_states=sorted({r['lift'] for r in rows}),
        windows=[summarize_window(rows, a, b) for a, b in WINDOWS],
        event_windows=[summarize_window(rows, a, b) for a, b in EVENT_WINDOWS],
        recovery_min_rpm=min(running, key=lambda r: r['rpm']),
        recovery_min_transient=min(running, key=lambda r: r['transient']),
        minimum_pulse_samples=sum(r['pulse'] == .6 for r in running),
        invalid_afr_samples=len(invalid),
        invalid_afr_with_adc_above_4_5V=sum(r['volts'] > 4.5 for r in invalid),
        invalid_afr_with_adc_below_0_5V=sum(r['volts'] < .5 for r in invalid),
        quantized_factor_pulse_check_median_error_ms=stats.median(errors),
        conditional_timing_points=points,
        sd_wrapper_opcode_replays=airflow_replays,
        user_observation='Engine stayed running but nearly stalled during blips; user confirms intentional key-off at the end.',
        assumptions='Base D comparison assumes normal timing-RPM input follows logged RPM, AVCS tracking blend k=0 and off-idle selection; these were not logged. C130 is not final spark. CSV channels and exhaust AFR are not synchronized physical events. Intentional end-of-run shutdown is excluded from recovery windows. Different temperatures/blip amplitudes prevent a controlled before/after attribution.')


def plot(rows, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(5, 2, figsize=(14, 12), sharex='col', layout='constrained')
    panels = (
        (('rpm', 'RPM', '#2857a4'),),
        (('afr', 'Wideband AFR', '#a94432'),),
        (('timing', 'Timing (degrees)', '#7752a3'),),
        (('transient', 'B874 additive', '#a44d1a'), ('factor', 'B7DC factor', '#21826b')),
        (('pulse', 'Net pulse (ms)', '#216c91'),),
    )
    for col, (start, end) in enumerate(((0, 261), (214.8, 219.8))):
        samples = [r for r in rows if start <= r['time'] <= end]
        for i, panel in enumerate(panels):
            ax = axes[i, col]
            for key, label, color in panel:
                values = [math.nan if key == 'afr' and r[key] == 0 else r[key] for r in samples]
                ax.plot([r['time'] for r in samples], values, label=label, color=color, linewidth=1.15)
            ax.set_ylabel(panel[0][1] if len(panel) == 1 else 'Fuel factors')
            ax.grid(alpha=.2)
            ax.set_xlim(start, end)
            if i == 1:
                ax.axhline(14.64, color='#888', linewidth=.8, linestyle='--')
                ax.set_ylim(11, 20)
            if i == 3:
                ax.axhline(0, color='#888', linewidth=.6)
                ax.legend(fontsize=8, loc='upper right')
            if col == 1:
                ax.axvspan(215.427, 215.842, color='#cb982f', alpha=.13)
        axes[0, col].set_title('Complete capture' if col == 0 else 'Opening timing drop; closing fuel reduction')
        axes[-1, col].set_xlabel('Seconds from log start')
    fig.suptitle('September 8 14:13 candidate — settled fueling improves; rev recovery remains unresolved', fontsize=14)
    fig.supxlabel('Shaded interval: low timing during opening. AFR gaps are invalid-input sentinels; exhaust/sampling delays remain.', fontsize=9)
    fig.savefig(output, dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plot', type=Path)
    args = parser.parse_args()
    headings, rows = read_capture()
    print(json.dumps(summary(headings, rows, CANDIDATE.read_bytes()), indent=2))
    if args.plot:
        plot(rows, args.plot)
