# Repurposing the EVAP purge solenoid output as a boost-control solenoid

Goal: drive a boost-control (wastegate) solenoid from the ECU output that currently runs the
EVAP canister purge (CPC) solenoid — hijack its PWM duty with a boost map, neutralize the
purge enable/schedule, and mask the purge DTCs.

CALID D2WD610H (EZ30R, SH7055). All code addresses are file offsets (flash base = 0).
Confidence in the purge identification: HIGH (~90%). Final proof = datalog the SSM purge-duty
parameter (or bench-probe the output pin) and watch it move with this chain. See "Identification".

================================================================================
## THE PURGE CONTROL CHAIN (reverse-engineered, renamed in Ghidra)
================================================================================

Runs from the slow-task dispatcher `FUN_000114B0` (a ~50-entry fn-ptr table @ 0x116E8).
Purge occupies two entries in the aux/emissions cluster: idx 33 (state) and idx 35 (duty).

1. `evap_purge_state_update` @ **0x0003F9E4** (slow-task idx 33)
   - Manages purge enable/mode; owns status byte RAM **0xFFFFCD81**.

2. `evap_purge_duty_compute` @ **0x0003FC0A** (slow-task idx 35)  ← MAIN CONTROL
   - State machine at RAM **0xFFFFCD77** (cases 0..7 = off / ramp / hold / active / etc.).
   - Enable input: ECT (float) @ RAM **0xFFFFB3AC** vs threshold @ RAM **0xFFFFB3B8**;
     sets status bit 0x80 @ 0xFFFFCD81.
   - Duty schedule = coolant-temp -> duty%% maps, looked up via `table2d_lookup_dispatch`
     (0x209C) with these descriptors (1-axis, u8 data, scale 1.0, offset 0.0):
       * desc **0x609C4**: 5 pts. axis @ **0x7BD6C** = {92,95,100,103,105} °C;
         data @ **0x7BD80** = {40,40,70,70,70} %%.
       * desc **0x609D8**: 4 pts. axis @ **0x7BD88** = {83,98,100,120} °C;
         data @ **0x7BD98** = {45,60,70,70} %%.
     (A further map @ data 0x7BDFC is used by case 7.) Full-scale constant = 100.0.
   - Writes computed duty %% to RAM **0xFFFFCD54**, then computes ratio = duty/100.0 and calls
     the output stage `evap_purge_pwm_output_write` (0xE8C4) with that ratio.

3. `evap_purge_pwm_output_write` @ **0x0000E8C4** (dedicated single-channel output stage)
   - count = ratio * 65536.0 (16.16 fixed).  Cached to RAM **0xFFFFB0F0**.
   - period read from RAM **0xFFFFAB84**.
   - Writes ATU-II output-compare register **0xFFFFF590** = period - scaled(count),
     via low-level helper `FUN_00002390`.
   - **0xFFFFF590 is the physical purge-solenoid PWM output** (the harness pin to reuse).

4. `evap_purge_flow_diagnostic` @ **0x00046748**
   - Reads duty 0xFFFFCD54, applies a rationality/flow check with debounce counters
     (increment-limit helper 0x46864), sets/clears a fault bit @ RAM byte DAT_0004684E
     -> purge DTC (P0458/P0459 circuit, P0441-class flow). Must be neutralized for the mod.

5. SSM datalogger reads duty 0xFFFFCD54 at 0x3187E (why "Purge Duty" is loggable).

### Identification (why this is purge, not something else)
- Dedicated **duty-PWM** solenoid (0-100%%), not on/off — rules out AVLS/AVCS (on/off, crank-synced
  bank at 0xFFFFF652+2n, separately RE'd) and the radiator fan (relay MODE bytes 0xFFFFF97C/FA80,
  set by FUN_0003F878 — not a PWM).
- Lives in the emissions/aux slow-task cluster; temp-scheduled + state machine; monitored by a
  dedicated rationality diagnostic; SSM-logged. On the ADM EZ30R (simple EVAP: only P0458/P0459
  in the def, no leak-detection codes) the temp-scheduled duty emissions solenoid is the CPC purge.
- REMAINING PROOF (do before flashing): datalog purge duty and confirm it tracks 0xFFFFCD54 /
  the ECT schedule above, or scope the pin driving 0xFFFFF590.

