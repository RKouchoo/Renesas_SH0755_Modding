# D2WD610H RAM Variable Map

> Archived investigation, retained for evidence and historical reproduction.
> Use the [central reference](../../reference/README.md) and [audited corrections](../../reference/FINDINGS.md) for current conclusions.
> Build identities, commands and recommendations below describe their original stage.

The central [signal reference](../../reference/SIGNALS.md) and
[address evidence index](../../reference/ADDRESS_INDEX.md) now own the reviewed
types, producers, consumers and confidence. Physical SH7055SF RAM spans
`0xFFFF6000–0xFFFFDFFF`. This older topic map is retained pending review;
an existing Ghidra label alone is not proof of a variable's meaning.

## Engine core signals
| RAM addr | Type | Meaning | Evidence |
|---|---|---|---|
| **0xFFFFB544** | float | **Engine RPM** | compared vs 4000/3800/512/510; table input; ign+AVLS |
| **0xFFFFB538** | float | **Vehicle speed, km/h** | `ign_idle_timing_target_update` compares it with the stock 4.0-km/h threshold at 0x77E1C; gate input to pedal conditioning |
| **0xFFFFB420** | float | **Final mass airflow, g/s** | stock final-airflow store; master speed density replaces its producer |
| **0xFFFFB428** | float | **Raw engine load, g/rev** | stock calculation is `B420 * 60 / B544` before conditioning |
| **0xFFFFB438** | float | **Conditioned engine load, g/rev** | load axis input for AVCS, ignition, fuel, and knock consumers |
| **0xFFFFB46C** | float | **Conditioned accelerator pedal, percent** | snapshot of B4C8 used by P30, AVLS and idle-air release qualification; [native proof](../master_patch/IDLE_AIR_RECOVERY_AUDIT.md) |
| **0xFFFFB124** | float | **Engine-oil temperature, degrees C** | AB12 thermistor conversion through descriptor 0x60950; source for the AVLS selector |
| **0xFFFFCF94** | float | **Conditioned/fallback engine-oil temperature, degrees C** | valid B124 or stock 70 C fallback; selects AVLS cold/normal/hot state |
| **0xFFFFABC4** | float | **Manifold pressure (MAP), native mmHg absolute** | `map_sensor_voltage_to_pressure_process` @0x7A14 output; `MAP = voltage × scaling[1] + scaling[0]` |
| 0xFFFFABC8 | u16 | Filtered MAP ADC word, not pressure or float | word accesses at `0x7A28/0x7A36/0x7A3E` in `map_sensor_voltage_to_pressure_process` |
| 0xFFFFAB04 | u16 | MAP raw ADC value | `map_sensor_voltage_to_pressure_process` input |
| **0xFFFFB3AC** | float | **Coolant temp (ECT), °C** | read by ~100 fns; purge/thermal input |
| **0xFFFFB3B8** | float | **Intake-air temperature (IAT), °C** | written by `intake_air_temperature_update` @0x16D1C; input to stock MAF-IAT compensation and the speed-density density curve |
| **0xFFFFB314** | float | **Processed throttle opening** | produced by `throttle_position_sensor_process` @0x14DCC; input to CL/OL throttle threshold and the boost-control demand gate |

> **Standalone donor component only:** its MAP transfer at `0x72810` is
> `{-414.0, 514.199951}`. Stock uses `{-150.0, 250.0}`. Current main and v2
> instead use the Omni transfer `{-67.7766571, 487.9919434}` in mmHg and
> mmHg/V. These calibrations are not interchangeable. See
> [exact image contracts](../../reference/IMAGES.md).

The standalone MAFless component retains the stock task at `0x172A4` for its downstream
`B428..B440` load/filter/state calculations, but redirects its final-airflow helper at `0x1743C`
to the SD model before the `B420` store. The helper prechecks exact zero RPM, then validates MAP,
RPM, IAT, and calibration data; zero RPM writes zero and every other invalid state writes the fixed
500 g/s rich/high-load fail-safe. Raw-MAF producers and known MAF-dependent diagnostics are
bypassed. A separate post-intercooler IAT sensor is required when the MAF/IAT assembly is
physically removed.

## Ignition timing (see notes §4)
| RAM addr | Meaning |
|---|---|
| 0xFFFFC154–C168 | Base Timing raw results A,B,C,D,E,F |
| 0xFFFFC16C / C170 / C174 | Blended timing (A·k+D·(1−k), etc.) |
| 0xFFFFC17C | Ignition AVCS-tracking blend factor k (0..1) |
| 0xFFFFC8C8 / C8CC | Measured intake AVCS angles, left / right |
| 0xFFFFC974 / C978 | Conditioned/commanded intake AVCS targets, left / right |
| 0xFFFFC984 | Common intake AVCS target selected from the current AVLS-mode map |
| 0xFFFFC180 | Timing-map select bits (0x80, 0x40) |
| 0xFFFFC184 | Selected base timing (deg) |
| 0xFFFFC150 / C188 | Final base timing after extra lookup |
| 0xFFFFCCC8–CCDC | Six per-cylinder correction floats; updated/cleared by the `ign_per_cylinder_correction_*` state path |
| **0xFFFFC0EC–C100** | **Six final per-cylinder ignition angles** produced by `ign_final_timing_per_cylinder_update`; consumed by minimum-check, schedule-count, current-cylinder, and logger paths |

