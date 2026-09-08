# Stock primary fueling execution audit

2026-09-08. The primary-calculation stage changed tests and documentation.
Its image was
`5fff8b3776af0b56b720c360e940b193f49893b35eb64e15b3578b203b97046c`,
Subaru checksum `0x75E22B4F`. Further downstream tracing then found and fixed
the [injector inhibit publication defect](INJECTOR_CUT_EXECUTION_AUDIT.md),
producing current `aea793...`. The primary-calculation findings below remain
valid; the second idle-VE trial is still unvalidated.

## Test-model defect corrected

The original shared instruction interpreter used host round-to-nearest
arithmetic. SH-2E instead fixes rounding toward zero, flushes subnormal
operands/results and saturates finite overflow. FMAC rounds its multiply and
add separately. These rules are specified in Renesas's
[SH-2E Software Manual](https://www.renesas.com/en/document/mah/sh-2e-software-manual),
sections 4.2–4.4 and 7.3.9.

`speed_density/sh2e_test_fpu.py` now applies those value rules using exact
rational arithmetic for executed instructions. ROM constants and test fixtures
retain their binary32 encoding. Table interpolation remains an explicit
mathematical substitute; its internal instructions are not emulated.

Five new FPU test groups include the manual's `4/3 -> 0x3FAAAAAA` example,
positive/negative truncation, cancellation, FMAC's two rounding steps and
destination alias, overflow, subnormal handling, signed zero, and NaNs with
exceptions disabled. Another 2,400 exact arithmetic cases check that the
result bounds the exact answer in the correct direction with no representable
normal value between them. The previous host model fails the rounding vector.

The observed startup instructions `F510/F512` load FPSCR from literal
`F5CC = 0x00040001`; invalid/divide-by-zero enable bits are clear. Tests pin
those bytes. FPSCR flags, exception delivery and all context restores remain
outside the value model. This correction improves the existing SD, retained
sensor, and guard instruction tests; all still pass. It has not demonstrated
another firmware defect or the September 7 lean-out cause.

## Stock target, transition and final fuel calculation

`test_primary_fueling_execution.py` follows the integrated task pointer at
`11D78` into pressure wrapper `7EB20`, then executes stock `22454` instead of
substituting its resulting permission byte. It also executes transition
routine `22756`, final composer `1DD04`, and actual helpers `2458`, `24A0`,
`24B0`, `24C0`, and `251C`. The tested stock code/literal ranges are pinned
against the immutable stock ROM. Scratch registers are poisoned at modeled
table calls, and each invocation checks saved registers, PR, stack balance,
and permitted RAM writes.

| Path | New coverage |
|---|---|
| Current primary A/B tables → pressure wrapper → composer | 135 RPM/load/pressure/blend combinations; wrapped and unwrapped calculations match except permission bit 0x80 |
| Cached table selection, previous correction and delay gates | 96 combinations using distinct table outputs, plus preserved ancillary enrichment factors |
| Actual permission-driven ramp | Zero ramp → guarded target → stock transition → enriched target; other permission bits preserved |
| Stock delay flags/counters | 54 combinations confirm below-threshold bits, hysteresis, ramp direction and counter saturation |
| Alternate RPM-based enrichment | 48 threshold/hysteresis/delay combinations |
| Final bank/cylinder composition | 80 independently calculated combinations of common/bank adders, ordinary trims, hot-IAT factor, base duration and six cylinder corrections |
| Native bounds | Factor clamp 0..32 and duration clamp 600..262136 |
| Negative controls | Wrong pressure bit operation and a dropped BDF8 fuel contribution both change the expected result |

There are eight primary-fueling test groups, integrated into the master
verifier alongside the five FPU groups.

## What the pressure override actually guarantees

`22454` computes the selected primary table value in `BE00`, main ramp output
`BDFC`, auxiliary ramp output `BE04`, and final primary enrichment `BDF8`.
The normal BDF8 branch takes the larger ramp output and multiplies by
`BE0C * BE10`. The pressure wrapper leaves these results intact and may clear
only `BE38` bit `0x80` after the stock calculation.

An initially zero `BE14` ramp can therefore produce zero enrichment on the
first high-pressure invocation even when the selected primary table is rich.
The stock `22756` routine sees the cleared permission bit and advances BE14
toward its current one-count calibration at `75E86`. With the other eligibility
gates satisfied, the next primary-target invocation supplies the selected
enrichment. The test executes this sequence; it assigns no milliseconds to it.

The earlier RAM-map labels for `BE38` bits `0x40/0x20` were reversed: stock
`22756` sets them below its throttle/base-duration thresholds and clears them
above, with hysteresis. The labels are corrected and the behavior is now
instruction-tested. The guard's use of bit `0x80` is unchanged.

Separately, high pressure paired with low **modeled load** can select zero
table enrichment even while the wrapper forces open loop. Pressure permission
is not a minimum-richness guarantee. The unchanged 6% conditioned-load filter,
transient behavior and scheduling therefore remain relevant to boost entry.
This is the existing component's scoped behavior, not a justification for a
new pressure-based fuel target or an unmeasured filter/calibration change.

`1DD04` carries BDF8 into both bank factors and all six cylinder fuel
calculations. Tests independently verify retained common corrections, bank
adders/subtractions, ordinary learned/short-term corrections, hot-IAT
multiplication, cylinder corrections and native clamps. Its several duration
variants are calculation outputs; executing this routine does not prove
injector selection, scheduling or physical pulse delivery.

## Verification and remaining limits

```
python3 master_patch/verify_master_patch.py
python3 speed_density/test_hook_execution.py master_patch/D2WD610H_master_patch.bin
```

Both pass. The master verifier also confirms a deterministic rebuild,
unchanged stock provenance, checksum, component ownership and definitions.
The stale source recommendation to reuse the old first-VE BIN was corrected;
any first-VE comparison must include the current firmware repairs.

The stock table-helper instructions, complete
injector scheduling/delivery, interrupts, task timing, controller fault behavior,
post-turbo feedback dynamics and actual calibration remain outside this pass.
The later cut audit also executes `1C5D4` and a downstream channel gate.
These tests close the primary-target stand-in gap for the cases above; they
do not establish 100% hardware/tune certainty or authorize load/boost testing.
See [COMMISSIONING.md](COMMISSIONING.md).
