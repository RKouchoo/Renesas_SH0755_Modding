# D2WD610H — EZ30R Denso ECU Reverse Engineering Notes

Working document. Updated as analysis progresses in Ghidra (live MCP session).
This file is the canonical state doc. Companion references:
- [ram_map.md](ram_map.md) — consolidated RAM variables
- [hardware_io_map.md](hardware_io_map.md) — memory map + peripheral registers
- [solenoid_subsystem.md](solenoid_subsystem.md) — cam-bank vs purge PWM outputs
- [boost_repurpose_notes.md](boost_repurpose_notes.md) — purge chain + boost-control design
- [patch_build_guide.md](patch_build_guide.md) — boost-patch build/flash plan
- [single_front_af_patch.md](single_front_af_patch.md) — retained factory A/F mirror design
- [../master_patch/README.md](../master_patch/README.md) — current MAFless turbo master image
- [readme.md](../readme.md) — project overview + goals

---

## 1. ROM Identity (confirmed)

| Field | Value |
|---|---|
| CALID | **D2WD610H** (ASCII @ 0x7BDDD; internal id @ 0x2000) |
| ECU ID | **3C5A387116** (packed @ 0x7BDA8) |
| Processor | **Renesas SH7055** (SH-2E core, big-endian) |
| Flash size | **512 KB** (0x00000000–0x0007FFFF) |
| Vehicle | 2005 ADM Subaru Liberty 3.0R **MT** (BLE) |
| Reset vector | initial PC 0x000009E0, initial SP 0xFFFFDFA0 |
| Def match | D2WD610A.xml contains a D2WD610H rom block (ecuid 3C5A387116) — exact match, table set incomplete |

## 2. Memory Map (SH7055)

| Region | Range | Notes |
|---|---|---|
| Flash | 0x00000000–0x0007FFFF | ROM image, base = file offset |
| On-chip RAM | 0xFFFF0000–0xFFFFDFFF | directly referenced by code (good xref anchors); stack at 0xFFFFDFA0 |
| Peripheral regs | 0xFFFFE400+ | I/O ports, timers, ADC — solenoid/sensor anchors live here |

**Denso literal trick:** RAM addresses ≥0xFFFF8000 are stored as *16-bit* PC-relative
literals (`mov.w`) and sign-extended — a 2-byte pool entry `c17c` means 0xFFFFC17C.
ROM pointers/descriptors are 4-byte `mov.l` literals. Read pools with `xxd` on the .bin
(flash base = file offset) when Ghidra shows opaque `DAT_`/`PTR_` names.

## 3. Table Access Architecture (SOLVED)

### Interpolation core (all renamed in Ghidra)

| Address | Name | Role |
|---|---|---|
| 0x0000209C | `table2d_lookup_dispatch` | **Central single-axis lookup.** r4=descriptor, fr4=x → float. 100+ call sites. |
| 0x00002150 | `table3d_lookup_dispatch` | **Central two-axis (bilinear) lookup.** r4=descriptor, fr4=x, fr5=y → float. |
| 0x000026E0 | `axis_index_search_float` | Walks float axis down; returns index (r0) + fraction (fr0). |
| 0x000027D0 | `axis_pair_index_search` | Runs axis search for both axes (r2/r3 idx, fr0/fr1 frac). |
| 0x00002118 | `table2d_lookup_u16_raw_int` | 1-axis u16 lookup, truncated to int, no rescale. |
| 0x000020E0 | `table2d_lookup_u8_raw_int` | 1-axis u8 lookup → int. |
| 0x00002194 / 0x000021B0 | `table3d_lookup_u8/u16_raw_int` | 2-axis integer variants. |
| 0x000027F0/2858/28A4/28C8/2838 | `interp_1axis_float32/u8/u16/s8/s16` | Leaf linear interp (fmac). Jump table @0x20CC. |
| 0x000025F8/2684/26B0/2628/2654 | 2-axis leaf handlers (float32/u8/u16/s8/s16) | Jump table @0x2180. 0x25F8/2628/2654 not defined as functions in Ghidra yet (jump-table-only targets) — rename pending. |

### Descriptor layouts

**1-axis (RomRaider "2D"):** `+0x00` u16 axis_len, `+0x02` u8 type, `+0x04` axis ptr
(float[]), `+0x08` data ptr, `+0x0C` float scale, `+0x10` float offset.
`result = scale*raw + offset` (skipped for type 0 = float32 data).
Type codes (byte = offset into handler fnptr table): 0=float32, 4=u8, 8=u16, 0xC=s8, 0x10=s16.
Type-0 descriptors may be packed to 0xC bytes (no scale fields).

**2-axis (RomRaider "3D"), stride 0x1C:** `+0x00` u16 xlen, `+0x02` u16 ylen,
`+0x04` xaxis ptr, `+0x08` yaxis ptr, `+0x0C` data ptr, `+0x10` u8 type,
`+0x14` float scale, `+0x18` float offset.

### Table→code recipe (THE unlock — old "dead end" was mid-struct queries)

1. `get_xrefs_to(table_data_addr)` → returns the descriptor **data-ptr slot**.
2. Subtract to descriptor **start**: slot−0x08 (1-axis) or slot−0x0C (2-axis).
3. `get_xrefs_to(descriptor_start)` → literal-pool ref in the **consumer function** (shows as [PARAM]/[DATA]).

Verified: Base Timing A data 0x78AA0 → slot 0x60114 → desc 0x60108 → consumer 0x28418.

## 4. Ignition Timing Architecture (SOLVED)

| Address | Name |
|---|---|
| 0x00028418 | `ign_base_timing_map_blend` |
| 0x000284B8 | `ign_base_timing_select` |
| 0x00028354 | `ign_avcs_tracking_blend_factor_update` |
| 0x000281FC | `ign_map_switch_flag_debounce` |
| 0x00027DE8 | `ign_idle_timing_blend_factor_update` |
| 0x00027F3E | `ign_idle_timing_target_update` |
| 0x00028166 | `ign_base_and_idle_timing_update` |
| 0x000279CC | `ign_final_timing_per_cylinder_update` |

- Six 3D maps via consecutive descriptors (stride 0x1C): **A**=0x60108, **B**=0x60124,
  **C**=0x60140, **D**=0x6015C, **E**=0x60178, **F**=0x60194. All u8,
  `deg = 0.3515625*raw − 20`, common X axis 0x780BC. C and F have 20-row Y axes (rest 14).
- Raw results → RAM 0xFFFFC154/C158/C15C (A,B,C) and 0xFFFFC160/C164/C168 (D,E,F).
- **Blend:** k = float @ **0xFFFFC17C**; outputs
  `0xFFFFC16C = A*k + D*(1−k)`, `0xFFFFC170 = B*k + E*(1−k)`, `0xFFFFC174 = C*k + F*(1−k)`.
  A/B/C are the AVCS-tracking-ratio-1.0 endpoints; D/E/F are the ratio-0.0 endpoints.
- **k computation** (`0x28354`):
  `k = clamp((float@0xFFFFC8C8 + float@0xFFFFC8CC) /
  (float@0xFFFFC974 + float@0xFFFFC978), 0, 1)`. The numerator is summed measured
  left/right intake AVCS angle and the denominator is summed conditioned/commanded target.
  A near-zero target sum produces 0; verified status paths can force 1. This is AVCS
  tracking, **not IAM**.
