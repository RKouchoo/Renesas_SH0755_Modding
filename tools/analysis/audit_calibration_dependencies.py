#!/usr/bin/env python3
"""Discover native table aliases of assigned calibration spans, read-only.

The descriptor scan is a bounded discovery aid. Native caller contracts resolve
integer-return lookup widths; a zero format field alone does not mean float.
It neither proves every computed consumer nor closes a table's process flow.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/reference/evidence'
CAL_START, CAL_END = 0x727A0, 0x7D790

# 2118 calls 26E0 then 28A4 (unsigned word interpolation), returns R0:u16.
# Confirmed actual JSR sites and their PC-relative literals, not XML labels.
INTEGER_CALLS = {
    0x5F8FC: (0x22A14, 0x22A64, 0x22A68),
    0x608D8: (0x98D4, 0x98F0, 0x98F4),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def u32(image, address):
    return struct.unpack_from('>I', image, address)[0]


def floats(image, address, count):
    return struct.unpack_from(f'>{count}f', image, address)


def axis_valid(image, address, count):
    if not (2 <= count <= 128 and CAL_START <= address <= CAL_END-count*4):
        return False
    values = floats(image, address, count)
    return all(math.isfinite(x) for x in values) and all(a < b for a, b in zip(values, values[1:]))


def descriptors(image):
    for address in range(0x2000, CAL_START-28, 4):
        n, kind, axis, data = struct.unpack_from('>HHII', image, address)
        if kind in (0, 0x400, 0x800) and axis_valid(image, axis, n):
            width = 2 if address in INTEGER_CALLS else {0: 4, 0x400: 1, 0x800: 2}[kind]
            if CAL_START <= data <= CAL_END-width*n:
                yield address, 'one_axis', kind, [
                    ('axis', axis, 4, n), ('data', data, width, n)]
        nx, ny, ax, ay, data, kind = struct.unpack_from('>HHIIII', image, address)
        if kind in (0, 0x04000000, 0x08000000) and nx*ny <= 4096:
            if axis_valid(image, ax, nx) and axis_valid(image, ay, ny):
                width = {0: 4, 0x04000000: 1, 0x08000000: 2}[kind]
                if CAL_START <= data <= CAL_END-width*nx*ny:
                    yield address, 'two_axis', kind, [
                        ('x_axis', ax, 4, nx), ('y_axis', ay, 4, ny),
                        ('data', data, width, nx*ny)]


def recorded_xrefs():
    captures = json.loads((EVIDENCE / 'patch_process_flow_20260912.json').read_text())['captures']
    refs = {}
    for capture in captures:
        if capture.get('method') != 'descriptor_xrefs_to':
            continue
        address = int(capture['address'], 16)
        result = capture['result']
        if 'status' in result:
            result = result.get('value', {})
        lines = [x.get('text', '') for x in result.get('content', [])]
        good = [line for line in lines if re.search(r'From [0-9A-Fa-f]{8}', line)]
        if good:
            refs[address] = good
    return refs


def main():
    inventory = json.loads((EVIDENCE / 'patch_touchpoints_20260912.json').read_text())
    stock = (ROOT / '2005 BLE MT.bin').read_bytes()
    images, spans = {}, {}
    for item in inventory['images']:
        image = (ROOT / item['artifact']).read_bytes()
        assert sha(image) == item['image_sha256']
        assert sha(stock) == item['stock_sha256']
        images[item['profile']] = image
        for event in item['events']:
            a, b = event['start'], event['end_exclusive']
            if CAL_START <= a < b <= CAL_END:
                span = spans.setdefault((a, b), {'labels': set(), 'profiles': set(), 'changed': False})
                span['labels'].add(event['label'])
                span['profiles'].add(item['profile'])
                span['changed'] |= bool(event['changed_bytes_in_final_image'])
    refs = recorded_xrefs()
    rows, covered = [], set()
    for address, dimensions, kind, parts in descriptors(stock):
        relevant = []
        for role, pointer, width, count in parts:
            hits = []
            for (a, b), span in spans.items():
                if max(a, pointer) < min(b, pointer+width*count):
                    covered.add((a, b))
                    hits.append({'start': f'{a:08X}', 'end_exclusive': f'{b:08X}',
                                 'labels': sorted(span['labels']),
                                 'profiles': sorted(span['profiles']),
                                 'changed_from_stock': span['changed']})
            if hits:
                relevant.append({'role': role, 'pointer': f'{pointer:08X}',
                                 'element_bytes': width, 'elements': count,
                                 'bytes': width*count, 'assigned_spans': hits})
        if not relevant:
            continue
        header_size = (12 if kind == 0 else 20) if dimensions == 'one_axis' else 28
        for image in images.values():
            assert image[address:address+header_size] == stock[address:address+header_size]
            for role, pointer, width, count in parts:
                if role != 'data':
                    assert axis_valid(image, pointer, count), (hex(address), role)
        caller = None
        if address in INTEGER_CALLS:
            site, descriptor_literal, target_literal = INTEGER_CALLS[address]
            for image in [stock, *images.values()]:
                assert u32(image, descriptor_literal) == address
                assert u32(image, target_literal) == 0x2118
                assert int.from_bytes(image[site:site+2], 'big') & 0xF0FF == 0x400B
            caller = {'jsr': f'{site:08X}', 'target': '00002118',
                      'descriptor_literal': f'{descriptor_literal:08X}',
                      'target_literal': f'{target_literal:08X}',
                      'contract': '2118 -> 28A4 reads u16, independent of zero format field'}
        rows.append({'descriptor': f'{address:08X}', 'dimensions': dimensions,
                     'format': f'{kind:08X}', 'changed_or_assigned_parts': relevant,
                     'native_xrefs_from_mcp': refs.get(address, []),
                     'integer_return_contract': caller,
                     'process_flow_status': 'Consumer identification; transitive process closure remains authored work.'})
    result = {
        'date': '2026-09-12', 'stock_sha256': sha(stock),
        'images': {name: sha(image) for name, image in images.items()},
        'scope': 'Aligned native descriptor discovery with monotonic calibration axes, intersected with every assigned native calibration span.',
        'limits': [
            'This bounded format scan can miss computed or differently encoded descriptors.',
            'MCP xrefs identify immediate consumers, not every downstream dependency.',
            'Zero format fields require the actual native call contract to resolve storage width.',
            'Non-table scalar/array spans below require separate direct and computed consumer tracing.',
            'No BIN, runtime source, calibration, ECU state or logger file is changed.'],
        'descriptors': rows,
        'assigned_spans_without_scanned_table_overlap': [
            {'start': f'{a:08X}', 'end_exclusive': f'{b:08X}', 'labels': sorted(span['labels']),
             'profiles': sorted(span['profiles']), 'changed_from_stock': span['changed']}
            for (a, b), span in sorted(spans.items()) if (a, b) not in covered],
    }
    path = EVIDENCE / 'calibration_dependencies_20260912.json'
    path.write_text(json.dumps(result, indent=2)+'\n')
    print(f'{len(rows)} intersecting descriptors; {sum(bool(r["native_xrefs_from_mcp"]) for r in rows)} have captured native xrefs; '
          f'{len(result["assigned_spans_without_scanned_table_overlap"])} spans remain in the scalar/array review.')
    for row in rows:
        if not row['native_xrefs_from_mcp']:
            print('Needs native xref review:', row['descriptor'])


if __name__ == '__main__':
    main()
