# D2WD610H — EZ30R Denso ECU Reverse Engineering Notes

Working document. Updated as analysis progresses in Ghidra (live MCP session).
This file is the canonical state doc. Companion references:
- [ram_map.md](ram_map.md) — consolidated RAM variables
- [hardware_io_map.md](hardware_io_map.md) — memory map + peripheral registers
- [solenoid_subsystem.md](solenoid_subsystem.md) — cam-bank vs purge PWM outputs
- [boost_repurpose_notes.md](boost_repurpose_notes.md) — purge chain + boost-control design
- [patch_build_guide.md](patch_build_guide.md) — boost-patch build/flash plan
- [single_front_af_patch.md](single_front_af_patch.md) — retained factory A/F mirror design
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
| 0x00028354 | `ign_blend_factor_from_advance_multiplier` |
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
  A/B/C = advance side (primary), D/E/F = retard side (reference).
- **k computation** (`0x28354`): k = float@0xFFFFC974 + float@0xFFFFC978 (knock-learned
  advance multiplier + step term), clamped; forced to 1.0 when a status check passes.
- **Selection** (`0x284B8`) → selected base timing @ **0xFFFFC184**:
  - default: A/D blend (0xFFFFC16C)
  - B/E (0xFFFFC170) when status fn==1 and bit 0x80 of flag byte 0xFFFFC180
  - **C/F (0xFFFFC174) when cam mode @0xFFFFCD86 == 3 (high cam) and debounced bit 0x40
    of 0xFFFFC180** → C/F are the AVLS high-cam maps (hence 20 rows).
  - Final (after extra 1-axis lookup, desc 0x5FC18) → 0xFFFFC150 and 0xFFFFC188.
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
| 0x00040168 | `avls_cam_mode_state_machine` |
| 0x000405B2 | `avls_mode_commit_copy` (0xFFFFCD87 → 0xFFFFCD86) |
| 0x000405CC | `avls_osv_actuation_gate` |
| 0x00040C94/40798/40CE6 | `cam_actuator_output_set_1/2/3` (called with 0|1) |

**RAM cells:** target mode **0xFFFFCD87** (1=low cam, 3=high cam), committed **0xFFFFCD86**,
operating state 0xFFFFCD9C (curve selector: 2=curve 1, 3=curve 2), mode timer 0xFFFFCD84
(u16, reload from ROM @0x7D468, −1/tick), hysteresis flags 0xFFFFCD9E
(mask 0x04 = RPM>4000 latch, mask 0x10 = engine running),
status latch 0xFFFFCD8F, threshold caches 0xFFFFCD94/0xFFFFCD98, defer flag 0xFFFFCD9D.

**Switchover is a load-vs-RPM line, not a single RPM constant:**

| Item | ROM addr | Value |
|---|---|---|
| Threshold table 1 data (7×float) | **0x7D67C** | 100,100,30,28,25,15,5 (load units) |
| Table 1 X axis (RPM, 7×float) | 0x7D660 | 1600,2000,2400,2800,3200,3600,4000 |
| Threshold table 2 data (7×float) | **0x7D6B4** | 100,100,90,50,30,10,0 |
| Table 2 X axis (RPM, 7×float) | 0x7D698 | 2000,2050,2400,2800,3200,3600,4000 |
| Hard high-cam engage RPM | **0x7D4BC** | float 4000.0 |
| Hard release RPM (hysteresis) | **0x7D4B8** | float 3800.0 |
| Threshold hysteresis offsets | 0x7D480/0x7D484 | 10.0 / 10.0 |
| Actuation RPM gate | 0x7D4AC | 3000.0 |
| Engine-run RPM gate | 0x7D4A8/0x7D4A4 | 512.0 / 510.0 |
| Sentinel band (table-result check) | 0x7D4A0/0x7D49C | 10000.0 / 9000.0 |
| Fallback thresholds | 0x7D4B0/0x7D4B4 | 15.0 / 15.0 |
| Mode timer reload (u16) | 0x7D468 | — |

Descriptors: table 1 = **0x60F58**, table 2 = **0x60F64** (compact 0xC float type).
RPM input is float @ **0xFFFFB544**. The normal curve path compares float load signal
**0xFFFFB46C**: operating state **0xFFFFCD9C == 2** selects table 1 plus hysteresis A;
state **3** selects table 2 plus hysteresis B. From low cam, high cam is requested at
`load >= curve + 10`; from high cam, low cam is requested at `load < curve`. Thus the two
tables are state-selected curves, **not** engage/release counterparts. **0xFFFFCF94** is used
only by the fallback path against the fixed 15.0 thresholds at 0x7D4B0/0x7D4B4.

Definition layout:

- `defs/D2WD610H.xml` is the retained base metric EcuFlash definition.
- `defs/D2WD610H_AVLS.xml` is the AVLS-only custom RomRaider definition.
- `defs/D2WD610H_AVLS_boost_patch.xml` contains the same D2WD610H + AVLS definition plus the
  canonical boost-patch tables and its one-byte runtime enable.
- `defs/D2WD610H_AVLS_single_front_af_patch.xml` contains D2WD610H + AVLS plus the one-byte
  front-mirror/rear-delete runtime enable; existing DTC switches cover all 13 removed-sensor edits.
- `defs/D2WD610H_AVLS_rotational_idle_patch.xml` contains D2WD610H + AVLS plus only the separate
  rotational-idle switch, operating gates, safety limits, and six timing offsets.
- `defs/D2WD610H_AVLS_boost_single_front_af_patch.xml` is the combined-image variant containing
  the canonical boost tables plus both unchanged runtime-enable switches.