================================================================================
## KEY ADDRESSES (patch cheat-sheet)
================================================================================
| Thing | Address | Notes |
|---|---|---|
| Purge duty computation (hijack point) | code **0x3FC0A** | replace duty source here |
| Purge output stage | code **0xE8C4** | ratio -> 0xFFFFF590 |
| Physical PWM output register (ATU-II) | IO **0xFFFFF590** | the purge solenoid pin |
| Purge duty %% variable | RAM **0xFFFFCD54** | overwrite this to drive the output |
| Purge duty count (16.16) | RAM **0xFFFFB0F0** | post-scale |
| Purge PWM period | RAM **0xFFFFAB84** | frequency control (from ATU config) |
| Purge state machine | RAM **0xFFFFCD77** | |
| Purge status byte | RAM **0xFFFFCD81** | bit 0x80 = enabled |
| ECT input | RAM **0xFFFFB3AC** | float °C |
| Purge diagnostic fault byte | RAM DAT_0004684E | bit 0x01 |
| Purge DTC config bytes | flash **0x5BD85** (P0458) / **0x5BD86** (P0459) | mask to disable |
| Free space for patch code + boost map | flash **0x7D790** (9 KB) | from setup script |
| Engine RPM (float) | RAM **0xFFFFB544** | boost-map X axis |
| Table interpolator (reuse for boost map) | code **0x209C** (2D) / **0x2150** (3D) | descriptor-based |

================================================================================
## ORIGINAL PATCH PLAN (implementation history)
================================================================================
The physical output (0xFFFFF590) already does clean PWM. The mod is purely about WHAT duty is
written and removing purge-specific behaviour. Cleanest approach = keep the output stage, replace
the duty source.

1. **Boost duty map** (new table in free space @ 0x7D790):
   - Build an RPM x load (or RPM x target-boost) -> duty%% map. Reuse the descriptor + interpolator
     system (0x209C / 0x2150) — write a 0x1C-byte 2-axis descriptor pointing at the new data, or a
     simple 1-axis RPM->duty to start. X axis from RPM @ 0xFFFFB544.
2. **Hijack the duty** (in `evap_purge_duty_compute` @ 0x3FC0A):
   - Simplest: after/instead of the temp-schedule, compute boost duty and store to 0xFFFFCD54, then
     let the existing `0xE8C4` call output it. i.e. patch the pre-output section so 0xFFFFCD54 =
     boost_map_lookup(...) clamped 0..100. Keep using the existing ratio/100.0 -> 0xE8C4 path.
   - Alternative (less invasive to 0x3FC0A): add a trampoline in the slow task that overwrites
     0xFFFFCD54 after 0x3FC0A runs and before 0xE8C4 — but 0xE8C4 is called from inside 0x3FC0A,
     so the in-function patch is cleaner.
3. **Neutralize purge gating**: remove/relax the ECT enable (threshold @ 0xFFFFB3B8) and force the
   state machine (0xFFFFCD77) / status (0xFFFFCD81 bit 0x80) so the output is live across the boost
   operating range regardless of coolant temp.
4. **PWM frequency**: purge runs at whatever the ATU channel period (RAM 0xFFFFAB84, from ATU init)
   gives. 3-port MAC boost solenoids want ~15-30 Hz. Verify the current purge frequency; if it
   differs, retune the ATU channel reload/period for that channel. (Find the ATU init that sets the
   0xFFFFF590 channel — writers of 0xFFFFF590 include a setup fn ~0xE884.)
5. **Disable the purge diagnostic**: stop `evap_purge_flow_diagnostic` (0x46748) from setting its
   fault bit (it will trip once the "purge" no longer flows like a purge valve), and flash-mask the
   DTC config bytes P0458 (0x5BD85) / P0459 (0x5BD86).
6. **Checksum**: re-run the Subaru DBW checksum after flashing (checksummodule subarudbw).

### Safety
NA EZ30R, no factory wastegate/turbo — only meaningful as part of a forced-induction build. Design
the boost duty map conservatively and keep an independent overboost fuel cut as a fail-safe.

