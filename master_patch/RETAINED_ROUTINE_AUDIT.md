# Retained stock routines: external-wideband and cold-idle audit

The later [guard execution audit](GUARD_EXECUTION_AUDIT.md) produced
master `5fff8b...`, fixing zero-lambda/stale-readiness handling. The subsequent
[injector-cut repair](INJECTOR_CUT_EXECUTION_AUDIT.md) produced `aea793...`;
the later [scheduler repair](INJECTOR_SCHEDULER_EXECUTION_AUDIT.md) produces
current `48d63c...`, with no sensor-correction or tuning-data changes.
The retained-sensor
changes and `5a1b3e...` output recorded below remain the preceding audit stage;
that later guard repair changes no sensor-correction or tuning data.

2026-09-08. The user confirms the car still runs the September 7 image.
This review changes the development master on disk, not the ECU. The missing
saved ECU-read file referenced in the older notes prevents an independent
byte-for-byte identification of the currently installed image. Commit
`1ebbc91` is an earlier saved baseline, not a substitute for that readback.

## Result and exact change

Retained factory-sensor assumptions are incompatible with the external lambda
source. The wideband component neutralizes these contributions:

| Range | Before | After | Purpose |
|---|---|---|---|
| `0x73E08..0x73E0F` | Q15 `B333 9B44 8DF4 8000` | `8000 8000 8000 8000` | Unity atmospheric correction for already decoded external lambda |
| `0x76384..0x7638B` | Two float `0.25` values | Two float positive zeros | Disable auxiliary fuel adders dependent on removed O2 voltage channels |
| `0x760F0..0x760F3` | Float `-0.04` | Float positive zero | Neutralize legacy-voltage bank target offset B900/B904 |
| `0x202CC..0x202CD` | `F428` (`fmov.s @r2,fr4`) | `F48D` (`fldi0 fr4`) | Exclude bank-1 voltage trim BD04 from lambda target |
| `0x202D0..0x202D1` | `F418` (`fmov.s @r1,fr4`) | `F48D` (`fldi0 fr4`) | Exclude bank-2 voltage trim BD08 from lambda target |

The retained-sensor repair declares 24 bytes, of which 16 actually differ
from stock. Including checksum, it changes exactly 20 bytes from the preceding
fan/purge-repaired `fbc1a8...` master. Its second pass changes ten bytes from
the first retained-sensor image `89ce82...`: six actual instruction/data bytes
and four checksum bytes. Only two existing instruction words change; no new
hook, RAM or free-flash allocation is needed. VE, injector, timing, AVCS,
after-start and pump data are unchanged by both retained-sensor passes.

Retained-sensor pass output SHA-256:
`5a1b3e389bdb1a6099b6ed39c3f59d53dfc1808b2d16e56f05148c127c4f48b5`.
Stored/calculated Subaru checksum: `0xCAACD6C4`.

This fixes identifiable sensor-integration mismatches. It does **not** establish
the cause of the cold lean-out. Removing a positive auxiliary adder can lower
fuel wherever that adder previously activated. The image still contains the
unvalidated second-VE trial; it is not a calibration-identical replacement for
the September 7 run. Do not use an older fan-hook image for comparison.

## 1. Factory atmospheric compensation changes external lambda

Stock assembly `front_af_sensor_lambda_condition_filter @ 0x18DAC` reads
`AE60/AE64`, which the master now fills using the external controller's supplied
transfer. At `0x18DDE..0x18DE6` it looks up descriptor `0x5EA2C` using selected
barometric pressure `CFBC`. At `0x18DF4..0x18E18` it calculates each bank as:

```
conditioned lambda = clamp(1 + (external lambda - 1) * K(baro), 0.75, 2.0)
```

