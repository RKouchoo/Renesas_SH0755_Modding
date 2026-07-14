# Boost-Control Patch Audit

Audit date: 2026-07-14. Target: D2WD610H, Renesas SH7055, stock image
`2005 BLE MT.bin`.

## Verdict

The single patch is structurally valid and its injected SH-2E code should execute as designed,
but binary verification is not hardware validation. It includes proportional + feed-forward
control, a minimum-throttle driver-demand gate, soft duty shutdown, and hard fuel cut. It still
requires the matching MAP-sensor fitment and calibration validation, PWM/polarity bench testing,
purge-DTC handling, checksum correction, and an overboost-cut bench test before boost is applied.

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
- `defs/D2WD610H_AVLS_boost_patch.xml` parses and its boost-table storage addresses match the
  current injected layout. The companion `D2WD610H_AVLS.xml` contains AVLS only; both use the
  pruned metric RomRaider base and contain no unrelated ECU definitions.
- No persistent scratch RAM is introduced.
- The A2WC510N donor image is pinned at SHA-256
  `db8827673a2383ce0ee3182d2c33f81be39fd63c3545e77b3e6bf8476488008d`. Its boost-table
  addresses match the pinned SubaruDefs definition; Target Boost A/B and Initial WGDC A/B are
  byte-identical pairs in that image.
- Ghidra revalidation renamed `0x7A14` to `map_sensor_voltage_to_pressure_process` and confirmed
  `MAP_native = voltage × multiplier + offset`. The patch copies donor floats
  `{-414.0, 514.199951}` over guarded stock values `{-150.0, 250.0}` at `0x72810`; pressure at
  `0xFFFFABC4` is native mmHg absolute, not kPa.
- The 5 psi defaults are a documented reduction of the donor's full-demand curves, not a raw 3D
  table transplant: the patch controller is RPM-only and has no integral state. See
  [boost_donor_A2WC510N.md](docs/boost_donor_A2WC510N.md).
