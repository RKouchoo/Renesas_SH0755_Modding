# D2WD610H Solenoid / PWM Output Subsystems

> **Historical identifications retracted, September 8:** Section A's six
> crank-phase channels are injector scheduling, not a cam-solenoid bank.
> The output previously identified here as repurposable purge was radiator-fan
> PWM. Do not use these old identities to select or repurpose an output. Current
> evidence is in the [injector-cut audit](../master_patch/INJECTOR_CUT_EXECUTION_AUDIT.md)
> and [fan/purge repair](../master_patch/GHIDRA_AUDIT.md).
> The original research below is retained as history.

Two independent solenoid/PWM output systems were reverse-engineered. Keeping them straight
matters for the boost patch: the **purge** output (a free-running duty PWM) is the repurpose
target; the **cam bank** (crank-angle-synced) is a different subsystem and must be left alone.

See also [hardware_io_map.md](hardware_io_map.md), [boost_repurpose_notes.md](boost_repurpose_notes.md).

================================================================================
## A. Crank-angle-synced solenoid bank — AVCS / AVLS cam solenoids  (NOT purge)
================================================================================
6 channels driven at precise crank angles. Ruled out as the purge output because it schedules
by crank position, not a free-running duty.

- **Scheduler** `solenoid_phase_scheduler` @ **0x000263EE** — phase index 0..23 × 30.0° = 720°
  crank; per-channel actuation inside crank-angle windows (dispatch thresholds 720.0/100.0).
- **Init** `solenoid_control_array_init` @ **0x00026320** — 6 control structs @ RAM
  0xFFFFBFB8, stride 0x28, channel index at +0x0C; per-channel config @ 0x4B690 / 0x4B6A8.
- **Per-channel actuate handler** @ 0x00026088 (via dispatch table @ 0x4B670, stride 0x10).
- **HW driver** `solenoid_pwm_channel_drive` @ **0x000096FC** `(physical_channel, duty_count)`.
  Descriptor table @ **0x0000FAE8** (6 × 0x18): channel n → enable bit `(0x0100<<n)` on control
  register **0xFFFFF602**, output-compare register **0xFFFFF652 + 2n**.
- **Per-solenoid update** `solenoid_channel_output_update` @ **0x000268E8**
  `(duty_fraction, _, logical_channel)` — duty→count (scale 0.25), inhibit gate, calls driver.
  Maps: logical→physical @ 0x4B6A8, enable flags @ 0x4B6AE, gate masks @ 0x4B64C.
- **Fault / inhibit**:
  - `solenoid_status_word_read` @ **0x00026DFC** → 16-bit inhibit word @ RAM **0xFFFFB744**
    (bit n inhibits channel n).
  - `solenoid_inhibit_word_build` @ **0x0001C5D4** — assembles 0xFFFFB744 from per-channel
    circuit faults + precondition AND-gate (batt/ign OK: 0xFFFFBF6C/BF70/BF74/CE24/CF24/CFA0).
  - `solenoid_circuit_diagnostic` @ **0x00024570** — sets circuit-fault byte @ RAM 0xFFFFBF21.

> These 6 channels are the AVCS oil-control + AVLS oil-switching valves (EZ30R has both).
> Confirm which channel index is which via `avls_cam_mode_state_machine` (0x40168) — open item.

================================================================================
## B. EVAP purge PWM — free-running duty  (THE boost-patch target)
================================================================================
Full chain in [boost_repurpose_notes.md](boost_repurpose_notes.md). Summary:

- Runs in the slow task (`slow_task_dispatcher` @0x114B0, idx 33 state / idx 35 duty).
- `evap_purge_state_update` @ **0x0003F9E4** — enable/mode; status byte 0xFFFFCD81.
- `evap_purge_duty_compute` @ **0x0003FC0A** — state machine 0xFFFFCD77; ECT-gated
  (0xFFFFB3AC vs 0xFFFFB3B8); coolant-temp→duty maps (desc 0x609C4 / 0x609D8, full-scale 100.0);
  writes duty %% to RAM **0xFFFFCD54**, then ratio = duty/100 → output stage.
- `evap_purge_pwm_output_write` @ **0x0000E8C4** — count = ratio×65536; writes ATU-II
  output-compare register **0xFFFFF590** (= period − scaled); period from RAM 0xFFFFAB84.
- `evap_purge_flow_diagnostic` @ **0x00046748** — rationality monitor → purge DTC
  (P0458 0x5BD85 / P0459 0x5BD86). Neutralize for the mod.
- SSM-logged (read at 0x3187E).

### Boost repurpose in one line
Keep the 0xE8C4 output stage; overwrite the duty at **0xFFFFCD54** from a boost map, neutralize
the ECT gating, retune the PWM period if needed, disable the diagnostic + mask the DTCs.

================================================================================
## C. Radiator fan — relay stages (reference; not PWM)
================================================================================
`radiator_fan_mode_select` @ **0x0003F878** — computes fan mode 0..3 from ECT with hysteresis,
writes mode bytes 0xFFFFF97C / 0xFFFFFA80 (drive relays). Not a duty PWM — listed so it isn't
confused with the purge/boost output.
