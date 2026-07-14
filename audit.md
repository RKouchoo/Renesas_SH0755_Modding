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
- `defs/D2WD610H_AVLS_boost_patch.xml` parses and its boost-table plus runtime-switch storage
  addresses match the current injected layout. The companion `D2WD610H_AVLS.xml` contains AVLS
  only; both use the pruned metric RomRaider base and contain no unrelated ECU definitions.
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
- The generated boost artifact is `patch/D2WD610H_boost.bin` (512 KiB, SHA-256
  `744f4c320f5097256af16101cbba1b71985d8c9dfa77805158a0c4e204fe4560`). Its 369 changed bytes
  are confined to the two guarded hooks (`0x11D3C..0x11D3F`, `0x3FD8C..0x3FD8F`), MAP scaling
  (`0x72810..0x72817`), and injected free-space region (`0x7D790..0x7D903`). The obsolete split
  patcher and `_p1`/`_p2` images have been removed.

## RomRaider runtime toggle

- `Boost Control Patch Enable` is a one-byte switch at `0x7D80C`; `01` is on and `00` is off.
  The generated image contains `01`.
- The controller at `0x7D810` requires the exact value `01` before saving `PR` or evaluating any
  boost table. `00`, erased `FF`, and all other values fail closed: the controller forces
  `FR4 = 0.0` and tail-calls the stock PWM output stage, producing zero commanded EBCS duty.
  Passing through stock purge duty was rejected because it could energize a solenoid physically
  rewired for boost control.
- The rev-limiter wrapper at `0x7D8C4` always runs the stock limiter first. With the switch off it
  returns immediately, bypassing only the patch's added MAP fuel cut.
- XML parsing and a byte-level simulation confirmed that changing the RomRaider switch from on
  to off changes only `0x7D80C` in the generated image before checksum correction.
- The definition edits a flash byte; it is not a live logger toggle. Changing state requires a
  checksum-correct save and reflash.
- Off is a spring-pressure fallback only after bench proof that zero commanded duty produces
  minimum boost with the installed valve and plumbing. It does not restore the stock
  `{-150.0, 250.0}` MAP conversion; `0x72810` remains on the donor calibration.

## Throttle gating

Ghidra tracing confirmed processed throttle opening at float RAM `0xFFFFB314`:

- `cl_ol_transition_delay_update` at `0x22756` passes `0xFFFFB314` to the calibrated
  “CL to OL Transition with Delay (Throttle)” lookup.
- Its producer at `0x14DCC` performs DBW throttle-sensor processing/plausibility and was renamed
  `throttle_position_sensor_process` in Ghidra.
- The controller compares this value with a tunable float at `0x7D8BC`.
- Boost duty is enabled only when `throttle > minimum`; at or below the threshold the stub
  tail-calls the stock output stage with duty ratio `0.0`.