- **Selection** (`0x284B8`) → selected base timing @ **0xFFFFC184**:
  - default: A/D blend (0xFFFFC16C)
  - B/E (0xFFFFC170) requires callback `constant_zero_return` at **0x27088** to return 1
    and bit 0x80 of flag byte 0xFFFFC180. Canonical D2WD610H implements that callback as
    `rts; mov #0,r0`, so B/E is dormant/unreachable in the stock ROM.
  - **C/F (0xFFFFC174) when cam mode @0xFFFFCD86 == 3 (high cam) and debounced bit 0x40
    of 0xFFFFC180** → C/F are the AVLS high-cam maps (hence 20 rows).
  - Final (after extra 1-axis lookup, desc 0x5FC18) → 0xFFFFC150 and 0xFFFFC188.
- Active definition identities are therefore **A/D = normal/AVLS-low-cam
  AVCS-tracking-ratio 1.0/0.0 endpoints** and **C/F = AVLS-high-cam
  AVCS-tracking-ratio 1.0/0.0 endpoints**. The master definition uses those functional names and
  omits dormant B/E. These are cam-phasing endpoints; neither member of a pair has a universal
  requirement to be more advanced or retarded than the other.
- `knock_correction_advance_max_select` at **0x3EB68** independently selects KCA Max A for
  normal cam and KCA Max B for the same verified AVLS-high-cam state.
- Flag debounce (`0x281FC`): bit 0x40 set after mode==3 held for a delay from 2D u16 table
  desc **0x5FFF8**; cleared on 3→1. Bit 0x80 via counter vs ROM u16 @0x77D34.
- The idle path was traced through `ign_idle_timing_blend_factor_update`,
  `ign_idle_timing_target_update`, and `ign_base_and_idle_timing_update`. The idle target checks
  vehicle-speed float **0xFFFFB538** against the `Base Timing Idle Vehicle Speed Threshold` at
  **0x77E1C** (stock 4.0 km/h), confirming the RAM signal's meaning.
- `ign_final_timing_per_cylinder_update` adds a common timing sum to six per-cylinder correction
  floats at **0xFFFFCCC8..0xFFFFCCDC**, then applies the stock clamps and publishes six final
  angles at **0xFFFFC0EC..0xFFFFC100**. Periodic task-pointer slot **0x11E30** points to this
  function in stock.
- The six final values feed `ign_timing_cylinder_minimum_check_update` (`0x28C38`),
  `ign_cylinder_timing_to_schedule_count` (`0x2A2BC`),
  `ign_current_cylinder_timing_select_update` (`0x3E45C`), and
  `ign_timing_logger_convert` (`0x4F1C4`). The normal ignition-timing logger reads the first
  output at `0xFFFFC0EC`.
- The correction-array state path is
  `ign_per_cylinder_correction_enable_latch_update` (`0x3D7E4`),
  `ign_per_cylinder_correction_array_update` (`0x3D824`),
  `ign_per_cylinder_correction_state_clear` (`0x3D8E2`),
  `ign_per_cylinder_correction_state_any_active` (`0x3D916`),
  `ign_per_cylinder_correction_initialize` (`0x3D95A`), and
  `ign_per_cylinder_correction_array_clear` (`0x3D980`).

## 5. AVLS (variable lift) — SOLVED except final port write

| Address | Name |
|---|---|
| 0x0003FFDA | `avls_threshold_curve_selector_state_update` |
| 0x000400EE | `avls_curve_selector_oil_temp_band_latches_update` |
| 0x00040168 | `avls_cam_mode_state_machine` |
| 0x000405B2 | `avls_mode_commit_copy` (0xFFFFCD87 → 0xFFFFCD86) |
| 0x000405CC | `avls_osv_actuation_gate` |
| 0x00040C94/40798/40CE6 | `cam_actuator_output_set_1/2/3` (called with 0|1) |

### Intake AVCS target maps A/B

`intake_avcs_target_by_avls_mode_update` at **0x353B0** directly consumes both
target descriptors. Committed AVLS mode **0xFFFFCD86 == 1** selects descriptor
**0x60C34**, data **0x7C5B0** (legacy AVCS A); mode **3** selects descriptor
**0x60C50**, data **0x7C764** (legacy AVCS B). A is therefore the intake AVCS
target for AVLS low lift and B is the target for AVLS high lift. They are not
left/right-bank maps and are selected by lift state, not blended together.

Both maps use the same 14-point load axis at 0x7C54C/0x7C6E4:
0.35, 0.45, 0.55, 0.70, 0.83, 0.96, 1.09, 1.22, 1.35, 1.48, 1.61, 1.74,
1.87, and 2.00 g/rev. A has 11 RPM rows (500..4000) at **0x7C584**; B has 18
rows (1000..6800) at **0x7C71C**. The native lookup clamps above the final axis
breakpoint, so loads above 2.00 g/rev use the last column unless those 14
breakpoints are rescaled. `intake_avcs_tracking_control_update` at **0x35750**
is the downstream per-bank tracking/control path.

**RAM cells:** target mode **0xFFFFCD87** (1=low cam, 3=high cam), committed **0xFFFFCD86**,
operating state 0xFFFFCD9C (curve selector: 2=curve 1, 3=curve 2), mode timer 0xFFFFCD84
(u16, reload from ROM @0x7D468, −1/tick), hysteresis flags 0xFFFFCD9E
(mask 0x04 = RPM>4000 latch, mask 0x10 = engine running),
status latch 0xFFFFCD8F, threshold caches 0xFFFFCD94/0xFFFFCD98, defer flag 0xFFFFCD9D.

**Switchover is a vehicle-speed-vs-RPM boundary, not an engine-load map:**

| Item | ROM addr | Value |
|---|---|---|
| Normal-oil-temperature speed data (7×float) | **0x7D67C** | 100,100,30,28,25,15,5 km/h |
| Table 1 X axis (RPM, 7×float) | 0x7D660 | 1600,2000,2400,2800,3200,3600,4000 |
| High-oil-temperature speed data (7×float) | **0x7D6B4** | 100,100,90,50,30,10,0 km/h |
| Table 2 X axis (RPM, 7×float) | 0x7D698 | 2000,2050,2400,2800,3200,3600,4000 |
| Hard high-cam engage RPM | **0x7D4BC** | float 4000.0 |
| Hard release RPM (hysteresis) | **0x7D4B8** | float 3800.0 |
| Vehicle-speed hysteresis offsets | 0x7D480/0x7D484 | 10.0 / 10.0 km/h |
| Oil-temperature selector bands | 0x7D488..0x7D494 | 13/15 and 113/115 degrees C |
| Actuation RPM gate | 0x7D4AC | 3000.0 |
| Engine-run RPM gate | 0x7D4A8/0x7D4A4 | 512.0 / 510.0 |
| Sentinel band (table-result check) | 0x7D4A0/0x7D49C | 10000.0 / 9000.0 |
| Fallback thresholds | 0x7D4B0/0x7D4B4 | 15.0 / 15.0 |
| Mode timer reload (u16) | 0x7D468 | — |