- `defs/romraider_ecu_defs.xml` is a clean upstream metric RomRaider snapshot and is not modified
  with project tables.

All five custom RomRaider ROM files are self-contained. Their embedded metric `32BITBASE` is pruned
to the 206 templates referenced by the 206 standard D2WD610H address overrides; the additions
are seven AVLS tables and, in the patch variants, only the matching patch tables/switches. Load
only the custom ROM variant matching the image being edited. Stock AVLS values were verified
against the ROM image 2026-07-14.

**Open sub-item:** the final OSV port write. `cam_actuator_output_set_*` descend into
float target/feedback layers (AVCS-style continuous control mixed in); the binary port
bit is likely flushed by a central output-image task. Next session: xref SH7055 port
data registers (datasheet) instead of descending the call tree.

## 6. Key RAM anchors (confirmed this session)

| RAM addr | Meaning | Evidence |
|---|---|---|
| **0xFFFFB544** | Engine RPM (float) | compared vs 4000/3800/512/510 rpm consts; input to switch tables; used across ign+AVLS |
| **0xFFFFB538** | Vehicle speed (float, km/h) | `ign_idle_timing_target_update` compares it with stock 4.0-km/h idle-timing threshold @0x77E1C; also consumed by AVLS logic |
| **0xFFFFB46C** | Normal AVLS switchover load signal (float; snapshot of filtered 0xFFFFB4C8) | compared against state-selected curves in 0x40168 |
| 0xFFFFCF94 | AVLS fallback load value | compared only against fixed 15.0 fallback threshold in 0x40168 |
| 0xFFFFC17C | Ignition blend factor k (float 0..1) | written 0x28354 |
| 0xFFFFC974/0xFFFFC978 | Advance-multiplier terms summed into k | 0x28354 |
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
      `evap_purge_flow_diagnostic` @0x46748. DTCs P0458 0x5BD85 / P0459 0x5BD86. Confidence HIGH;
      confirm by datalogging purge duty. REMAINING for patch: build boost map (free space 0x7D790),
      hijack duty at 0x3FC0A, neutralize ECT gating, check/retune PWM freq, mask DTCs, re-checksum.
      NOTE: the crank-synced 6-ch bank (0x96FC/0x268E8, 0xFFFFF602/0xFFFFF652+2n) is AVCS/AVLS cam,
      NOT purge (earlier mis-ID, corrected).
- [ ] AVLS physical OSV port write — **likely resolved**: OSV/OCV solenoids are driven by the
      crank-angle-synced bank above (ATU-II compare 0xFFFFF652+2n, ctrl bit on 0xFFFFF602).
      Confirm which of the 6 channels `avls_cam_mode_state_machine` (0x40168) commands.
- [x] ECU-side aftermarket-wideband input retired. External lambda data will be timestamped and
      merged with the ECU log off-board; the ROM publishes no aftermarket-sensor value.
- [x] Combined stock-to-ROM builder and definition created. `patch/patch_combined.py` applies both
      guarded components to one fresh stock copy; `verify_combined.py` proves the 811 changed bytes
      are the exact 369 + 442 union with zero overlap. Hardware use remains gated on both standalone
      commissioning plans.
- [x] **Rotational-idle standalone component built.** `patch_rotational_idle.py` wraps the complete
      stock task at 0x279CC through task-pointer slot 0x11E30, defaults OFF, and applies bounded
      retard-only six-cylinder offsets only inside the calibrated warm/stationary idle window.
      `verify_rotational_idle.py` proves exact binary ownership and future three-component
      compatibility in memory. It is not yet installed in the combined patch or base turbo map.
- [ ] Airflow model (speed density — capstone)
- [ ] Define 0x25F8/0x2628/0x2654 as functions in Ghidra and rename (interp_2axis_float32/s8/s16)
- [ ] Identify status fns feeding ign_base_timing_select (0x27088, 0x6504C) and the B/E map condition (cruise?)

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
- 0x00028354 → **ign_blend_factor_from_advance_multiplier**
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
- 0x00018A68 → **engine_load_signal_filter_update** (produces filtered load @0xFFFFB4C8)
- 0x00018AEA → **engine_load_signal_snapshot_copy** (0xFFFFB4C8 → AVLS compare signal 0xFFFFB46C)
- 0x00047000 → **engine_load_fallback_select** (selects 0xFFFFCF94 fallback value)
- 0x00014DCC → **throttle_position_sensor_process** (DBW throttle sensor plausibility/processing;
  produces processed throttle opening @0xFFFFB314 used by CL/OL logic and boost demand gate)
- 0x0000B690 → **front_af_sensor_pair_signal_process** (stock two-channel front A/F processing;
  single-front patch runs the complete body, then mirrors Bank 1 into Bank 2)
- 0x0000B8CC → **front_af_sensor_pump_current_diagnostic_update** (retained stock front-sensor
  diagnostic calculation; single-front task wrapper refreshes Bank-2 readiness afterward)
- 0x00064FD0 / 0x0006500C → **front_af_sensor_bank1_inhibit_check** /
  **front_af_sensor_bank2_inhibit_check** (single-front patch redirects the Bank-2 entry to a
  runtime selector: patch on uses Bank 1; patch off reconstructs stock Bank-2 semantics)
- 0x00018DAC → **front_af_sensor_lambda_condition_filter** (downstream conditioned factory
  lambda path producing the B4E8/B4EC logger values)
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
0x33AAC, 0x33964, 0x33970, 0x34BE4, and 0x69568.

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
- 2026-07-14: both generated patches gained definition-backed runtime-enable bytes. Boost uses
  0x7D80C (`OFF` forces zero EBCS duty and skips the added MAP cut); single-front A/F uses
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
