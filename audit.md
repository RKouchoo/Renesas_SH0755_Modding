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

# Five-Psi / 98 RON Base Turbo Map Audit

Audit date: 2026-07-15. Output:
`base_turbo_map/D2WD610H_5psi_98RON_base_turbo.bin`.

## Verdict

The base-turbo image is a reproducible, checksum-valid calibration derivative of the verified
combined patch. It is suitable as a conservative **starting file for hardware entry and dyno
commissioning**, not as an assumption-complete flash-and-drive tune. The fuel and ignition edits
are structurally verified, and an OEM STI-pink injector starting calibration is now installed, but
injector identity/condition, fuel-pressure capacity, MAF
scaling, MAP validation, post-turbo wideband logging, and physical boost tests remain mandatory.

## Build provenance and binary checks

- `build_base_turbo_map.py` reads the pinned root stock ROM, verifies both stock BIN copies and the
  original SRF `MEMD` payload, and reconstructs the combined patch in memory.
- That intermediate stage must be byte-identical to
  `patch/D2WD610H_boost_single_front_af.bin`, SHA-256
  `019e06e509afce2e798bfe29543e2536524c259d3ab6683c7dd3131ee069fb5e`, before calibration is
  allowed. No generated image is used as patch input.
- The pinned 192-KiB A4TE002B injector donor must have CALID `A4TE002B`, SHA-256
  `e3cc868a51476aaa25c1ffb63e8af8ba3e35ca4ace404e842f193bf117754b44`, flow raw `4900` at
  `0x2866B`, and latency raw `{697,372,245,171,95}` at `0x28673` before calibration is allowed.
- Output SHA-256 is
  `fd9a9354c7a9f2d82813253d41b17adb058b68ceb3f426a0c197a6322fbf2c0f`.
- Exactly 1,043 bytes differ from the combined stage across 39 owned writes. Ownership covers the
  paired Primary Open Loop axes/maps, CL-to-OL delay, shared timing and KCA axes, six base-timing
  maps, two KCA maps, IAT compensation, Rev Limit A, injector scalar/deadtime, four cranking maps,
  two tip-in maps and threshold, five AVLS tables, six boost calibration fields, and checksum.
- The first Subaru checksum table entry remains `0x2000..0x7FAF7`; calculated/stored difference
  `0x4BD6335B` satisfies additive target `0x5AA5A55A`.
- The matching combined RomRaider definition parses with all edited table addresses unchanged.
- The canonical root/base stock ROMs, SRF, combined artifact, patch code/hooks, enable bytes, MAP
  scaling, O2 patch, and removed-sensor DTC edits remain unchanged.

## Calibration safety properties verified

- Spring-only boost: base WGDC is all zero, Kp is zero, and maximum final duty ratio is zero. Both
  patches remain enabled, retaining the hard MAP fuel-cut wrapper.
- The target remains 5 psi from 2500 RPM through its final breakpoint rather than tapering at high
  RPM. Because the final duty clamp is zero, it still cannot raise boost above spring pressure.
- Soft duty shutdown is 5.5 psi and hard fuel cut is 6.5 psi relative to 760 mmHg. The limits still
  depend completely on validating the installed donor-scaled MAP sensor and have no atmospheric
  compensation or hard-cut hysteresis.
- Both 14x10 Primary Open Loop maps use the richer stock bank or the new lambda cap, then match
  banks at each edited cell. No cell becomes leaner. Caps progress from lambda 0.93 at 0.96 g/rev
  to 0.78 at 1.60+ g/rev, with 0.77 at 6000+ RPM. Both fuel axes, the shared timing axis, and both
  KCA axes now end at 3.0 g/rev rather than 2.0.
- Both atmospheric CL-to-OL delay counters are zero, making the enriched Primary OL result decide
  the transition instead of the stock delayed threshold path.
- All six base-timing maps are capped from 1.09 g/rev / 2000 RPM up, including the two high-cam
  paths used by earlier AVLS, and no cell is advanced. Full-load ceilings are -2 degrees at 2000,
  4 at 3200, and 13 at 6800 RPM.
  Positive KCA is capped at 2 degrees at 1.09 g/rev and removed at 1.22+ g/rev; no KCA cell is
  increased.
