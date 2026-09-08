#!/usr/bin/env python3
"""Read-only opcode census, not a cycle-accurate or whole-ECU timing model.

SD executes the actual float lookup helpers as well as the emitted wrapper.
Guard fixtures reuse the existing native execution harness and its explicit
stock-task boundaries. No ROM, logger, or calibration file is written.
"""

import _analysis_paths  # Locate shared offline interpreters after repository cleanup.
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch as mock_patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for directory in (ROOT / 'patches/core', ROOT / 'patches/speed_density', ROOT / 'patches/fueling_safety', HERE):
    sys.path.insert(0, str(directory))

import patch_speed_density as sd
import patch_rotational_idle as rot
import patch_boost as boost
import wideband_component as wb
import fueling_safety_component as safety
import sh2_asm
import test_hook_execution as sd_test
from test_primary_fueling_execution import PrimaryFuelMachine
from test_wideband_fuel_guard_execution import GuardMachine, bits, number, signed


def fp_operation(op):
    if op & 0xF000 == 0xF000:
        low = op & 15
        if low in (0, 1, 2, 3, 4, 5, 14):
            return {0: 'FADD', 1: 'FSUB', 2: 'FMUL', 3: 'FDIV',
                    4: 'FCMP/EQ', 5: 'FCMP/GT', 14: 'FMAC'}[low]
        if low in (6, 7, 8, 9, 10, 11, 12):
            return 'FMOV'
        return {0x0D: 'FSTS', 0x1D: 'FLDS', 0x2D: 'FLOAT',
                0x3D: 'FTRC', 0x4D: 'FNEG', 0x5D: 'FABS',
                0x8D: 'FLDI0', 0x9D: 'FLDI1'}[op & 255]
    if op & 0xF0FF in (0x405A, 0x4056, 0x005A, 0x4052):
        return 'FPUL transfer'
    if op & 0xF0FF in (0x406A, 0x4066, 0x006A, 0x4062):
        return 'FPSCR transfer'
    return None


def fp_access(op):
    """FR/FPUL read/write sets for the selected SH-2E instruction subset."""
    n, m, low = (op >> 8) & 15, (op >> 4) & 15, op & 15
    if op & 0xF000 == 0xF000:
        if low in (0, 1, 2, 3):
            return {n, m}, {n}
        if low in (4, 5):
            return {n, m}, set()
        if low == 14:
            return {0, n, m}, {n}
        if low in (6, 8, 9):
            return set(), {n}
        if low in (7, 10, 11):
            return {m}, set()
        if low == 12:
            return {m}, {n}
        subtype = op & 255
        if subtype in (0x0D, 0x2D):
            return {'FPUL'}, {n}
        if subtype in (0x1D, 0x3D):
            return {n}, {'FPUL'}
        if subtype in (0x4D, 0x5D):
            return {n}, {n}
        if subtype in (0x8D, 0x9D):
            return set(), {n}
        raise AssertionError(hex(op))
    if op & 0xF0FF in (0x405A, 0x4056):
        return set(), {'FPUL'}
    if op & 0xF0FF in (0x005A, 0x4052):
        return {'FPUL'}, set()
    return set(), set()


def census(trace, include=lambda pc: True):
    selected = [(pc, op) for pc, op in trace if include(pc)]
    counts = Counter(fp_operation(op) for _, op in selected)
    counts.pop(None, None)
    dependencies = []
    for (pc, op), (next_pc, next_op) in zip(trace, trace[1:]):
        if not include(pc) or not include(next_pc) or fp_operation(op) == 'FDIV':
            continue
        shared = fp_access(op)[1] & fp_access(next_op)[0]
        if shared:
            dependencies.append({'producer': f'0x{pc:05X}',
                                 'consumer': f'0x{next_pc:05X}',
                                 'registers': sorted(map(str, shared))})
    return {'instructions': len(selected), 'fpu_instructions': sum(counts.values()),
            'operations': dict(sorted(counts.items())),
            'immediate_non_div_fp_dependencies': len(dependencies),
            'dependency_sites': dependencies}


