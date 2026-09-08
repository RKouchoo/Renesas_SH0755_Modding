#!/usr/bin/env python3
"""Offline SD optimisation experiment. Never writes a BIN or changes defaults.

Reuse float limit/zero constants within call-free regions and schedule existing
independent loads around the unchanged multiplication sequence. All lookups,
validation comparisons and arithmetic operands/order remain the same. Caller-
saved constant registers are reloaded after each native lookup call.
"""

import _analysis_paths  # Shared repository, artifact and interpreter paths.
from contextlib import contextmanager
import argparse
import hashlib
import json
from pathlib import Path
import random
import unittest
from unittest.mock import patch as mock_patch

from audit_fpu_usage import NativeSDMachine, census, sd, sd_test, sh2_asm

HERE = _analysis_paths.MASTER
ORIGINAL_BUILDER = sd.build_wrapper


def replace_once(items, before, after):
    matches = [i for i in range(len(items)-len(before)+1)
               if items[i:i+len(before)] == before]
    assert len(matches) == 1, ('Expected one known instruction sequence', matches)
    index = matches[0]
    items[index:index+len(before)] = after


class ReuseAsm(sh2_asm.Asm):
    constants_ready = False

    def jsr(self, rn):
        # FR6/FR7/FR8 are caller-saved. Never assume a table helper preserves
        # them, even if a particular native path happens not to overwrite them.
        self.constants_ready = False
        return super().jsr(rn)

    def assemble(self):
        before, after = sh2_asm.Asm(0), sh2_asm.Asm(0)
        before.fmul(12, 0).fmul(15, 0)
        for address in (sd.DISPLACEMENT_ADDR, sd.AIRFLOW_CONSTANT_ADDR, sd.GLOBAL_MULTIPLIER_ADDR):
            before.movl_pool(1, address).fmov_load(2, 1).fmul(2, 0)
        before.fpush(0).fmov(13, 4).movl_pool(4, sd.IAT_DESC_ADDR)

        # Preserve all five products and their rounding order, while moving
        # existing address/argument setup into immediate dependency gaps.
        after.fmul(12, 0).movl_pool(1, sd.DISPLACEMENT_ADDR).fmul(15, 0)
        after.fmov_load(2, 1).movl_pool(1, sd.AIRFLOW_CONSTANT_ADDR).fmul(2, 0)
        after.fmov_load(2, 1).movl_pool(1, sd.GLOBAL_MULTIPLIER_ADDR).fmul(2, 0)
        after.fmov_load(2, 1).movl_pool(4, sd.IAT_DESC_ADDR).fmul(2, 0)
        after.fmov(13, 4).fpush(0)
        replace_once(self.items, before.items, after.items)

        # FR2 can hold the final cap across the final value gate, which uses
        # cached FR6/FR8. No call occurs before the cap is consumed.
        before, after = sh2_asm.Asm(0), sh2_asm.Asm(0)
        before.fpop(1).fmul(1, 0)
        after.fpop(1).movl_pool(1, sd.MAX_AIRFLOW_ADDR).fmul(1, 0).fmov_load(2, 1)
        replace_once(self.items, before.items, after.items)
        before, after = sh2_asm.Asm(0), sh2_asm.Asm(0)
        before.label('product_valid').movl_pool(1, sd.MAX_AIRFLOW_ADDR).fmov_load(2, 1)
        after.label('product_valid')
        replace_once(self.items, before.items, after.items)
        return super().assemble()


def ensure_constants(a, negative=False):
    if a.constants_ready:
        assert not negative, 'Negative limit is initialised only at the first range gate'
        return
    a.movl_pool(1, sd.FINITE_FLOAT_MAX_ADDR).fmov_load(6, 1).fldi0(8)
    if negative:
        a.fmov(6, 7).fneg(7)
    a.constants_ready = True


def range_gate(a, minimum, maximum, value_fr, exit_label):
    if not a.constants_ready:
        ensure_constants(a, negative=True)
    a.fcmpeq(value_fr, value_fr).bf(exit_label)
    a.movl_pool(1, minimum).fmov_load(3, 1)
    a.fcmpeq(3, 3).bf(exit_label)
    a.fcmpgt(3, 7).bt(exit_label)
    a.fcmpgt(value_fr, 3).bt(exit_label)
    a.movl_pool(1, maximum).fmov_load(3, 1)
    a.fcmpeq(3, 3).bf(exit_label)
    a.fcmpgt(6, 3).bt(exit_label)
    a.fcmpgt(3, value_fr).bt(exit_label)


def positive_gate(a, value_fr, exit_label):
    ensure_constants(a)
    a.fcmpeq(value_fr, value_fr).bf(exit_label)
    a.fcmpgt(8, value_fr).bf(exit_label)
    a.fcmpgt(6, value_fr).bt(exit_label)