`engine_oil_temperature_sensor_process` at **0xF474** converts ADC **0xFFFFAB12** through
descriptor **0x60950** (voltage axis **0x7B748**, temperature data **0x7B7C4**) and writes
**0xFFFFB124** in degrees C. The 31-point transfer spans -40 through 150 degrees C, and this
CALID's P0197/P0198 switches identify it as engine-oil temperature. At **0x47000**,
`engine_oil_temperature_fallback_select` validates that signal and publishes **0xFFFFCF94**;
fault/startup paths substitute the stock 70 degrees C value at 0x73B88/0x73B8C.

`avls_curve_selector_oil_temp_band_latches_update` applies oil-temperature hysteresis to
**0xFFFFCF94**: the first latch sets at 15 degrees C and clears below 13; the second sets at 115
and clears below 113. Subject to runtime-status and delay gates,
`avls_threshold_curve_selector_state_update` publishes selector state 1 for cold/fallback,
state 2 for the normal oil-temperature band, or state 3 for the hot band. State 1 uses fixed
15 km/h fallback boundaries; state 2 selects the normal-temperature curve and state 3 selects
the high-temperature curve.

Descriptors: table 1 = **0x60F58**, table 2 = **0x60F64** (compact 0xC float type).
RPM input is float @ **0xFFFFB544**. The curve path compares conditioned vehicle speed
**0xFFFFB46C** in km/h: selector state **0xFFFFCD9C == 2** chooses the normal-temperature curve;
state **3** chooses the high-temperature curve. From low lift, high lift is requested at
`speed >= curve + 10 km/h`; from high lift, low lift is requested at `speed < curve`. Thus the
two tables are oil-temperature-selected curves, **not** engage/release counterparts. State 1
uses fixed 15 km/h thresholds at 0x7D4B0/0x7D4B4.

The genuine table load signal is separate. `maf_airflow_temperature_compensation_update` writes
mass airflow **0xFFFFB420** in g/s, calculates raw load **0xFFFFB428** as
`airflow_g_s * 60 / RPM`, and conditions it into **0xFFFFB438** in g/rev. AVCS, ignition,
fuel, and knock tables consume B438. The master speed-density helper supplies B420 in g/s and
retains this stock normalization, so its g/rev load scaling remains correct; it simply does not
control the AVLS lift-state boundary.

Definition layout:

- `defs/D2WD610H.xml` is the retained base metric EcuFlash definition.
- `defs/D2WD610H_AVLS.xml` is the AVLS-only custom RomRaider definition.
- `defs/D2WD610H_AVLS_boost_patch.xml` contains the same D2WD610H + AVLS definition plus the
  canonical boost-patch tables and independent EBCS/hard-cut enable bytes.
- `speed_density/D2WD610H_AVLS_speed_density_patch.xml` is the single standalone MAFless
  component input used by the master definition generator. It contains committed-state
  low/high-lift VE and fixed 3200/3000-RPM AVLS hysteresis.
- `master_patch/D2WD610H_master_patch.xml` is the current focused integration definition. It
  retains only relevant engine-tuning controls plus AVLS, SD/VE, exact Omni MAP, boost, and AEM
  input calibration, fueling safeties, and rotational idle; it renames the active timing/KCA paths
  and the AVCS A/B targets by their verified roles, and removes obsolete MAF/O2/DTC, readiness,
  fuel-temperature, and dormant B/E entries. Retired single-front, rotational-only, and old
  combined XML files are no longer committed.
- `defs/romraider_ecu_defs.xml` is a clean upstream metric RomRaider snapshot and is not modified
  with project tables.

All seven custom RomRaider ROM files are self-contained. The legacy variants embed metric
`32BITBASE` pruned to the standard D2WD610H overrides; the master prunes that set further for its
changed hardware architecture. Load only the custom ROM variant matching the image being edited.
Stock AVLS values were verified against the ROM image 2026-07-14.

**Open sub-item:** the final OSV port write. `cam_actuator_output_set_*` descend into
float target/feedback layers (AVCS-style continuous control mixed in); the binary port
bit is likely flushed by a central output-image task. Next session: xref SH7055 port
data registers (datasheet) instead of descending the call tree.

## 6. Key RAM anchors (confirmed this session)

| RAM addr | Meaning | Evidence |
|---|---|---|
| **0xFFFFB544** | Engine RPM (float) | compared vs 4000/3800/512/510 rpm consts; input to switch tables; used across ign+AVLS |
| **0xFFFFB538** | Vehicle speed (float, km/h) | `ign_idle_timing_target_update` compares it with stock 4.0-km/h idle-timing threshold @0x77E1C; also consumed by AVLS logic |
| **0xFFFFB3B8** | Intake-air temperature (float, degrees C) | written by `intake_air_temperature_update` @0x16D1C; passed into stock MAF-IAT compensation descriptor 0x5EB88 |
| **0xFFFFB420** | Final post-compensation mass airflow (float, g/s) | written at 0x1739E in `maf_airflow_temperature_compensation_update`; broad fuel/load consumer xrefs include 0x1B800 and 0x216EA |
| **0xFFFFB46C** | Conditioned AVLS vehicle-speed signal in km/h (snapshot of filtered 0xFFFFB4C8) | compared against oil-temperature-selected curves in 0x40168 |
| **0xFFFFB124** | Converted engine-oil temperature in degrees C | ADC AB12 through descriptor 0x60950 in 0xF474 |
| **0xFFFFCF94** | Validated engine-oil temperature, or 70 C fallback | selector latches at 13/15 and 113/115 C in 0x400EE |
| 0xFFFFC17C | Ignition AVCS-tracking blend factor k (float 0..1) | written 0x28354 |
| 0xFFFFC8C8/0xFFFFC8CC | Measured intake AVCS angles, left/right | numerator at 0x28354 |
| 0xFFFFC974/0xFFFFC978 | Conditioned/commanded intake AVCS targets, left/right | denominator at 0x28354 |
| 0xFFFFC984 | Common AVCS target selected by committed AVLS mode | written 0x353B0 |
| 0xFFFFC184 | Selected base timing (deg, float) | 0x284B8 |
| 0xFFFFC150 / 0xFFFFC188 | Final base timing after extra lookup | 0x284B8 |
| 0xFFFFCCC8..0xFFFFCCDC | Six per-cylinder ignition correction floats | written/cleared by 0x3D824/0x3D980; consumed by 0x279CC |
| 0xFFFFC0EC..0xFFFFC100 | Six final per-cylinder ignition angles | produced by 0x279CC; consumed by scheduling/current-cylinder/logger paths |
| 0xFFFFCD86/87 | AVLS cam mode committed/target (1 low, 3 high) | 0x40168/0x405B2 |
| 0xFFFFB528 | Phase/crank counter used to sync OSV actuation | 0x405CC |

## 7. Open Targets / TODO

- [x] Central table-interpolation routines (2D+3D, all handlers) — DONE
- [x] Timing selection + blend math — DONE (see §4)
- [x] AVLS switchover thresholds + def entries — DONE (see §5)
- [ ] AVLS: physical OSV port write (via SH7055 port register xrefs — datasheet needed)
- [x] AVLS curve direction — resolved: curve selected by 0xFFFFCD9C state 2/3; each uses
      +10 engage hysteresis and its raw curve for release (not an engage/release table pair)
