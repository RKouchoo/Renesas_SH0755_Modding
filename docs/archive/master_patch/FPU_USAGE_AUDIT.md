# SH7055 floating-point workload — 2026-09-08

> Archived investigation, retained for evidence and historical reproduction.
> Use the [central reference](../../reference/README.md) and [audited corrections](../../reference/FINDINGS.md) for current conclusions.
> Build identities, commands and recommendations below describe their original stage.

The added routines use native single-precision SH-2E operations. None of the
eight emitted routines inspected contains `FDIV`. Speed density does add up
to **three native divisions per calculation** through the stock float-axis
lookup helper at `0x2702`: MAP, RPM and IAT each require at most one.

This is an instruction census and dependency review, **not measured execution
time, total CPU utilization, or a deadline guarantee**. No BIN changed.

## Subsequent optimisation prototype

`prototype_sd_fpu_reuse.py` reuses the same float limits/zero within call-free
regions and moves existing independent loads between dependent instructions.
The default builder and every BIN remain unchanged. A shorter wrapper exists
only in an emulator byte array; that array is not checksummed or exported.

| Valid low-lift path | Current | Prototype |
|---|---:|---:|
| Wrapper instructions | 200 | 178 |
| Wrapper FP instructions | 101 | 88 |
| Immediate non-divide FP dependency pairs | 42 | 13 |
| Idle instructions including native lookups | 476 | 454 |
| Idle FP instructions including native lookups | 194 | 181 |
| Wrapper code plus literal-pool bytes | 536 | 492 |

The six multiplications retain their operands and order. All 42 validation
comparisons remain; native table lookups and their possible three divisions
remain. Cached constants use caller-saved FR6/FR7/FR8 and are reloaded after
each call. The retained caller defines FR6/FR7 before its subsequent uses and
does not use FR8; the generic ABI checks also pass. This is not a fixed-point
rewrite or reciprocal approximation.

All eight existing SD regression groups pass for both variants, including
lookup helpers that deliberately poison caller-saved registers, invalid
inputs/results, changed RAM after snapshots, and stack checks. Another 518
paired cases per input image execute the native lookup instructions and return
**bit-identical airflow**. Baseline, original idle candidate and the user's
current dashpot image all pass (1,554 paired cases total).

This reduces valid-path FP instruction count by 12.9%, and immediate dependency
pairs by 69.0%; neither percentage is a measured speed improvement. The whole
idle call loses 22 of 476 instructions (4.6%). An early NaN-MAP exit instead
grows from 33 to 38 instructions because constants are loaded before that
check. FPSCR flags/exception delivery and interrupt interference remain outside
the emulator's checks. No claim of faster execution on every path is made.

```sh
python3 tools/analysis/prototype_sd_fpu_reuse.py --output /tmp/d2wd-fpu-reuse.json
```

The later [transient-component analysis](TRANSIENT_COMPONENT_AUDIT.md) gives a
more direct explanation for persistent fuel subtraction during recovery. The
FPU prototype is kept separate from that calibration sensitivity experiment.

## What the processor actually waits for

