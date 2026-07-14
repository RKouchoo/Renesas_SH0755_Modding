# D2WD610H RAM Variable Map

Consolidated reference of confirmed RAM variables (segment `0xFFFF0000–0xFFFFBFFF`, plus
actuator-state block up into `0xFFFFCxxx`). Addresses verified in the live Ghidra session
unless marked *(inferred)*. Cross-refs: [D2WD610H_RE_notes.md](D2WD610H_RE_notes.md),
[boost_repurpose_notes.md](boost_repurpose_notes.md).

## Engine core signals
| RAM addr | Type | Meaning | Evidence |
|---|---|---|---|
| **0xFFFFB544** | float | **Engine RPM** | compared vs 4000/3800/512/510; table input; ign+AVLS |
| 0xFFFFB538 | float | RPM-related raw (checked vs 10000/9000 band) | AVLS state machine |
| 0xFFFFB46C | float | engine param | AVLS state machine compare |
| **0xFFFFABC4** | float | **Manifold pressure (MAP), native mmHg absolute** | `map_sensor_voltage_to_pressure_process` @0x7A14 output; `MAP = voltage × scaling[1] + scaling[0]` |
| 0xFFFFABC8 | — | MAP filtered/scaled intermediate | `map_sensor_voltage_to_pressure_process` |
| 0xFFFFAB04 | u16 | MAP raw ADC value | `map_sensor_voltage_to_pressure_process` input |
| **0xFFFFB3AC** | float | **Coolant temp (ECT), °C** | read by ~100 fns; purge/thermal input |
| 0xFFFFB3B8 | float | ECT-related threshold (purge enable) | `evap_purge_duty_compute` |
| **0xFFFFB314** | float | **Processed throttle opening** | produced by `throttle_position_sensor_process` @0x14DCC; input to CL/OL throttle threshold and the boost-control demand gate |

> Boost feedback for the WRX-style loop = **0xFFFFABC4**. The patch replaces the stock
> `{-150.0, 250.0}` calibration at `0x72810` with the A2WC510N EJ255 donor calibration
> `{-414.0, 514.199951}`. Fit the matching sensor and validate the result against a reference;
> pressure remains native mmHg absolute in RAM even though the patch definition displays psi
> relative to its 760 mmHg sea-level reference.

## Ignition timing (see notes §4)
| RAM addr | Meaning |
|---|---|
| 0xFFFFC154–C168 | Base Timing raw results A,B,C,D,E,F |
| 0xFFFFC16C / C170 / C174 | Blended timing (A·k+D·(1−k), etc.) |
| 0xFFFFC17C | Ignition blend factor k (0..1) |
| 0xFFFFC974 / C978 | Advance-multiplier terms summed into k |
| 0xFFFFC180 | Timing-map select bits (0x80, 0x40) |
| 0xFFFFC184 | Selected base timing (deg) |
| 0xFFFFC150 / C188 | Final base timing after extra lookup |

## AVLS (variable lift) (see notes §5)
| RAM addr | Meaning |
|---|---|
| 0xFFFFCD86 / CD87 | Cam mode committed / target (1=low, 3=high) |
| 0xFFFFCD94 / CD98 | Switchover-threshold caches (state-2 curve / state-3 curve) |
| 0xFFFFCD9C | AVLS operating state / curve selector (2=curve 1, 3=curve 2) |
| 0xFFFFCD9E | AVLS flags (mask 0x04 = hard-RPM high-cam latch; mask 0x10 = engine running) |
| 0xFFFFCD84 | Mode timer |
| 0xFFFFB46C | Normal load signal compared to the state-selected switchover curve |
| 0xFFFFCF94 | Fallback load value compared to the fixed 15.0 threshold only |
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
| 0xFFFFBE38 | CL/OL state flag byte (0x40 throttle-above, 0x20 BPW-above, 0x80 delay) |
| 0xFFFFBE2C / BE30 | CL/OL thresholds cached (throttle / BPW) |
| 0xFFFFBE14/16/18/1A/28 | CL/OL delay counters |

## Oxygen sensors / single-front-A/F patch
| RAM addr | Type | Meaning |
|---|---|---|
| 0xFFFFAB18 / AB00 | u16 | Raw RH/Bank-1 and LH/Bank-2 front A/F channels; patch retains RH and mirrors its processed results into Bank 2 |
| 0xFFFFAE60 / AE64 | float | Scaled front lambda Bank 1 / Bank 2; patch copies AE60 -> AE64 after stock processing |
| 0xFFFFAE68 / AE6C | float | Front pump-current-like result Bank 1 / Bank 2; patch copies AE68 -> AE6C |
| 0xFFFFAE70 / AE74 | float | Front readiness/diagnostic metric Bank 1 / Bank 2; patch refreshes AE70 -> AE74 after both relevant stock tasks |
| 0xFFFFB4E8 / B4EC | float | Conditioned factory front-sensor values logged by RomRaider E91/E109; both follow the retained sensor after patching |
| 0xFFFFAB20 / B098 | u16 / float | Raw/processed RH rear narrowband; stock chain when patch is off, conversion/monitoring bypassed when the single-front patch is on |
| 0xFFFFAB0C / B09C | u16 / float | Raw/processed LH rear narrowband; stock chain when patch is off, conversion/monitoring bypassed when the single-front patch is on |

The patch publishes no external-wideband value into ECU RAM. Post-turbo lambda is recorded by a
separate logger and merged with the ECU log by timestamp. See
[single_front_af_patch.md](single_front_af_patch.md) for the patch and logging boundary.

## Solenoid output subsystem (cam AVCS/AVLS bank — see solenoid_subsystem.md)
| RAM addr | Meaning |
|---|---|
| 0xFFFFBFB8 | Control-struct array base (6 × 0x28 = **spans 0xFFFFBFB8–0xFFFFC0A7**, channel idx @ +0x0C). Accessed by computed base+index, so per-field addresses (e.g. 0xFFFFBFF0/BFF8) show NO xref but ARE used — do not repurpose. |
| 0xFFFFB744 | Solenoid inhibit/fault word (16-bit; bit n = channel n) |
| 0xFFFFBF21 | Circuit-fault byte (bits 0x80..0x04 = ch0..5) |
| 0xFFFFD94C | Solenoid command byte (bits read by fault thunks) |
| 0xFFFFC0A8 / C0AC / C0B0 | Solenoid init/global vars |
