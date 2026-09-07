# D2WD610H master-patch Ghidra audit

> **Repair implemented — 2026-09-08:** the current `5a1b3e...` development image
> restores stock radiator-fan control and deletes actual CPC output/purge fuel
> subtraction. Previous images overriding fan PWM remain quarantined, including
> `0600d73a...`. Passing tests does not establish a lean-out cure or physical
> validation. See the repair and idle-timing clarification at the end of this
> file; earlier purge-output identification and EBCS safety claims are retracted.
> The [retained-routine follow-up](RETAINED_ROUTINE_AUDIT.md) additionally
> neutralizes factory lambda atmospheric correction, auxiliary adders, and two
> feedback-target contributions dependent on removed stock O2 voltage channels.
> No lean-out cure is claimed.

## Result

The master image is structurally consistent with the canonical stock ROM and
passes the deterministic verifier. The result remains firmware-development
quality: no bench ECU, harness, running engine, or dyno validation has been
performed by this repository.

The live Ghidra project was checked against root `2005 BLE MT.bin` SHA-256
`ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
Every function opened during this pass was assigned a project-convention name.
`ghidra_scripts/ApplyMasterNames.java` makes those names and evidence comments
reproducible without importing a modified ROM into the stock analysis project.

## Functions checked and named

| Address | Ghidra name | Evidence used |
|---:|---|---|
| `0x2458` | `float_divide_guarded` | Guarded floating-point divide used by the AVCS tracking-ratio calculation. |
| `0x24C0` | `float_clamp` | Bounds the calculated tracking ratio to 0..1. |
| `0x24B0` | `float_minimum_select` | Returns the lower float; named while tracing AVLS threshold conditioning. |
| `0x24FC` | `float_difference_exceeds_tolerance` | Near-zero/tolerance test used by AVCS target and tracking logic. |
| `0x26E0` | `axis_index_search_float` | Rechecked for Primary Open Loop indexing: inputs below the first breakpoint return index 0. |
| `0x27088` | `constant_zero_return` | Exact `rts; mov #0,r0`; makes timing B/E selector branch dormant. |
| `0x6504C` | `runtime_status_d26d_bit5_get` | Timing selector status input. |
| `0x28354` | `ign_avcs_tracking_blend_factor_update` | Builds and clamps the measured/commanded intake-AVCS tracking factor `k` at `0xFFFFC17C`. |
| `0x28418` | `ign_base_timing_map_blend` | Looks up/blends all base-timing endpoints. |
| `0x284B8` | `ign_base_timing_select` | A/D normal-cam, C/F AVLS-high-cam selection; B/E requires the constant-zero callback. |
| `0x353B0` | `intake_avcs_target_by_avls_mode_update` | Selects AVCS A in committed low-lift mode and AVCS B in high-lift mode. |
| `0x35750` | `intake_avcs_tracking_control_update` | Downstream per-bank AVCS target/tracking control. |
| `0x3EB68` | `knock_correction_advance_max_select` | KCA A normal-cam versus B AVLS-high-cam selection. |
| `0x3FFDA` | `avls_threshold_curve_selector_state_update` | Publishes internal AVLS curve-selector state 1/2/3. |
| `0x400EE` | `avls_curve_selector_oil_temp_band_latches_update` | Builds engine-oil-temperature selector latches at 13/15 and 113/115 degrees C. |
| `0x40168` | `avls_cam_mode_state_machine` | Compares conditioned vehicle speed with the oil-temperature-selected RPM-versus-speed boundary. |
| `0x3FDBC` | `avls_control_sequence_update` | Runs AVLS request selection/state machine, committed-mode copy, then OSV actuation. |
| `0x405B2` | `avls_mode_commit_copy` | Copies requested mode `0xFFFFCD87` to committed mode `0xFFFFCD86`. |
| `0x405CC` | `avls_osv_actuation_gate` | Retained stock status/timing gate for lift-solenoid actuation. |
| `0xF474` | `engine_oil_temperature_sensor_process` | Converts ADC AB12 through descriptor 0x60950 to B124 in degrees C. |
| `0x3253C` | `engine_oil_temperature_logger_convert` | Logger conversion entry for B124. |
| `0x47000` | `engine_oil_temperature_fallback_select` | Publishes valid B124 or the stock 70 C fallback to CF94. |
| `0x17984` | `airflow_load_and_vehicle_speed_processing_sequence_update` | Orchestrates the distinct load and vehicle-speed chains. |
| `0x179EE` | `airflow_load_filter_state_initialize` | Initializes airflow/load filter state. |
| `0x17A24` | `airflow_load_filter_state_requires_initialization` | Checks that filter state before the processing sequence. |
| `0x18438` | `vehicle_speed_conditioning_status_flags_update` | Status input for the speed conditioner. |
| `0x184CC` | `vehicle_speed_conditioning_coefficient_set_a_update` | Produces B4A4/B4A8/B4AC coefficients. |
| `0x1873C` | `vehicle_speed_conditioning_coefficient_set_b_update` | Produces B4B0/B4B4/B4B8 coefficients. |
| `0x188F4` | `vehicle_speed_conditioned_source_update` | Conditions B538 km/h into B4C0 and caps it at 100.0. |
| `0x18A68` | `vehicle_speed_conditioned_filter_update` | Filters B4C0 into B4C8 without changing units. |
| `0x18AEA` | `vehicle_speed_conditioned_snapshot_copy` | Copies B4C8 to AVLS compare signal B46C. |
| `0x7A14` | `map_sensor_voltage_to_pressure_process` | `MAP = voltage*multiplier + offset`; writes native absolute mmHg to `0xFFFFABC4`. |
| `0x7A56` | `map_sensor_raw_adc_range_classify` | Raw `0xFFFFABC8` compared with thresholds at `0x7B284/0x7B286`. |
| `0x78AC` | `analog_sensor_abac_range_classify` | Neighboring analog range path separated from MAP. |
| `0x79B4` | `analog_sensor_abbc_range_classify` | Neighboring analog range path separated from MAP. |
| `0x98CC` | `injector_battery_voltage_latency_lookup` | Injector voltage-axis/deadtime descriptor path. |
| `0x1E0C8` | `injector_flow_scaling_factor_update` | Reads D2WD injector scalar at `0x76014`. |
| `0x11958` | `crank_synchronous_engine_output_task` | Schedules the injection, ignition, cam-solenoid and AVLS output updates. |
| `0x26208` | `crank_output_mode_update_gate` | Gates the adjacent crank-output mode selector from runtime byte `0xFFFFBFB6`. |
| `0x26256` | `crank_output_mode_select` | Selects and publishes the retained crank-output mode used ahead of injection scheduling. |
| `0x26F8C` | `injector_scheduled_pulse_width_channels_publish` | Publishes scheduled pulse widths at `0xFFFFC0B8` onward and latency at `0xFFFFC0D8`; forms latency-inclusive outputs at `0xFFFFC0D0/C0D4`. |
| `0x1ADD8` | `runtime_status_b6b8_bit7_is_set` | Common runtime/reset-condition predicate used by after-start fuel and other state updates. |
| `0xA9A8` | `injector_control_lookup_sequence_a9a8` | Supporting injector lookup sequence. |
| `0xB690` | `front_af_sensor_pair_signal_process` | Original paired-front conversion entry replaced by the external-wideband hook. |
| `0x192A8` | `front_af_sensor_pump_current_pair_offset_clamp_update` | Obsolete front pump-current diagnostic path. |
| `0x18DAC` | `front_af_sensor_lambda_condition_filter` | Conditions lambda for stock closed-loop consumers. |
| `0x18FDC` | `front_af_sensor_closed_loop_status_pair_update` | Updates the paired front-feedback status consumed by closed-loop logic. |
| `0x1BE8E` | `fuel_trim_state_initialize` | Initializes retained fuel-trim controller state. |
| `0x1DD04` | `final_fueling_multiplier_compose` | Combines short-term and learned trim inputs into final fueling. |
| `0x1EE74` | `closed_loop_fuel_control_bank_update` | Confirms bank feedback/readiness consumption. |
| `0x1F1DC` | `closed_loop_short_term_correction_publish` | Publishes/resets per-bank short-term correction state. |
| `0x1FB16` | `closed_loop_lambda_delay_coefficients_update` | Builds the stock 21-element lambda response/delay vector. |
| `0x1FCD4` | `closed_loop_lambda_delay_filter_update` | Applies the 21-sample feedback history against the target lambda. |
| `0x20326` | `closed_loop_bank_feedback_correction_update` | Updates the retained per-bank feedback correction. |
| `0x2104E` | `closed_loop_bank_trim_state_update` | Updates the long-term closed-loop trim state. |
| `0x13330` | `runtime_status_b6c0_bit7_is_set` | Supporting front-feedback gate. |
| `0x1D228` | `runtime_status_b748_bit7_is_set` | Supporting front-feedback gate. |
| `0x1884` | `diagnostic_request_download_handle` | Named while separating diagnostic infrastructure from sensor tasks. |

Existing project names used by the integrated components include
`maf_airflow_temperature_compensation_update` (`0x172A4`),
`radiator_fan_duty_compute` (`0x3FC0A`),
`radiator_fan_pwm_output_write` (`0xE8C4`),
`rev_limiter_fuel_cut` (`0x24B24`), and
`fuel_cut_flag_aggregate` (`0x23FC0`).

## Firmware decisions confirmed

### Timing

The stock selection/blend path references all six legacy base maps. For the
normal/AVLS-low-cam path, address `0x78AA0` is the AVCS-tracking-ratio-1.0
endpoint and `0x78E34` is the ratio-0.0 endpoint. For AVLS high cam, `0x78CD0`
is the ratio-1.0 endpoint and `0x79064` is the ratio-0.0 endpoint.
`ign_base_timing_map_blend` calculates `ratio_1.0*k + ratio_0.0*(1-k)` using the
factor published at `0xFFFFC17C` by
`ign_avcs_tracking_blend_factor_update`.

