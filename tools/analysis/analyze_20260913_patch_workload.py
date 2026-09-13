#!/usr/bin/env python3
"""Compare selected stock and patched native workloads; not elapsed timing.

Uses explicit histories, inputs and caller masks. All CPU callees execute
saved instructions; there are no timer arrivals, bus waits or engine model.
The SD call-control image exists only in memory and is never written as a ROM.
"""
import _analysis_paths
from collections import Counter
import hashlib
from itertools import product
import json

from analyze_20260913_cylinder_fuel_followup import PipelineMachine, RAM
from analyze_20260913_cut_trace import ROM, ROM_SHA, LOG_SHA
from audit_fpu_usage import census
from test_airflow_task_process_flow import AirflowTaskMachine, FLOW_WRITES

ROOT = _analysis_paths.ROOT
OUT = ROOT/'logs/20260913_patch_workload_review.json'
STOCK_SHA = 'ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee'
INIT_WRITES = {(RAM+a, 4) for a in (*range(0xAE60, 0xAE80, 4),
    0xAE8C, 0xAE90, 0xAEB4, 0xAEB8)} | {(RAM+a, 1) for a in (
    0xAE80, 0xAE81, 0xAE82, 0xAE83, *range(0xAEC8, 0xAED3), 0xF45A, 0xF628)} | {
    (RAM+a, 2) for a in (0xAEBC, 0xAEBE, 0xF462, 0xF632, 0xF464, 0xF630, 0xF66C)}


class WorkloadMachine(PipelineMachine):
    def __init__(self, image):
        self.steps = []
        super().__init__(image)

    def step(self, in_delay=False):
        self.steps.append((self.pc, self.read(self.pc, 2), (self.sr >> 4) & 15))
        return super().step(in_delay)

    def measure(self, entry, writes):
        self.steps.clear()
        self.trace.clear()
        self.native_targets.clear()
        self.execute(entry, writes)
        assert len(self.steps) == self.instructions == len(self.trace)
        assert [(a, b) for a, b, _ in self.steps] == self.trace
        result = census(self.trace)
        result.pop('dependency_sites')
        result['instructions_by_imask'] = dict(sorted(Counter(m for _, _, m in self.steps).items()))
        result['local_stack_bytes'] = self.STACK-self.min_sp
        result['division_sites'] = [hex(pc) for pc, op in self.trace if op & 0xF00F == 0xF003]
        result['trace_sha256'] = hashlib.sha256(json.dumps(self.steps).encode()).hexdigest()
        return result


def airflow(images, seed_image, rpm, mode, pressure):
    setup = AirflowTaskMachine(seed_image, rpm, pressure, 37, 61)
    results = {}
    for name, image in images.items():
        cpu = WorkloadMachine(image)
        # Identical explicit signal/history RAM; no foreign registers or stack.
        for a, value in setup.memory.items():
            if RAM+0x8000 <= a < RAM+0xE000:
                cpu.write(a, value, 1)
        cpu.sr = 0
        cpu.write(RAM+0xCD86, mode, 1)
        for a in (0xABE4, 0xB448, 0xB458, 0xB45C):
            cpu.put_float(RAM+a, 105)
        result = cpu.measure(0x172A4, FLOW_WRITES)
        assert result['instructions_by_imask'] == {0: result['instructions']}
        result['airflow_output_g_s'] = cpu.get_float(RAM+0xB420)
        results[name] = result
    # Same native path/census when only the two SD call pointers are restored.
    for key in ('instructions', 'operations', 'local_stack_bytes', 'division_sites', 'trace_sha256'):
        assert results['stock'][key] == results['sd_call_control'][key], key
    return {'rpm_fixture': rpm, 'mode_fixture': mode, 'map_mmhg_fixture': pressure,
            'iat_c_fixture': 37, 'ect_c_fixture': 61, 'old_airflow_g_s_fixture': 105,
            'paths': results,
            'added_instructions': results['v2']['instructions']-results['stock']['instructions']}


def wideband(image, raw, old_counter):
    cpu = WorkloadMachine(image)
    for address, size in INIT_WRITES:
        cpu.write(address, 0, size)
    # Explicit nonzero caller mask keeps final native unlock out of dispatch.
    # The priority-9 publication section itself is counted in full on both ROMs.
    cpu.sr = 0x20
    cpu.measure(0xB49A, INIT_WRITES)
    cpu.write(RAM+0xAB06, raw, 2)
    cpu.write(RAM+0xAED0, old_counter, 1)
    result = cpu.measure(0xB62A, INIT_WRITES)
    assert set(result['instructions_by_imask']) == {2, 9}
    assert cpu.sr & 0xF0 == 0x20
    result['masked9'] = census([(pc, op) for pc, op, mask in cpu.steps if mask == 9])
    result['masked9'].pop('dependency_sites')
    return result


def main():
    stock = (ROOT/'2005 BLE MT.bin').read_bytes()
    v2 = ROM.read_bytes()
    assert hashlib.sha256(stock).hexdigest() == STOCK_SHA
    assert hashlib.sha256(v2).hexdigest() == ROM_SHA
    control = bytearray(v2)
    for address in (0x173FC, 0x1743C):
        control[address:address+4] = stock[address:address+4]
    images = {'stock': stock, 'v2': v2, 'sd_call_control': bytes(control)}
    cases = [airflow(images, v2, rpm, mode, pressure) for rpm, mode, pressure in product(
        (2500, 2800, 2999, 3000, 3016, 3152, 3200, 3300, 3500, 3600, 3800, 4144),
        (1, 3), (300, 760, 810))]
    wb_cases = []
    for raw, old_counter in product((0, 30000, 65535), (0, 255)):
        paths = {name: wideband(image, raw, old_counter)
                 for name, image in (('stock', stock), ('v2', v2))}
        assert paths['v2']['masked9']['instructions'] < paths['stock']['masked9']['instructions']
        assert paths['v2']['masked9']['operations'].get('FDIV', 0) == 0
        wb_cases.append({'adc_fixture': raw, 'old_AED0_fixture': old_counter,
                         'caller_imask_fixture': 2, 'paths': paths})
    report = {
        'stock_sha256': STOCK_SHA, 'rom_sha256': ROM_SHA, 'context_log_sha256': LOG_SHA,
        'scope': 'Paired native workload and mask census, not measured execution time.',
        'airflow_cases': cases, 'wideband_cases': wb_cases,
        'added_airflow_instruction_range': [min(c['added_instructions'] for c in cases),
                                            max(c['added_instructions'] for c in cases)],
        'limitations': [
            'Explicit histories and input grid, not logged internal state or an engine replay.',
            'Stock and SD outputs need not match; this compares workload at the same supplied inputs.',
            'The in-memory two-pointer control isolates the SD entry substitution from other v2 changes.',
            'Instruction counts and FP dependencies are not CPU cycles or microseconds.',
            'No bus waits, pipeline timing, interrupt arrivals, full task occupancy or deadlines.',
            'Wideband caller mask2 is supplied to isolate native mask9 work; unlock-to-zero dispatch is outside this fixture.',
            'Native B49A initialization supplies old front-A/F history; all retained operating histories are not covered.',
            'Local stack depth excludes caller frames and interrupts; no total headroom claim.',
            'No causal defect or cure established; no ROM/calibration/logger writes or ECU I/O.',
        ],
        'new_registered_test_groups': 0,
    }
    OUT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'output': str(OUT), 'airflow_cases': len(cases),
        'wideband_cases': len(wb_cases), 'added_airflow_instruction_range':
        report['added_airflow_instruction_range']}, indent=2))


if __name__ == '__main__':
    main()