- The sole generated artifact is `patch/D2WD610H_boost.bin` (512 KiB, SHA-256
  `6caca8c2ce8cc6522ee5e6e83808992ec7aa2920177f08c3856255405161cd0a`). Its 336 changed bytes
  are confined to the two guarded hooks (`0x11D3C..0x11D3F`, `0x3FD8C..0x3FD8F`), MAP scaling
  (`0x72810..0x72817`), and injected free-space region (`0x7D790..0x7D8DF`). The obsolete split
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
- Default minimum throttle is `30.0` (about 35.7% under the donor definition's display scaling).
  This is a commissioning value, not a validated final calibration. The gate is deliberately
  fail-closed for equality and ordinary low-throttle operation.
- The hard MAP overboost wrapper is independent of this gate and remains active at low throttle.

The gate is stateless and therefore has no hysteresis. If testing shows chatter around the
threshold, use separate enable/disable thresholds only after a safe state-storage strategy is
proven, or gate from a confirmed existing hysteretic demand flag.

## Remaining blockers

1. **MAP sensor and scaling:** the patch installs the A2WC510N scaling at `0x72810`, but cannot
   prove the physical sensor. Fit the compatible sensor and validate `0xFFFFABC4` against a
   reference gauge. Closed-loop correction and both MAP overboost limits remain untrusted until
   that measurement passes.
2. **PWM frequency:** stock period calibration is `8000`, but the actual ATU-II clock/divider and
   output frequency have not been bench measured. Scope the former purge output and adjust it for
   the selected solenoid.
3. **Output polarity/plumbing:** prove that commanded zero produces minimum boost and establish
   whether increasing duty raises or lowers boost with the installed 3-port plumbing.
4. **Purge diagnostics:** `evap_purge_flow_diagnostic` and P0458/P0459 are not neutralized by the
   patcher and may set faults.
5. **Controller scope:** target and feed-forward remain RPM-only. The throttle gate prevents
   boost control at low demand, but a future 2-axis RPM×load/throttle target is preferable. The
   target and limits are absolute-pressure values referenced to 760 mmHg; unlike the donor, the
   patch does not apply atmospheric-pressure target compensation.
6. **Hard-cut behavior:** the hard cut has no hysteresis and can chatter at its threshold. Prove
   injector cut and recovery on a bench before relying on it.
7. **Checksum:** hook edits lie inside the stock checksum region. Save with a verified
   `subarudbw` checksum implementation before flashing.
8. **Hardware confidence:** the purge-output identification and all patch behavior remain
   statically/binary verified, not vehicle verified.

## Required commissioning sequence

1. Fit the A2WC510N-compatible MAP sensor and validate the installed donor calibration over the
   full logged range.
2. Override the donor-derived default to `Kp = 0`, use zero/very conservative base duty, and
   validate throttle-gate transitions.
3. Scope output frequency and polarity with the solenoid disconnected from boost control.
4. Prove soft duty shutdown and hard fuel cut using simulated MAP input.
5. Resolve purge diagnostics and verify the final checksum.
6. Connect the solenoid with wastegate spring pressure as the mechanical fallback.
7. Tune feed-forward first, then introduce proportional gain gradually.

# Single-Front-A/F Patch Audit

Audit date: 2026-07-14. Target: D2WD610H / ECU ID `3C5A387116`, Renesas SH7055,
stock image `2005 BLE MT.bin`.

## Verdict

The standalone single-front-A/F patch is structurally valid. It retains the complete stock
RH/Bank-1 front A/F processing path and mirrors its processed lambda-like, pump-current-like, and
readiness results into the Bank-2 RAM paths. It disables only the five diagnostic switches tied
to the physically removed LH/Bank-2 front sensor.

The former ECU-side aftermarket-wideband input has been completely retired. Both rear
narrowband channels, the rear processing entry, their processed RAM values, and their checked DTC
switches remain stock. A post-turbo lambda sensor is external instrumentation and must be logged
outside the ECU.

This is binary verification, not vehicle validation. The retained sensor, both-bank behavior,
exact harness variant, checksum, and rear-sensor operation still require physical testing before
the patch is merged with boost control or flashed for road use.

## Binary checks completed

- The patcher always reads the fixed root stock image, verifies its 512 KiB length and SHA-256,
  patches a private in-memory copy, and refuses an output path that aliases the stock file.
- The root `2005 BLE MT.bin` remains unchanged at SHA-256
  `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
- The generated `patch/D2WD610H_single_front_af.bin` is 512 KiB with SHA-256
  `cd7c926b45a3f14be1aeb2e50df25ed254ad1780beb76f9c871515047a7cf5b1`.
- All 144 changed bytes are confined to three guarded front hooks/task entries, five explicit
  Bank-2 front A/F DTC switches, and the three injected front-mirror blobs.
- The front process hook at `0xB690` runs the complete stock
  `front_af_sensor_pair_signal_process` through a prologue trampoline, then copies
  `AE60->AE64`, `AE68->AE6C`, and `AE70->AE74`.
- The stock front pump-current diagnostic task still executes. Its task-pointer wrapper refreshes
  `AE70->AE74`, and the Bank-2 inhibit entry at `0x6500C` tail-jumps to the unchanged Bank-1
  helper at `0x64FD0`.
- The only disabled switches are P0051, P0052, P0151, P0152, and P0154 for the removed
  LH/Bank-2 front sensor.
- The verifier confirms that the retained RH/Bank-1 front switches, all four checked RH-rear
  switches, and all four checked LH-rear switches remain enabled.
- The rear process entry at `0xE0D0` is byte-identical to stock. No hook writes `0xFFFFB098` or
  `0xFFFFB09C`; the retired calibration range `0x7D900..0x7D91F` and external-input code range
  `0x7DA60..0x7DB3F` both remain erased stock flash.
- The standalone image leaves the boost allocation `0x7D790..0x7D8DF` byte-identical to stock.
- The verifier regenerated every blob and hook from source, rejected all unexpected changed
  offsets, replayed the overwritten stock prologue byte-for-byte, and decoded 42 injected SH-2E
  instructions with no unknown opcodes.
- The shared assembler self-tests pass. Rebuilding the boost patch produced a byte-identical
  image with its existing SHA-256
  `6caca8c2ce8cc6522ee5e6e83808992ec7aa2920177f08c3856255405161cd0a`, and the pinned donor
  table/default verifier also passes.

## Project cleanup checks

- `patch/patch_single_front_af.py` and `patch/verify_single_front_af.py` replace the retired
  wideband-named patcher and verifier.
- The ECU-side analog conversion, voltage-window test, rear-process trampoline, external-sensor
  RAM publication, and four RH-rear DTC edits have been removed from the patch.
- The dedicated external-sensor logger installer, logger fragment, six-table calibration
  definition, and old generated ROM have been removed.
- The front-A/F patch now adds no calibration tables and requires no separate RomRaider ROM or
  logger definition.
- `defs/D2WD610H.xml` remains the D2WD610H metric base;
  `defs/D2WD610H_AVLS.xml` remains AVLS-only; and
  `defs/D2WD610H_AVLS_boost_patch.xml` remains AVLS plus only the canonical boost-patch
  calibrations.
- The stock reverse-engineering notes now describe `0xFFFFAB20/0xFFFFB098` and
  `0xFFFFAB0C/0xFFFFB09C` as the unmodified RH/LH rear narrowband paths.

## External logging boundary

The post-turbo lambda sensor has no ECU electrical or firmware interface. Record it through its
own serial or CAN logger and merge it with RomRaider data using monotonic timestamps. The
analysis file should use lambda units and retain validity/fault fields when the external protocol
provides them. Account for exhaust transport delay when comparing the post-turbo measurement with
RPM, throttle, load, or boost transitions.

No external lambda reading currently commands enrichment, wastegate duty shutdown, or fuel cut.
Boost commissioning must therefore retain independent mechanical and ECU MAP-based safeguards.

## Remaining blockers and commissioning order

1. Confirm the car has the expected retained RH and removed LH front-sensor connector variant;
   stop on any mismatch in connector colour, cavity numbering, or continuity.
2. Correct and independently verify the `subarudbw` checksum.
3. First-run the single-front image without boost. Log E91/E109, closed-loop state, both fuel
   corrections, and all front/rear sensor DTCs.
4. Prove the two logged front channels track through idle, steady cruise, warm-up, throttle
   transitions, forced open loop, and a controlled retained-sensor fault.
5. Confirm both stock rear sensors, heaters, and catalyst diagnostic behavior remain normal.
6. Validate the external post-turbo lambda stream, its status indication, and timestamp alignment
   before using it for tuning decisions.
7. Merge the independently verified boost and front-A/F builders only from a fresh copy of the
   canonical root stock ROM. Repeat the complete binary audit and hardware tests as one system.