The descriptor has four float pressure knots at `0x73DF8` and four uint16
coefficients at `0x73E08`, multiplied by `2^-15`. Stock K falls from about
1.40 at 523.83 mmHg to 1.00 at 758.20 mmHg. At 720 mmHg it is approximately
1.0533: an external lambda of 1.20 becomes about 1.2107 before the remaining
readiness/state handling. The external logger mirror B098 bypasses this
conditioning, so its agreement with the gauge does not verify the feedback
value B4E8.

The supplied external transfer is already expressed as lambda. Reapplying
this factory sensor curve changes that defined quantity without an established
controller-specific basis. Unity coefficients preserve the supplied lambda
through this arithmetic for the accepted 11..19 AFR range. Stock readiness,
fallback, clamps and filters remain. This does not validate the controller's
physical accuracy or exhaust-pressure sensitivity.

Descriptor `0x5EA2C` has a single mapped consumer here. Its complete bytes and
the consumer's code/literals are installation guards. This is not a change to
the MAP transfer or to the SD density calculation.

## 2. The O2 delete left an auxiliary voltage-dependent fuel adder

`0x7AB0` still converts raw ADC words `AB22` and `AB0E` into `ABCC` and `ABD0`
using `5/65536`. These are separate from the former-MAF wideband ADC `AB06`.

The identity trace is reproducible through stock SSM dispatch:

| SSM byte(s) | Pointer slot(s) | Handler(s) | Input |
|---|---|---|---|
| `0x16/0x17` | `0x4B754/0x4B758` | `0x316DE/0x316F6` | ABCC |
| `0x1A/0x1B` | `0x4B764/0x4B768` | `0x3170C/0x31724` | ABD0 |

