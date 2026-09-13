#!/usr/bin/env python3
"""Bounded individual-cylinder fuel producers through native pulse updates.

Unlogged bank/common fuel inputs, record stages and timer counts are explicit
fixtures. This does not reproduce the engine, actual task cadence or outputs.
All CPU callees in PipelineMachine execute ROM instructions, including21CC.
"""
import _analysis_paths
import hashlib
import json
from itertools import product

from analyze_20260913_cut_trace import ROM, ROM_SHA, LOG_SHA
from test_ssm_command_process_flow import SSMCommandMachine, RAM
from test_primary_fueling_execution import PrimaryFuelMachine, FUEL_WRITES
from test_injector_device_process_flow import InjectorDeviceMachine, DEVICE_WRITES
from test_injector_scheduler_execution import RECORDS, HARDWARE, LAST_PHASE, SCHEDULER_WRITES
from analyze_20260913_crank_refresh_followup import REFRESH_WRITES

ROOT = _analysis_paths.ROOT
OUT = ROOT/'logs/20260913_cylinder_fuel_followup_review.json'
PATTERNS = (0x48E32, 0x48E4E, 0x48E74, 0x48E9A, 0x48EC4)
PATTERN_WRITES = {(RAM+0xD050+4*n, 4) for n in range(6)}
OFFSET_WRITES = {(RAM+0xCC88+4*n, 4) for n in range(6)} | {(RAM+0xCCA4, 4)}
SCALE_WRITES = {(RAM+a, 4) for a in (0xBEB8, 0xBEBC, 0xBEC0,
    *range(0xBECC, 0xBEE4, 4))} | {(RAM+0xBEE6, 2), (RAM+0x8220, 2)} | {
    (RAM+a, 1) for a in (0xBEE8, 0xBEE9, 0xBEEA)}
DURATION_WRITES = {(RAM+0xB768+4*n, 4) for n in range(6)}


class PipelineMachine(SSMCommandMachine):
    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        if op & 0xF00F == 0x200A:
            # XOR Rm,Rn, T unchanged; Renesas SH-1/SH-2/SH-DSP manual5.1.3.
            # https://www.renesas.com/en/document/mah/sh-1sh-2sh-dsp-software-manual
            self.r[(op >> 8) & 15] ^= self.r[(op >> 4) & 15]
            self.visited.add(pc)
            self.trace.append((pc, op))
            self.pc += 2
            self.instructions += 1
            assert self.instructions < self.INSTRUCTION_LIMIT
        elif op & 0xF0FF == 0x4020:  # SHAL Rn, high bit ->T; low bit becomes0.
            n = (op >> 8) & 15
            self.t = bool(self.r[n] & 0x80000000)
            self.r[n] = (self.r[n] << 1) & 0xFFFFFFFF
            self.visited.add(pc)
            self.trace.append((pc, op))
            self.pc += 2
            self.instructions += 1
            assert self.instructions < self.INSTRUCTION_LIMIT
        else:
            super().step(in_delay)


def values(cpu, address):
    return [cpu.get_float(RAM+address+4*n) for n in range(6)]


def offset_and_scale(image):
    cpu = PipelineMachine(image)
    offsets = []
    for rpm in (1999, 2000, 2500, 2800, 3016, 3152, 3500, 3800):
        cpu.put_float(RAM+0xB544, rpm)
        cpu.write(RAM+0xCCA0, 0x40, 1)
        for n in range(6):
            cpu.put_float(RAM+0x82BC+8*n, (-1 if n % 2 else 1)*20)
            cpu.put_float(RAM+0xCC88+4*n, -10)
        cpu.execute(0x3CBC0, OFFSET_WRITES)
        result = values(cpu, 0xCC88)
        assert all(abs(v) <= .030001 for v in result)
        assert result == [0]*6 if rpm >= 2000 else any(result)
        offsets.append({'rpm_fixture': rpm, 'offsets': result})
    scales = []
    assert image[0x75E2B] == 0
    for crank, speed, counter in product((0, 128), (0, 57), (0, 65535)):
        cpu.write(RAM+0xB748, crank, 1)
        cpu.put_float(RAM+0xB538, speed)
        cpu.write(RAM+0xB68A, counter, 2)
        cpu.write(RAM+0xBEE8, 0, 1)
        cpu.write(RAM+0xBEE9, 0, 1)
        for n in range(6):
            cpu.put_float(RAM+0xBECC+4*n, .1*n)
        for a in (0xBEB8, 0xBEBC, 0xBEC0):
            cpu.put_float(RAM+a, -1)
        cpu.execute(0x23864, SCALE_WRITES)
        assert values(cpu, 0xBECC) == [1]*6
        assert all(cpu.get_float(RAM+a) == 0 for a in (0xBEB8, 0xBEBC, 0xBEC0))
        scales.append({'crank_fixture': crank, 'speed_fixture': speed,
                       'counter_fixture': counter, 'multipliers': values(cpu, 0xBECC)})
    return offsets, scales


