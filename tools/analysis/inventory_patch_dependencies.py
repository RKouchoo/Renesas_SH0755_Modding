#!/usr/bin/env python3
"""Inventory every build write without treating byte ownership as flow proof.

Builders run in separate processes to isolate their same-named Python modules.
The rolling ROMs are read and compared with in-memory builds, never rewritten.
Every assignment to the builder's ROM bytearray is recorded, including writes
which leave stock bytes unchanged and seed values subsequently overwritten.
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'docs/reference/evidence/patch_touchpoints_20260912.json'
REGISTER = ROOT / 'docs/reference/PATCH_TOUCHPOINT_REGISTER.md'


def flow_family(address):
    exact = {
        0x639C: 'SD', 0x66D8: 'SD', 0x107F8: 'SD', 0x11804: 'SD',
        0x1062C: 'SD', 0x1185C: 'SD', 0x11D20: 'SD', 0x17398: 'SD',
        0x1743C: 'SD', 0x173FC: 'SD', 0x27088: 'SD', 0x172CE: 'SD',
        0x1753C: 'SD', 0x73968: 'SD', 0x5BD57: 'SD', 0x5BD58: 'SD',
        0x72810: 'MAP', 0x7B286: 'MAP', 0x11D3C: 'CUT', 0x11D78: 'CUT',
        0x1055C: 'CUT', 0x11E30: 'ROT', 0xB690: 'WB', 0xE0D0: 'AVCS',
        0x64FD0: 'WB', 0x6500C: 'WB', 0x6A6C: 'WB',
        0x11488: 'AVCS', 0x1148C: 'AVCS', 0x11490: 'AVCS', 0x11494: 'AVCS',
        0x114A0: 'AVCS', 0x73E08: 'WB', 0x76384: 'WB', 0x760F0: 'WB',
        0x202CC: 'WB', 0x202D0: 'WB', 0x1BAF0: 'PURGE', 0x23054: 'PURGE',
        0x5BD85: 'PURGE', 0x5BD86: 'PURGE', 0x72D54: 'INJECTOR',
        0x76014: 'INJECTOR', 0x7B318: 'INJECTOR', 0x7644C: 'CUT',
        0x7D80D: 'CUT', 0x7D8BC: 'RETIRED', 0x7D91C: 'WB',
        0x7FB88: 'IMAGE', 0x7FC4C: 'IMAGE', 0x7616C: 'FUEL',
        0x76050: 'TRANSIENT', 0x763E0: 'TRANSIENT', 0x76AC8: 'TRANSIENT',
        0x76D08: 'TRANSIENT', 0x76D48: 'TRANSIENT',
        0x7739C: 'TRANSIENT', 0x773BC: 'TRANSIENT', 0x7963C: 'IDLE_DBW',
        0x7834C: 'TIMING',
    }
    if address in exact:
        return exact[address]
    for start, end, family in (
        (0x5BD9F, 0x5BDC5, 'WB'), (0x72960, 0x72A50, 'IAT'),
        (0x76B76, 0x76BF6, 'INJECTOR'), (0x772DC, 0x772E0, 'FUEL'),
        (0x7771C, 0x77A9A, 'FUEL'), (0x77FD8, 0x7806C, 'KNOCK'),
        (0x780BC, 0x794D8, 'TIMING'), (0x79C9C, 0x79E24, 'IDLE_DBW'),
        (0x7A738, 0x7AD24, 'IDLE_DBW'), (0x7C54C, 0x7C95C, 'AVCS'),
        (0x7D4AC, 0x7D4C0, 'AVLS'), (0x7D67C, 0x7D6D0, 'AVLS'),
        (0x7D790, 0x7D8BC, 'RETIRED'), (0x7D8C0, 0x7D91C, 'CUT'),
        (0x7DB40, 0x7DD00, 'ROT'), (0x7DD00, 0x7E400, 'SD'),
        (0x7E400, 0x7E540, 'WB'), (0x7E560, 0x7E640, 'RETIRED'),
        (0x7E640, 0x7EAC8, 'SD'), (0x7EAC8, 0x7EE00, 'CUT'),
    ):
        if start <= address < end:
            return family
    raise AssertionError(f'Assign a process-flow family for {address:05X}')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def collect(profile):
    directory = ROOT / ('master_patch_v2' if profile == 'v2' else 'master_patch')
    spec = importlib.util.spec_from_file_location('dependency_builder', directory / 'build_master_patch.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    events = []

    class RecordedROM(bytearray):
        def __setitem__(self, key, value):
            if isinstance(key, slice):
                start, end, step = key.indices(len(self))
                assert step == 1 and end - start == len(value), 'ROM resizing is not supported'
                replacement = bytes(value)
            else:
                start, end = key, key + 1
                replacement = bytes([value])
            before = bytes(self[start:end])
            context = []
            label = None
            frame = inspect.currentframe().f_back
            try:
                while frame:
                    filename = Path(frame.f_code.co_filename).resolve()
                    if filename.is_relative_to(ROOT) and filename != Path(__file__).resolve():
                        context.append({'file': str(filename.relative_to(ROOT)),
                                        'line': frame.f_lineno, 'function': frame.f_code.co_name})
                        if label is None:
                            for field in ('label', 'name'):
                                item = frame.f_locals.get(field)
                                if isinstance(item, str):
                                    label = item
                                    break
                    frame = frame.f_back
            finally:
                del frame
            events.append({'start': start, 'end_exclusive': end, 'label': label,
                           'source': context, 'before_sha256': digest(before),
                           'replacement_sha256': digest(replacement),
                           'bytes_changed_at_stage': sum(a != b for a, b in zip(before, replacement))})
            super().__setitem__(key, value)

    builder.bytearray = RecordedROM
    stock, image, blobs, calibration = builder.build_image()
    saved = builder.DEFAULT_OUT.read_bytes()
    assert image == saved, 'Rolling artifact does not match its current builder'
    declared = [{'label': f'{owner}/{label}', 'start': start, 'size': len(data), 'class': 'component'}
                for owner, items in blobs.items() for label, start, data in items]
    declared += [{'label': label, 'start': start, 'size': len(data), 'class': 'calibration'}
                 for label, (start, data) in calibration.items()]
    declared += [{'label': label, 'start': start, 'size': len(data), 'class': 'retained_consumer'}
                 for label, start, _, data in builder.wideband.STOCK_SENSOR_PATCHES]
    covered = set()
    for event in events:
        start, end = event['start'], event['end_exclusive']
        covered.update(range(start, end))
        matches = [x for x in declared if x['start'] == start and x['size'] == end-start]
        # A loop variable called label/name can remain in scope after the loop.
        # Exact declared regions take precedence over this debugging context.
        event['context_label'] = event['label']
        if matches:
            event['label'] = ' / '.join(dict.fromkeys(x['label'] for x in matches))
        elif (start, end) == (0x72810, 0x72818):
            event['label'] = 'MAP affine sensor transfer'
        elif (start, end) == (0x11D3C, 0x11D40):
            event['label'] = 'composed rev-limit/overboost/lean task pointer'
        elif event['label'] is None:
            event['label'] = 'unlabelled assignment'
        event['declarations'] = [x['label'] for x in matches]
        event['final_sha256'] = digest(image[start:end])
        event['changed_bytes_in_final_image'] = sum(a != b for a, b in zip(stock[start:end], image[start:end]))
        event['full_flow_status'] = 'open; consult authored process-flow register'
        event['flow_family'] = flow_family(start)
        if end-start <= 16:
            event['stock_hex'] = stock[start:end].hex()
            event['final_hex'] = image[start:end].hex()
    changed = {i for i, (a, b) in enumerate(zip(stock, image)) if a != b}
    assert not changed - covered, 'An actual changed byte has no recorded build assignment'
    # These are candidate references only: data may resemble a pointer, and
    # computed references need a separate native-code review.
    pointers = [(a, struct.unpack_from('>I', stock, a)[0]) for a in range(0x2000, 0x70000, 4)]
    for record in declared:
        record['native_pointer_candidates'] = [f'{a:08X}' for a, value in pointers
            if record['start'] <= value < record['start'] + record['size']]
    return {'profile': profile, 'artifact': str(builder.DEFAULT_OUT.relative_to(ROOT)),
            'stock_sha256': digest(stock), 'image_sha256': digest(image),
            'build_matches_saved_artifact': True, 'changed_bytes': len(changed),
            'recorded_write_events': len(events), 'written_byte_union': len(covered),
            'unattributed_changed_bytes': [], 'events': events, 'declared_regions': declared}


def render_register(images):
    rows = {}
    for image in images:
        for event in image['events']:
            key = (event['start'], event['end_exclusive'])
            row = rows.setdefault(key, {'labels': [], 'profiles': set(), 'family': event['flow_family'],
                                         'changed': False})
            row['profiles'].add(image['profile'])
            row['changed'] |= bool(event['changed_bytes_in_final_image'])
            if event['label'] not in row['labels']:
                row['labels'].append(event['label'])
    lines = ['# Patch touchpoint register', '',
             '[Process-flow review](PATCH_PROCESS_FLOW.md) · [Machine-readable assignments](evidence/patch_touchpoints_20260912.json)', '',
             'Generated by `tools/analysis/inventory_patch_dependencies.py`. Every assignment in both',
             'current builders is captured, including unchanged retained contracts and overwritten seeds.',
             'Identical spans are grouped here; the JSON preserves stage order, source lines and hashes.',
             'A family assignment is a review index, **not a completed dependency trace**.', '',
             '| Span (inclusive) | Builds | Family | Final difference from stock | Assignment |',
             '|---|---|---|---|---|']
    for (start, end), row in sorted(rows.items()):
        span = f'{start:05X}' if end == start + 1 else f'{start:05X}–{end-1:05X}'
        label = '; '.join(row['labels']).replace('|', '/')
        lines.append(f"| `{span}` | {', '.join(sorted(row['profiles']))} | {row['family']} | "
                     f"{'yes' if row['changed'] else 'retained identical'} | {label} |")
    lines += ['', 'Regeneration changes documentation only. It never writes either rolling BIN.', '']
    REGISTER.write_text('\n'.join(lines))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--collect':
        print(json.dumps(collect(sys.argv[2])))
        return
    images = [json.loads(subprocess.check_output(
        [sys.executable, '-B', str(Path(__file__).resolve()), '--collect', profile], cwd=ROOT))
        for profile in ('v1', 'v2')]
    result = {'schema_version': 1, 'date': '2026-09-12', 'images': images,
              'scope': 'All ROM assignments in both current deterministic builders, including unchanged and overwritten writes.',
              'limits': ['Inventory completeness applies to these builders and pinned artifacts.',
                         'Recording a write or pointer candidate does not verify any native dependency.',
                         'Transitive RAM writes, computed aliases, state transitions and deadlines require authored review.',
                         'No ECU connection, ROM write, or vehicle behavior simulation.']}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n')
    render_register(images)
    for item in images:
        print(f"{item['profile']}: {item['recorded_write_events']} writes, {item['changed_bytes']} changed bytes, "
              f"0 unattributed; matches {item['image_sha256']}")


if __name__ == '__main__':
    main()
