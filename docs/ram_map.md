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
| **0xFFFFABC4** | float | **Manifold pressure (MAP), eng. units** | `map_sensor_process` @0x7A14 output |
| 0xFFFFABC8 | — | MAP filtered/scaled intermediate | `map_sensor_process` |
| 0xFFFFAB04 | u16 | MAP raw ADC value | `map_sensor_process` input |
| **0xFFFFB3AC** | float | **Coolant temp (ECT), °C** | read by ~100 fns; purge/thermal input |
| 0xFFFFB3B8 | float | ECT-related threshold (purge enable) | `evap_purge_duty_compute` |

> Boost feedback for the WRX-style loop = **0xFFFFABC4**. Stock MAP sensor is ~1 bar; fitting
> the EJ255 (turbo) sensor + rescaling table 0x72810 makes this read positive boost.

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
| 0xFFFFCD94 / CD98 | Switchover-threshold caches (curve 1 / 2) |
| 0xFFFFCD9E | Hard-RPM hysteresis bits (bit4 = high-cam forced) |
| 0xFFFFCD84 | Mode timer |
| 0xFFFFCF94 | Load value compared to switchover curves |
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

## Solenoid output subsystem (cam AVCS/AVLS bank — see solenoid_subsystem.md)
| RAM addr | Meaning |
|---|---|
| 0xFFFFBFB8 | Control-struct array base (6 × 0x28 = **spans 0xFFFFBFB8–0xFFFFC0A7**, channel idx @ +0x0C). Accessed by computed base+index, so per-field addresses (e.g. 0xFFFFBFF0/BFF8) show NO xref but ARE used — do not repurpose. |
| 0xFFFFB744 | Solenoid inhibit/fault word (16-bit; bit n = channel n) |
| 0xFFFFBF21 | Circuit-fault byte (bits 0x80..0x04 = ch0..5) |
| 0xFFFFD94C | Solenoid command byte (bits read by fault thunks) |
| 0xFFFFC0A8 / C0AC / C0B0 | Solenoid init/global vars |
