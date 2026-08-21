# D2WD610H RAM Variable Map

Consolidated reference of confirmed RAM variables (segment `0xFFFF0000–0xFFFFBFFF`, plus
actuator-state block up into `0xFFFFCxxx`). Addresses verified in the live Ghidra session
unless marked *(inferred)*. Cross-refs: [D2WD610H_RE_notes.md](D2WD610H_RE_notes.md),
[boost_repurpose_notes.md](boost_repurpose_notes.md).

## Engine core signals
| RAM addr | Type | Meaning | Evidence |
|---|---|---|---|
| **0xFFFFB544** | float | **Engine RPM** | compared vs 4000/3800/512/510; table input; ign+AVLS |
| **0xFFFFB538** | float | **Vehicle speed, km/h** | `ign_idle_timing_target_update` compares it with the stock 4.0-km/h threshold at 0x77E1C; also consumed by AVLS logic |
| **0xFFFFB420** | float | **Final mass airflow, g/s** | stock final-airflow store; master speed density replaces its producer |
| **0xFFFFB428** | float | **Raw engine load, g/rev** | stock calculation is `B420 * 60 / B544` before conditioning |
| **0xFFFFB438** | float | **Conditioned engine load, g/rev** | load axis input for AVCS, ignition, fuel, and knock consumers |
| **0xFFFFB46C** | float | **Conditioned vehicle speed, km/h** | snapshot of B4C8 compared with the AVLS RPM-versus-speed boundary; not engine load |
| **0xFFFFB124** | float | **Engine-oil temperature, degrees C** | AB12 thermistor conversion through descriptor 0x60950; source for the AVLS selector |
| **0xFFFFCF94** | float | **Conditioned/fallback engine-oil temperature, degrees C** | valid B124 or stock 70 C fallback; selects AVLS cold/normal/hot state |
| **0xFFFFABC4** | float | **Manifold pressure (MAP), native mmHg absolute** | `map_sensor_voltage_to_pressure_process` @0x7A14 output; `MAP = voltage × scaling[1] + scaling[0]` |
| 0xFFFFABC8 | — | MAP filtered/scaled intermediate | `map_sensor_voltage_to_pressure_process` |
| 0xFFFFAB04 | u16 | MAP raw ADC value | `map_sensor_voltage_to_pressure_process` input |
| **0xFFFFB3AC** | float | **Coolant temp (ECT), °C** | read by ~100 fns; purge/thermal input |
| **0xFFFFB3B8** | float | **Intake-air temperature (IAT), °C** | written by `intake_air_temperature_update` @0x16D1C; input to stock MAF-IAT compensation and the speed-density density curve |
| **0xFFFFB314** | float | **Processed throttle opening** | produced by `throttle_position_sensor_process` @0x14DCC; input to CL/OL throttle threshold and the boost-control demand gate |

> Boost feedback for the WRX-style loop = **0xFFFFABC4**. The patch replaces the stock
> `{-150.0, 250.0}` calibration at `0x72810` with the A2WC510N EJ255 donor calibration
> `{-414.0, 514.199951}`. Fit the matching sensor and validate the result against a reference;
> pressure remains native mmHg absolute in RAM even though the patch definition displays psi
> relative to its 760 mmHg sea-level reference.

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

The standalone rotational-idle component runs the stock final-timing task first and then, only
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
| 0xFFFFB46C | Conditioned vehicle speed in km/h compared to the oil-temperature-selected RPM-versus-speed curve |
| 0xFFFFB124 | Converted engine-oil temperature in degrees C |
| 0xFFFFCF94 | Validated oil temperature, or stock 70 C fallback, used by the 13/15 and 113/115 C selector bands |
| 0xFFFFB528 | Phase/crank counter (OSV actuation sync) |

## EVAP purge / boost-patch target (see boost_repurpose_notes.md)
| RAM addr | Meaning |
|---|---|
| **0xFFFFCD54** | Purge duty %% (write target to drive the output) |
| 0xFFFFCD77 | Purge state machine (cases 0..7) |
| 0xFFFFCD81 | Purge status byte (bit 0x80 = enabled) |
| 0xFFFFCD58 / CD5C | Purge duty caches |
| 0xFFFFB0F0 | Purge duty count (16.16 fixed) |
| 0xFFFFAB84 | Purge PWM period (frequency) |

## Closed-loop / open-loop fuel (see notes §7, task #4)
| RAM addr | Meaning |
|---|---|
| 0xFFFFBE38 | CL/OL state flag byte (0x40 throttle-above, 0x20 BPW-above, 0x80 closed-loop permitted by the primary target path; master pressure safety may clear only 0x80) |
| 0xFFFFBE2C / BE30 | CL/OL thresholds cached (throttle / BPW) |
| 0xFFFFBE14/16/18/1A/28 | CL/OL delay counters |

## Oxygen sensors / current master patch
| RAM addr | Type | Meaning |
|---|---|---|
| 0xFFFFAB06 | u16 | Former MAF raw ADC, still refreshed by the hardware scan; current master external-wideband 0--5 V input and logger E501 |
| 0xFFFFAB18 / AB00 | u16 | Stock RH/LH front A/F raw channels; unused by the master feedback producer after both stock front sensors are disconnected |
| 0xFFFFAE60 / AE64 | float | Master synthetic lambda Bank 1 / Bank 2, both written from the same valid former-MAF external-wideband input |
| 0xFFFFAE68 / AE6C | float | Master pump-current placeholders, always 0.0 |
| 0xFFFFAE70 / AE74 | float | Master readiness: 50.0 valid, 0.0 invalid; both bank-inhibit helpers require greater than 35.0, and this is one prerequisite of the wider EBCS sensor/SD gate |
| 0xFFFFB4E8 / B4EC | float | Retained stock conditioned front feedback/logger paths; both ultimately follow the same synthetic lambda in the master image |
| 0xFFFFAB20 / AB0C | u16 | Stock rear narrowband raw channels; master bypasses conversion and every traced rear monitor stage |
| 0xFFFFB098 / B09C | float | Master external-wideband logger mirrors E500 (same lambda when valid, 0.0 fault sentinel); no longer rear-O2 results in the master image |
| 0xFFFFC85C | u16 | Master lean-cut delay/confirmation counter, reclaimed only after every traced rear-O2 runtime task is bypassed |
| 0xFFFFC860 | u8 | Master lean-cut state: 0 idle, 1 sensor delay, 2 AFR monitoring, 3 fuel-cut latched |

The older standalone single-front-A/F patch has different semantics and remains documented in
[single_front_af_patch.md](single_front_af_patch.md). For the current master image, use the logger
fragment and installation script in `master_patch`; never treat E500 = 0.0 as a real lambda.

## Solenoid output subsystem (cam AVCS/AVLS bank — see solenoid_subsystem.md)
| RAM addr | Meaning |
|---|---|
| 0xFFFFBFB8 | Control-struct array base (6 × 0x28 = **spans 0xFFFFBFB8–0xFFFFC0A7**, channel idx @ +0x0C). Accessed by computed base+index, so per-field addresses (e.g. 0xFFFFBFF0/BFF8) show NO xref but ARE used — do not repurpose. |
| 0xFFFFB744 | Solenoid inhibit/fault word (16-bit; bit n = channel n) |
| 0xFFFFBF21 | Circuit-fault byte (bits 0x80..0x04 = ch0..5) |
| 0xFFFFD94C | Solenoid command byte (bits read by fault thunks) |
| 0xFFFFC0A8 / C0AC / C0B0 | Solenoid init/global vars |