- The high-IAT curve reaches -10.20 degrees at 110 C. Rev Limit A is set to the requested 6800 cut /
  6770 resume, retaining 30 RPM hysteresis and a hard limiter.
- The A4TE002B factory injector calibration translates to D2WD raw flow `3266.667236` (552.47
  cc/min estimated) and deadtimes 2.788/1.488/0.980/0.684/0.380 ms. The 0.4893883551 injector-scale
  ratio is applied to all absolute cranking/tip-in IPW starting values, rounding toward richer.
- AVLS actuation is permitted at 2500 RPM; the load curves are lowered and the hard high-cam
  engage/release points are 3200/3000 RPM with stock 10-unit hysteresis retained.
- Both MAF arrays remain byte-identical. The MAF Limit is already max-encoded at about 300 g/s,
  and Engine Load Limit remains 4.0 g/rev above the expanded 3.0 g/rev calibration axes.

## Remaining flash blockers

1. Confirm all six injectors are genuine/matched STI top-feed pinks, validate the OEM starting
   scalar/deadtime with trims and start/transient tests, and prove fuel-pump/regulator differential
   pressure at boost.
2. Calibrate the installed MAF/housing and prove it does not reach its voltage or approximately
   297.69 g/s table ceiling.
3. Fit the MAP sensor matching `{-414.0, 514.199951}` and validate it against a reference over
   vacuum and positive pressure.
4. Complete standalone front-A/F/rear-delete tests and validate external post-turbo wideband
   timestamps/status.
5. Pressure-test the 45 mm wastegate and prove direct-reference spring pressure, zero-duty
   polarity, PWM behavior, boost-creep margin, and the simulated hard-cut response.
6. Use a load-controlled dyno, monitor fuel/oil pressure externally, and follow
   `base_turbo_map/COMMISSIONING.md`; stop rather than tuning around a failed hardware gate.

No Ghidra function was opened for this calibration revision. Every edited address was an already
mapped, named RomRaider table, so there was no inspected function requiring a rename.

# Standalone Rotational-Idle Patch Audit

Audit date: 2026-07-15. Target: D2WD610H / ECU ID `3C5A387116`, Renesas SH7055,
stock image `2005 BLE MT.bin`.

## Verdict

`patch/patch_rotational_idle.py` produces a separate, default-OFF development image that should
execute the intended bounded timing post-processing. It always runs the complete stock final
timing task first, requires exact enable `01` and a warm/stationary/closed-throttle/high-vacuum
idle window, then applies six retard-only offsets. It does not cut fuel, modify idle airflow,
force AVLS, disable misfire detection, alter the limiter, or allocate RAM.

The component follows the same guarded stock-to-ROM and `apply_to_rom()` framework as the boost
and front-A/F components. Its allocation and changed-byte ownership are disjoint, making it ready
for a later combined-patch integration. That integration has deliberately not been performed:
`patch_combined.py`, the existing combined binary, and `base_turbo_map` remain unchanged.

This verdict is static and binary only. It does not prove idle quality, sound, exhaust/turbo
temperature, vibration, misfire behavior, checksum acceptance, or safe operation on the vehicle.

## Ghidra verification and naming

- Periodic task-pointer slot `0x11E30` contains stock target `0x279CC`.
- `ign_final_timing_per_cylinder_update` at `0x279CC` combines a common timing result with six
  correction floats at `0xFFFFCCC8..0xFFFFCCDC`, applies stock clamps, and writes six final
  angles at `0xFFFFC0EC..0xFFFFC100`.
- The six-output consumers were traced through the minimum check, schedule-count conversion,
  current-cylinder selection, and logger conversion. The normal ignition logger reads the first
  final angle at `0xFFFFC0EC`.
- ECT `0xFFFFB3AC`, RPM `0xFFFFB544`, processed throttle `0xFFFFB314`, MAP
  `0xFFFFABC4`, and vehicle speed `0xFFFFB538` are confirmed live float inputs. The vehicle-speed
  identity is independently supported by its comparison with the stock 4.0-km/h idle-timing
  threshold at ROM `0x77E1C`.
- Every function opened in this trace was renamed in the live Ghidra project using the project's
  underscore convention: the three idle/base timing functions, final per-cylinder update, six
  correction-state functions, four downstream timing/logger functions, and the fixed-point
  runtime export helper. The exact names and addresses are recorded in
  `docs/D2WD610H_RE_notes.md`.