The factor is not IAM. The code sums conditioned/commanded left and right AVCS
targets at `0xFFFFC974/0xFFFFC978`, sums measured left and right intake-cam
angles at `0xFFFFC8C8/0xFFFFC8CC`, divides measured by commanded, and clamps the
result to 0..1. A near-zero commanded sum produces zero, while verified stock
status paths can force one. These are cam-phasing endpoints; neither surface has
a universal requirement to be more advanced or retarded than its partner.

The two remaining legacy maps require a callback at `0x27088` to return one,
but that function always returns zero in canonical D2WD610H. They are still
conservatively calibrated in the binary but removed from the focused tuning
definition. The two KCA surfaces select normal cam versus AVLS high cam.

### AVCS target A/B meaning

`intake_avcs_target_by_avls_mode_update` is the direct consumer of both target
descriptors. Committed AVLS cam mode `0xFFFFCD86 == 1` selects descriptor
`0x60C34`, data `0x7C5B0` (legacy AVCS A). Mode `3` selects descriptor `0x60C50`,
data `0x7C764` (legacy AVCS B). Therefore A is the intake AVCS target for AVLS
low lift and B is the target for AVLS high lift. They are not left/right-bank
maps and are selected by lift state rather than blended with one another.

Both maps share a 14-point 0.35..2.00 g/rev load axis. A has 11 RPM rows from
500 through 4000 RPM; B has 18 rows from 1000 through 6800 RPM. The native
lookup clamps above the final axis breakpoint, so loads above 2.00 g/rev use the
last column unless the existing axis is rescaled. The master calibration
resamples those existing columns onto a 0.35..4.00 g/rev axis and preserves the
same final-column target above the stock 2.00 g/rev limit.

### How AVLS chooses low or high lift

AVLS makes the lift decision before AVCS A/B selection. In the master baseline,
the high-lift engage threshold is 3200 RPM, the release threshold is 3000 RPM,
and the actuation minimum is 3000 RPM. Both RPM-indexed speed boundaries and
both fixed/fallback thresholds are calibrated to 110 km/h. The conditioned
speed source is capped at 100 km/h by `vehicle_speed_conditioned_source_update`,
so the old vehicle-speed request route is unreachable. The requested mode is
written at `0xFFFFCD87`; `avls_control_sequence_update` then calls
`avls_mode_commit_copy` before the retained OSV actuation gate. The dual-VE
wrapper selects from committed mode `0xFFFFCD86`, not the earlier request.

The two switchover curves are not engage/release maps. Internal selector state
`0xFFFFCD9C == 2` uses the normal-oil-temperature curve and state 3 uses the
high-oil-temperature curve. ADC AB12 is converted through descriptor `0x60950`
(axis `0x7B748`, data `0x7B7C4`) to engine-oil temperature `0xFFFFB124` in
degrees C. `engine_oil_temperature_fallback_select` publishes that value or a
70 C fail-safe to `0xFFFFCF94`. The selector uses 13/15 and 113/115 C hysteretic
bands, plus runtime/delay gates, to choose cold/fallback state 1, normal state 2,
or hot state 3.

The stock oil-temperature selector and speed-state machinery therefore still
executes, but cannot cause a high-lift request in this calibration. It is omitted
from the focused master definition to avoid exposing controls that no longer
affect the chosen lift policy.

This is separate from genuine engine load. The retained stock airflow task
writes mass airflow `0xFFFFB420` in g/s, calculates raw load `0xFFFFB428` as
`airflow_g_s * 60 / RPM`, and conditions it into `0xFFFFB438` in g/rev. AVCS,
ignition, fuel, and knock tables use B438. The speed-density component supplies
B420 in g/s and preserves that normalization, so calculated-load scaling remains
correct even though load does not select AVLS lift mode.

### MAP and injectors

`0x7A14` consumes the two floats at `0x72810` in offset/multiplier order and
writes native mmHg absolute MAP. The raw diagnostic thresholds are separate at
`0x7B284/0x7B286`. Injector latency uses the descriptor at `0x608D8`, voltage
axis at `0x7B304`, and data at `0x7B318`; injector flow processing reads
`0x76014`. These are the locations used by the builder and definition.

The injector profile was re-audited against both the raw donor and the upstream
RomRaider definitions. `injector_flow_scaling_factor_update @ 0x1E0C8` consumes
the scalar at `0x76014`; a lower raw scalar commands the expected shorter base
pulse for a larger injector. `injector_battery_voltage_latency_lookup @ 0x98CC`
uses the five-point voltage/latency descriptor. The SHA-pinned 2003 JDM STI
`A4TE002B` donor decodes to 552.47 cc/min and
`2.788, 1.488, 0.980, 0.684, 0.380 ms` at
`6.5, 9.0, 11.5, 14.0, 16.5 V`. Its four per-injector offsets at
`0x29032..0x29038` are neutral, and its `0x2902E` thresholds disable those
offsets once running. This establishes that those particular offsets are
inactive; it does not exclude unidentified short-pulse/minimum-duration logic.

The generic description "pink 565" is not a unique calibration identity. The
installed marking was subsequently identified as Subaru `16611AA510`; catalog
application data places it on the same early JDM STI generation as A4TE002B and
cross-references Denso `195500-3910`. The donor-ROM profile is therefore
retained as the best factory match. All six injectors must still carry the same
marking, and copied, modified, or remanufactured sets require measured data. No
injector calibration bytes were changed by this identification audit.

### MAFless airflow and AVLS VE selection

The single speed-density component replaces the final airflow helper called
inside the retained stock airflow/load task and contains the committed-state
selector directly: mode 3 uses a 13x11 high-lift surface covering
3000..7500 RPM; all other modes use a 13x9 low-lift surface covering 0..3200
RPM. The 3000..3200 overlap represents the real hysteresis region and is resolved
by committed state. Both tables are initially resampled from the same seed.

The two raw MAF conversions, the
raw MAF limit update, high/low diagnostic task, and MAF-dependent temperature
condition are bypassed. The shared ADC scan remains, so former-MAF ADC RAM
`0xFFFFAB06` continues updating even though no airflow calculation consumes it.

### One external wideband replacing four stock paths

The hook at original front-pair entry `0xB690` converts unsigned AB06 ADC counts
to volts and the configured external-wideband lambda, then writes both bank
lambda/readiness paths. Both
closed-loop inhibit helpers at `0x64FD0/0x6500C` are redirected to the common
readiness test. The front pump diagnostic task pointer at `0x6A6C` is moved to
the stock return stub.

The rear conversion entry at `0xE0D0` and five rear monitor-task pointers at
`0x11488..0x114A0` are bypassed. Eighteen mapped front/rear O2 DTC switches are
cleared. Static xrefs show the old rear `B098/B09C` results feed rear monitoring
and logging, not a direct fuel consumer; the patch safely reuses them only as
logger mirrors.

The master prerequisite guard at `0x7E560` now owns the boost output tail call.
It tail-calls the stock PWM writer with zero duty unless wideband readiness is
valid, MAP/RPM/IAT are inside their SD windows, RPM is at least the first boost
axis breakpoint, and final modeled airflow is finite and not the 500 g/s fault
sentinel. Only a fully valid state tail-calls the existing boost controller.

### Integrated rotational idle

Task pointer `0x11E30` originally calls
`ign_final_timing_per_cylinder_update` at `0x279CC`. That stock routine produces
six final ignition angles at `0xFFFFC0EC..0xFFFFC100`. The integrated wrapper at
`0x7DB90` calls the complete stock routine first and returns unchanged unless
the exact-`01` enable and every warm/stationary/closed-throttle/high-vacuum gate
passes. It modifies those six final values in place without persistent RAM.

Positive offsets are clamped to zero, negative offsets are limited by Maximum
Retard, the result is floored by Minimum Final Timing, and a final original-angle
ceiling prevents either the floor or malformed calibration from adding advance.
Master defaults the switch to `00`; the focused definition exposes the switch,
ten gates/limits, and six offsets. This hook and flash range are disjoint from
all boost, speed-density, wideband, fueling-safety, calibration, and RAM state.

## Injected layout

| Region | Use |
|---:|---|
| `0x7D790..0x7D91F` | Existing boost component and master signatures. |
| `0x7DB40..0x7DCEB` | Integrated default-OFF rotational-idle calibration and wrapper. |
| `0x7DCF0..0x7E18B` | Existing speed-density calibration and support data. |
| `0x7E18C..0x7E3B3` | Committed-state dual-VE speed-density wrapper. |
| `0x7E400..0x7E41B` | Wideband constants. |
| `0x7E440..0x7E51B` | Wideband update routine. |
| `0x7E520..0x7E53B` | Closed-loop inhibit helper. |
| `0x7E560..0x7E63F` | Wideband/SD-input/result boost prerequisite guard. |
| `0x7E640..0x7E667` | Low/high VE descriptors. |
| `0x7E668..0x7E6B7` | Low 0..3200 and high 3000..7500 RPM axes. |
| `0x7E6B8..0x7EAC7` | Low 13x9 and high 13x11 VE surfaces. |
| `0x7EAC8..0x7EAEB` | Pressure/open-loop and lean-cut switches/calibration. |
| `0x7EB20..0x7EB9B` | Pressure-forced-open-loop wrapper. |
| `0x7EBA0..0x7EBB7` | Explicit lean-state zero initializer. |
| `0x7EC00..0x7EDE7` | Composed latched-lean-cut wrapper. |

The verifier rejects overlap, writes outside declared stock hooks/calibration
regions, unknown injected opcodes, stale generated XML, unexpected logger RAM
addresses, stock/SRF provenance drift, and checksum failure.