def build_wrapper():
    with mock_patch.object(sd, 'Asm', ReuseAsm), \
         mock_patch.object(sd, 'emit_float_register_range_gate', range_gate), \
         mock_patch.object(sd, 'emit_positive_finite_value_gate', positive_gate):
        return ORIGINAL_BUILDER()


@contextmanager
def optimized_builder():
    with mock_patch.object(sd, 'build_wrapper', build_wrapper):
        yield


def prototype_image(image):
    original, optimized = ORIGINAL_BUILDER(), build_wrapper()
    assert image[sd.WRAPPER_ADDR:sd.WRAPPER_ADDR+len(original)] == original
    assert len(optimized) <= len(original), 'Prototype must fit the current reservation'
    result = bytearray(image)
    result[sd.WRAPPER_ADDR:sd.WRAPPER_ADDR+len(optimized)] = optimized
    # Intentionally no checksum repair/export: this byte array is an emulator
    # input, never a prepared flash artifact. Remaining old tail is unreachable.
    return bytes(result)


def execute(image, args):
    cpu = NativeSDMachine(image, **args)
    sd_test.Machine.run(cpu)
    assert len(cpu.trace) == cpu.instructions
    assert (cpu.mach, cpu.macl) == (0x12345678, 0x76543210)
    return cpu


def verify(image, samples=512):
    optimized = prototype_image(image)
    # Existing regressions poison all caller-saved registers on both lookup
    # boundaries, mutate sensor RAM after reads, and exercise invalid outputs.
    sd_test.verify_execution(image)
    with optimized_builder():
        sd_test.verify_execution(optimized)

    named = [('idle', dict(rpm=1300, map_mmhg=315, iat=20, mode=1)),
             ('opening', dict(rpm=1738, map_mmhg=712, iat=20, mode=1)),
             ('low_first_intervals', dict(rpm=250, map_mmhg=200, iat=-40, mode=1)),
             ('high_first_intervals', dict(rpm=3100, map_mmhg=200, iat=-40, mode=3)),
             ('stopped', dict(rpm=0, map_mmhg=315, iat=20, mode=1)),
             ('invalid_map', dict(rpm=1300, map_mmhg=float('nan'), iat=20, mode=1))]
    rng = random.Random(0x7055)
    cases = [args for _, args in named] + [dict(rpm=rng.uniform(1, 7500),
            map_mmhg=rng.uniform(100, 1600), iat=rng.uniform(-50, 150),
            mode=rng.choice((0, 1, 2, 3, 4, 255))) for _ in range(samples)]
    results = []
    for index, args in enumerate(cases):
        before = execute(image, args)
        with optimized_builder():
            after = execute(optimized, args)
        assert before.fr[0] == after.fr[0], ('Airflow bits changed', args)
        assert before.entered == after.entered, ('Native call route changed', args)
        for address in (sd.MAP_ADDR, sd.IAT_ADDR, sd.RPM_ADDR):
            assert before.reads[address] == after.reads[address]
        # Exact outputs/ABI are checked; FPSCR flags and interrupts are not
        # modelled, so this is not a claim of equivalence for every CPU state.
        if index < len(named):
            results.append({'fixture': named[index][0],
                            'before_wrapper': census(before.trace, lambda pc: pc >= sd.WRAPPER_ADDR),
                            'after_wrapper': census(after.trace, lambda pc: pc >= sd.WRAPPER_ADDR),
                            'before_including_lookups': census(before.trace),
                            'after_including_lookups': census(after.trace)})
    return {'source_sha256': hashlib.sha256(image).hexdigest(),
            'status': 'OFFLINE PROTOTYPE ONLY; no BIN exported or default builder changed',
            'original_wrapper_bytes': len(ORIGINAL_BUILDER()),
            'optimized_wrapper_bytes': len(build_wrapper()),
            'existing_regression_groups_per_variant': unittest.defaultTestLoader.loadTestsFromTestCase(
                sd_test.HookExecutionTests).countTestCases(),
            'paired_native_cases_with_identical_airflow_bits': len(cases),
            'fixtures': results,
            'limits': ['Instruction/dependency counts are not measured execution time.',
                       'FPSCR flags/exception delivery, interrupts and whole-ECU deadlines are not emulated.',
                       'No fixed-point conversion or reciprocal interpolation; three stock lookup divisions remain possible.',
                       'Read-only ROM/calibration assumption; sensor reads and saved caller RPM remain unchanged.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', nargs='?', type=Path,
                        default=HERE / 'candidates/D2WD610H_slight_dashpot_candidate.bin')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.rom.read_bytes())
    if args.output:
        assert args.output.suffix.lower() == '.json', 'Only JSON reports may be exported'
        assert args.output.resolve() != args.rom.resolve()
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        print(f"PASS: {result['paired_native_cases_with_identical_airflow_bits']} paired native cases; "
              f"{result['existing_regression_groups_per_variant']} existing regression groups per variant; "
              f"source {result['source_sha256']}; report {args.output}")
    else:
        print(json.dumps(result, indent=2))