## Binary checks completed

- The builder always reads the fixed root stock ROM, requires its exact 512-KiB length and
  SHA-256 `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`, patches an
  in-memory copy, and refuses an output path that aliases the stock source.
- Generated artifact: `patch/D2WD610H_rotational_idle.bin`, 512 KiB, SHA-256
  `f5ce45cb46b244e0c3973e3dfab699a3a2a13a1b296b758c96ec19f655ed7165`.
- Exactly 404 bytes differ from stock. Ownership is limited to the guarded task pointer and the
  dedicated enable/calibration/wrapper allocations at `0x7DB40..0x7DCEB`.
- The enable byte is `00` in the generated image. Machine code compares it with exact `01`; all
  other values leave the newly computed stock timing outputs unchanged.
- Every operating boundary is inclusive: ECT 80–105 C, RPM 600–1050, throttle no greater than
  native 1.68 (about 2%), vehicle speed no greater than 1 km/h, and MAP 150–550 mmHg absolute.
- Each sensor and gate threshold is self-compared before its range check, so NaN values return
  directly to stock timing. NaN offsets and non-positive/NaN maximum-retard calibration produce
  zero offset for the affected calculation; a NaN final-timing floor retains the stock angle.
- Default offsets are `{-6,0,-6,0,-6,0}` degrees. Positive requested offsets are forced to zero,
  requested retard is limited by the 8-degree maximum, and the result uses a 5-degree-BTDC floor.
  A final original-angle ceiling prevents either the floor or malformed maximum-retard data from
  adding advance relative to the stock result.
- `verify_rotational_idle.py` regenerates the complete expected image, verifies every float and
  changed offset, pins the exact-enable branch, six-cylinder loop, stock-angle ceiling, and
  balanced return, and decodes 136 injected SH-2E instructions with no unknown opcode.
- The executable policy model exercises every gate on and outside its boundary, all non-`01`
  enable values, positive offsets, maximum-retard limiting, the final timing floor, and the
  no-advance ceiling.
- Independent stock builds of boost, front-A/F, and rotational-idle components have pairwise
  disjoint changed-byte sets. Applying all three guarded APIs in memory produces their exact
  byte-set union and preserves every independently generated component byte.
- The canonical root ROM was re-read after build and verification and remains unchanged.

## RomRaider definition and separation

- `defs/D2WD610H_AVLS_rotational_idle_patch.xml` is self-contained and contains only the pruned
  metric `32BITBASE` plus target XMLID `D2WD610H_AVLS_ROTATIONAL_IDLE_PATCH` for internal ID
  `D2WD610H`.
- It exposes `Rotational Idle Patch Enable` at `0x7DB40`, ten scalar gates/limits, and the six
  per-cylinder offsets at `0x7DB6C`. All addresses and `01`/`00` switch states parse and verify.
- Byte simulation confirms an OFF-to-ON definition edit changes only `0x7DB40` before checksum
  handling. This is a flash calibration switch, not a live logger control.
- No rotational table or switch was added to the boost, front-A/F, existing combined, or base
  turbo definitions. A later merge must add the component and its definition entries together,
  then extend the combined exact-union verifier.

## Remaining blockers and commissioning order

1. Produce and independently verify a valid Subaru checksum; the standalone builder does not
   correct it.
2. Flash/run the standalone image with the switch OFF first. Confirm the complete stock warm idle
   and log ECT, RPM, throttle, speed, MAP, timing, lambda, corrections, battery voltage, and all
   six misfire counters.
3. Test the mild defaults only while fully warm, stationary, in neutral, and without boost
   control. Confirm cylinder-1 timing changes only inside the documented window and returns to
   stock immediately outside it.
4. Monitor exhaust/turbo temperature, oil pressure, lambda, RPM stability, misfire counts, and
   vibration. Stop on any abnormal result; do not disable misfire protection to mask it.
5. Decide from measured behavior whether a stronger effect is safe or useful. The current patch
   supplies uneven timing only and may produce a mild or negligible audible effect.
6. Merge the unchanged component API into the main patch only after standalone testing passes,
   then create a matching three-switch combined definition, checksum-valid output, and complete
   three-component regression audit.
