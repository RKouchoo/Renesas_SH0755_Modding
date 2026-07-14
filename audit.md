# Boost-Control Patch Audit

Audit date: 2026-07-14. Target: D2WD610H, Renesas SH7055, stock image
`2005 BLE MT.bin`.

## Verdict

The single patch is structurally valid and its injected SH-2E code should execute as designed,
but binary verification is not hardware validation. It includes proportional + feed-forward
control, a minimum-throttle driver-demand gate, soft duty shutdown, and hard fuel cut. It still
requires MAP-sensor calibration, PWM/polarity bench testing, purge-DTC handling, checksum
correction, and an overboost-cut bench test before boost is applied.

## Checks completed

- The canonical patcher verifies the exact 512 KB root stock image by SHA-256, patches a private
  copy, and refuses to use the stock file as output.
- The root `2005 BLE MT.bin` remains unchanged at SHA-256
  `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
- Free-space writes stay within the verified `0xFF` run at `0x7D790..0x7FAF7`.
- Stock hook guards match before patching:
  - purge output pointer `0x3FD8C`: `0x0000E8C4`
  - rev-limiter task pointer `0x11D3C`: `0x00024B24`
- The controller and fuel-cut wrapper disassemble to the intended SH-2E instructions.
- Stack and `PR` save/restore paths are balanced, including early throttle/overboost exits.
- Low/high duty clamps have the intended floating-point comparison polarity.
- The rev-limiter wrapper runs before `fuel_cut_flag_aggregate` at `0x23FC0` in the same
  dispatcher, allowing the forced `0xFFFFBF6C` bit `0x80` to be consumed that cycle.
- `evap_purge_pwm_output_write` at `0xE8C4` accepts the injected `0.0..1.0` ratio and remains
  the sole runtime writer used by the patched control path.
- Patch definition XML parses and its storage addresses match the current injected layout.
- No persistent scratch RAM is introduced.
- The sole generated artifact is `patch/D2WD610H_boost.bin` (512 KiB, SHA-256
  `f318986eaa45cd94a8f37133359dc48c5721fb46f827d718cd069cf866d2f751`). The obsolete split
  patcher and `_p1`/`_p2` images have been removed.

## Throttle gating

Ghidra tracing confirmed processed throttle opening at float RAM `0xFFFFB314`:

- `cl_ol_transition_delay_update` at `0x22756` passes `0xFFFFB314` to the calibrated
  “CL to OL Transition with Delay (Throttle)” lookup.
- Its producer at `0x14DCC` performs DBW throttle-sensor processing/plausibility and was renamed
  `throttle_position_sensor_process` in Ghidra.
- The controller compares this value with a tunable float at `0x7D8A4`.
- Boost duty is enabled only when `throttle > minimum`; at or below the threshold the stub
  tail-calls the stock output stage with duty ratio `0.0`.
- Default minimum throttle is `20.0`. This is a commissioning value, not a validated final
  calibration. The gate is deliberately fail-closed for equality and ordinary low-throttle
  operation.
- The hard MAP overboost wrapper is independent of this gate and remains active at low throttle.

The gate is stateless and therefore has no hysteresis. If testing shows chatter around the
threshold, use separate enable/disable thresholds only after a safe state-storage strategy is
proven, or gate from a confirmed existing hysteretic demand flag.

## Remaining blockers

1. **MAP sensor and scaling:** the patch does not install or automatically calibrate the EJ255
   sensor. Table `0x72810` must be rescaled and `0xFFFFABC4` validated against a reference gauge.
   Closed-loop correction and both MAP overboost limits are untrusted until then.
2. **PWM frequency:** stock period calibration is `8000`, but the actual ATU-II clock/divider and
   output frequency have not been bench measured. Scope the former purge output and adjust it for
   the selected solenoid.
3. **Output polarity/plumbing:** prove that commanded zero produces minimum boost and establish
   whether increasing duty raises or lowers boost with the installed 3-port plumbing.
4. **Purge diagnostics:** `evap_purge_flow_diagnostic` and P0458/P0459 are not neutralized by the
   patcher and may set faults.
5. **Controller scope:** target and feed-forward remain RPM-only. The throttle gate prevents
   boost control at low demand, but a future 2-axis RPM×load/throttle target is preferable.
6. **Hard-cut behavior:** the hard cut has no hysteresis and can chatter at its threshold. Prove
   injector cut and recovery on a bench before relying on it.
7. **Checksum:** hook edits lie inside the stock checksum region. Save with a verified
   `subarudbw` checksum implementation before flashing.
8. **Hardware confidence:** the purge-output identification and all patch behavior remain
   statically/binary verified, not vehicle verified.

## Required commissioning sequence

1. Fit and calibrate the boost-capable MAP sensor; verify logged MAP over the full range.
2. Keep `Kp = 0`, use zero/very conservative base duty, and validate throttle-gate transitions.
3. Scope output frequency and polarity with the solenoid disconnected from boost control.
4. Prove soft duty shutdown and hard fuel cut using simulated MAP input.
5. Resolve purge diagnostics and verify the final checksum.
6. Connect the solenoid with wastegate spring pressure as the mechanical fallback.
7. Tune feed-forward first, then introduce proportional gain gradually.
