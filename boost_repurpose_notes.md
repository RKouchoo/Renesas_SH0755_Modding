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
## PATCH PLAN (to implement later)
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