The [Renesas SH-2E Software Manual](https://www.renesas.com/en/document/mah/sh-2e-software-manual)
(Rev. 2.00, printed pages 2, 179, 216–217 and 290) specifies a one-cycle issue
pitch and two-cycle result latency for add/subtract/multiply. An immediately
following consumer of an ordinary FP result incurs one extra pipeline slot.
`FDIV` occupies E1 for 13 cycles and blocks subsequent FPU-related work until
completion; independent integer instructions can proceed. The manual suggests
keeping the next 14 instructions free of FPU-related operations to hide that
latency where possible. The wait preserves the dependency's correct result.

At the project's **assumed 40 MHz**, one clock is 25 ns and 13 clocks are
0.325 µs. Three divisions occupy 0.975 µs of E1 time. Those conversions are
not a measurement of a complete call: memory contention, branches, other
pipeline stages and interrupts affect elapsed time. Actual oscillator rate
has not been measured.

## Actual added instruction paths

The supplied image is checked byte-for-byte against all eight code builders;
literal pools and padding are excluded. Dynamic counts include delay slots.
FP totals include loads, stores, compares, constant loads and FPUL transfers,
as well as arithmetic. The following counts exclude retained callees unless
explicitly stated otherwise.

| Executed fixture | Added instructions | FP instructions | Arithmetic |
|---|---:|---:|---|
| SD, valid low lift | 200 | 101 | 6 multiplies, 3 sign negations; no divide |
| SD, valid high lift | 198 | 101 | Same |
| Wideband, valid ADC | 58 | 30 | 2 multiplies, 1 add, 1 integer-to-float conversion |
| Wideband inhibit, ready | 8 | 3 | 1 compare, 2 loads |
| Pressure-forced OL, vacuum / atmosphere | 41 / 45 | 16 | 1 subtract |
| Combined overboost/lean wrappers, vacuum | 91 | 25 | 1 subtract |
| Combined overboost/lean wrappers, monitoring | 122 | 35 | 1 subtract |
| Rotational idle, current OFF setting | 11 | 0 | None |

SD's 101 FP instructions comprise 43 moves/loads/stores, 42 compares, seven
zero loads, three negations and six multiplies. Validation and moving values
account for most of the FP instruction count. Its temperature-density factor
is precomputed in an IAT table; the wrapper does not divide by temperature.
Rotational idle's six-cylinder arithmetic loop is skipped with the current
enable byte zero. Retired boost actuator code is not an active control loop.

## SD including the actual stock lookup instructions

The new census executes `209C`, `2150`, `26E0`, `27D0`, `27F0` and `25F8`
from the ROM instead of treating table interpolation as a mathematical call.
Outputs are compared with the existing independent mathematical lookup model,
allowing the small difference from native SH-2E arithmetic rounding. Return
addresses, saved registers, stack, output writes, MACH and MACL are checked.

| Fixture: RPM / MAP mmHg / IAT °C / mode | Total instructions | FP instructions | FDIV |
|---|---:|---:|---:|
| Idle: 1300 / 315 / 20 / low | 476 | 194 | 3 |
| Opening: 1738 / 712 / 20 / low | 446 | 184 | 3 |
| First axis intervals: 250 / 200 / −40 / low | 527 | 213 | 3 |
| First axis intervals: 3100 / 200 / −40 / high | 537 | 217 | 3 |
| Running: 4500 / 1000 / 30 / high | 424 | 176 | 3 |
| Upper axis clamps: 7500 / 1600 / 150 / high | 313 | 131 | 0 |
| Stopped: RPM zero | 27 | 13 | 0 |
| Invalid MAP: NaN fixture | 33 | 17 | 0 |

The first-interval cases exercise long backward scans; they are not a claim
that every possible ECU path was covered. Axis scans are bounded by the table
dimensions (13 MAP, 9/11 RPM and 10 IAT entries). These exact emitted/fixture
counts supersede the earlier hand estimates of 226 static instructions,
204/202 wrapper instructions and approximately 531/541 including helpers.
The current wrapper has 220 static instructions across all branches.

## Dependencies worth improving if timing measurements justify it

There are **42 immediate non-divide FP dependency pairs** along a valid SD
wrapper execution. Many are loads immediately followed by validity checks.
These three examples are direct arithmetic-result dependencies:

```asm
7E2BA: FMUL   FR12,FR0
7E2BC: FMUL   FR15,FR0

7E2CE: FMUL   FR2,FR0
7E2D0: FMOV.S FR0,@-R15

7E2F0: FMUL   FR1,FR0
7E2F2: FCMP/EQ FR0,FR0
```

Under an ideal one-clock-per-slot assumption, 42 extra slots represent
1.05 µs at 40 MHz. This is an isolated dependency cost, not the wrapper's
total elapsed time or an exact optimization saving. Reordering existing
independent work can hide some latency; adding NOPs alone does not save time.

With stock helpers included, the idle fixture has 77 ordinary immediate FP
dependency pairs. Its three divisions are followed by 3, 4 and 10 non-FPU
instructions before the next FPU instruction. Return/branch and memory costs
mean instruction spacing alone does not determine the remaining divide stall.
The helpers are not specially scheduled to hide all divide latency.

This is real added work over the replaced minimum-select helper. Removed MAF
and O2 processing also changes workload; the net change has not been timed.
The modest, bounded FPU work does not by itself explain a prolonged rough
running state. CPU overload remains unproved: a task already near its deadline
could still be affected. A definitive timing investigation needs task duration,
release/completion and interrupt/overrun evidence at the ECU, including maximum
RPM. The approximately 104-ms SSM captures cannot supply that evidence.

The retained timing/fuel-transient findings in the
[evening review](../../../logs/20260908_dashpot_review.md) remain relevant. No FPU
instruction scheduling change, fixed-point rewrite or new flash image is
justified by this census alone.

## Reproduction

```sh
python3 tools/analysis/audit_fpu_usage.py master_patch/candidates/D2WD610H_slight_dashpot_candidate.bin --output /tmp/d2wd-fpu-usage.json
```

The script writes only the requested JSON report. Nine SD fixtures and ten
other-hook fixtures pass on the baseline and both original/current candidate
files; each run asserts that executed added code matches its source builders.
The existing full functional verifier also passed before this read-only audit.

Images inspected:

- Baseline: `48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0`.
- Original idle candidate: `6af0d130b585abf9c9b275840ddb0b237485d84f8f8adf7b15df8462adc72433`.
- User's current dashpot file: `2f80b8e5cb80361cdee170655bc26aa8ed8a41bcf4cd7f7249fe3f8c8eaa1f1c`.

The census is deliberately outside the master verifier: it reports workload
and does not turn an instruction-count threshold into a false timing pass.