The spring-pressure revision separates the former combined boost switch into
`Electronic Boost Control Enable` at `0x7D80C` (default `00`) and `Overboost
Fuel Cut Enable` at `0x7D80D` (default `01`). Live Ghidra reconfirmed the named
stock endpoints `evap_purge_pwm_output_write` at `0xE8C4`,
`rev_limiter_fuel_cut` at `0x24B24`, and `fuel_cut_flag_aggregate` at `0x23FC0`.
The component and master verifiers independently pin both exact-`01` branches,
their literal addresses, the zero-duty path, and the `0x80` fuel-cut flag write.

The Primary Open Loop RPM-axis correction was also checked against the stock
lookup behavior. `axis_index_search_float` at `0x26E0` was already meaningfully
named and its decompilation confirms that a value below the first breakpoint
selects index 0. Stock axes A/B at `0x77754`/`0x77840` therefore held their
3200-RPM row below 3200 RPM. The master builder now writes both axes as
`1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000, 6800` RPM and
conservatively resamples the complete original bank surfaces onto those points
before applying high-load caps. Descriptor sizes and table storage do not move.

## Pressure-based open-loop and lean-cut trace

Live canonical-stock Ghidra inspection identified and renamed these additional
functions while designing the safety component:

- `engine_control_periodic_task_dispatch` at `0x10A28`;
- `primary_open_loop_fueling_target_update` at `0x22454`;
- `cl_ol_transition_delay_update` at `0x22756`;
- `cl_ol_delay_condition_and_counter_update` at `0x22948`;
- `cl_ol_transition_state_update` at `0x22AAE`;
- `cl_ol_transition_state_initialize` at `0x22AC2`;
- `fueling_state_flag_clear_on_condition` at `0x2331E`;
- `fuel_cut_flag_aggregate` at `0x23FC0`;
- `rev_limiter_fuel_cut` at `0x24B24`; and
- `atmospheric_pressure_source_select_update` at `0x47DB2`.

The primary target routine uses RPM `0xFFFFB544`, conditioned load
`0xFFFFB438`, and Primary Open Loop descriptors `0x5FA9C/0x5FAB8`. It publishes
through `0xFFFFBE20/BE24/BE00`. Its read/modify/write of `0xFFFFBE38` establishes
bit `0x80` as closed-loop permission for this path: sufficiently enriched
open-loop targeting clears the bit; closed-loop-eligible targeting sets it. The
new wrapper occupies task pointer slot `0x11D78`, calls the entire stock routine
first, and may only clear bit `0x80` afterward. It does not synthesize a fuel
target or replace the stock CL/OL state machine.

`cl_ol_delay_condition_and_counter_update` reads `0xFFFFCFBC` and passes it to
descriptor `0x5F8FC`, whose axis/data are the mapped CL Delay Atmospheric
Pressure table at `0x772D4/0x772DC`. The writer at `0x47DB2` selects the live
source from `0xFFFF8E04` or `0xFFFFB3A8`. Follow-up tracing confirms that the
stock/master selector byte `0x737D9 = 0` chooses the stored MAP-based estimate
at `0xFFFF8E04`, not the alternate conditioned sensor channel at `0xFFFFB3A8`.
Thus `0xFFFFCFBC` is the ECU's selected native-mmHg barometric estimate, not
proof of an independent atmospheric-pressure measurement.

### Atmospheric-pressure source and logger follow-up (2026-09-07)

P24's SSM address `0x23` resolves through slot `0x4B788` to handler `0x317EC`.
The handler shares selector `0x737D9`; zero reads `0xFFFF8E04`, while nonzero
would read raw alternate sensor state `0xFFFFABE8`. Conversion helper `0x258C`
divides by `7.50063467`, adds 0.5 and truncates/clamps to a byte, i.e. whole
kPa. The logger's `x*7.5` mmHg conversion therefore displays 720 when the ECU
returns 96 kPa. A flat 720 trace is a quantized estimate, not an exact sensor
measurement or the manifold-pressure input used by the VE table.

`atmospheric_pressure_estimate_update @ 0x47DCC` maintains `0xFFFF8E04`:

- Its fallback status can select 760 mmHg.
- Flag `0xFFFFCFD0` bit `0x80` samples native MAP `0xFFFFABC4`.
- Bit `0x40` allows a filtered update from processed MAP `0xFFFFB2A0` plus
  pressure-loss compensation `0xFFFFCFC4`.
- Bit `0x20` adds 2.5 mmHg; with none of those flags it holds its prior value.
- It clamps the result to the stock 570..770-mmHg limits before writing the
  protected stored state. The separate initializer at `0x47D6A` seeds 760.

The sample gate at `0x47EA6` and running-learning gate at `0x47F84` were named
in live Ghidra, along with the initializer/status helpers, alternate sensor
conditioning at `0x16ACC`, fallback helper `0x64FBC`, sample-trigger helper
`0x312E0`, and conversion helper `0x258C`. The previously undefined P24 entry
was inspected from stock bytes and labeled; `ApplyMasterNames.java` now also
creates/names its function. The entire reviewed estimator/selector block,
sensor conditioner, logger handler and source selector are unchanged in the
master ROM. No physical separate barometer is inferred from another model's
wiring diagram. The modified engine's running-learning assumptions are not
validated by this static trace. SD uses actual native MAP `0xFFFFABC4` as its
pressure input, while the pressure-based fuel guards use the selected baro.

The lean wrapper repoints the already-composed task slot at `0x11D3C`. It first
calls the existing boost component wrapper at `0x7D8C4`, which itself calls the
stock limiter at `0x24B24`; only then can it set `0xFFFFBF6C` bit `0x80` for a
lean trip. `fuel_cut_flag_aggregate` consumes that bit. The trip state is latched
until MAP falls below the barometrically referenced reset, so the AFR value made
lean by fuel cut cannot chatter the cut on and off.

Persistent state uses retired rear-O2 response-integrator RAM `0xFFFFC85C` and
`0xFFFFC860`. Their traced runtime updater/reader task pointers at `0x11490` and
`0x11494`, plus the other rear-O2 tasks, are already redirected to the stock
return stub by the mandatory master wideband component. Stock initializer
`rear_o2_sensor_response_integrator_initialize` at `0x33964` writes float 1.0,
so task pointer `0x1055C` is repointed to an explicit zero initializer at
`0x7EBA0`. Installation is refused unless all pointer guards pass.

## Unresolved physical risks

- AB06 is proven as the continuing former-MAF ADC channel in firmware, but its
  allowable source impedance, protection behavior, and real harness voltage
  offset still require bench measurement.
- The supplied 50-4110-style four-wire controller is single-ended: white is the
  only analog signal and black carries controller/heater return current. Its
  warm-up and disconnected-sensor output may remain inside the firmware's
  plausibility window, so readiness is not a hardware-health indication.
- The four stock heater drivers remain electrically active even though their
  sensor tasks and mapped DTCs are removed.
- A single post-turbo sensor cannot detect per-bank mixture imbalance and adds
  exhaust transport delay to the stock closed-loop algorithm.
- No single physical purge/EBCS terminal is asserted for every market harness;
  continuity and scope tests are still required.
- MAP transfer, injector behavior, PWM frequency/polarity, fuel pressure,
  modeled VE, timing, boost creep, and protection response all remain physical
  commissioning items.

## Closed-loop lean-out investigation (2026-09-03)

The current master wideband hook publishes its converted value to both stock
front-bank lambda words and forces their ready metric to 50 whenever the former
MAF input is between 0.50 and 4.50 V. This preserves the stock per-bank
closed-loop controller, but does not preserve its original sensor location or
dynamics: the AEM sensor is post-turbo, while the original feedback was
pre-turbo.

Live canonical-stock disassembly confirms that
`closed_loop_lambda_delay_coefficients_update` builds a 21-element response
vector and `closed_loop_lambda_delay_filter_update` shifts a 21-sample history
using conditioned lambda `0xFFFFB4E8/0xFFFFB4EC` and target lambda
`0xFFFFB8F4/0xFFFFB8F8`. Neither routine nor its response calibrations is
changed by master_patch. The additional exhaust volume and turbine delay are
therefore unmodelled and may cause feedback hunting or overshoot. The final
fueling path also consumes short-term corrections at `0xFFFFB8D4/B8D8` and
learned trims at `0xFFFFBCB8/BCBC`; learned trim can carry a bad feedback result
into later open-loop operation.

The originally supplied `../logs/romraiderlog_20260903_022932.csv` is an
engine-off/invalid capture. The later
`../logs/romraiderlog_20260903_023334.csv` contains the actual start and rules out
closed-loop feedback as the cause of this particular lean-out. Engine speed
first becomes nonzero at 5.009 seconds. External-wideband readiness becomes
50 at 11.062 seconds, initially at 17.11 AFR, and CL/OL status remains 7 for
every running sample. The logger definition identifies status 7 as open loop
due to insufficient coolant temperature; coolant remains 31--32 C.

The measured AFR reaches roughly 14.5 at 15.4 seconds, spends approximately
15.4--31.5 seconds between about 14.5 and 15.6, then trends through 16.1 at
31.8 seconds and 18.6 at 35.8 seconds. At 36.153 seconds the ADC exceeds the
4.50-V acceptance limit and the patch correctly publishes zero AFR/readiness.
RPM remains approximately 1300 and modeled airflow/load remain approximately
10.7 g/s and 0.49--0.50 g/rev during the final lean trend. Battery voltage is
stable around 14.3 V, coolant is stable, and indicated IAT falls from 5 to 3 C.
The ECU and gauge transfer agree with the raw ADC, so this is not a closed-loop
command or an ECU-side AFR-conversion error.

The observed timing is strongly compatible with after-start enrichment decaying
and revealing an under-fuelled base VE/deadtime/fuel-pressure condition. At
18.6 AFR versus a 14.7 target, approximately 27 percent more delivered fuel
would be required if combustion and the wideband reading are valid. Do not
blindly add that amount to VE: a fuel-pump duty transition, falling rail
pressure, injector latency error, exhaust leak, or misfire can produce the same
trace. The false cold IAT indication is not a mechanism for the lean-out because
the SD density model adds modeled air and fuel as indicated IAT falls.