class NativeSDMachine(PrimaryFuelMachine):
    """Add only the integer opcodes required by the stock float LUT path."""
    LOOKUPS = {0x209C, 0x2150, 0x26E0, 0x27D0, 0x27F0, 0x25F8}

    def __init__(self, image, rpm, map_mmhg, iat, mode):
        super().__init__(image)
        self.trace = []
        self.mach, self.macl = 0x12345678, 0x76543210
        self.fr[15] = bits(rpm)
        self.original_fr = self.fr.copy()
        self.put_float(sd.MAP_ADDR, map_mmhg)
        self.put_float(sd.IAT_ADDR, iat)
        self.write(sd.AVLS_COMMITTED_MODE_ADDR, mode, 1)
        self.pc = sd.WRAPPER_ADDR

    def call_lookup(self, target):
        assert target in self.LOOKUPS, hex(target)
        self.entered.append(target)
        return_pc, self.pc = self.pr, target
        while self.pc != return_pc:
            self.step()

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        self.trace.append((pc, op))
        n, m = (op >> 8) & 15, (op >> 4) & 15
        self.pc += 2
        if op & 0xF000 == 0xB000:
            assert not in_delay
            self.pr = pc + 4
            self.step(in_delay=True)
            self.call_lookup(pc + 4 + signed(op & 0xFFF, 12) * 2)
            self.pc = self.pr
        elif op & 0xFF00 == 0x8500:
            self.r[0] = signed(self.load(self.r[m] + (op & 15) * 2, 2), 16) & 0xFFFFFFFF
        elif op & 0xF00F == 0x000E:
            self.r[n] = self.load((self.r[0] + self.r[m]) & 0xFFFFFFFF, 4)
        elif op & 0xF0FF == 0x4008:
            self.r[n] = (self.r[n] << 2) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x4009:
            self.r[n] >>= 2
        elif op & 0xF00F == 0x200F:
            self.macl = (signed(self.r[n] & 65535, 16) * signed(self.r[m] & 65535, 16)) & 0xFFFFFFFF
        elif op in (0x4F02, 0x4F12):
            self.push(self.mach if op == 0x4F02 else self.macl)
        elif op == 0x4F06:
            self.mach = self.pop()
        elif op == 0x4F16:
            self.macl = self.pop()
        elif op & 0xF0FF == 0x001A:
            self.r[n] = self.macl
        else:
            self.pc = pc
            return super().step(in_delay)
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT


class TracedGuard(GuardMachine):
    def invoke(self, entry, allowed_writes):
        self.trace = []
        result = super().invoke(entry, allowed_writes)
        assert len(self.trace) == self.instructions
        return result

    def step(self, in_delay=False):
        self.trace.append((self.pc, self.read(self.pc, 2)))
        return super().step(in_delay)


class TracedRotationalIdle(TracedGuard):
    def call_lookup(self, target):
        assert target == rot.STOCK_FINAL_TIMING_TASK
        # Count only the added disabled wrapper; stock timing is a boundary.
        self.entered.append(target)
        self.poison_scratch()