- Default minimum throttle is `30.0` (about 35.7% under the donor definition's display scaling).
  This is a commissioning value, not a validated final calibration. The gate is deliberately
  fail-closed for equality and ordinary low-throttle operation.
- The hard MAP overboost wrapper is independent of this gate and remains active at low throttle
  while the patch-enable switch is on.

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

Audit date: 2026-07-15. Target: D2WD610H / ECU ID `3C5A387116`, Renesas SH7055,
stock image `2005 BLE MT.bin`.

## Verdict

The standalone single-front-A/F patch is structurally valid. It retains the complete stock
RH/Bank-1 front A/F processing path and mirrors its processed lambda-like, pump-current-like, and
readiness results into the Bank-2 RAM paths. Exact runtime enable `01` also bypasses both rear
narrowband ADC conversion and all five traced rear monitor stages. The generated image disables
five DTC switches for the removed LH/Bank-2 front sensor and eight mapped DTC switches for the
removed rear sensors/heaters.

The former ECU-side aftermarket-wideband input remains completely retired. A post-turbo lambda
sensor is external instrumentation and must be logged outside the ECU. Rear-O2 logger results are
stale/undefined while the delete is enabled.

This is binary verification, not vehicle validation. The retained sensor, both-bank behavior,
exact harness variant, checksum, rear-delete behavior, and open-circuit heater outputs still require physical testing before
the patch is used alone or enabled in the combined image.

## Binary checks completed

- The patcher always reads the fixed root stock image, verifies its 512 KiB length and SHA-256,
  patches a private in-memory copy, and refuses an output path that aliases the stock file.
- The root `2005 BLE MT.bin` remains unchanged at SHA-256
  `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
- The generated `patch/D2WD610H_single_front_af.bin` is 512 KiB with SHA-256
  `99a0b2df7f24a247307dfdde6790d464264bbbe6ae8498632735d6d98b4ae5eb`.
- All 442 changed bytes are confined to nine guarded front/rear hooks or task pointers, 13
  explicit removed-sensor DTC switches, and 12 injected allocations.
- The front process hook at `0xB690` runs the complete stock
  `front_af_sensor_pair_signal_process` through a prologue trampoline, then copies
  `AE60->AE64`, `AE68->AE6C`, and `AE70->AE74`.
- The stock front pump-current diagnostic task still executes. Its task-pointer wrapper refreshes
  `AE70->AE74` only while enabled. The Bank-2 inhibit entry at `0x6500C` jumps to a selector at
  `0x7DA20`: enabled tail-jumps to the unchanged Bank-1 helper at `0x64FD0`; disabled directly
  reproduces the stock Bank-2 helper's `0xFFFFD26C bit 0 -> return 0/2` behavior.
- The disabled front switches are P0051, P0052, P0151, P0152, and P0154. The disabled rear
  switches are P0037, P0038, P0057, P0058, P0137, P0138, P0157, and P0158. Retained RH/Bank-1
  front DTC switches remain enabled.
- The rear process entry at `0xE0D0` is guardedly replaced with an exact-`01` selector. Enabled
  returns before converting either raw rear channel; disabled uses a relocated prologue and
  resumes stock at `0xE0DC`.
- Task pointers `0x11488`, `0x1148C`, `0x11490`, `0x11494`, and `0x114A0` are guardedly
  redirected through selectors for rear threshold, filter/delta, response integrator, response
  ratio publication, and paired low/high-voltage diagnostics. Each returns immediately only for
  exact `01` and otherwise tail-jumps to its original stock target.
- Former external-wideband free space `0x7DA60..0x7DB3B` now holds only these rear-delete
  selectors and relocated stock prologue. No aftermarket conversion or ECU logger input returned.
- The standalone image leaves the boost allocation `0x7D790..0x7D903` byte-identical to stock.
- The verifier regenerated every blob and hook from source, rejected all unexpected changed
  offsets, reconstructed both overwritten stock prologues, and decoded 136 injected SH-2E
  instructions with no unknown opcodes.
- The shared assembler self-tests pass. Rebuilding the boost patch produced a byte-identical
  image with its existing SHA-256
  `744f4c320f5097256af16101cbba1b71985d8c9dfa77805158a0c4e204fe4560`, and the pinned donor
  table/default verifier also passes.

## Ghidra rear-path verification

- Raw RH/LH rear ADC words `0xFFFFAB20/0xFFFFAB0C` are converted by
  `rear_o2_sensor_pair_adc_convert` at `0xE0D0` into processed floats
  `0xFFFFB098/0xFFFFB09C`.
- Ghidra xrefs from the processed values lead to `rear_o2_sensor_bank_voltage_select` at
  `0xDFB4`. Its consumers are `rear_o2_sensor_pair_filter_delta_update` and two small SSM/log
  conversion stubs at `0x31962/0x31978`; no fuel-control consumer was found.
- The traced downstream chain is `rear_o2_sensor_monitor_threshold_update` (`0x33B12`),
  `rear_o2_sensor_pair_filter_delta_update` (`0x33AAC`),
  `rear_o2_sensor_response_integrator_update` (`0x33970`),
  `rear_o2_sensor_response_ratio_update` (`0x34BE4`), then
  `rear_o2_sensor_voltage_diagnostic_dispatch` (`0x69568`) and its low/high pair functions.
- The initialization-only `rear_o2_sensor_response_integrator_initialize` (`0x33964`) writes
  1.0 to both integrators. It remains stock; all runtime consumers of those integrators are
  bypassed while the delete is enabled.
- Every function inspected in this pass was renamed in the live Ghidra project using underscore
  conventions. Comments at the converter/getter and five patched stages were updated to record
  the switch behavior and task-pointer locations.
- The rear heater-output driver path was not hooked or electrically tri-stated. With sensors
  disconnected, its pins can still be commanded into an open circuit; the eight mapped circuit
  DTCs are disabled. This hardware behavior remains a bench check.

## RomRaider runtime toggle

- `defs/D2WD610H_AVLS_single_front_af_patch.xml` is a self-contained metric definition with XMLID
  `D2WD610H_AVLS_SINGLE_FRONT_AF_PATCH`. It parses successfully and exposes `Single Front A/F
  Patch Enable` at `0x7D91C` with `01`/`00` on/off states. The generated image defaults to `01`.
- Only exact `01` enables front mirroring/Bank-2 inhibit substitution and all six rear no-op
  selectors. `00`, erased `FF`, and all other values select stock front and rear runtime paths.
  XML and byte-level simulation confirmed that operating this switch changes only `0x7D91C`
  before checksum correction.
- The definition edits a flash byte; state changes require a checksum-correct save and reflash.
- The 13 removed-sensor DTC switches are noncontiguous static edits and are deliberately not
  hidden behind the one-byte runtime flag. For fully stock diagnostics, re-enable all five front
  and eight rear codes listed above in the same definition before saving/flashing.
- Off is not a valid normal configuration after any of the three sensors is removed, because
  stock front/rear runtime logic will again consume absent channels.

## Project cleanup checks

- `patch/patch_single_front_af.py` and `patch/verify_single_front_af.py` replace the retired
  wideband-named patcher and verifier.
- The retired ECU-side aftermarket analog conversion, calibration, and RAM publication remain
  removed. The newly used `0x7DA60..0x7DB3B` blocks are rear-delete selectors only.
- The dedicated external-sensor logger installer, logger fragment, six-table calibration
  definition, and old generated ROM have been removed.
- The front-A/F patch adds no sensor calibration or logger parameter. It now has a dedicated
  RomRaider ROM definition solely so its runtime-enable byte and existing DTC switches can be
  edited together.
- `defs/D2WD610H.xml` remains the D2WD610H metric base;
  `defs/D2WD610H_AVLS.xml` remains AVLS-only; and
  `defs/D2WD610H_AVLS_boost_patch.xml` remains AVLS plus only the canonical boost-patch
  calibrations/runtime switch. `defs/D2WD610H_AVLS_single_front_af_patch.xml` remains AVLS plus
  only the single-front runtime switch. The combined
  `defs/D2WD610H_AVLS_boost_single_front_af_patch.xml` contains the unchanged boost tables plus
  both component runtime switches.
- The reverse-engineering notes now describe `0xFFFFAB20/0xFFFFB098` and
  `0xFFFFAB0C/0xFFFFB09C` as stock hardware/RAM paths whose conversion and monitor consumers are
  bypassed while the single-front/rear-delete switch is enabled.

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
5. Safely isolate both rear connectors. Confirm all eight mapped rear DTCs remain inactive,
   ignore stale rear logger values, and verify both fuel corrections remain stable. Scope the
   disconnected heater outputs if no-command behavior is required.
6. Validate the external post-turbo lambda stream, its status indication, and timestamp alignment
   before using it for tuning decisions.
7. After both standalone commissioning plans pass, rebuild and verify the combined image from the
   canonical root stock ROM. Repeat the hardware tests with both systems enabled together.

# Combined Boost + Single-Front-A/F Patch Audit

Audit date: 2026-07-15. Target: D2WD610H / ECU ID `3C5A387116`, Renesas SH7055,
stock image `2005 BLE MT.bin`.

## Verdict

`patch/patch_combined.py` produces one combined development image directly from a fresh copy of
the canonical root stock ROM. It does not patch either generated standalone image. The generated
ROM is the exact, non-overlapping union of the boost-control patch and the single-front-A/F plus
rear-O2-delete patch. Its structure, changed-byte ownership, injected instructions, O2 paths, and both
RomRaider switches are binary verified.

This does not make the image vehicle-validated. The standalone front-A/F behavior must first be
proven without boost, and the boost output/MAP/failsafe commissioning sequence must be completed
before the combined image is flashed. The combined ROM still requires a valid `subarudbw`
checksum.

## Original SRF provenance and de-encapsulation

- `base_roms/2005 BLE MT.srf` is 524,749 bytes with SHA-256
  `05eae5322072449d90e20e20125d5333738675168d623a320735958bfc7619aa`.
- `patch/extract_srf.py` parses the SRF as big-endian `INFO`, `DRMI`, `MEML`, and `MEMD` chunks;
  it does not scan for a guessed ROM signature or use a hard-coded tail carve.
- The single `MEMD` payload starts at file offset `0x1CD`, is exactly `0x80000` bytes, and contains
  CALID `D2WD610H` at ROM address `0x2000`.
- Its SHA-256 is
  `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
- The extracted payload is byte-identical to both `base_roms/2005 BLE MT.bin` and the canonical
  root `2005 BLE MT.bin`. The existing extracted BIN was therefore left unchanged.
- The combined builder repeats the SRF parse and byte comparison before every output build and
  rereads all protected stock sources afterward.

## Combined binary checks completed

- Generated artifact: `patch/D2WD610H_boost_single_front_af.bin`, 512 KiB, SHA-256
  `019e06e509afce2e798bfe29543e2536524c259d3ab6683c7dd3131ee069fb5e`.
- Exactly 811 bytes differ from stock: 369 owned by the boost patch plus 442 owned by the
  single-front-A/F patch, with zero overlapping offsets.
- Before composing the image, the builder independently applies each component to stock and
  rejects any intersecting changed-byte ownership. It then applies both guarded change sets to a
  separate fresh stock copy and requires the result to equal their exact union.
- Refactoring the component scripts to expose shared `apply_to_rom` functions did not change
  either standalone artifact: boost remains SHA-256
  `744f4c320f5097256af16101cbba1b71985d8c9dfa77805158a0c4e204fe4560`; single-front-A/F remains
  SHA-256 `99a0b2df7f24a247307dfdde6790d464264bbbe6ae8498632735d6d98b4ae5eb`.
- `patch/verify_combined.py` regenerates the expected image from stock, checks every byte, pins all
  component hooks/task edits and enable-dependent branches, verifies all 13 removed-sensor DTC
  edits, and confirms the retained Bank-1 front plus both rear-delete paths.
- All 13 injected code spans decode as 220 known SH-2E instructions with no unknown opcodes.
- The former external-wideband region `0x7DA60..0x7DB3B` now contains only verified rear-delete
  selectors/trampoline. No aftermarket-wideband input or logger publication was reintroduced.

## Combined RomRaider definition

- `defs/D2WD610H_AVLS_boost_single_front_af_patch.xml` is self-contained and contains only the
  pruned metric `32BITBASE` plus the D2WD610H target ROM.
- Target XMLID: `D2WD610H_AVLS_BOOST_SINGLE_FRONT_AF_PATCH`.
- It exposes all canonical boost calibrations, `Boost Control Patch Enable` at `0x7D80C`, and
  `Single Front A/F Patch Enable` at `0x7D91C`.
- Both generated bytes default to `01`. XML parsing and byte simulation verify that changing
  either switch to `00` changes only its own one-byte address before checksum handling.
- Boost `OFF` retains the donor MAP scaling and bypasses the added hard overboost cut. Front-A/F
  `OFF` restores stock front/rear runtime logic but does not re-enable the 13 removed-sensor DTC
  bytes. The existing component caveats remain unchanged in the combined image.