Do not run under load. The white-wire isolation test is no longer needed for
this event because the ECU remained open loop throughout it. Check mechanical
rail pressure from prime through at least 40 seconds and compare it with logged
fuel-pump duty. A new minimal log must include RPM, MAP, IAT, modeled
airflow/load, injector pulse width and latency, battery voltage, fuel-pump duty,
wideband AFR/raw/ready, primary and final fueling multipliers, both short-term
corrections, both learned trims, roughness/misfire counters, and CL/OL status.

The retained post-turbo closed-loop architecture remains an independent design
risk once the engine warms, but it did not cause this cold, open-loop event.
Resolve the open-loop delivered-fuel error first. A dedicated feedback
controller would still require its own transport-delay and gain calibration;
treating the downpipe signal as a drop-in front-sensor replacement is not
considered verified.

## Static idle-fueling diagnosis (2026-09-06)

The causal interpretation below is superseded by the 2026-09-07 reassessment
after the second correction. The available captures do not establish settled
AFR or prove that after-start decay, rather than another fuel factor, accounts
for the observed pulse-width fall.

This follow-up treats the log only as a timestamp and operating-point locator.
The ROM and generated tune contain enough evidence to identify the tune-side
failure mode: stock after-start enrichment is temporarily masking an
under-fuelled steady-state speed-density/injector model.

The MAFless wrapper's equation was checked again against the retained stock
airflow task in Ghidra. The wrapper calculates grams per second from absolute
MAP, RPM, 2.999-litre displacement, charge-temperature density and VE. The
stock task then calculates raw load exactly once as `airflow_g_s * 60 / RPM`.
There is no extra cylinder factor, duplicate displacement term, or second load
normalization. The boost, wideband and pressure/lean-safety components also
have no vacuum-idle branch that subtracts fuel. Electronic wastegate control is
disabled in the master calibration.

At the observed 1,300 RPM, 0.49--0.50 g/rev and 3--5 C indicated IAT, solving
the exact patched equation backwards places the engine at approximately
313--318 mmHg absolute MAP. The previous low-lift VE surface interpolated to
only about 0.623--0.625 there. Those cells came from the synthetic commissioning
formula in `speed_density/patch_speed_density.py`; they were not measured EZ30R
volumetric-efficiency data. The Primary Open Loop A surface requests 14.70 AFR
at this speed/load. Changing an 18.6-AFR steady result to 14.7 requires a
multiplier of about 1.265 if injector delivery is correctly modelled.

The first corrected component applied that ratio only through a tapered low-lift
idle/vacuum neighbourhood. At 1,300 RPM and 315 mmHg it raises VE from 0.624 to
0.789. The correction is zero in the 3,000/3,200-RPM AVLS overlap rows, zero at
and above 1,150 mmHg absolute MAP, never makes a cell leaner, and does not alter
the high-lift table, injector calibration, or global airflow multiplier. It is
therefore was a bounded correction to the observed site rather than a
1.265 global multiplier.

The injector model was initially an equally important uncertainty. The master
does not contain generic "STI pink 565 cc" data; it translates the exact factory
A4TE002B donor-ROM profile. It currently displays 552.47 cc/min and uses
2.788, 1.488, 0.980, 0.684 and 0.380 ms at 6.5, 9.0, 11.5, 14.0 and 16.5 V.
Interpolation gives about 0.648 ms at the logged 14.3 V. The stock base-pulse
formula gives about 1.617 ms at 0.495 g/rev with that scalar, before other
fuel factors and latency. A roughly 0.429 ms
additional real-vs-modelled dead-time error could therefore produce the same
26.5-percent idle fuel deficit without any VE error. The fact that AFR improves
when RPM and pulse width rise makes an incorrect short-pulse/dead-time model
particularly credible in isolation, but does not uniquely prove it. The later
`16611AA510` identification matches the donor application closely enough that
the factory scalar/dead-time profile is retained while correcting VE. An
independent Subaru-ROM-derived reference lists the exact part at 550 cc/min and
describes latency with a 0.12-ms/V slope plus 2.36-ms offset, which evaluates to
0.68 ms at 14 V and independently agrees with the donor's 0.684-ms knot. This
does not guarantee the behavior of non-genuine or altered injectors.

The stock after-start code and its supporting calibration bytes were compared
byte-for-byte between the canonical ROM and the generated master image. The
descriptor blocks at `0x5F21C..0x5F25F` and `0x5F564..0x5F5DF`, plus table
regions `0x76769..0x767A8` and `0x76C16..0x76CE7`, are unchanged. At 31 C,
`after_start_enrichment_group_a_initialize` selects approximately 0.294 or
0.118 initial additive enrichment, depending on its stock runtime-condition
branch (the first branch also applies the stock `0xFFFFB760` multiplier).
Group B initializes to approximately 0.0349. These stock magnitudes are large
enough to conceal much of the observed 0.265 steady-state fuel deficit just
after starting. As a scale check, applying the 0.294 group-A value alone to an
18.6-AFR steady result predicts approximately `18.6 / 1.294 = 14.37 AFR`,
essentially the observed initial 14.4 AFR. This numerical agreement identifies
the masking mechanism; it does not by itself divide the underlying error
between VE and injector dead-time.

Correcting the steady-state model while leaving that stock cold enrichment
intact also changes the expected restart shape. If the full 0.294 group-A value
were active, the corrected 14.7-AFR base would give a simple upper-bound
estimate of `14.7 / 1.294 = 11.36 AFR` for the early transient. That estimate
does not include the other stock modifiers and is not a target, but it warns
that a brief richer start is plausible. The acceptance criterion is the fully
decayed stationary result; sustained AFR below 12, fouling, misfire, or renewed
lean drift requires shutdown and recalibration.

At the same coolant temperature, the decoded group-A delay lookup is
approximately 93 counter calls; the group-B delay is approximately 253 calls,
and its decay lookup is approximately 0.000145 per update. These are
state-machine counters, not direct seconds, so they must not be relabelled as a
fixed 30-second timer. Ghidra confirms the outputs still flow into
`final_fueling_multiplier_compose`.

The static conclusion is therefore narrower than "one bad timer": the base
open-loop target and airflow units are sane, while normal after-start decay
exposed a low steady-state VE estimate. Injector identification supports
retaining the A4TE002B profile, so the generated master now corrects only the
observed low-lift idle/vacuum neighbourhood. This change requires a stationary
restart and fully-decayed idle check before any other calibration work. The
master image remains unsuitable for load or boost testing until that result is
confirmed.

## Second stationary idle correction (2026-09-07)

This section records the trial artifact, not an established solution. The user
subsequently confirmed that the first 1.27 correction was flashed for this
run. The reassessment below withdraws the claim that its AFR endpoint was a
steady-state measurement or that normal after-start decay was proved to be
the source of the entire pulse-width drop.

The second supplied run used the first 1.27 low-lift VE correction. At roughly
30 seconds after engine start it still recorded 18.39 AFR at about 1300 RPM,
with open-loop status 7 and zero short-term corrections. The user separately
observed injector pulse width falling as AFR rose; that pulse-width observation
was visible live but was not recorded in the CSV. It supports a falling
command, but does not quantify which factor caused it. Stock after-start
decay is a candidate; the observation does not identify a defective stock
timer. The decay paths and `final_fueling_multiplier_compose @ 0x1DD04` remain
byte-identical to stock.

Ghidra reconfirmed that `injector_flow_scaling_factor_update @ 0x1E0C8`
multiplies conditioned engine load `0xFFFFB438` by the injector scalar at
`0x76014`, and that `injector_scheduled_pulse_width_channels_publish @ 0x26F8C`
publishes the scheduled high-resolution pulse-width channels. The scheduler
containing that output path is now named
`crank_synchronous_engine_output_task @ 0x11958`; the two adjacent retained
mode helpers are named `crank_output_mode_update_gate @ 0x26208` and
`crank_output_mode_select @ 0x26256`. No executable byte was changed by this
trace.

The remaining measured correction is `18.39 / 14.70 = 1.2517`. Applying it to
the first 1.27 factor gives 1.5897, rounded to a 1.59 total factor. The generated
low-lift VE is therefore approximately 0.985 at 1300 RPM/315 mmHg instead of
the original synthetic 0.624. The existing RPM/MAP taper remains unchanged:
the correction is zero from 2500 RPM upward, zero from 1150 mmHg upward, and
does not touch high-lift VE, injector data, after-start tables, timing, boost,
wideband logic or executable code. This is an empirical stationary correction,
not a validated physical VE model.

Relative to the prior checked master image, 124 bytes change, all within the
low-lift VE allocation `0x7E6B8..0x7E88B` or checksum word
`0x7FB88..0x7FB8B`. The rebuilt master SHA-256 is
`745cd7365c71e0cffad1f905d845c00547f3ed1893f779b631a56bed48735a71` and
its Subaru checksum is `0xB89A8BFA`. It requires a stationary restart with no
boost route. Stop immediately below 11 AFR, if AFR remains below 12 after the
first ten seconds, or if it still trends lean after the after-start additions
decay.

## Reassessment and bounded diagnostic capture (2026-09-07)

The 1.59 peak VE factor remains in the generated development artifact, but is
not recommended as a verified repair. No ROM byte changed during this
reassessment. User confirmation establishes that the September 7 run used the
first VE increase. It does not establish that the resulting AFR was settled:
the trace rose from 16.60 at about +25 s to 18.39 at about +30 s, with a slope
near 0.36 AFR/s; fault-zero samples began at +32.651 s. Consequently
`1.27 * 18.39 / 14.70` cannot be treated as a measured final VE correction.