def inspect(image):
    # Capture assembler code boundaries, excluding literal pools and padding.
    # Verify every captured blob against the supplied ROM's executable bytes.
    static = {}
    builders = (('speed_density', sd.build_wrapper), ('wideband', wb.build_wideband_update),
                ('wideband_inhibit', wb.build_inhibit_helper),
                ('overboost', boost.build_fuelcut_wrapper),
                ('pressure_open_loop', safety.build_pressure_ol_wrapper),
                ('lean_cut', safety.build_lean_cut_wrapper),
                ('lean_initialize', safety.build_lean_state_initialize),
                ('rotational_idle', rot.build_wrapper))
    assemble = sh2_asm.Asm.assemble
    records = []

    def capture(assembler):
        blob = assemble(assembler)
        assert image[assembler.base:assembler.base + len(blob)] == blob
        length = sum(item[0] != 'label' for item in assembler.items) * 2
        records.append([(pc, int.from_bytes(image[pc:pc+2], 'big'))
                        for pc in range(assembler.base, assembler.base + length, 2)])
        return blob

    with mock_patch.object(sh2_asm.Asm, 'assemble', capture):
        for label, builder in builders:
            records.clear()
            builder()
            assert len(records) == 1
            static[label] = census(records[0])

    sd_cases = []
    cases = [('idle', 1300, 315, 20, 1), ('opening', 1738, 712, 20, 1),
             ('low_first_intervals', 250, 200, -40, 1),
             ('high_first_intervals', 3100, 200, -40, 3),
             ('high_running', 4500, 1000, 30, 3),
             ('map_iat_lower_clamps', 300, 100, -50, 1),
             ('upper_clamps', 7500, 1600, 150, 3),
             ('stopped', 0, 315, 20, 1), ('invalid_map', 1300, float('nan'), 20, 1)]
    with mock_patch.object(sd_test, 'IMAGE', image):
        for label, rpm, pressure, iat, mode in cases:
            cpu = NativeSDMachine(image, rpm, pressure, iat, mode)
            actual = sd_test.Machine.run(cpu)
            model = sd_test.Machine(rpm=rpm, map_mmhg=pressure, iat=iat, mode=mode).run()
            assert abs(actual-model) <= max(2e-5, abs(model)*2e-6), (label, actual, model)
            assert (cpu.mach, cpu.macl) == (0x12345678, 0x76543210)
            assert len(cpu.trace) == cpu.instructions
            result = {'fixture': label, 'airflow_g_s': actual,
                      'wrapper': census(cpu.trace, lambda pc: pc >= 0x7D700),
                      'including_native_lookups': census(cpu.trace)}
            result['divisions'] = []
            for index, (pc, op) in enumerate(cpu.trace):
                if fp_operation(op) == 'FDIV':
                    next_fp = next((i for i in range(index+1, len(cpu.trace))
                                    if fp_operation(cpu.trace[i][1])), None)
                    result['divisions'].append({'pc': f'0x{pc:05X}',
                        'non_fpu_instructions_before_next_fpu': next_fp-index-1 if next_fp else None})
            sd_cases.append(result)

    other = []
    cpu = TracedGuard(image)
    for label, raw in (('wideband_valid', 30000), ('wideband_invalid', 0)):
        cpu.update_wideband(raw)
        other.append({'fixture': label, 'added_code': census(cpu.trace, lambda pc: pc >= 0x7D700)})
    cpu.put_float(wb.FRONT_READY_METRIC_BANK1, 50)
    cpu.invoke(wb.BANK1_INHIBIT_ENTRY, set())
    other.append({'fixture': 'wideband_inhibit_ready',
                  'added_code': census(cpu.trace, lambda pc: pc >= 0x7D700)})
    for label, pressure in (('pressure_open_loop_vacuum', 315), ('pressure_open_loop_atmosphere', 760)):
        cpu.put_float(safety.MAP_PRESSURE, pressure)
        cpu.invoke(safety.PRESSURE_OL_WRAPPER_ADDR, {(safety.CL_OL_STATE_FLAGS, 1)})
        other.append({'fixture': label, 'added_code': census(cpu.trace, lambda pc: pc >= 0x7D700)})
    for label, pressure, state in (('cut_vacuum', 315, 0), ('cut_arm', 820, 0),
                                   ('cut_monitor', 820, 2), ('cut_latched', 820, 3)):
        cpu.put_float(safety.MAP_PRESSURE, pressure)
        cpu.put_float(wb.FRONT_READY_METRIC_BANK1, 50)
        cpu.put_float(wb.WIDEBAND_LOG_LAMBDA_BANK1, 1)
        cpu.write(safety.LEAN_STATE_RAM, state, 1)
        cpu.write(safety.LEAN_COUNTER_RAM, 0, 2)
        cpu.cut_step()
        other.append({'fixture': label, 'added_code': census(cpu.trace, lambda pc: pc >= 0x7D700)})
    assert image[rot.ROT_IDLE_ENABLE_ADDR] == 0, 'This audit assumes rotational idle is disabled.'
    rotational = TracedRotationalIdle(image)
    rotational.invoke(rot.ROT_IDLE_WRAPPER_ADDR, set())
    other.append({'fixture': 'rotational_idle_disabled',
                  'added_code': census(rotational.trace, lambda pc: pc >= 0x7D700)})
    return {'sha256': hashlib.sha256(image).hexdigest(), 'static_emitted_code': static,
            'sd_fixtures': sd_cases, 'other_hook_fixtures': other,
            'limits': ['Instruction counts and adjacency only, not CPU cycles or measured time.',
                       'Selected fixtures, not exhaustive path or whole-ECU coverage.',
                       'SD stock float table helpers execute native instructions; other guard boundaries remain as documented in their harness.',
                       'No bus waits, task rates, interrupt interference, FPSCR exception delivery, or deadline measurement.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', nargs='?', type=Path, default=HERE / 'D2WD610H_master_patch.bin')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = inspect(args.rom.read_bytes())
    rendered = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered)
        print(f"Opcode audit passed: {args.output}; ROM SHA256 {result['sha256']}")
    else:
        print(rendered, end='')