The master rotational-idle component runs the stock final-timing task first and then, only
inside its calibrated idle window, post-processes the six `0xFFFFC0EC–C100` values in place. It
allocates no RAM and does not alter the stock correction array.

## AVLS (variable lift) (see notes §5)
| RAM addr | Meaning |
|---|---|
| 0xFFFFCD86 / CD87 | Cam mode committed / target (1=low, 3=high) |
| 0xFFFFCD94 / CD98 | Switchover-threshold caches (state-2 curve / state-3 curve) |
| 0xFFFFCD9C | AVLS operating state / curve selector (2=curve 1, 3=curve 2) |
| 0xFFFFCD9E | AVLS flags (mask 0x04 = hard-RPM high-cam latch; mask 0x10 = engine running) |
| 0xFFFFCD84 | Mode timer |
| 0xFFFFB46C | Conditioned accelerator pedal in percent compared to the oil-temperature-selected RPM-versus-pedal curve |
| 0xFFFFB124 | Converted engine-oil temperature in degrees C |
| 0xFFFFCF94 | Validated oil temperature, or stock 70 C fallback, used by the 13/15 and 113/115 C selector bands |
| 0xFFFFB528 | Phase/crank counter (OSV actuation sync) |

## Radiator fan and actual EVAP purge (see boost_repurpose_notes.md)
| RAM addr | Meaning |
|---|---|
| **0xFFFFCD54** | Stock radiator-fan request, percent; P92. The old purge/EBCS identity is retracted. |
| **0xFFFFB6D4** | Actual CPC purge-duty ratio; P38. Current master publishes zero. |
| **0xFFFFB6D8** | Actual modeled purge airflow; current master publishes zero. |
| **0xFFFFBE60 / BE64** | Bank purge-fuel subtraction terms; current master independently publishes zero. |

The earlier CD77/CD81/CD58/CD5C/B0F0/AB84 purge labels were based on the
misidentified fan subsystem. They must not be used to identify CPC hardware.
See the master audit for the verified `3FD8C -> E8C4` fan route and
`1BBFC -> B182` actual CPC route.

## Closed-loop / open-loop fuel (see notes §7, task #4)
| RAM addr | Meaning |
|---|---|
| 0xFFFFBE38 | CL/OL state flag byte (0x40 throttle-below-threshold, 0x20 base-pulse-below-threshold, both hysteretic; 0x80 closed-loop permitted by the primary target path; master pressure safety may clear only 0x80) |
| 0xFFFFBE2C / BE30 | CL/OL thresholds cached (throttle / BPW) |
| 0xFFFFBE14/16/18/1A/28 | CL/OL delay counters |
| 0xFFFFBE20 / BE24 / BE00 | Primary OL table A/B cached values and selected enrichment from 22454 |
| 0xFFFFBDFC / BE04 | Main and auxiliary primary OL ramp outputs; stock delay/eligibility gates remain |
| 0xFFFFBDF8 | Primary OL enrichment from 22454; normal branch max(BDFC, BE04) times BE0C times BE10. Added into both banks by final composer 1DD04 |
| 0xFFFFB874 | Signed transient load-change fuel correction, produced by 1E7E8 and added by 1DD04; E511. Its old after-start-only label was incorrect. |
| 0xFFFFB878 / B87C | Slowly followed load / signed current-minus-followed load used by transient fueling |
| 0xFFFFB880 | Signed fast load change from current B438 to the three-updates-old sample, with native limits/deadband |
| 0xFFFFB884 / B888 / B890 | Fast/slow transient terms and startup gain used to compose B874 |
| 0xFFFFB8B8..B8C4 | Four-sample conditioned-load history, updated by 1E7E8 once per 120 crank degrees in normal synchronized running |

The pressure wrapper clears permission after the stock target calculation; it
does not synthesize enrichment. See
[the execution audit](../master_patch/PRIMARY_FUEL_EXECUTION_AUDIT.md).
The signed load-change routine remains active after startup; see the
[transient/recovery audit](../master_patch/IDLE_RECOVERY_AUDIT.md).