- [x] **Single-front-A/F plus rear-O2-delete path — standalone development patch built.** The stock RH/Bank-1
      front A/F process remains intact, with processed lambda/current/readiness mirrored to the
      Bank-2 RAM paths after stock processing. Bank-2 inhibit checks reuse the unchanged Bank-1
      helper. Exact enable `01` bypasses the rear ADC converter and five traced monitor stages,
      and disables eight mapped rear sensor/heater DTC switches. The
      post-turbo wideband is recorded by an external logger and has no ECU input or ROM code.
      See `single_front_af_patch.md`. The stock CL/OL state flag remains `0xFFFFBE38`; the patch
      does not replace normal CL/OL transition logic.
- [x] **Boost repurpose of EVAP purge output — purge chain FOUND** (see `boost_repurpose_notes.md`
      for full chain + patch plan). Purge = temp-scheduled duty PWM in the emissions aux slow task.
      Duty compute `evap_purge_duty_compute` @0x3FC0A (state m/c 0xFFFFCD77, ECT 0xFFFFB3AC, maps
      desc 0x609C4/0x609D8) → duty%% RAM 0xFFFFCD54 → output stage `evap_purge_pwm_output_write`
      @0xE8C4 → **physical PWM register 0xFFFFF590** (ATU-II), period RAM 0xFFFFAB84. Diagnostic
      `evap_purge_flow_diagnostic` @0x46748. DTCs P0458 0x5BD85 / P0459 0x5BD86. Confidence HIGH.
      The controller/hijack, DTC handling, checksum, and master AEM/SD prerequisite gate are built;
      remaining work is harness continuity, datalog/scope proof, PWM-frequency/polarity testing,
      wastegate plumbing, and physical soft/hard-limit commissioning.
      NOTE: the crank-synced 6-ch bank (0x96FC/0x268E8, 0xFFFFF602/0xFFFFF652+2n) is AVCS/AVLS cam,
      NOT purge (earlier mis-ID, corrected).
- [ ] AVLS physical OSV port write — **likely resolved**: OSV/OCV solenoids are driven by the
      crank-angle-synced bank above (ATU-II compare 0xFFFFF652+2n, ctrl bit on 0xFFFFF602).
      Confirm which of the 6 channels `avls_cam_mode_state_machine` (0x40168) commands.
- [x] The earlier combined/single-front experiment retired its ECU-side aftermarket-wideband
      input. This is retained as historical documentation only and is superseded by the current
      `master_patch`, which deliberately uses the former MAF ADC for one external 0--5 V lambda
      controller and publishes explicit lambda/raw/readiness logger parameters.
- [x] Combined stock-to-ROM builder and definition created. `patch/patch_combined.py` applies both
      guarded components to one fresh stock copy; `verify_combined.py` proves the 811 changed bytes
      are the exact 369 + 442 union with zero overlap. Hardware use remains gated on both standalone
      commissioning plans.
- [x] **Rotational-idle component integrated in the current master.** `patch_rotational_idle.py` wraps the complete
      stock task at 0x279CC through task-pointer slot 0x11E30, defaults OFF, and applies bounded
      retard-only six-cylinder offsets only inside the calibrated warm/stationary idle window.
      `verify_rotational_idle.py` proves exact binary ownership and policy behavior; the master
      verifier proves its hook and flash allocation are collision-free. The switch defaults OFF.
- [x] **MAFless speed density integrated in the current master.** The stock raw-MAF
      converter `maf_sensor_voltage_to_airflow_process` (`0x7C30`) is no longer called from
      `0x639C` or `0x66D8`; the scheduled raw-MAF limit/filter call at `0x107F8` is also removed.
      Periodic pointer `0x11D20` retains `maf_airflow_temperature_compensation_update`
      (`0x172A4`) for its downstream `B428..B440` load/filter state. Its final-airflow helper
      pointer at `0x1743C` is redirected to the SD calculation at `0x7E18C` before the B420 store.
      The helper uses guarded committed-AVLS low/high MAP/RPM VE surfaces and IAT density correction, with no MAF fallback
      or runtime OFF state; exact zero RPM writes zero and other invalid states write a fixed
      500 g/s rich/high-load fail-safe. The MAF high/low diagnostic task and both MAF-dependent
      temperature-condition calls are bypassed, and P0102/P0103 are disabled. Its reusable
      component API is integrated by `master_patch`; standalone output is only a local regression.
      See `../speed_density/README.md`.
- [x] **Current master composition built and audited.** `master_patch` reconstructs only from
      canonical stock, installs the MAFless model, Omni MAP-SUP-3BR transfer, EVAP-output boost
      control and gates, one former-MAF external-wideband producer for both fuel banks, complete
      traced four-stock-O2 signal/diagnostic removal, STI-pink injector data, dual AVLS-state
      VE/fueling/timing, fixed 3200/3000-RPM AVLS, and the 6800-RPM limiter. The focused definition exposes only active
      A/D and C/F timing identities plus relevant tune/patch tables. This remains a static
      development baseline requiring bench/dyno validation, not vehicle proof.
- [ ] Define 0x25F8/0x2628/0x2654 as functions in Ghidra and rename (interp_2axis_float32/s8/s16)
- [x] Identify status functions at 0x27088/0x6504C and B/E condition: 0x27088 is a constant-zero
      return, making B/E unreachable; 0x6504C returns 2/0 from 0xFFFFD26D bit 0x20.

## 8. Rename Log (Ghidra, applied)

_(underscore names only — strict naming enforcement is ON)_
- 0x00010690 → **fnptr_task_list_dispatch** — init/scheduler sequential fn-ptr caller
- 0x0000b536 → **fp_support_helper** — SH-2E FP register support
- 0x0000209C → **table2d_lookup_dispatch**
- 0x00002150 → **table3d_lookup_dispatch**
- 0x000026E0 → **axis_index_search_float**
- 0x000027D0 → **axis_pair_index_search**
- 0x00002118 → **table2d_lookup_u16_raw_int**
- 0x000020E0 → **table2d_lookup_u8_raw_int**
- 0x00002194 → **table3d_lookup_u8_raw_int**
- 0x000021B0 → **table3d_lookup_u16_raw_int**
- 0x000027F0 → **interp_1axis_float32**, 0x2858 → **interp_1axis_u8**, 0x28A4 → **interp_1axis_u16**, 0x28C8 → **interp_1axis_s8**, 0x2838 → **interp_1axis_s16**
- 0x00002684 → **interp_2axis_u8**, 0x26B0 → **interp_2axis_u16** (0x25F8/2628/2654 pending function definition)
- 0x00028418 → **ign_base_timing_map_blend**
- 0x000284B8 → **ign_base_timing_select**
- 0x00027088 → **constant_zero_return** (exact `rts; mov #0,r0`; makes the B/E timing
  selector condition unreachable in canonical stock)
- 0x0006504C → **runtime_status_d26d_bit5_get** (returns 2 when 0xFFFFD26D bit 0x20 is set,
  otherwise 0)