[RomRaider's SSM definitions](https://github.com/RomRaider/RomRaider/blob/master/definitions/log_defs.xml)
identify `0x16` and `0x1A` as the two Front O2 Sensor voltage values. This
cross-check names the firmware channels; it does not establish harness pins.

`fueling_correction_d114_d118_update @ 0x49B20` reads these voltages alongside
conditioned lambda `B4E8/B4EC`. Its common gates include `D110 == 0`,
`B90C > 0`, and near-zero checks on `BDF8` and `BE48`. For each bank, it requires
legacy voltage below 0.3 V and conditioned lambda at least 1.05. It then writes
one of the float constants at `0x76384/0x76388`; both are 0.25 in stock.
Otherwise it writes zero. `0x18CF4` chooses between those two constants.

Final fueling `0x1DD04` explicitly adds D114/D118 to the respective bank's
additive base, separately from normal short-term/learned feedback. Thus this
path can depend on disconnected circuits even with a valid synthetic lambda.
Setting both constants to zero removes that dependency from this specific
adder without changing the routine or inventing an emulated narrowband voltage.
Mapped xrefs for both constants are confined to this consumer.

B90C is stateful: `0x1F722` updates it, including a load-dependent decrement
using a 4.0-g/rev threshold (`0x7611C`). It is not established as a 30-second
timer. Neither B90C nor D114/D118 nor the two raw voltages was captured in the
usable idle logs. Activation and subsequent removal of this adder during the
event therefore remain unproved; its positive sign alone cannot exclude a
lean transition when it ceases to apply.

## 3. A second voltage path changes the lambda target and fuel correction

The original four-sensor delete bypassed the principal conversion/monitor
tasks, but not the separate front-O2 voltage path through `ABCC/ABD0`.
Two further contributions survive the first retained-sensor repair.

### Bank offset B900/B904

`0x1F0D8` snapshots ABCC/ABD0 to BC64/BC68, then calls `0x20564` for each
bank with ROM descriptors `0x4B2CC/0x4B2DC` and `0x4B27C/0x4B28C`.
When BCAB is not 1, B90C is zero and the bank counter BB64/BB66 is positive,
20564 sets B918/B919 to 1 and compares the voltage with lookup `0x5F2E8`.
All five stock threshold values are 61 times 0.0048828125, or 0.2978515625 V.
Below that threshold it writes the float at `0x760F0` (-0.04) to B900/B904;
otherwise it uses `0x760F4` (zero). An inactive gate clears the flag and offset.

`0x202B8` adds this offset to each lambda target B8F4/B8F8. Independently,
`0x45258/0x452B8` use it in the CEFC/CF00 correction:

```
clamp((1 / (1 + B8FC + bank_offset) - 1), -0.01, +0.10)
```

This expression describes stock unit gains and a denominator outside the
near-zero guard. With B8FC=0, an offset of -0.04 produces approximately
+0.041667, which the final fuel composer consumes outside the logged main
short-term trims. Changing `0x760F0` to zero makes this publisher produce zero
for both voltage branches and all its gates; the other constant is guarded
as already zero. Mapped references to these two constants are confined to
20564. The active-state flags retain their stock behavior.

### Voltage trim BD04/BD08, including stored history

`0x219C6` filters ABCC/ABD0 into BD20/BD24. The bank structures at
`0x4B33C/0x4B398` pass those filtered voltages to `0x21F0C`, which produces
BD04/BD08. Its active branch uses the measured voltage and PI-like state;
its inactive branch copies the stored baseline at `0xFFFF8200/0xFFFF8208`.
The related `0x22286` learning path updates retained state via `0x49530`.
Therefore simply preventing this loop's activation would not eliminate its
stored contribution to the fuel target.

`0x202B8` starts with BD04/BD08 and computes, before stock clamps:

```
bank 1 target = 1 + BD04 + BB50 - BB60 + B900 + B8FC - B910 + B908
bank 2 target = 1 + BD08 + BB54 - BB60 + B904 + B8FC - B914 + B908
```

The two one-word substitutions at 202CC/202D0 set that initial FR4 contribution
to zero. Bank 1's substitution is in the existing BRA delay slot; execution
tests cover it. Neither voltage trim is read by this consumer after repair,
even if its value is stale or NaN. All the other terms and both clamps remain
instruction-equivalent. With other terms zero and a legacy trim of -0.04,
stock targets 0.96 lambda while the corrected target is 1.00.

The voltage loop and its diagnostic/learning consumers continue to execute;
their complete effects are not deleted. Main external-lambda feedback,
its transport-delay filter, and ordinary learned fuel corrections BCB8/BCBC
remain intact. The repair excludes the two identified voltage contributions
where they enter fuel control instead of fabricating a narrowband voltage.

### Activation limits

The counter producer `0x205FA` includes history, mode transition and 70 C
coolant gates. The voltage-loop enable at `0x218F0` requires multiple runtime
conditions, including coolant at least 40 C, load at least 0.15 g/rev, RPM
below 6000, B91D=1, a bank state and an engine-runtime gate. These are not
unconditional cold-start adders. B91D is computed at `0x1F3AC`; it is not a
fixed disabled-ROM option. The inactive voltage loop can still publish its
stored baseline, as described above.

B90C's 120-count reload (`0x75E1B`) is updated by `0x1F722`, called from the
bank-selected paths of `0x1EE74`. Converting that count to seconds requires
the relevant calling cadence; it must not be presented as a 30-second timer.
No live values for these offsets, counters, voltage trims or stored baselines
were captured in the usable idle logs. This pass establishes firmware data
dependencies, not activation during the September 7 event.

## 4. Retained routines that were not changed

| Path | Evidence / disposition |
|---|---|
| Final fuel composition `0x1DD04` | Assembly confirms base pulse B82C, hot-IAT factor BE88, bank additive terms, normal corrections B8D4/B8D8 and learned terms BCB8/BCBC. Code unchanged; zero logged short-term trims do not account for every term. |
| After-start groups A/B and C/D | Inspected functions at `0x1E1B0`, `0x1E47A`, `0x22B7E`, `0x22CE4`, `0x22E0E` remain stock. No demonstrated new mismatch justifies stopping their decay. Their runtime values are needed to distinguish normal decay exposing low base fueling from another loss. |
| Injector scheduling / scalar / latency | Existing donor translation and scheduling audit remains applicable. No new scheduler replacement justified by this review. Physical short-pulse behavior remains unvalidated. |
| SD-to-load integration | September 8 already stabilizes per-call inputs and bypasses local obsolete MAF-fault substitution. Eight emitted-wrapper execution test groups pass. This does not establish the old fallback activated on September 7. |
| Pump output `0x2A53A` | Code/literals remain stock. September 7 P47 changes at 32.546 s file time, 30.305 s after first nonzero RPM; the AFR rise precedes it. Command is not measured rail pressure. |
| AVCS / VE interaction | Lift-specific VE has no actual-cam-angle dimension. Increased synthetic load can move AVCS targets. No cam angle was captured; holding cams or retuning targets is not justified by these files. |
| Pressure/lean fuel guards | Their intended gates are near/above barometric pressure; no new unconditional idle cut was identified. Native MAP, state and cut flags are needed to verify runtime gating. |

In both the earlier saved `1ebbc91` baseline and the pre-audit master,
instruction bytes and PC-relative literals in the inspected after-start
functions, final-fuel composer and pump-output routine were stock-equivalent.
This bounded comparison does not certify their inputs, every reachable callee,
all table data, or the exact installed September 7 ROM.

## Validation and limits

Commands:

```
python3 master_patch/verify_master_patch.py
python3 master_patch/test_stock_sensor_corrections.py master_patch/D2WD610H_master_patch.bin
python3 speed_density/test_hook_execution.py master_patch/D2WD610H_master_patch.bin
```

The auxiliary-adder test executes the retained 49B20 opcodes in 192
gate/input combinations, checks both bank outputs, stack and callee-saved
registers, and starts with stale NaN output state. The external helper results
are enumerated rather than instruction-emulated. Stock and independently
restored constants are negative controls that recover the 0.25 adders.
The second pass executes 20564 in 486 bank/gate/voltage cases and 202B8 in
312 bank/trim/other-input cases, including both substituted instructions and
the original clamp helper 24C0. Negative controls restore the -0.04 constant
and each original load instruction separately, recovering the old behavior.
The target tests compare against the original consumer with voltage trim zero,
vary each other term independently through both clamps, and assert zero reads
of the excluded trim. Stack, saved registers and exact output writes are checked.
The voltage lookup is modeled from its pinned uint8 descriptor and ROM data;
the upstream voltage-loop/counter scheduler is not instruction-emulated.
Atmospheric behavior is a descriptor-pinned Q15 interpolation/arithmetic model,
not execution of the stock table helper. Guards reject changed code, descriptor
or original data before mutation. The full verifier checks fresh-build equality,
declared ownership, other components, definitions, checksum and stock provenance.

The 17040 family derives readiness bits read through 17210/1722C by 217B8 and
diagnostic consumers. The 170BA/170F4 families maintain voltage snapshots and
filters. Direct xrefs alone do not establish every computed-pointer consumer.
The continuing 217B8 voltage loop and its learning/diagnostic effects also remain
audit limits, despite removing its identified fuel-target contribution. These
scoped repairs do not prove full independence from removed O2 circuits. Factory
closed-loop transport delay and ordinary learned trims remain validation items.

The next discriminating capture should include conditioned load B438, base
injector duration B82C, final fuel factors, scheduled pulse/latency and after-start
terms alongside MAP/RPM/IAT/AFR. A targeted follow-up can substitute D114/D118,
B90C and the two legacy voltages to test the first identified path. A separate
targeted profile can capture B900/B904, BD04/BD08, B8F4/B8F8 and CEFC/CF00.
Keep the
SSM request within 84 byte addresses; the existing 79-address profile cannot
simply have all these channels appended. No live ECU traffic or flashing was
performed during this audit.