Across +25..30 s, modeled airflow increased from 10.699 to 15.656 g/s between
runs while RPM stayed near 1301 and indicated IAT changed from 3 to 19 C. MAP
was absent from the newer capture. This modeled output is not independent
evidence of physical airflow, and the two runs cannot be treated as identical
VE-table sites. The newer file also lacks pulse width, latency, coolant,
conditioned load and final fueling factors. The user-observed pulse-width
fall remains relevant evidence, but its components cannot be reconstructed.

Live stock-ROM assembly rechecks established:

- The normal B428 -> B438 path retains a uniformly 1.0 compensation table at
  descriptor `0x5EB6C`. Its ECT override has a zero timer threshold at
  `0x737FA`; its other gate is B748 bit 7. This is not a stock 30-second
  default timer. Other runtime branches remain relevant until logged.
- `0x1E0C8` forms `B82C = clamp(B438 * injector_scalar, ...)` in microseconds.
  At 0.495 g/rev, the master scalar 3266.667 gives 1.617 ms before other
  factors. The earlier 2.43-ms estimate accidentally used the four-cylinder
  donor raw scalar. The ROM's translated scalar itself is correct.
- `0x98CC` returns latency counts. `0x26F8C` publishes those counts times 0.25
  as microseconds, confirming the donor-count conversion. At 14 V the master
  latency is 0.684 ms. E60 reports scheduled pulse width without latency;
  standard P21 includes it. Renamed `0x26F8C` to
  `injector_scheduled_pulse_width_channels_publish` and updated the repeatable
  naming script.
- Raising VE raises synthetic airflow and load, so timing/AVCS lookup positions
  may change even when the timing/AVCS table bytes do not.

The diagnostic profile itself had a concrete defect: 85 selected parameter
bytes plus two distinct switch bytes require 87 addresses. An SSM A8 payload
has two prefix bytes plus three bytes per address, and its one-byte length
allows at most 84 addresses. The profile now explicitly deselects E81/E105,
retains the equivalent bank corrections P3/P5, and uses 79 addresses. The
verifier counts expanded address lengths and deduplicates shared switch/view
addresses before checking the packet limit. E81/E105 remain available in the
logger definition. Clear unrelated subscriptions in every logger view before
loading the profile; loading it cannot guarantee removal of arbitrary older
subscriptions. This corrects the profile budget, not proof of a vehicle run.

Next evidence is a single synchronized capture on the user-confirmed first-VE
ROM with the repaired profile. In particular, compare MAP/IAT/load, E60 net
scheduled pulse, E50 latency, P21 inclusive pulse, E84 primary OL enrichment,
E123 composed base factor and E508--E513 after-start terms. E123 is not an
independently measured AFR or the entire injector command: the assembly
applies additional multiplicative corrections downstream. If the falling
pulse tracks decay of those terms, calibrate steady-state fueling first and
then cold-start enrichment. If it falls beyond the accounted-for factors,
trace that difference in the retained command/scheduler path. Do not derive
another VE ratio from a rising or out-of-range AFR endpoint.

## Fuel-pump command definition trace (2026-09-03)

The standard SSM handler pointer table starts at `0x4B6FC`; byte address
`0x3B` resolves to pointer slot `0x4B7E8` and
`fuel_pump_duty_logger_value_get @ 0x3191C`. That handler reads float RAM
`0xFFFFC298` and applies the standard P47 byte scaling.

The only runtime producer is
`fuel_pump_pwm_command_output_update @ 0x2A53A`. It selects zero or one of
three float literals—33.3% at `0x2A610`, 66.7% at `0x2A60C`, and 100.0% at
`0x2A5FC`—from the fuel-pump mode bits at `0xFFFFC2AC`. It publishes the
selected percentage to `0xFFFFC298`, divides by 100, then tail-calls
`fuel_pump_pwm_output_write @ 0xDEAA`. The writer scales that ratio against the
ATU period and writes the complementary compare value to `0xFFFFF592`.

The master definition exposes the low and medium literals as direct big-endian
float scalars. The 100.0 literal is also the divisor that normalizes the selected
percentage before the PWM writer, so it is deliberately fixed and omitted from
the editor. The generated master image does not alter any of them. Setting both
reduced-speed commands to 100.0 in a copied BIN provides a bounded diagnostic:
all running pump modes request full command, but the ECU's explicit pump-off
state remains zero. The mode-selection thresholds and timers remain hidden
from the focused editor. The engine-runtime threshold is now identified below,
but changing it is unnecessary for the diagnostic and the surrounding
state-machine gates are not yet suitable as user-facing calibration controls.

A subsequent ECU-learning reset reproduced the same result, and measured rail
pressure remained stable. Stored trim and pressure collapse are therefore no
longer leading causes. After-start enrichment decay exposing the base
SD/injector calibration is the primary software hypothesis; injector latency,
misfire, and an exhaust leak ahead of the sensor remain unresolved until the
reduced parameter set is captured.

## Engine-runtime timer cross-reference (2026-09-03)

No ROM bytes were changed by this trace. Ghidra xrefs establish that
`engine_run_counter_update @ 0x1A838` is the producer of saturating u16 RAM
counter `0xFFFFB688`. It increments from the main engine-control periodic task
and resets while `runtime_status_b748_bit7_is_set` is true. The approximately
10 ms cadence used below is derived from the scheduler grouping and the
consistent physical meaning of several stock calibrations, including the
977-count radiator-fan startup gate (about 9.77 seconds); it has not been
measured on a running ECU with an instrumented task pin.

Manual data-flow checks were performed after a ROM-wide B688 xref and candidate
constant scan. This distinction matters because merely finding a 16-bit value
inside a function does not prove that it is compared with B688.

| Consumer | Direct B688 calibration | Approximate time | Relevance |
|---|---:|---:|---|
| `fuel_pump_control_state_update @ 0x2A614` | `0x794DA = 3750` | 37.5 s | Direct fuel-pump mode gate. This is D2WD610H evidence, not an inference from another Subaru ROM. |
| `after_start_enrichment_group_c_residual_decay_update @ 0x22CE4` | `0x75E8E = 5000` | 50.0 s | Updates the group-C residual state; group output `0xFFFFBE40` is read by final fueling. |
| `ign_timing_cylinder_minimum_check_update @ 0x28C38` | `0x77D44 = 2500` | 25.0 s | Ignition/cylinder-minimum logic, not a direct fuel-delivery command. |
| `diagnostic_monitor_enable_state_update_6e338 @ 0x6E338` | `0x74D44 = 2500` | 25.0 s | Diagnostic enable gate, not base fueling. |

The recorded run lasted 34.813 seconds from first to last nonzero RPM, and the
sustained lean trend was already visible about 26.8 seconds after first nonzero
RPM. If B688 reset with the non-running state as its producer indicates, the
specific 37.5-second fuel-pump gate was not reached in this capture. B688 itself
was not logged, so this is a strong timing exclusion rather than a measured
counter value; P47 remains the direct way to confirm any earlier pump-mode
change caused by another state-machine condition.

Three initially suspicious candidates were rejected after following the actual
compare operands: `diagnostic_enable_runtime_latch_update_123f6` uses a
500-count B688 gate (about 5 seconds),
`diagnostic_monitor_11_condition_counter_update` uses 375 counts (about
3.75 seconds), and `diagnostic_monitor_state_latch_update_6b6fc` uses 625
counts (about 6.25 seconds). Values near 20--40 seconds loaded elsewhere in
those functions belong to other operands and are not their B688 thresholds.

The fixed-duration list is not the whole after-start fuel story. Groups A and B
at `0x1E1B0` and `0x1E47A` also read B688, but their delay and decay behavior is
coolant-dependent rather than one universal 30-second switch. They publish
`0xFFFFB834` and `0xFFFFB854`; related compensation routines publish
`0xFFFFB868` and `0xFFFFB874`. Together with group-C `0xFFFFBE40` and group-D
`0xFFFFBE48`, these values are consumed by
`final_fueling_multiplier_compose @ 0x1DD04`. Their decay can gradually expose
an under-fuelled steady-state VE/injector calibration while CL/OL status remains
open loop, matching the shape of the supplied cold-start trace better than a
closed-loop correction event.

`closed_loop_feedback_bank_state_update @ 0x1F0D8` has a separate
`0xFFFFBC98` counter capped by `0x75E5E = 31`. That is 31 scheduler calls, not
31 seconds and not the B688 engine-runtime clock. **September 8 correction:**
status 7 alone does not exclude this family's auxiliary fuel effects. Its bank
offsets also feed CEFC/CF00 outside the main short-term correction; their gates
and event-time values must be checked separately. See the
[retained-routine follow-up](RETAINED_ROUTINE_AUDIT.md). Likewise, the float
30 used by `evap_purge_condition_counter_update` is a signal threshold and the
integer 30 values in the ignition scheduler are crank-angle/event quantities,
not post-start timers.

The most discriminating next stationary test is to capture the after-start
fueling/additive states together with injector pulse width, then use P47 to
exclude an earlier pump-mode change. Temporarily setting the editable low- and
medium-pump commands to 100% in a copy of the ROM remains a useful secondary
test. If the AFR trend remains with a constant 100% request and stable
differential rail pressure, calibration work should focus on the after-start
additive states, injector latency at idle pulse width, and the steady-state
low-load VE cells. Do not use the present result as authority for load testing.

## Live MAP responsiveness and SD CPU workload (2026-09-08)

This is a static source/assembly check, not an execution-time measurement.
No stock or patched ROM bytes changed. The live stock Ghidra trace confirms:

- `sensor_adc_processing_task @ 0x66C6` calls
  `adc_scan_results_collect_and_schedule @ 0x6EAC` before calling
  `map_sensor_voltage_to_pressure_process @ 0x7A14` at `0x66DE`.