- 0x00002458 → **float_divide_guarded**
- 0x000024C0 → **float_clamp**
- 0x000024FC → **float_difference_exceeds_tolerance**
- 0x00028354 → **ign_avcs_tracking_blend_factor_update**
- 0x000281FC → **ign_map_switch_flag_debounce**
- 0x00027DE8 → **ign_idle_timing_blend_factor_update**
- 0x00027F3E → **ign_idle_timing_target_update**
- 0x00028166 → **ign_base_and_idle_timing_update**
- 0x000279CC → **ign_final_timing_per_cylinder_update**
- 0x0003D7E4 → **ign_per_cylinder_correction_enable_latch_update**
- 0x0003D824 → **ign_per_cylinder_correction_array_update**
- 0x0003D8E2 → **ign_per_cylinder_correction_state_clear**
- 0x0003D916 → **ign_per_cylinder_correction_state_any_active**
- 0x0003D95A → **ign_per_cylinder_correction_initialize**
- 0x0003D980 → **ign_per_cylinder_correction_array_clear**
- 0x00028C38 → **ign_timing_cylinder_minimum_check_update**
- 0x0002A2BC → **ign_cylinder_timing_to_schedule_count**
- 0x0003E45C → **ign_current_cylinder_timing_select_update**
- 0x0004F1C4 → **ign_timing_logger_convert**
- 0x000482DC → **runtime_signal_fixedpoint_export_update**
- 0x00040168 → **avls_cam_mode_state_machine**
- 0x000405B2 → **avls_mode_commit_copy**
- 0x000405CC → **avls_osv_actuation_gate**
- 0x00040C94/40798/40CE6 → **cam_actuator_output_set_1/2/3**
- 0x00022756 → **cl_ol_transition_delay_update**
- 0x000096FC → **solenoid_pwm_channel_drive** (crank-angle-synced 6-ch PWM HW driver; AVCS/AVLS; table @0xFAE8)
- 0x000268E8 → **solenoid_channel_output_update** (per-channel duty→count + inhibit gate)
- 0x00026DFC → **solenoid_status_word_read** (returns solenoid inhibit word @0xFFFFB744)
  (Note: this bank is cam/valve-timing solenoids, not purge — scheduler 0x263EE, 30°×24 phase.)
- 0x0003FC0A → **evap_purge_duty_compute** (purge duty schedule; state m/c 0xFFFFCD77 → duty 0xFFFFCD54)
- 0x0003F9E4 → **evap_purge_state_update** (purge enable/status byte 0xFFFFCD81)
- 0x0000E8C4 → **evap_purge_pwm_output_write** (duty ratio → ATU-II reg 0xFFFFF590; period 0xFFFFAB84)
- 0x00046748 → **evap_purge_flow_diagnostic** (rationality/circuit monitor → P0458/P0459)
- 0x00007A14 → **map_sensor_voltage_to_pressure_process** (sensor voltage × multiplier + offset → native mmHg absolute at RAM 0xFFFFABC4; boost feedback source)
- 0x00007A56 → **map_sensor_raw_adc_range_classify** (raw MAP ADC 0xFFFFABC8 against
  0x7B284/0x7B286 high/low thresholds)
- 0x000078AC → **analog_sensor_abac_range_classify**
- 0x000079B4 → **analog_sensor_abbc_range_classify**
- 0x00002390 → **fixedpoint_mul_q16_sat**
- 0x00024B24 → **rev_limiter_fuel_cut** (RPM vs Rev Limit A/B → sets fuel-cut flag 0xFFFFBF6C bit0x80)
- 0x00023FC0 → **fuel_cut_flag_aggregate** (ORs cut conditions → master fuel cut)
- 0x0004FB8C → **rom_checksum_accumulate** (sums flash up to free-space boundary 0x7D790) (generic 16.16 fixed-point multiply w/ saturation; PWM on-time)
- 0x000114B0 → **slow_task_dispatcher** (~50 fn-ptr sequential caller, slow loop)
- 0x0003F878 → **radiator_fan_mode_select** (fan mode 0-3 from ECT hysteresis; relay stages, not PWM)
- 0x000263EE → **solenoid_phase_scheduler** (crank-angle 30°×24 scheduler for cam solenoid bank)
- 0x00026320 → **solenoid_control_array_init** (inits 6 solenoid structs @0xFFFFBFB8 stride 0x28)
- 0x0001C5D4 → **solenoid_inhibit_word_build** (builds inhibit word 0xFFFFB744 from per-ch faults)
- 0x00024570 → **solenoid_circuit_diagnostic** (sets circuit-fault byte 0xFFFFBF21)
- 0x000182AC → **engine_load_compensation_update**
- 0x00017984 → **airflow_load_and_vehicle_speed_processing_sequence_update**
- 0x000179EE → **airflow_load_filter_state_initialize**
- 0x00017A24 → **airflow_load_filter_state_requires_initialization**
- 0x00018A68 → **vehicle_speed_conditioned_filter_update** (B4C0 → filtered km/h @0xFFFFB4C8)
- 0x00009FEC → **float_3d_table_consumer_update**
- 0x0000C5C8 → **cylinder_airflow_pair_update**
- 0x00017B2A → **airflow_bank_charge_update**
- 0x00017C40 → **airflow_bank_charge_diagnostic_update**
- 0x000180C6 → **engine_load_from_airflow_calculate**
- 0x000181EA → **engine_load_limit_update**
- 0x00018438 → **vehicle_speed_conditioning_status_flags_update**
- 0x000184CC → **vehicle_speed_conditioning_coefficient_set_a_update**
- 0x0001873C → **vehicle_speed_conditioning_coefficient_set_b_update**
- 0x000188F4 → **vehicle_speed_conditioned_source_update** (B538 km/h → B4C0)
- 0x0001B15E → **fuel_system_monitor_enable_update**
- 0x000216EA → **fueling_airflow_input_update**
- 0x000098CC → **injector_battery_voltage_latency_lookup** (descriptor 0x608D8; voltage
  axis 0x7B304; latency data 0x7B318)
- 0x0001E0C8 → **injector_flow_scaling_factor_update** (consumes flow scaling at 0x76014)
- 0x0000A9A8 → **injector_control_lookup_sequence_a9a8**
- 0x0003EB68 → **knock_correction_advance_max_select** (KCA A normal cam / KCA B AVLS high cam)
- 0x000024B0 → **float_minimum_select** (returns the lower float; confirmed while tracing AVLS)
- 0x0003FDBC → **avls_control_sequence_update** (request state machine, commit copy, then OSV gate)
- 0x000405B2 → **avls_mode_commit_copy** (CD87 requested mode → CD86 committed mode)
- 0x000405CC → **avls_osv_actuation_gate** (retained timing/status gate for lift actuation)
- 0x0003FFDA → **avls_threshold_curve_selector_state_update**
- 0x000400EE → **avls_curve_selector_oil_temp_band_latches_update**
- 0x00018AEA → **vehicle_speed_conditioned_snapshot_copy** (B4C8 → AVLS km/h compare B46C)
- 0x0000F474 → **engine_oil_temperature_sensor_process** (AB12 → B124 degrees C)
- 0x0003253C → **engine_oil_temperature_logger_convert**
- 0x00047000 → **engine_oil_temperature_fallback_select** (B124 or 70 C → CF94)
- 0x00014DCC → **throttle_position_sensor_process** (DBW throttle sensor plausibility/processing;
  produces processed throttle opening @0xFFFFB314 used by CL/OL logic and boost demand gate)
- 0x00007C30 → **maf_sensor_voltage_to_airflow_process** (raw MAF ADC 0xFFFFAB06 through
  descriptor 0x60914 / scaling table 0x7B568 to raw airflow 0xFFFFABE4)