## Oxygen sensors / current master patch
| RAM addr | Type | Meaning |
|---|---|---|
| 0xFFFFAB06 | u16 | Former MAF raw ADC, still refreshed by the hardware scan; current master external-wideband 0--5 V input and logger E501 |
| 0xFFFFAB18 / AB00 | u16 | Stock RH/LH front A/F raw channels; unused by the master feedback producer after both stock front sensors are disconnected |
| 0xFFFFAE60 / AE64 | float | Master synthetic lambda Bank 1 / Bank 2, both written from the same valid former-MAF external-wideband input |
| 0xFFFFAE68 / AE6C | float | Master pump-current placeholders, always 0.0 |
| 0xFFFFAE70 / AE74 | float | Master readiness: 50.0 valid, 0.0 invalid; both bank-inhibit helpers require greater than 35.0. Electronic boost actuator/guard is retired. |
| 0xFFFFB4E8 / B4EC | float | Retained stock conditioned front feedback/logger paths; both ultimately follow the same synthetic lambda in the master image |
| 0xFFFFAB20 / AB0C | u16 | Stock rear narrowband raw channels; master bypasses conversion and every traced rear monitor stage |
| 0xFFFFB098 / B09C | float | Master external-wideband logger mirrors E500 (same lambda when valid, 0.0 fault sentinel); no longer rear-O2 results in the master image |
| 0xFFFFABCC / ABD0 | float | Legacy front-O2 voltage channels from raw AB22/AB0E; stock conversion and some consumers remain. Distinct from external-wideband ADC AB06. |
| 0xFFFFD114 / D118 | float | Auxiliary bank fuel adders using legacy O2 voltage plus conditioned lambda; current master zeros both selectable constants so this publisher always produces zero. |
| 0xFFFFBC64 / BC68 | float | Legacy front-O2 voltage snapshots from ABCC/ABD0, copied by 1F0D8; not the external-wideband lambda. |
| 0xFFFFB900 / B904 | float | Legacy-voltage bank offsets from 20564, added to lambda targets and used by CEFC/CF00 correction. Current master makes both selectable values zero. |
| 0xFFFFBD20 / BD24 | float | Filtered legacy front-O2 voltages, still updated by 219C6 and used by the retained voltage loop. |
| 0xFFFFBD04 / BD08 | float | Separate voltage-loop trims from 21F0C, with stored 8200/8208 baseline when inactive. Current master excludes these reads from the lambda-target composer 202B8; diagnostic/learning paths remain. |
| 0xFFFFB8F4 / B8F8 | float | Per-bank lambda feedback targets from 202B8; main lambda feedback and other target terms remain after the scoped legacy-voltage repair. |
| 0xFFFFC85C | u16 | Master lean-cut delay/confirmation counter, reclaimed only after every traced rear-O2 runtime task is bypassed |
| 0xFFFFC860 | u8 | Master lean-cut state: 0 idle, 1 sensor delay, 2 AFR monitoring, 3 fuel-cut latched |
| 0xFFFFCF08 / CF09 / CF0A | u8 | Retained legacy-voltage diagnostic eligibility flags from 45350/453F2; CF08 can gate B91A. Their setting path requires CEFC/CF00 >=0.09, above the bounded normal current-calibration correction. They are not a blanket deleted subsystem. |

The older standalone single-front-A/F patch has different semantics and remains documented in
[single_front_af_patch.md](single_front_af_patch.md). For the current master image, use the logger
fragment and installation script in `master_patch`; never treat E500 = 0.0 as a real lambda.

## Injector scheduling and inhibit state
| RAM addr | Meaning |
|---|---|
| 0xFFFFBFB8 | Control-struct array base (6 × 0x28 = **spans 0xFFFFBFB8–0xFFFFC0A7**, channel idx @ +0x0C). Accessed by computed base+index, so per-field addresses (e.g. 0xFFFFBFF0/BFF8) show NO xref but ARE used — do not repurpose. |
| 0xFFFFB744 | Injector scheduler inhibit word (16-bit; bits 0..5 per channel, FFFF native global cut). Added overboost/lean cuts publish FFFF as well as BF6C bit80 under the native scheduler lock; old cam-solenoid identity is retracted. |
| 0xFFFFBF21 | Circuit-fault byte (bits 0x80..0x04 = ch0..5) |
| 0xFFFFD94C | Six channel inhibit-status bits read by 46EE0..46F3E; not a cam command |
| 0xFFFFC0A8 / C0AC | Injector scheduling sequence/counter state |
| 0xFFFFC0B0 | Injector output-activity byte; 26958 writes 1 |
| 0xFFFFC0B2 | Cached B744 word used by phase scheduler 263EE |

`26AEC` can defer a record's inhibit transition for a pulse already handed to
the timer. The record catches up at its native phase boundary. `26F8C` logs
the record's scheduled count times 0.25 when its inhibit byte is clear, not
the global B744 word or a measurement of physical on-time. See
[the scheduler audit](../master_patch/INJECTOR_SCHEDULER_EXECUTION_AUDIT.md).
