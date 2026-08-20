# D2WD610H master-patch Ghidra audit

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
| `0x24FC` | `float_difference_exceeds_tolerance` | Near-zero/tolerance test used by AVCS target and tracking logic. |
| `0x27088` | `constant_zero_return` | Exact `rts; mov #0,r0`; makes timing B/E selector branch dormant. |
| `0x6504C` | `runtime_status_d26d_bit5_get` | Timing selector status input. |
| `0x28354` | `ign_avcs_tracking_blend_factor_update` | Builds and clamps the measured/commanded intake-AVCS tracking factor `k` at `0xFFFFC17C`. |
| `0x28418` | `ign_base_timing_map_blend` | Looks up/blends all base-timing endpoints. |
| `0x284B8` | `ign_base_timing_select` | A/D normal-cam, C/F AVLS-high-cam selection; B/E requires the constant-zero callback. |
| `0x353B0` | `intake_avcs_target_by_avls_mode_update` | Selects AVCS A in committed low-lift mode and AVCS B in high-lift mode. |
| `0x35750` | `intake_avcs_tracking_control_update` | Downstream per-bank AVCS target/tracking control. |
| `0x3EB68` | `knock_correction_advance_max_select` | KCA A normal-cam versus B AVLS-high-cam selection. |
| `0x3FFDA` | `avls_threshold_curve_selector_state_update` | Publishes internal AVLS curve-selector state 1/2/3. |
| `0x400EE` | `avls_curve_selector_load_band_latches_update` | Builds selector latches from fallback-load bands 13/15 and 113/115. |
| `0x7A14` | `map_sensor_voltage_to_pressure_process` | `MAP = voltage*multiplier + offset`; writes native absolute mmHg to `0xFFFFABC4`. |
| `0x7A56` | `map_sensor_raw_adc_range_classify` | Raw `0xFFFFABC8` compared with thresholds at `0x7B284/0x7B286`. |
| `0x78AC` | `analog_sensor_abac_range_classify` | Neighboring analog range path separated from MAP. |
| `0x79B4` | `analog_sensor_abbc_range_classify` | Neighboring analog range path separated from MAP. |
| `0x98CC` | `injector_battery_voltage_latency_lookup` | Injector voltage-axis/deadtime descriptor path. |
| `0x1E0C8` | `injector_flow_scaling_factor_update` | Reads D2WD injector scalar at `0x76014`. |
| `0xA9A8` | `injector_control_lookup_sequence_a9a8` | Supporting injector lookup sequence. |
| `0xB690` | `front_af_sensor_pair_signal_process` | Original paired-front conversion entry replaced by the external-wideband hook. |
| `0x192A8` | `front_af_sensor_pump_current_pair_offset_clamp_update` | Obsolete front pump-current diagnostic path. |
| `0x18DAC` | `front_af_sensor_lambda_condition_filter` | Conditions lambda for stock closed-loop consumers. |
| `0x1EE74` | `closed_loop_fuel_control_bank_update` | Confirms bank feedback/readiness consumption. |
| `0x13330` | `runtime_status_b6c0_bit7_is_set` | Supporting front-feedback gate. |
| `0x1D228` | `runtime_status_b748_bit7_is_set` | Supporting front-feedback gate. |
| `0x1884` | `diagnostic_request_download_handle` | Named while separating diagnostic infrastructure from sensor tasks. |

Existing project names used by the integrated components include
`maf_airflow_temperature_compensation_update` (`0x172A4`),
`evap_purge_duty_compute` (`0x3FC0A`),
`evap_purge_pwm_output_write` (`0xE8C4`),
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
last column unless the existing axis is rescaled.

### How AVLS chooses low or high lift

AVLS makes the lift decision before AVCS A/B selection. In the master baseline,
high-lift OSV actuation is prohibited below 2500 RPM. Between 2500 and 3200 RPM,
the state machine compares load `0xFFFFB46C` with the currently selected
load-versus-RPM threshold curve. From low lift it requests high lift at
`load >= curve + 10`; from high lift it requests low lift below the raw curve.
At 3200 RPM the hard override requests high lift regardless of load and holds
that override until RPM falls below 3000. The target mode is written at
`0xFFFFCD87`; the committed mode at `0xFFFFCD86` changes after the existing
timer, status, and OSV-actuation gates.

The two switchover curves are not engage/release maps. Internal selector state
`0xFFFFCD9C == 2` uses curve 1 and state 3 uses curve 2. The selector derives
those states from hysteretic bands of fallback-load signal `0xFFFFCF94` (13/15
and 113/115), plus runtime/delay gates. That signal's physical units and broader
meaning are not yet proven, so commissioning must log the actual requested and
committed transition rather than interpreting those numbers as g/rev.

### MAP and injectors

`0x7A14` consumes the two floats at `0x72810` in offset/multiplier order and
writes native mmHg absolute MAP. The raw diagnostic thresholds are separate at
`0x7B284/0x7B286`. Injector latency uses the descriptor at `0x608D8`, voltage
axis at `0x7B304`, and data at `0x7B318`; injector flow processing reads
`0x76014`. These are the locations used by the builder and definition.

### MAFless airflow

The existing speed-density component replaces the final airflow helper called
inside the retained stock airflow/load task. The two raw MAF conversions, the
raw MAF limit update, high/low diagnostic task, and MAF-dependent temperature
condition are bypassed. The shared ADC scan remains, so former-MAF ADC RAM
`0xFFFFAB06` continues updating even though no airflow calculation consumes it.

### One external wideband replacing four stock paths

The hook at original front-pair entry `0xB690` converts unsigned AB06 ADC counts
to volts and AEM lambda, then writes both bank lambda/readiness paths. Both
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

## Injected layout

| Region | Use |
|---:|---|
| `0x7D790..0x7D91F` | Existing boost component and master signatures. |
| `0x7DB40..0x7DCEB` | Reserved separate rotational-idle component; untouched. |
| `0x7DCF0..0x7E39B` | Existing speed-density calibration and firmware. |
| `0x7E400..0x7E41B` | Wideband constants. |
| `0x7E440..0x7E51B` | Wideband update routine. |
| `0x7E520..0x7E53B` | Closed-loop inhibit helper. |
| `0x7E560..0x7E63F` | Wideband/SD-input/result boost prerequisite guard. |

The verifier rejects overlap, writes outside declared stock hooks/calibration
regions, unknown injected opcodes, stale generated XML, unexpected logger RAM
addresses, stock/SRF provenance drift, and checksum failure.

## Unresolved physical risks

- AB06 is proven as the continuing former-MAF ADC channel in firmware, but its
  allowable source impedance, protection behavior, and real harness voltage
  offset still require bench measurement.
- The four stock heater drivers remain electrically active even though their
  sensor tasks and mapped DTCs are removed.
- A single post-turbo sensor cannot detect per-bank mixture imbalance and adds
  exhaust transport delay to the stock closed-loop algorithm.
- No single physical purge/EBCS terminal is asserted for every market harness;
  continuity and scope tests are still required.
- MAP transfer, injector behavior, PWM frequency/polarity, fuel pressure,
  modeled VE, timing, boost creep, and protection response all remain physical
  commissioning items.