- `adc_module_0_scan_results_copy @ 0x6FF2` copies MAP hardware result
  `0xFFFFF804` into raw ADC RAM `0xFFFFAB04` at `0x7060`. Normal module-0
  scheduling selects 4, 8 or 12 channels; all include this MAP channel.
  The code retains startup/no-scan conditions; this does not prove that every
  result is fresh on a running ECU or establish a wall-clock sampling rate.
- MAP conversion passes raw AB04 and previous ABC8 through
  `integer_signal_first_order_filter_q8 @ 0x25CC`. Its exact expression is
  `new + trunc((1 - coefficient/256) * (previous - new))`. Stock and master
  coefficient `0x72818 = 0x0100` therefore pass the new sample unchanged:
  **there is no averaging lag in this converter stage**. This does not exclude
  sensor response time, electrical filtering or task scheduling latency.
- `u16_scale_offset_to_float @ 0x257C` converts the unsigned count to volts
  using `5/65536`; the offset/multiplier at `0x72810/0x72814` then publish
  native mmHg absolute at `0xFFFFABC4`. The SD wrapper reads ABC4 directly,
  not barometric estimate `0xFFFF8E04` or selected baro `0xFFFFCFBC`.
- SD remains in stock airflow task `0x172A4`, called through pointer
  `0x11D20` at `0x11AEE`. It does not wait for logger polling or atmospheric
  estimate updates. Sensor and airflow tasks are distinct; their relative
  scheduling and worst-case sample age have not been established here.

An independent source/offline-disassembly review counted 226 static wrapper
instructions, with 204/202 instructions on the valid low/high-lift paths
excluding callees. Each valid calculation makes two stock lookup calls (VE and
IAT) and six direct float multiplications. The wrapper has no backward branch.
The lookup helpers have bounded axis scans over 13 MAP entries, 9/11 RPM
entries and 10 IAT entries. Manual path accounting estimates approximately
531/541 instructions including the helpers on the longest valid paths. These
are instruction counts, **not CPU cycles or measured microseconds**. The
wrapper contains no division, but its axis-search helpers can execute three
floating-point divisions in total.

This is a real increase over the replaced `float_minimum_select @ 0x24B0`
helper; removed MAF processing offsets an unquantified amount of work. Nothing
in this check establishes total master-patch CPU utilization, interrupt
contention, memory wait states, missed deadlines or stack high-water usage.
The wrapper also reads MAP/RPM more than once rather than taking one protected
input snapshot; whether task preemption can mix samples is unproved here.

Conclusion: the selected source is the live MAP path, its converter is not
slowly smoothing the signal, and SD has modest bounded work rather than a
runaway loop. CPU overload is not established as the cause of the idle lean-out,
but "100% fast enough" would require actual timing/deadline evidence. A proper
runtime check would measure sample age and task execution/overrun behavior,
including other active master hooks; ordinary slow SSM logs cannot prove those
worst-case timing bounds. This review does not diagnose or resolve the lean-out.

Newly inspected unnamed functions were renamed in Ghidra and recorded in
`ghidra_scripts/ApplyMasterNames.java`, including the conservatively named
`periodic_status_counter_service_d24c @ 0xD24C` encountered before ADC dispatch.

## Speed-density hook assumptions recheck (2026-09-08)

The stock Ghidra assembly and actual current master bytes were checked again,
with independent caller-ABI and scheduling/writer reviews. SH4 decompiler
double-width/FPSCR alternatives were not treated as SH-2E execution evidence.
No executable or calibration bytes changed; master and standalone SD verifiers
both pass. These checks establish the following, not complete vehicle validation:

| Assumption | Finding |
|---|---|
| The right helper is replaced | Master `0x1743C = 0x7E18C`; stock call/store `0x17398..0x1739F` remain unchanged. Actual 552-byte wrapper matches its builder. |
| Every airflow-task invocation reaches SD | No conditional branch before the hook in `0x172A4`; caller `0x11AD0` invokes it through `0x11D20` unconditionally. Absolute cadence is still unmeasured. |
| Return value and calling convention fit | FR0 is stored to B420. Actual caller-live high registers survive; extra low-register clobbers are overwritten before use, with no live old-T dependency. |
| Stack handling is balanced | Every syntactically reachable wrapper return balances SP. Maximum extra depth including selected float lookup helpers is 20 bytes, excluding interrupt frames; total stack headroom is unmeasured. |
| VE axis order and data layout fit | FR4=MAP, FR5=RPM; actual float descriptors are 13x9/13x11, with MAP-fastest row-major cells. IAT lookup consumes Celsius and its multiplier is applied to the saved product. |
| Stock final MAF scaling overwrites SD afterward | Not in the retained task: original B448/B458/B45C intermediate work occurs before the hook. SD mirrors those states, and the separately scheduled raw-MAF filter call is bypassed. Other initialization writers still exist, as below. |

### Important qualifications to the handoff

**Unfiltered MAP is not unfiltered engine load.** The MAP converter's
pass-through setting does not describe the later B428 -> B42C load filter.
`float_first_order_filter_with_snap @ 0x2424`, called at `0x1756E`, uses
unchanged calibration `0x73968 = 0.06`:

```text
filtered_load = new_load + (1 - 0.06) * (previous_filtered_load - new_load)
```

Except for its nonfinite/near-target snap conditions, it advances 6% toward
the target each call. An ideal constant step reaches 95% in about 49 updates;
this is not a measured number of milliseconds. Compensation descriptor
`0x5EB6C` is uniformly 1.0. Later normal B438 gains at `0x73974..0x73980`
are 1.0, while the separate B440 filter uses `0x73984 = 0.5`. Thus any blanket
claim that all retained load filtering is unity would be wrong. Retaining the
stock filter is not automatically a defect, but transient response needs
assessment for the speed-density conversion. It is not itself a 30-second
after-start timer or evidence explaining the sustained lean-out.

**Not all downstream branches use the normal VE-derived load.**
`airflow_load_fallback_status_get @ 0x65168` returns 2 when `D26F bit0x40`
is set. The task then uses `max(processed_MAP_B2A0 * 0.00264 - 0.0851, 0)`
for B438. `diagnostic_fallback_status_flags_update @ 0x63174` sets/clears
that bit at `0x64490/0x644A0`, using descriptor base `0x5BDF0` records 3,
4 and 103: P0102, P0103 and P0101 respectively. It reads current-status
RAM `0xFFFF8E5A` masks 0x01/0x02 and `0xFFFF8EA6` mask 0x80. The master
disables P0102/P0103 switch bytes `0x5BD57/0x5BD58`; P0101 switch
`0x5BDBB` is already zero in stock and remains zero. This trace establishes
the fallback's presence, not that it activated during the user's run.
The retained B748-bit7/ECT lookup branch also remains; its runtime-counter
threshold `0x737FA` is zero, not a hidden 30-second delay.

**B420 has other writers.** Initialization entry `0x1780A` and periodically
called `airflow_state_coolant_initialization @ 0x1785C` write airflow/load
from coolant tables. The periodic branch requires B52C bit7. That flag is
copied from AC0C by `0x1A16E`; AC0C follows engine-signal timeout latches
handled by `0x8AD6`, cleared by event paths `0x8B2E/0x8B80`. Crank-event
routine `0x19F9C` also clears B52C bit7. This supports a stopped/timeout
interpretation, not a demonstrated normal-idle override. It is incorrect to
claim the hooked task is the only possible writer in every engine state.

**Sensor inputs are not one coherent snapshot.** The stock caller captures
RPM in FR15 at `0x172CE`. SD independently reloads B544 for checks, VE lookup
and multiplication; the later load division at `0x17550` uses the earlier
saved FR15. MAP and IAT are also reloaded after their validity checks. If
input producers can preempt this task, the lookup, product and load divisor
can use different sample ages. This structural property is confirmed; actual
preemption, error magnitude and relevance to the user's slow lean trend are
not. Snapshot consistency is a sensible hardening target, not a proved cure.

Conclusion: the central hook placement, ABI, table layout and normal output
units check out. The stronger assumptions of immediate/unfiltered fueling,
exclusive ownership of final load in every state, and coherent sampling do
not. No register/stack corruption, axis reversal or bypass of the hook was
found. Retained load behavior and sample coherence must remain explicit limits
on confidence; the lean-out root cause remains unproved. All newly inspected
generic function names were updated in Ghidra and recorded in the master
naming script. `0x25F8` remains undefined as a live Ghidra function; a label
rename was attempted, and the script contains its create/name action.

## SD hook hardening implemented (2026-09-08)

The user authorized the targeted fix after the preceding audit. The central
hook location and normal mass-flow equation remain unchanged. This implements
stable per-call input use and removes one obsolete MAF-only load diversion;
it does not claim to resolve the engine's sustained lean-out.

### Executable changes

- The wrapper at `0x7E18C` saves FR12/FR13 and PR, uses the stock caller's
  already-captured FR15 RPM, and reads MAP ABC4 and IAT B3B8 once each on the
  nonzero-RPM path. Saved FR12/FR13 hold MAP/IAT across both stock lookup calls.
  Validation, table inputs and multiplication use these values. Load division
  at `0x17550` still uses the same FR15. No live B544 literal remains in the
  wrapper. Every exit restores the caller's saved registers and stack.