def pipeline(image, pattern, state):
    setup = InjectorDeviceMachine(image, rpm=3152)
    setup.write(LAST_PHASE, 0, 1)
    old = 8000*4 if state == 'pending' else 12000*4
    for n, record in enumerate(RECORDS):
        setup.enqueue(n, 600, old)
        setup.write(record+2, 1, 1)
        setup.write(record+17, 1, 1)
        if state != 'pending':
            setup.write(HARDWARE[n]+19, 0, 1)
            setup.write(HARDWARE[n]+12, old, 4)
            setup.write(RAM+0xF640+2*n,
                        100 if state == 'late' else (old+2736)//16, 2)
    if state != 'pending':
        setup.write(RAM+0xF666, 63, 2)
    cpu = PipelineMachine(image)
    # Transfer only explicit scheduler/device/peripheral fixture state, not
    # the other interpreter's CPU registers, stack or lookup implementations.
    for a, v in setup.memory.items():
        if (RAM+0xAC00 <= a < RAM+0xAD14 or RAM+0xBFB4 <= a < RAM+0xC0DC
                or RAM+0xF400 <= a < RAM+0xF670):
            cpu.write(a, v, 1)
    PrimaryFuelMachine.seed_composer(cpu)
    cpu.put_float(RAM+0xB82C, 10000)  # Explicit base effective microseconds.
    cpu.put_float(RAM+0xB544, 3152)
    cpu.write(RAM+0xB748, 0, 1)
    cpu.write(RAM+0xB74A, 0, 1)
    cpu.execute(0x3CBC0, OFFSET_WRITES)
    cpu.execute(0x23864, SCALE_WRITES)
    cpu.execute(pattern, PATTERN_WRITES)
    factors = values(cpu, 0xD050)
    cpu.execute(0x1DD04, FUEL_WRITES)
    cpu.execute(0x1CA38, DURATION_WRITES)
    durations = values(cpu, 0xB768)
    assert all(abs(d-10000*f) < .002 for d, f in zip(durations, factors))
    cpu.execute(0x26E80, REFRESH_WRITES)
    assert all(cpu.read(r+6, 1) == 1 for r in RECORDS)
    cpu.original_r[4] = 1
    cpu.write(RAM+0xAC17, 1, 1)
    cpu.native_targets.clear()
    cpu.execute(0x263EE, SCHEDULER_WRITES | DEVICE_WRITES)
    effective = [cpu.read(hw+(0 if state == 'pending' else 12), 4) for hw in HARDWARE]
    remaining = [cpu.read(RAM+0xF640+2*n, 2) for n in range(6)]
    assert effective == [int(d*4) for d in durations]
    assert 0x90F8 in cpu.native_targets and 0x920C not in cpu.native_targets
    assert all(cpu.read(r+6, 1) == 0 for r in RECORDS)
    if state == 'pending':
        assert 0x21CC in cpu.native_targets
        assert all(cpu.read(hw+19, 1) == 2 for hw in HARDWARE)
    elif state == 'active':
        assert all(abs(v-(count+2736)//16) <= 1 for v, count in zip(remaining, effective))
        assert all(v > 0 for v in remaining)
    else:
        # Supplied elapsed gross time exceeds every revised gross target.
        assert all((old+2736)//16-100 > (count+2736)//16 for count in effective)
        assert remaining == [0]*6
    return {'pattern_entry': hex(pattern), 'device_state_fixture': state,
            'multipliers': factors, 'effective_duration_us': durations,
            'device_effective_counts': effective, 'remaining_counts': remaining,
            'native_cancel_called': False}


def main():
    image = ROM.read_bytes()
    assert hashlib.sha256(image).hexdigest() == ROM_SHA
    stock = (ROOT/'2005 BLE MT.bin').read_bytes()
    for a, b in ((0x3CBC0, 0x3CD80), (0x2379C, 0x239C8), (0x48D12, 0x48F20),
                 (0x1DD04, 0x1E0C8), (0x1CA38, 0x1CC78), (0x26E64, 0x27080),
                 (0x263EE, 0x2687C), (0x26C50, 0x26D44), (0x90F8, 0x915C),
                 (0x92DA, 0x9350), (0x21CC, 0x2378), (0x7635C, 0x76364),
                 (0x763B4, 0x763C8), (0x75E2B, 0x75E34), (0x10268, 0x1026C),
                 (0x11E54, 0x11E58), (0x11D84, 0x11D88)):
        assert image[a:b] == stock[a:b], hex(a)
    cpu = PipelineMachine(image)
    division = []
    for numerator, divisor in ((0, 26700), (1, 26700), (32000, 26700),
            (48000, 26700), (41999, 25000), (65535, 44444), (500, 1000), (12345, 6789)):
        cpu.original_r[4:6] = [numerator, divisor]
        cpu.execute(0x21CC, set())
        assert cpu.r[0] == (numerator << 16)//divisor
        division.append({'numerator': numerator, 'divisor': divisor, 'result': cpu.r[0]})
    init_writes = PATTERN_WRITES | {(RAM+a, 1) for a in (0xD06E, 0xD06F)} | {
        (RAM+a, 2) for a in (0xD06C, 0xD070, 0xD072)}
    for n in range(6):
        cpu.put_float(RAM+0xD050+4*n, 0)
    cpu.execute(0x48D12, init_writes)
    assert values(cpu, 0xD050) == [1]*6
    offsets, scales = offset_and_scale(image)
    cases = [pipeline(image, p, state) for p, state in product(PATTERNS, ('pending', 'active', 'late'))]
    report = {
        'rom_sha256': ROM_SHA, 'context_log_sha256': LOG_SHA,
        'scope': 'Native individual-cylinder modifiers and connected duration refresh; no ECU I/O.',
        'native_division_controls': division,
        'native_pattern_initializer_result': values(cpu, 0xD050),
        'individual_offsets': offsets, 'installed_selector_scale_cases': scales,
        'connected_cases': cases, 'case_count': len(cases),
        'interpretation': [
            'Native3CBC0 clears all six CC88 offsets atRPM>=2000; forced-enabled lower-RPM '
            'control clamps them to approximately +/-0.03.',
            'Installed75E2B=0 makes23864 reset all six BECC multipliers to1 and '
            'BEB8/BEBC/BEC0 to0, even from deliberately nonneutral prior values.',
            'All five identified D050 pattern publishers emit only0.9..1.05 multipliers. '
            'Initializer48D12 tails48E32 to set unity.',
            'Selected producer/composer/selector/refresh/scheduler/device path preserves six '
            'nonzero duration targets and makes no cancellation call in15 connected fixtures.',
            'An active pulse with only100 counts left terminates on a sufficiently shorter '
            'request because supplied elapsed time already exceeds the revised total; '
            'a positive logged target is not an instantaneous timer-active indication.',
        ],
        'limits': [
            'These are explicit input/state fixtures, not measured individual-cylinder values '
            'or an engine replay; no cause or cure is established.',
            'Common/bank corrections are neutral fixtures; retained bank histories remain separate.',
            'The pattern parent489E0/48D2C qualification and physical startup are not reconstructed.',
            'The selected native chain is not the complete periodic/crank tasks or their interleavings.',
            'Setup reuses the existing device fixture; all CPU callees in the connected '
            'PipelineMachine path execute natively, including fixed-point divide21CC.',
            'Timer counts are supplied; electrical delivery, elapsed hardware and deadlines '
            'are not simulated. No new registered regression groups;355 total unchanged.',
        ],
    }
    OUT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'output': str(OUT), 'connected_cases': len(cases),
                      'rpm_offset_cases': len(offsets), 'selector_cases': len(scales)}, indent=2))


if __name__ == '__main__':
    main()