================================================================================
## RULED OUT (so we don't re-walk it)
================================================================================
- The 6-channel crank-angle-synced ATU bank (0xFFFFF602 ctrl / 0xFFFFF652+2n compare, driver
  `solenoid_pwm_channel_drive` 0x96FC, scheduler 0x263EE @ 30°×24=720°) is the AVCS/AVLS cam
  oil-control solenoids, NOT purge.
- The radiator fan (FUN_0003F878) is relay-driven (mode bytes 0xFFFFF97C / 0xFFFFFA80), not PWM.
- ATU config cluster 0xFFFFF444-F44E is setup data (ref only from table @ 0xFA94), not an output.

================================================================================
## WRX-STYLE BOOST CONTROL (target architecture)
================================================================================
Replicate the 32-bit Subaru (WRX STi, = 32BITBASE in the defs) boost-control algorithm as
custom code in free space, driving the repurposed purge PWM output (0xFFFFF590).

### The WRX algorithm (from 32BITBASE tables)
  target = TargetBoost[rpm, load/throttle]  (+ atm/ECT/IAT/gear compensations)
  base   = InitialWastegateDuty[rpm, target]   (feed-forward)
  error  = target - actualMAP
  corr   = TurboDynamics: integral(error)*Ki + proportional(error)*Kp   (closed loop)
  duty   = clamp( base + corr, 0, MaxWastegateDuty[rpm] )
  if actualMAP > BoostLimit(FuelCut): cut fuel/ignition   (overboost protection)
  -> write duty to wastegate solenoid PWM

### What this ECU already has
  - Output: purge PWM chain -> ATU-II reg 0xFFFFF590 (see above).
  - Feedback: MAP value @ RAM **0xFFFFABC4**
    (`map_sensor_voltage_to_pressure_process` @0x7A14, raw ADC 0xFFFFAB04, scaling table
    0x72810). Ghidra confirms `MAP_native = voltage × multiplier + offset`; native pressure is
    mmHg absolute. Firmware plumbing for boost feedback exists.
  - RPM @ 0xFFFFB544; load/airflow available; ECT 0xFFFFB3AC; IAT/atm available.
  - Interpolators 0x209C (2D) / 0x2150 (3D); free space 0x7D790 (9KB).

### Hardware prerequisite for closed loop
  The stock NA MAP sensor cannot cover the required boost range. `patch_boost.py` now copies the
  A2WC510N calibration `{-414.0, 514.199951}` into 0x72810, but the compatible turbo MAP sensor
  must be fitted and 0xFFFFABC4 must be checked against a reference gauge before the controller
  or either MAP limit can be trusted.

### Implemented controller strategy
  There is one patch and one injected controller. It always installs the feed-forward duty map,
  target map, proportional correction, throttle-demand gate, final-duty clamp, soft duty
  shutdown, and hard fuel cut. The generated default is the A2WC510N near-zero proportional
  slope (`Kp=0.0005 ratio/mmHg`); setting Kp to zero remains the recommended first hardware
  commissioning step because it disables correction without changing patch code. The purge path
  runs in a slow task; a faster task hook remains a possible future controller improvement.

### New RAM/registers found this step (renamed in Ghidra)
  - `map_sensor_voltage_to_pressure_process` @0x00007A14; native mmHg absolute MAP
    @0xFFFFABC4; MAP raw ADC @0xFFFFAB04.

================================================================================
## PATCH WORKING FILES / DECISIONS
================================================================================
- RomRaider def (iterating): **defs/D2WD610H_boost_patch.xml** — clone of D2WD610H_AVLS.xml,
  xmlid D2WD610H_BOOST (internalidstring stays D2WD610H for auto-detect). Boost patch tables get
  added under category "Boost Control (patch)". Load this one going forward (not the AVLS file).
- Because 32BITBASE = WRX STi base, the WRX boost table TEMPLATES + scalings are already in the
  file (categories "Boost Control - Target/Wastegate/Turbo Dynamics/Limits"). Reuse those exact
  scalings when adding the patch overrides (e.g. Target Boost psi expr (x-760)*.01933677).