- 0x000172A4 → **maf_airflow_temperature_compensation_update** (stock airflow/IAT/limit
  processing retained for downstream load/state; helper literal 0x1743C is redirected to SD
  immediately before final mass-airflow write 0xFFFFB420 at 0x1739E)
- 0x00017726 → **maf_airflow_limit_update** (moves raw MAF into the stock filtered/fallback
  airflow channels before the main compensation task)
- 0x000107EE → **periodic_airflow_sensor_task_dispatcher** (scheduled sensor/condition group;
  contains the sole `maf_airflow_limit_update` call at 0x107F8, NOP'd by the MAFless image)
- 0x00007C52 → **maf_sensor_input_range_classify** (returns high/normal/low classification from
  raw MAF ADC 0xFFFFAB06 against the 0x7B29C/0x7B29E thresholds)
- 0x00061328 → **maf_sensor_input_diagnostic_update** (common MAF input diagnostic entry)
- 0x00061332 → **maf_sensor_high_input_diagnostic_update** (classification 1/high-input path;
  mapped D2WD610H switch is P0103)
- 0x000613AC → **maf_sensor_low_input_diagnostic_update** (classification 2/low-input path;
  mapped D2WD610H switch is P0102)
- 0x000066C2 → **sensor_processing_return_stub**
- 0x00006328 → **sensor_processing_batch_task** (first sensor-processing batch containing the
  raw MAF converter call at 0x639C; that call is NOP'd by the MAFless image)
- 0x000066C6 → **sensor_adc_processing_task** (sensor conversion dispatcher containing the raw
  MAF converter call at 0x66D8; that call is NOP'd by the MAFless image)
- 0x000316A2 / 0x000316BA → **mass_airflow_logger_high_byte_get** /
  **mass_airflow_logger_low_byte_get**
- 0x00031790 → **maf_sensor_raw_adc_logger_value_get**
- 0x0007266C → **diagnostic_temperature_maf_condition_flag_update** (diagnostic condition flag
  using converted temperature signals, raw MAF ADC, and ADC status bits)
- 0x0000786C → **intake_air_temperature_adc_conversion**
- 0x00007974 → **engine_coolant_temperature_adc_conversion**
- 0x00016CA4 → **engine_coolant_temperature_output_update**
- 0x00013394 → **periodic_diagnostic_task_rate_dispatcher**
- 0x000115EA → **diagnostic_task_list_dispatcher** (sequential diagnostic task-pointer caller;
  MAF high/low entry is pointer 0x11804 and the mixed temperature/MAF condition is 0x1185C)
- 0x0001785C → **airflow_state_coolant_initialization**
- 0x000177BE → **mass_airflow_slow_filter_update** (retained downstream filter: final airflow
  0xFFFFB420 to filtered airflow 0xFFFFB424; sole computed call is 0x114D2)
- 0x0001F8CA → **closed_loop_fuel_control_airflow_tables_update**
- 0x0001BAF0 → **fuel_trim_correction_mode_dispatch**
- 0x0001BCCA → **fuel_trim_airflow_table_mode_update**
- 0x0002300A → **airflow_monitor_periodic_update**
- 0x000230E8 → **airflow_monitor_accumulator_update**
- 0x0002333C → **airflow_based_monitor_conditions_update**
- 0x000235D6 → **airflow_vehicle_speed_monitor_state_update**
- 0x000374F0 → **airflow_rpm_diagnostic_monitor_update**
- 0x00046A48 → **airflow_operating_condition_monitor_update**
- 0x0004F014 → **mass_airflow_scaled_output_update**
- 0x00070CD6 → **airflow_temperature_monitor_bit80_update**
- 0x00071104 → **airflow_temperature_monitor_bit40_update**
- 0x00016D1C → **intake_air_temperature_update** (updates IAT 0xFFFFB3B8 in degrees C)
- 0x0001B800 → **engine_load_from_mass_airflow_calculate** (reads RPM 0xFFFFB544, final mass
  airflow 0xFFFFB420, and throttle 0xFFFFB314; confirms the SD write feeds stock load logic)
- 0x00011AD0 → **periodic_engine_control_task_dispatcher** (computed-call dispatcher whose
  pointer array contains the stock airflow slot at 0x11D20)
- Confirmed filtered-airflow `0xFFFFB424` consumers:
  - 0x0002FFA8 → **filtered_mass_airflow_consumer_2ffa8**
  - 0x0004F1FA → **filtered_mass_airflow_logger_convert**
  - 0x000673C6 → **filtered_mass_airflow_consumer_673c6**
  - 0x0002212C → **filtered_mass_airflow_consumer_2212c**
  - 0x00021C50 → **filtered_mass_airflow_consumer_21c50**
- Confirmed compensated-load `0xFFFFB430` consumer:
  - 0x00012F10 → **compensated_engine_load_consumer_12f10**
- Confirmed load `0xFFFFB438` consumers. These conservative names record the recovered channel
  dependency without guessing a narrower subsystem purpose:
  - 0x0003DA30 → **engine_load_dependent_update_3da30**
  - 0x0003EA94 → **engine_load_dependent_update_3ea94**
  - 0x0003DAA6 → **engine_load_dependent_update_3daa6**
  - 0x0003E1C8 → **engine_load_dependent_update_3e1c8**
  - 0x000289E0 → **engine_load_dependent_update_289e0**
  - 0x000135C4 → **engine_load_dependent_update_135c4**
  - 0x000498B0 → **engine_load_dependent_update_498b0**
  - 0x00024CB0 → **engine_load_dependent_update_24cb0**
  - 0x0003DA60 → **engine_load_dependent_update_3da60**
  - 0x0003EACE → **engine_load_dependent_update_3eace**
  - 0x000353B0 → **intake_avcs_target_by_avls_mode_update**
  - 0x0003E20E → **engine_load_dependent_update_3e20e**
  - 0x00029024 → **engine_load_dependent_update_29024**
  - 0x00022454 → **primary_open_loop_fueling_target_update**
  - 0x0002046C → **engine_load_dependent_update_2046c**
  - 0x0003DEF0 → **engine_load_dependent_update_3def0**
  - 0x000666EC → **engine_load_and_delta_dependent_update_666ec**
  - 0x000672E4 → **engine_load_dependent_update_672e4**
  - 0x0002FB50 → **engine_load_dependent_update_2fb50**
  - 0x0001496C → **engine_load_dependent_update_1496c**
  - 0x0003E7DC → **engine_load_dependent_update_3e7dc**
  - 0x0003EBDC → **engine_load_dependent_update_3ebdc**
  - 0x0001E7E8 → **engine_load_dependent_update_1e7e8**
  - 0x00046D74 → **engine_load_dependent_update_46d74**
  - 0x000217B8 → **engine_load_and_filtered_airflow_update_217b8**
  - 0x0001E5E8 → **engine_load_dependent_update_1e5e8**
  - 0x0006BBA2 → **engine_load_dependent_update_6bba2**
  - 0x0006BFDC → **engine_load_dependent_update_6bfdc**
- Other retained airflow/load-state consumers:
  - 0x00023238 → **engine_load_delta_consumer_23238** (`0xFFFFB43C`)
  - 0x0001AF80 → **filtered_engine_load_consumer_1af80** (`0xFFFFB440`)
  - 0x000177DC → **airflow_state_flag_counter_update** (`0xFFFFB444`)
- 0x0000B690 → **front_af_sensor_pair_signal_process** (stock two-channel front A/F processing;
  single-front patch runs the complete body, then mirrors Bank 1 into Bank 2)
- 0x00001884 → **diagnostic_request_download_handle**
- 0x00013330 → **runtime_status_b6c0_bit7_is_set**
- 0x0001D228 → **runtime_status_b748_bit7_is_set**
- 0x000192A8 → **front_af_sensor_pump_current_pair_offset_clamp_update**
- 0x0000B8CC → **front_af_sensor_pump_current_diagnostic_update** (retained stock front-sensor
  diagnostic calculation; single-front task wrapper refreshes Bank-2 readiness afterward)
- 0x00064FD0 / 0x0006500C → **front_af_sensor_bank1_inhibit_check** /
  **front_af_sensor_bank2_inhibit_check** (single-front patch redirects the Bank-2 entry to a
  runtime selector: patch on uses Bank 1; patch off reconstructs stock Bank-2 semantics)
- 0x00018DAC → **front_af_sensor_lambda_condition_filter** (downstream conditioned factory
  lambda path producing the B4E8/B4EC logger values)
- 0x0001EE74 → **closed_loop_fuel_control_bank_update** (retained per-bank consumer; master
  patch deliberately feeds both banks from the same synthetic external-wideband lambda)
- 0x0001917A → **front_af_sensor_ready_status_pair_update**
- 0x0000B62A → **front_af_sensor_sample_task**
- 0x0000E0C8 → **rear_o2_sensor_pair_adc_task_thunk**
- 0x0000E0D0 → **rear_o2_sensor_pair_adc_convert** (AB20/AB0C rear-input scaling to B098/B09C;
  entry is now runtime-hooked by the single-front/rear-delete patch)
- 0x0000DFB4 → **rear_o2_sensor_bank_voltage_select** (bank-select getter for B098/B09C; traced
  consumers are the rear monitor pipeline and SSM/log conversion stubs)
- 0x00011270 → **diagnostic_monitor_update_dispatch** (task-pointer dispatcher containing all
  five rear pipeline slots used by the patch)
- 0x00033B12 → **rear_o2_sensor_monitor_threshold_update**
- 0x00033AAC → **rear_o2_sensor_pair_filter_delta_update**
- 0x00033964 → **rear_o2_sensor_response_integrator_initialize**
- 0x00033970 → **rear_o2_sensor_response_integrator_update**
- 0x00034BE4 → **rear_o2_sensor_response_ratio_update**
- 0x00069568 → **rear_o2_sensor_voltage_diagnostic_dispatch**
- 0x00069572 → **rear_o2_sensor_voltage_low_diagnostic_pair**
- 0x000697B4 → **rear_o2_sensor_voltage_high_diagnostic_pair**

Decompiler comments set at: 0x209C, 0x2150, 0x28418, 0x284B8, 0x40168, 0x405CC, 0x281FC,
0x27DE8, 0x27F3E, 0x28166, 0x279CC, 0x3D7E4, 0x3D824, 0x3D8E2, 0x3D916, 0x3D95A,
0x3D980, 0x28C38, 0x2A2BC, 0x3E45C, 0x4F1C4, 0x482DC,
0xB690, 0xE0D0, 0xB8CC, 0x64FD0, 0x6500C, 0x18DAC, 0x1917A, 0xDFB4, 0x33B12,
0x33AAC, 0x33964, 0x33970, 0x34BE4, 0x69568, 0x172A4, 0x1739E, 0x16D1C,
and 0x1B81E.

## 9. Session Log / Method Notes

- 2026-07-13: Interpolator found via literal-pool chain: xref descriptor-adjacent data →
  caller passes descriptor as PARAM → fnptr in pool → 0x209C. All goals 1–3 architecture
  decoded in one session using the table→code recipe (§3) + xxd literal-pool dumps (§2).
- Descriptor consumers show up as [PARAM] xrefs on the descriptor start; [DATA] xref next
  to it is the literal-pool word itself. Both point at the consumer function.
- RAM xrefs (sign-extended mov.w) are fully indexed by Ghidra — get_xrefs_to on
  0xFFFFxxxx addresses works and distinguishes READ/WRITE. This is the fastest way to
  walk producer→consumer chains (e.g. blend factor writer found instantly).
- Decompiler output is polluted by FPSCR_SZ/PR dual-path modeling; for precise operand
  tracking (which float compares against which constant) prefer `disassemble_function`.
- Datalog RAM anchor no longer needed — 0xFFFFB544 (RPM) confirmed statically from three
  independent comparison sites.
- 2026-07-14: initial oxygen-sensor tracing confirmed the front processed-result chain AE60/64,
  AE68/6C, AE70/74 -> B4E8/B4EC and the stock rear raw/result chain AB20/AB0C -> B098/B09C.
  That first revision retained the rear paths; it was superseded by the 2026-07-15 rear-delete
  revision below.
- 2026-07-14: both generated patches gained definition-backed runtime-enable bytes. The original
  boost switch used 0x7D80C; on 2026-08-21 it was split into EBCS at 0x7D80C (default OFF) and
  independent hard cut at 0x7D80D (default ON). Single-front A/F uses
  0x7D91C (`OFF` restores stock front and rear runtime paths). The switches do not undo the boost
  MAP calibration or the 13 single-front/rear-delete DTC bytes, respectively.
- 2026-07-14: retired ECU-side aftermarket-sensor annotations were replaced in the active Ghidra
  program. The established stock function names were re-applied while comments were updated to
  the then-current single-front-A/F design.
- 2026-07-15: rear narrowband removal trace completed in live Ghidra. `B098/B09C` have no found
  fuel-control consumer: their bank getter feeds the rear threshold/filter/response/voltage-DTC
  pipeline plus two logger stubs. Every inspected function was renamed with underscore names and
  the relevant decompiler comments were updated. The patch now hooks `0xE0D0`, redirects task
  pointers `0x11488/0x1148C/0x11490/0x11494/0x114A0` through exact-`01` no-op selectors, and disables
  P0037/P0038/P0057/P0058/P0137/P0138/P0157/P0158. The heater drivers themselves remain stock.
- 2026-07-15: final ignition path traced for the standalone rotational-idle experiment. The stock
  periodic pointer at `0x11E30` calls `ign_final_timing_per_cylinder_update` (`0x279CC`), which
  combines six corrections at `0xFFFFCCC8..CCDC` with the common timing result and writes six
  final angles at `0xFFFFC0EC..C100`. Producers and downstream scheduling/logger consumers were
  all renamed with underscore names. The separate default-OFF wrapper now runs the stock task
  first and applies only gated, bounded, retard-only post-processing; compatibility with the two
  existing components is verified in memory, but no combined artifact was changed.
- 2026-07-27/28: the speed-density airflow path was traced in the live stock Ghidra project. Raw
  MAF conversion runs at `0x7C30` from calls at `0x639C` and `0x66D8` and writes
  `0xFFFFABE4`; the stock limit and compensation chain
  ends at final-airflow RAM `0xFFFFB420`. IAT is `0xFFFFB3B8`, MAP is `0xFFFFABC4`, and periodic
  slot `0x11D20` targets `0x172A4`. The final MAFless revision retains that task for its
  downstream B428..B440 load/filter state, redirects final-airflow helper literal `0x1743C` to
  the guarded SD model, and NOPs both raw conversion calls plus the only scheduled raw-input
  `maf_airflow_limit_update` call. P0102/P0103 are disabled. The downstream
  `mass_airflow_slow_filter_update` remains active to filter B420 into B424. The input-diagnostic
  entries at `0x61328`, `0x61332`, and
  `0x613AC` were traced and renamed; classification 1 is the high/P0103 path and classification 2
  is the low/P0102 path. Their task pointer at `0x11804` is bypassed. Both task pointers to the
  mixed temperature/MAF condition at `0x7266C` (`0x1062C` and `0x1185C`) are also bypassed, so no
  diagnostic decision depends on the removed MAF ADC. Additional airflow consumers and monitor
  routines were traced and renamed. The standalone image remains byte-disjoint from boost,
  single-front/rear-delete, and rotational-idle components; the combined patch and base turbo map
  remain unchanged.
- 2026-08-21: master-patch timing validation completed against canonical stock in the live Ghidra
  project. `ign_base_timing_map_blend` still evaluates all A--F descriptors, but
  `ign_base_timing_select` defaults to A/D, selects C/F only for the verified AVLS-high-cam mode,
  and can select B/E only if callback 0x27088 returns 1. That callback was renamed
  `constant_zero_return` after confirming its complete body is `rts; mov #0,r0`; B/E is therefore
  unreachable in this stock calibration. Function 0x6504C was renamed
  `runtime_status_d26d_bit5_get` after confirming its 2/0 result from D26D bit 0x20. KCA selector
  0x3EB68 was renamed `knock_correction_advance_max_select`; it selects KCA A normally and KCA B
  for AVLS high cam. The master definition labels A/D and C/F by these real roles and omits B/E.
- 2026-08-21: MAP/injector validation completed. `map_sensor_voltage_to_pressure_process` reads
  the offset/multiplier pair at 0x72810 and publishes native mmHg absolute at ABC4;
  `map_sensor_raw_adc_range_classify` compares ABC8 with raw thresholds 0x7B284/286. The selected
  Omni MAP-SUP-3BR transfer is derived from 0.60 V = 30 kPa and 4.75 V = 300 kPa, yielding
  487.991938145 mmHg/V and -67.776658076 mmHg before float32 storage. The raw low-input CEL gate
  is reduced to 0.30 V to permit the SD model's deep-vacuum window; output below the supplier's
  published 30-kPa endpoint is extrapolated and must be pressure-tested. The stock 4.921 V high
  gate remains.
  Injector latency lookup 0x98CC and flow consumer 0x1E0C8 were renamed and tied directly to
  0x7B304/0x7B318 and 0x76014 respectively. The installed starting values remain translated from
  the hash-pinned factory STI A4TE002B donor rather than unverified catalogue data.
- 2026-08-21: single-external-wideband substitution was rechecked. The hardware ADC scan continues
  updating unsigned former-MAF word AB06 after the MAF conversion calls are removed. Master code
  converts AB06 at 5/65536 V/count, applies the editable AEM lambda transfer, then writes the same
  valid lambda to AE60/AE64 and logger mirrors B098/B09C. It writes readiness 50 to AE70/AE74;
  invalid/rail input publishes logger sentinel 0, readiness 0, inhibits both stock bank feedback
  helpers, and forces EBCS duty to zero. The EBCS guard also requires valid MAP/RPM/IAT, RPM at
  or above the first boost-axis point, and a non-fault SD result. The retained lambda condition filter and per-bank
  closed-loop consumer were rechecked. Front producer B690 and both inhibit helpers are hooked;
  the pump diagnostic pointer, rear ADC converter, and all five traced rear monitor pointers are
  no-ops; all 18 mapped front/rear O2 DTC switches are off. Heater output drivers remain stock and
  disconnected connector terminals must be insulated.
- 2026-08-21: `master_patch/verify_master_patch.py` independently composes every component from
  immutable stock, decodes each new SH-2E executable region, checks hooks/task pointers/DTC bytes,
  validates sensor math and tune policy, enforces free-space ownership (including leaving the
  separate rotational-idle region untouched), regenerates the focused XML, and validates the
  Subaru checksum. The generated ROM remains a development baseline requiring bench and dyno
  validation.
- 2026-08-21: the AVCS/timing usability pass re-opened the target descriptors and their live
  consumers. `intake_avcs_target_by_avls_mode_update` at 0x353B0 proves legacy AVCS A is selected
  for committed AVLS mode 1 (low lift), while AVCS B is selected for mode 3 (high lift); they are
  modes, not banks. `ign_avcs_tracking_blend_factor_update` at 0x28354 proves timing factor `k`
  is measured/commanded intake AVCS tracking, not IAM. This corrects the earlier
  advance-multiplier interpretation. The focused definition now labels both AVCS targets by lift
  state and the four reachable timing surfaces by cam state plus AVCS-tracking-ratio endpoint,
  documents `ratio_1.0*k + ratio_0.0*(1-k)`, and does not impose a false retard ordering. The
  newly inspected math helpers and downstream controller were also assigned project-convention
  names. A local RomRaider check showed that loading the standalone speed-density XML against the
  unchanged `D2WD610H` CALID explains why the master binary can still appear with legacy labels.
- 2026-08-21: the master airflow wrapper was extended to select VE from committed AVLS state
  `0xFFFFCD86`: mode 3 selects a 13x11 high-lift table covering 3000..7500 RPM and all other
  modes select a 13x9 low-lift table covering 0..3200 RPM. Both are cloned/resampled from the
  same conservative seed. The 3000..3200 overlap is real hysteresis coverage. All table-driven
  and fixed/fallback vehicle-speed request thresholds are 110 km/h, above the verified 100-km/h
  conditioner cap, leaving a predictable 3200-RPM engage / 3000-RPM release policy. The stock
  request/commit/actuation sequence remains. The focused XML omits controls made inoperative by
  this policy and E503 logs the committed state used by the VE selector.
- 2026-08-22: the pressure/lean safety trace renamed
  `engine_control_periodic_task_dispatch` (0x10A28),
  `primary_open_loop_fueling_target_update` (0x22454),
  `cl_ol_transition_delay_update` (0x22756),
  `cl_ol_delay_condition_and_counter_update` (0x22948),
  `cl_ol_transition_state_update` (0x22AAE),
  `cl_ol_transition_state_initialize` (0x22AC2),
  `fueling_state_flag_clear_on_condition` (0x2331E),
  `fuel_cut_flag_aggregate` (0x23FC0), `rev_limiter_fuel_cut` (0x24B24), and
  `atmospheric_pressure_source_select_update` (0x47DB2). The primary target
  task proves `0xFFFFBE38` bit `0x80` is its closed-loop-permission bit. The
  delay lookup and atmospheric source writer prove `0xFFFFCFBC` is live native
  absolute barometric pressure. The master now calls the stock target first and
  may clear only bit `0x80` near atmospheric pressure; its separate lean wrapper
  composes after the prior rev-limit/overboost wrapper and sets the same verified
  fuel-cut flag only after delayed, confirmed AFR failure.