- Only the local status-helper literal `0x173FC` changes from `0x65168` to
  `constant_zero_return @ 0x27088` (verified bytes `000B E000`: RTS with
  MOV #0,R0 delay slot). Ghidra showed one reader of that literal, at `0x172E2`.
  This makes the old P0101/P0102/P0103 MAP-linear load substitution unreachable
  in this task without altering the shared diagnostic getter or its other
  ignition/fueling/diagnostic consumers.
- Stock cranking/ECT and engine-signal timeout initialization remain intact.
  None of the earlier evidence established those protections as defective.

Inputs are stable for this calculation, **not atomically or simultaneously
sampled physical signals**. No interrupt masking is added. Sensor acquisition
age, ISR scheduling, total stack margin and worst-case execution deadlines
remain unmeasured. The wrapper uses 16 bytes of its own stack at peak and
28 bytes including the previously traced stock lookup frames, excluding
interrupts/caller frame (8 bytes more than the prior wrapper).

The new wrapper is 536 bytes including literals, versus 552 before. Its last
byte is `0x7E3A3`; `0x7E3A4..0x7E3FF` is unused reservation (92 bytes).
No new static RAM or other component allocation is used. The contiguous free
tail remains 3,344 bytes at `0x7EDE8..0x7FAF7`.

### Filter/calibration decision

The default load-filter alpha `0x73968 = 0.06` remains unchanged. Removing it
without measured MAP noise/cadence is not justified by finding that it exists.
The focused definition now exposes `Speed Density Load Filter Response` under
`01.5 - Air Model - Load Calculation` as `% per update`: display `x*100`,
storage `x/100`. Default is 6%; 100% is pass-through; 0% can freeze load and is
not a usable setting. Documentation states the finite `(0,100]` range; no
new firmware clamp on this stock calibration is claimed.

All existing VE, injector, IAT/MAP, fuel, timing, AVLS and safety calibration
bytes are unchanged. In particular, the generated master **still contains the
unvalidated second idle-VE trial**. It is not a calibration-identical code test
against the first-VE ROM from the latest usable log; establish that baseline
before adopting a newly flashed image. No new calibration fix is inferred.

### Verification and artifacts

- Direct old-master/new-master comparison found 464 changed bytes, confined
  to the old wrapper allocation, local fallback pointer and checksum word.
  No other byte changed relative to pre-hardening master hash `745cd736...`.
- Both ordinary binary verifiers now run the actual-wrapper opcode harness
  `speed_density/test_hook_execution.py`. Eight test groups pass against both
  rebuilt ROMs: valid modes/edges, stale live RPM, MAP/IAT changed immediately
  after capture, adversarial scratch-register clobbering, invalid sensors and
  calibrations, invalid lookup returns, overflow/underflow/cap, and zero RPM.
  A missing-FP-restore mutation is detected. The harness decodes wrapper
  opcodes/delay slots but models stock lookups from descriptor/table bytes;
  it is not a full ECU/ISR/FPSCR or timing simulator.
- Mutating each guarded caller capture, retained load divisor, constant-zero
  helper, default filter alpha or original fallback pointer makes the builder
  refuse the in-memory input. Binary checks also retain the global diagnostic
  getter, cranking/ECT branch and timeout initializer bytes.
- Full master/standalone audits pass: deterministic rebuild, SH opcode checks,
  ownership/collision checks, checksums, definition regeneration/categories,
  logger/profile checks and unchanged stock/base-copy/SRF provenance.

Current master SHA-256:
`0600d73aeffb7e6566275644776d787b142d76f4aab55331bca52a6a2a3df9ab`,
checksum `0xB33060BB`.
Standalone SD SHA-256:
`272e623890a2cc516df35ea7bd340ec3e9f5076801e4a865627954799c9c1636`,
checksum `0xF98E7CC8`.
Root stock remains
`ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
Stock Ghidra comments and both repeatable naming scripts describe the new
call-site semantics; the Ghidra program remains the untouched stock image.

## 2026-09-08 — Retained-system audit and fan-output misidentification

This section records the pre-repair findings. The subsequent repair section
supersedes its statements that the current artifact still owns the fan channel.

Requested diagnosis: could omitted patch interactions explain the repeatable
cold idle lean-out and poor torque? The user additionally reports substantial
turbo spooling. This pass changes annotations/documentation only, not firmware.

### Confirmed integration fault: boost hook owns the fan channel

The previous purge identification is retracted. Two independent stock-ROM
traces agree with the existing generated logger definitions:

| Function | SSM address | Dispatch slot -> handler | RAM source |
|---|---|---|---|
| P92 Radiator Fan Control | `0x2F` | `0x4B7B8 -> 0x31878` | `CD54`, percent directly |
| P38 CPC Valve Duty Ratio | `0x32` | `0x4B7C4 -> 0x318E8` | `B6D4`, ratio scaled by 255 |

`radiator_fan_duty_compute @ 0x3FC0A`, formerly labelled purge, calculates
`CD54`. Descriptor `0x609C4` has coolant knots 92/95/100/103/105 C and duties
40/40/70/70/70 percent. Descriptor `0x609D8` has 83/98/100/120 C and
45/60/70/70 percent. Its IAT hysteresis is 25/26 C. This corroborates the fan
identity rather than relying on the logger name alone.

The stock final output literal `0x3FD8C = 0xE8C4` is replaced with `0x7E560`
in master. Invalid guard conditions send `FR4 = 0` to `0xE8C4`; valid conditions
reach the boost controller, whose EBCS-OFF branch also sends `FR4 = 0` there.
Thus the current default image overrides every stock request on this channel
with a zero duty command. The output writer computes `F590 = AB84 - scaled_duty`;
zero ratio writes the PWM period itself. Physical fan-controller polarity and
fail-safe behavior are not established here: this does **not** prove that the
fans necessarily stop, but normal ECU fan control is unquestionably displaced.

`CD54` still holds the stock calculated request. P92 can therefore look normal
while the actual output is overridden. Its readers in idle-control routines
`0x2BD5C/0x2E0E0` also still see the pre-override request. The real canister-purge
output route, literal `0x1BBFC -> 0xB182`, is unchanged in master.

**Disposition:** do not flash/run this master or regard EBCS OFF as restoring
stock fan operation. Restore and verify fan control before further running;
retain wastegate-spring operation as requested. No replacement EBCS output
should be enabled without a separately verified CPC output/harness identity.
No repaired ROM was produced in this diagnostic pass. The fault is serious,
but it is not yet shown to cause the cold ~30-second lean-out.

### Purge fuel subtraction was not removed

`B6D8` is modeled purge airflow, not an obsolete MAF measurement. At `0x1BCCA`,
`B6D8 = clamp(B6DC * B420, 0, B6F4)`; lookup `0x5ECC8` derives CPC duty `B6D4`.
Other modes use inverse lookup `0x5ECE4`. These computations now consume the
SD-generated `B420`. Their output driver and the bank fuel-subtraction paths
remain stock, despite removed/capped purge plumbing.

`0x23054` publishes `BE60/BE64 = BE6C * B730/B734 * 100`, where `BE6C` uses
filtered purge airflow divided by `B420`, bounded to 0..0.125. Final fueling
`0x1DD04` explicitly subtracts `BE60/BE64` from the respective bank's additive
base terms. Ordinary activation is gated by `0x748AC = 72 C`; `B705 bit 6` is
another selection condition. This is an unresolved hardware-delete integration
issue and could matter when warm. It is **not** proof of the observed cold event;
the ordinary temperature gate argues against that simple attribution.

### VE, AVCS and timing are coupled

Ghidra `intake_avcs_target_by_avls_mode_update @ 0x353B0` consumes conditioned
load `B438` and RPM `B544`. Mode 1 selects the low-lift cam map; mode 3 selects
the high-lift map. Other modes/runtime gates can zero the requested angle.
The SD VE surface selects lift state but has no actual-cam-angle dimension.

Example from bilinear interpolation of the current BIN at **1300 RPM**:

| Calculated load | Low-lift intake AVCS table target | Base Timing A | Base Timing D |
|---|---|---|---|
| 0.49 g/rev | 4.00 degrees | 25.77 degrees | 24.72 degrees |
| 0.72 g/rev | 23.08 degrees | 21.56 degrees | 15.95 degrees |

AVCS data `0x7C5B0` are 14x11 uint16, axes `0x7C54C/0x7C584`, conversion
`raw * 0.0054931640625`. Timing A/D data are `0x78AA0/0x78E34`, common load
axis `0x780BC`, RPM axes `0x78A68/0x78DFC`. These are **table requests**, not
measured cam position or final ignition timing. The newer log's ~0.72 is a raw
load inferred from modeled airflow/RPM, not logged conditioned `B438`.

Recognised idle has a separate timing-target/blend path; the A/D values above
must not be described as measured or necessarily commanded idle ignition.
The follow-up below traces that distinction. At unchanged load the checked
idle timing bytes remain stock-equivalent. Increasing VE can move cam/base-timing demands substantially and
change cylinder filling inside the same low-lift VE surface. This could
contribute to poor torque/roughness; actual occurrence and its relation to
lean-out remain unproved. `0x33B92` uses a 125-count normal AVCS permission
threshold (`0x7BE3E`), not a demonstrated 30-second enable. Other temperature,
oil and runtime gates remain.

The user's spool observation makes actual ignition/cam timing worth checking,
but it is not evidence of positive manifold boost or an active anti-lag mode.
Retarded ignition can increase exhaust energy while reducing useful torque
([Haltech's explanation](https://www.haltech.com/news-events/how-launch-control-works/));
the example table values above do not prove such extreme retard occurred.
Rotational idle is **OFF** in this BIN (`0x7DB40 = 00`).

### Other checks and remaining limits

- The mapped former-MAF ADC readers are bypassed conversion/diagnostic paths
  or the raw logger. No additional direct raw-MAF-to-fuel path was found in the
  inspected references. This is a bounded reference audit, not exhaustive proof
  about every computed address.
- Common fuel multiplier `BE88` is hot-IAT compensation, not an unexplained
  monitor term. `0x2333C` forms `clamp(1 + BE90*BE94*BE98*BE9C, .5, 1.5)`.
  Present table values bound it to 1..1.05078125, with no correction at filtered
  IAT <=60 C. Under valid state it cannot explain a large cold fuel reduction.
- Donor injector scalar/latency translation still checks out. The retained
  final-fuel lower clamp is 600 us; it does not account for the observed falling
  command at the estimated base pulse. Installed-injector short-pulse behavior
  and stock wall-film/transient calibration remain unvalidated.
- Additional stock corrections exist: `0x45258/0x452B8` publish `CEFC/CF00`,
  bounded -0.01..+0.10; `0x49B20` publishes `D114/D118` as zero or +0.25 under
  its gates. `0x23864` zeros `BEB8/BEBC/BEC0` for current selector `0x75E2B=0`.
  The remaining analog voltage pair `ABCC/ABD0`, updated at `0x7AB0`, is used
  by `0x49B20`; its full sensor/activation interpretation was not resolved in
  this pass. Do not equate zero short-term trims with a complete accounting of
  all final-fuel terms.

The cold lean-out root cause is still open. Findings establish a real fan-output
bug, a retained purge-compensation dependency, and significant VE/cam/timing
coupling; they do not justify another blind VE increase or a claimed cure.
ROM hashes are unchanged from the preceding SD hardening section. Newly
inspected stock functions have descriptive Ghidra names, persisted in the master
naming script; the SD script's old `0x1B800` load-calculation label is corrected
to purge airflow limit/correction. Existing structural tests need output-identity
regressions as part of the eventual firmware fix, not another assertion that the
old boost byte pattern matches its generator.

### Follow-up: spool at idle and while revving; unusual exhaust sound

The user confirms the spool observation occurs both at idle and when revving,
and reports an unusual exhaust sound. This is a symptom report, not a measured
boost pressure, exhaust temperature, ignition angle or cam position. It raises
the priority of checking combustion timing/cam behavior alongside fueling; it
does not establish an active anti-lag strategy or a new lean-out diagnosis.

The actual current BIN's rotational-idle OFF path was checked independently:
`0x11E30 -> 0x7DB90`, switch `0x7DB40 = 00`, 348-byte wrapper matches its
generator. It calls stock `0x279CC` exactly once, then branches from `0x7DB9E`
directly to return at `0x7DC98`. No additional FP instruction or timing-state
write executes after the stock call on this path. PR/SP balance; the extra
stack use is four bytes. The next task `0x4AC6E` defines scratch R0/R1/R2
before consuming them, and the dispatcher does not consume the wrapper's T bit.
The stock final-timing body `0x279CC..0x27D37` is unchanged. This does not prove
which exact image/settings were flashed; it rules out the default wrapper path
as a demonstrated source of unintended retard in the inspected artifact.

The final-timing routine was rechecked in Ghidra. It combines multiple RAM
corrections and operating-mode overrides before publishing the six final angles
at `C0EC..C100`; the base-map values from the preceding example are not final
spark timing. Two inspected subtractive terms are dormant with present valid
calibration/state:

- `0x29024` publishes `C1C8`. Its increase/decrease calibrations `0x77EC8/CC`
  are zero, duration threshold `0x77D46` is zero, temperature bounds
  `0x77EBC/C0` are 140/150 C and speed threshold `0x77EC4` is 777 km/h.
  There is no calibrated cold-idle retard build-up here.
- `0x29128` publishes `C1D0`; its high-RPM retard magnitude `0x77ED0` is zero
  in stock and master. The RPM hysteresis tracks the existing limiter change
  (7000/6970 stock, 6800/6770 master), not a cold-start timer.

Other corrections remain runtime-dependent: `0x28958` selects coolant-based
`C1A0` adjustment tables and `0x2931A` supplies `C1E0` through a retained state
path. Their inspection is not proof of activation or harmlessness at every
operating point. Actual final timing and actual/target AVCS must be distinguished
from table lookups before attributing the sound/spool to retard. The fan-control
stop notice remains in force; no further engine-running test is recommended on
the current image. No ROM or tune bytes changed in this follow-up. Names are
persisted in the Ghidra naming scripts.

## 2026-09-08 — Fan restoration, purge delete and idle-timing clarification

Implemented for the user's request to fix the confirmed findings. The new
development master is SHA-256
`fbc1a8fad234dbf09934da8dda8a0eda8629965c3d162eb957c06c46a4d9848e`,
Subaru checksum `0x503BE476`. Canonical stock remains byte-identical at
`ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.

### Bounded firmware repairs

- Restore stock fan tail-call literal `0x3FD8C = 0x0000E8C4`. The standalone
  boost and master-wideband installers now require and preserve it. The old
  controller at `0x7D810` and guard at `0x7E560` contain only `rts; nop` followed
  by erased bytes across their full 172/224-byte reservations. Their legacy
  switch cannot reactivate either path. Obsolete actuator controls are removed
  from both master and boost definitions; the independent hard overboost fuel
  cut remains enabled for spring-pressure operation.
- Replace the first 40 bytes of actual CPC dispatcher `0x1BAF0` with a leaf
  that publishes zero duty `B6D4`, zero modeled purge airflow `B6D8`, zero mode
  `B720`, and tail-calls the unchanged CPC writer `0xB182` with `FR4 = 0`.
  The separate `AB64` initialization/interrupt-consumer path was checked;
  this is not a fan-output hook or a write of zero to an arbitrary PWM register.
- Replace eight bytes at `purge_bank_fuel_subtraction_publish @ 0x23054`
  with a zero publisher for both retained caller destinations, `BE60/BE64`.
  This defeats stale modeled purge corrections regardless of coolant state.
  The two verified CPC circuit DTC switches P0458/P0459 at `0x5BD85/86` are
  disabled. Other DTC switches are not changed by this component.

The purge component owns **50 in-place stock bytes** and adds no RAM, stack or
free-space allocation. Retired allocations remain reserved, so the 3,344-byte
contiguous free region is unchanged. Against the prior `0600d73a...` master,
exactly **436 bytes** differ, wholly within these seven ranges:

| Range start | Reserved size | Changed bytes | Purpose |
|---|---:|---:|---|
| `0x1BAF0` | 40 | 40 | CPC zero dispatcher |
| `0x23054` | 8 | 8 | Both-bank purge subtraction zero |
| `0x3FD8C` | 4 | 3 | Stock fan route restored |
| `0x5BD85` | 2 | 2 | CPC circuit diagnostics |
| `0x7D810` | 172 | 165 | Actuator retired |
| `0x7E560` | 224 | 214 | Actuator guard retired |
| `0x7FB88` | 4 | 4 | Subaru checksum |

VE, injector, sensor, ignition, AVCS/AVLS, rotational-idle and fueling-safety
code/calibrations are otherwise unchanged from that previous image. In
particular this still contains the unvalidated second idle-VE trial, not a
calibration-identical comparison against the first-VE image used for the log.
Do not run an older fan-hook image merely to recover the first-VE calibration.

### The VE/load/cam link is real; the idle-ignition inference was too broad

More VE produces more modeled airflow/load. That can change the requested AVCS
angle, which changes actual cylinder filling while the VE lookup has only
RPM, MAP and committed lift state. Base ignition tables are also load-indexed.
This interaction is **not fixed by the fan/purge repairs**, nor does its
existence prove that it caused the observed cold lean-out.

Further stock Ghidra tracing establishes:

- `ign_idle_timing_blend_factor_update @ 0x27DE8` writes `C134` using RPM,
  vehicle speed and the debounced throttle-idle flag `B2BC bit 1`, read by
  `runtime_b2bc_bit1_is_set @ 0x15192`. There is no load input to this blend
  calculation. Stationary recognised idle ramps toward `C134 = 0` (idle
  target); leaving the condition ramps toward `1` (base timing), using the
  stock 0.008-per-call calibration. `throttle_position_sensor_process @
  0x14DCC` produces the idle flag, using the threshold at `0x737DC`.
- `ign_idle_timing_target_update @ 0x27F3E` publishes `C138`. The stationary
  idle maps at `0x7828F/0x78298` are flat **15.15625 degrees** over 400..2000
  RPM. Load compensation at `0x782AC` is flat approximately 0.039 degrees.
  The 4 km/h threshold at `0x77E1C` selects idle maps; it is not by itself
  the idle-versus-base blend gate.
- `ign_base_and_idle_timing_update @ 0x28166` combines the `C138` idle target
  and `C150` base value using `C134`, publishing `C130`. `0x281AA` is inside
  this function, not another function entry. Downstream corrections still
  separate these targets from actual per-cylinder final spark timing.
- `intake_avcs_target_by_avls_mode_update @ 0x353B0` has no corresponding
  direct `B2BC`/`C134` idle gate. Raising a global AVCS minimum RPM or flattening
  an entire low-RPM table would also affect loaded clutch take-up/tip-in.

Therefore the earlier 1300-RPM A/D table example describes a **conditional
base-timing effect**, not demonstrated retard at recognised idle. No blind
timing advance, global cam lockout or further VE increase was applied. An
idle-only cam hold would be a new, unvalidated feature requiring explicit
selection and narrow idle/stationary/RPM/vacuum gates; it is not included.
Live function names are persisted in `ghidra_scripts/ApplyMasterNames.java`.

### Verification and remaining limit

The full master verifier independently preserves stock fan scheduler/code,
writer and calibration bytes and pins separate P92 fan / P38 CPC identities.
`test_actuator_retirement.py` has ten regression groups, including old-hook
destinations, resurrected code, legacy switch values 0/1/255, and refusal of
an upstream fan hijack before the wideband installer mutates any bytes.
`test_purge_delete.py` has six groups and executes the actual injected opcodes
and delay slots, checking both bank destinations, stale/NaN inputs, register/
stack behavior, guard refusal and bounded ownership. Its execution stops at
the stock CPC-writer handoff; it is not a whole ECU/hardware simulator.

These tests and deterministic master/standalone-SD verification pass. They
establish the scoped software repairs, not fan polarity, physical plumbing,
actual cam/ignition behavior or a cure for the cold lean-out. The ordinary
72 C purge gate in stock remains evidence against attributing the cold event
solely to purge subtraction. No ECU was flashed or engine run by this work.