- DONOR/HARDWARE DECISION: A2WC510N, a 2005 USDM Legacy GT MT turbo-EJ25 ROM, supplies Target
  Boost A/B, Initial/Max WGDC, Turbo Dynamics Proportional, fuel-cut strategy, and MAP scaling.
  The patch installs its exact MAP conversion at **0x72810** and reduces the full-demand target
  shape to a 5 psi peak. See [boost_donor_A2WC510N.md](boost_donor_A2WC510N.md). The compatible
  sensor still must be fitted and validated; copying calibration bytes alone does not identify or
  prove the installed hardware.

================================================================================
## PATCH STATUS (single proportional + feed-forward controller)
================================================================================
- `patch/patch_boost.py` is the only patcher. It always reads the root `2005 BLE MT.bin`, patches
  a private copy, and writes `patch/D2WD610H_boost.bin` by default. The stock input path is fixed,
  and the patcher refuses output paths that alias it.
- `patch/sh2_asm.py` is a two-pass SH-2E assembler with a known-encoding self-test;
  `patch/sh2_disasm.py` supports binary inspection; `patch/verify_regions.py` audits free flash
  and RAM assumptions.
- The controller stub is at 0x7D80C. `evap_purge_duty_compute` @0x3FC0A tail-calls its output via
  pooled pointer @0x3FD8C (=0x0000E8C4); the patch repoints that pointer to the stub. Disassembly
  confirms the controller is STATELESS (no persistent RAM stores). err = TargetBoost[rpm] − MAP(0xFFFFABC4);
  ratio = clamp(base + Kp·err, 0, MaxRatio); throttle @0xFFFFB314 at/below the tunable minimum
  @0x7D8A4 → ratio 0; overboost → ratio 0.
- **P-only, not PI — deliberate.** Audit (verify_regions.py, cross-checked in Ghidra) found NO RAM
  word can be proven free: 0xFFFFBFF0/BFF8 are inside the cam-solenoid struct array (0xFFFFBFB8 +
  i·0x28, computed access → invisible to xref); the big unreferenced RAM gaps are computed buffers
  / jump tables (e.g. 0xFFFF6004 is a jump-table base). So the integral term is omitted rather than
  corrupt another subsystem. Adding I later needs a verified scratch or reclaimed purge RAM.
- Solenoid ownership VERIFIED SAFE: 0xE8C4 has exactly one caller (the hijacked tail-call);
  0xFFFFF590 is otherwise written only by init (ATU channel setup @0xE884/0xE8B4, period from cal
  0x72808). The stub is the sole runtime driver — nothing else can fight boost control.
- Free flash VERIFIED CLEAN: 9064 contiguous 0xFF @0x7D790; no code points into it.
- Layout: base_desc 0x7D790 / rpm_axis 0x7D7A4 / base_data 0x7D7C4 / target_desc 0x7D7CC /
  target_data 0x7D7E0 / Kp 0x7D800 / MaxRatio 0x7D804 / Overboost 0x7D808 / stub 0x7D80C.
- Default calibration is donor-derived: 5 psi peak target, base WGDC
  `{0,0,21,19,18,17,15,14}`, Kp `0.0005 ratio/mmHg`, maximum duty `0.33`, 30.0 native throttle
  gate, 6 psi duty shutdown, and 7 psi fuel cut (all pressure figures relative to 760 mmHg). The
  patch also replaces 0x72810 with the donor MAP conversion. These are traceable starting values,
  not hardware validation; use Kp=0 and zero/low base duty for first commissioning. Future work:
  integral term (needs verified RAM), 2-axis target, and faster loop rate.

### Overboost fuel cut
Two-tier: SOFT (MAP>0x7D808 → duty 0, in the boost stub) + HARD (MAP>0x7D8A8 → fuel cut). Hard cut
reuses the factory rev-limiter path — wrapper @0x7D8AC hooked at rev-limiter fn-ptr 0x11D3C
(`FUN_00011AD0` dispatcher) calls `rev_limiter_fuel_cut` @0x24B24 then sets fuel-cut flag
0xFFFFBF6C bit0x80 on overboost; `fuel_cut_flag_aggregate` @0x23FC0 propagates → injectors off.
Rev limits: A 0x7644C (resume 0x76450) / B 0x76454 (resume 0x76458). Stateless. Second hijack
(0x11D3C) added alongside the output hijack (0x3FD8C); both guarded in the patcher.
