# D2WD610H Patch Audits

# Standalone Boost-Control Patch Audit

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
  `d4c215a3acc2a68e7daa355d56510589b8f9aa4bf573e6bc4aa4224b16ffa2bc`). Its 370 changed bytes
  are confined to the two guarded hooks (`0x11D3C..0x11D3F`, `0x3FD8C..0x3FD8F`), MAP scaling
  (`0x72810..0x72817`), and injected free-space region (`0x7D790..0x7D903`). The obsolete split
  patcher and `_p1`/`_p2` images have been removed.

## RomRaider runtime toggles

- `Electronic Boost Control Enable` is at `0x7D80C` and defaults `00` so the actuator cannot
  command duty. `Overboost Fuel Cut Enable` is independent at `0x7D80D` and defaults `01`.
- The controller at `0x7D810` requires the exact value `01` before saving `PR` or evaluating any
  boost table. `00`, erased `FF`, and all other values fail closed: the controller forces
  `FR4 = 0.0` and tail-calls the stock PWM output stage, producing zero commanded EBCS duty.
  Passing through stock purge duty was rejected because it could energize a solenoid physically
  rewired for boost control.
- The rev-limiter wrapper at `0x7D8C4` always runs the stock limiter first. With its own switch off it
  returns immediately, bypassing only the patch's added MAP fuel cut.
- XML parsing and byte-level simulation confirm each RomRaider switch changes only its respective
  byte before checksum correction.
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
- The shared assembler self-tests pass. The current spring-pressure switch-split boost image is
  byte-identical to regeneration at SHA-256
  `d4c215a3acc2a68e7daa355d56510589b8f9aa4bf573e6bc4aa4224b16ffa2bc`, and the pinned donor
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
  `71b28714106dcc1eb7adfe59738fc8c6e968b2b94ca9337158f4442f46fcc1fe`.
- Exactly 812 bytes differ from stock: 370 owned by the boost patch plus 442 owned by the
  single-front-A/F patch, with zero overlapping offsets.
- Before composing the image, the builder independently applies each component to stock and
  rejects any intersecting changed-byte ownership. It then applies both guarded change sets to a
  separate fresh stock copy and requires the result to equal their exact union.
- Refactoring the component scripts to expose shared `apply_to_rom` functions did not change
  the single-front-A/F artifact. The spring-pressure switch split changes boost to SHA-256
  `d4c215a3acc2a68e7daa355d56510589b8f9aa4bf573e6bc4aa4224b16ffa2bc`; single-front-A/F remains
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
- It exposes all canonical boost calibrations, `Electronic Boost Control Enable` at `0x7D80C`,
  `Overboost Fuel Cut Enable` at `0x7D80D`, and `Single Front A/F Patch Enable` at `0x7D91C`.
- Defaults are `00`, `01`, and `01`, respectively. XML parsing and byte simulation verify that
  changing any switch changes only its own one-byte address before checksum handling.
- Both boost switches retain donor MAP scaling. Front-A/F
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
  `71b28714106dcc1eb7adfe59738fc8c6e968b2b94ca9337158f4442f46fcc1fe`, before calibration is
  allowed. No generated image is used as patch input.
- The pinned 192-KiB A4TE002B injector donor must have CALID `A4TE002B`, SHA-256
  `e3cc868a51476aaa25c1ffb63e8af8ba3e35ca4ace404e842f193bf117754b44`, flow raw `4900` at
  `0x2866B`, and latency raw `{697,372,245,171,95}` at `0x28673` before calibration is allowed.
- Output SHA-256 is
  `3564985c8e5d6e60b7d259408900e1b386bea51e372b90c805b04a32db4f404b`.
- Exactly 1,043 bytes differ from the combined stage across 39 owned writes. Ownership covers the
  paired Primary Open Loop axes/maps, CL-to-OL delay, shared timing and KCA axes, six base-timing
  maps, two KCA maps, IAT compensation, Rev Limit A, injector scalar/deadtime, four cranking maps,
  two tip-in maps and threshold, five AVLS tables, six boost calibration fields, and checksum.
- The first Subaru checksum table entry remains `0x2000..0x7FAF7`; calculated/stored difference
  `0x4DD4335A` satisfies additive target `0x5AA5A55A`.
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
- AVLS actuation is permitted at 2500 RPM; the oil-temperature-selected vehicle-speed curves are
  lowered and the hard high-cam engage/release points are 3200/3000 RPM with the stock 10 km/h
  hysteresis retained.
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

# Standalone MAFless Speed-Density Patch Audit

Audit updated: 2026-07-28. Target: D2WD610H / ECU ID `3C5A387116`, Renesas SH7055,
stock image `2005 BLE MT.bin`.

## Verdict

`speed_density/patch_speed_density.py` now produces a separate, always-on MAFless development
image. Periodic airflow is calculated only from MAP, RPM, a 13×17 VE surface, engine displacement,
post-intercooler IAT density correction, and a global multiplier. The injected helper has no MAF
fallback or runtime OFF state.

Both raw MAF conversion calls and the only scheduled raw-MAF limit/filter update are removed. The
MAF high/low input monitor and both scheduled calls to its mixed temperature-plausibility
condition are bypassed, and D2WD610H P0102/P0103 switches are disabled. Exact zero RPM produces
zero airflow. Any other invalid sensor, calibration, lookup, or arithmetic state produces a fixed
500 g/s rich/high-load fail-safe instead of preserving stale MAF data. That value is a shutdown
indication, not a validated limp mode.

The component retains the guarded stock-to-ROM and `apply_to_rom()` framework. Its changed-byte
ownership is disjoint from boost control, single-front-A/F plus rear delete, and rotational idle,
so it remains mergeable without relocating a current component. It has not been added to
`patch_combined.py` or `base_turbo_map`.

This verdict is static. It does not establish VE accuracy, transient fueling quality, checksum
acceptance, hardware wiring correctness, or safe vehicle operation.

## Ghidra verification and naming

- `sensor_processing_batch_task` at `0x6328` and `sensor_adc_processing_task` at `0x66C6` call the
  stock raw-MAF converter at instructions `0x639C` and `0x66D8`. The MAFless image changes both
  `jsr @r3` instructions (`430B`) to `nop` (`0009`).
- `maf_sensor_voltage_to_airflow_process` at `0x7C30` normally reads raw ADC `0xFFFFAB06`, uses
  the 44-point stock MAF curve, and writes `0xFFFFABE4`. The removed call means this result is no
  longer refreshed by the sensor task in the MAFless image.
- `periodic_airflow_sensor_task_dispatcher` at `0x107EE` contains the only computed call to
  `maf_airflow_limit_update` at `0x107F8`. That `jsr @r2` (`420B`) becomes `nop`, preventing stale
  raw-MAF state from propagating into the stock filter/fallback channels.
- `mass_airflow_slow_filter_update` at `0x177BE` is deliberately retained. Its sole scheduled call
  is at `0x114D2`; it reads final airflow `0xFFFFB420` and filters it into `0xFFFFB424`, so it is a
  downstream consumer of the speed-density result rather than a raw-MAF source.
- `maf_sensor_input_range_classify` at `0x7C52` classifies high/normal/low raw MAF ADC input.
  `maf_sensor_high_input_diagnostic_update` at `0x61332` handles classification 1/P0103, while
  `maf_sensor_low_input_diagnostic_update` at `0x613AC` handles classification 2/P0102 through
  the common entry at `0x61328`. `diagnostic_task_list_dispatcher` calls that entry through pointer
  `0x11804`; the patch replaces it with `sensor_processing_return_stub` at `0x66C2`. The mapped
  central DTC switches P0102/P0103 are bytes `0x5BD57/0x5BD58`; both stock `01` bytes become `00`.
- `diagnostic_temperature_maf_condition_flag_update` at `0x7266C` combines two temperature
  windows, raw MAF ADC, and ADC status bits into `0xFFFFB1F8` bit 0. Its two computed calls use
  pointers `0x1062C` and `0x1185C`; both are redirected to the same no-op return stub because the
  condition is invalid after physical MAF removal.
- Periodic slot `0x11D20` remains `maf_airflow_temperature_compensation_update` at `0x172A4`.
  The retained downstream half calculates load/filter/state channels `B428..B440`, which have
  broad ignition, fueling, trim, and diagnostic consumers.
- Immediately before the stock `B420` store, call `0x17398` loads its helper target from literal
  `0x1743C`. The patch changes that literal from `0x24B0` to the SD helper at `0x7E18C`, so the
  stock task stores modeled airflow and then continues all downstream calculations.
- MAP `0xFFFFABC4` is native mmHg absolute, RPM is float `0xFFFFB544`, IAT is degrees Celsius at
  `0xFFFFB3B8`, and final airflow is float g/s at `0xFFFFB420`.
- `engine_load_from_mass_airflow_calculate`, `fueling_airflow_input_update`, the closed-loop fuel
  tables, fuel-trim modes, airflow monitors, and logger conversion routines all consume the shared
  final-airflow channel. The patch therefore supplies the established load/fueling pipeline
  without patching each consumer.
- Additional inspected functions were renamed in the live project with underscore-style names,
  including airflow initialization/filtering, fuel-control airflow-table updates, diagnostic
  monitors, scaled logger outputs, and the three missed logger function boundaries around
  `0x316A2..0x31790`. A final consumer pass conservatively named 39 formerly generic functions by
  their confirmed use of `B424/B430/B438/B43C/B440/B444`; the names do not claim a narrower
  subsystem role than the recovered data flow. The full address/name list is in
  `docs/D2WD610H_RE_notes.md`.
- `speed_density/ghidra_scripts/ApplyMaflessNames.java` reproducibly applies all 49 late-trace
  names, including the four function boundaries missed by auto-analysis. The final headless run
  saved every name and the hook comments to the same stock Ghidra program.
  `ReportMafDiagnostics.java` is the read-only reference report used to locate the raw converter,
  classifier, diagnostic callers, and airflow channels.

## Runtime design and calibration

- The helper at `0x7E18C` allocates no RAM and is called inside the retained task immediately
  before its final B420 store. It mirrors the same modeled value into `B448/B458/B45C`, keeping
  the former raw-MAF state coherent for the next task cycle without reading the sensor.
- Model:
  `airflow_g/s = VE × MAP_mmHg × RPM × displacement_L × 1.3203052e-5 × IAT_correction × global`.
- Defaults are 2.999 L, 1.0 global multiplier, 500 g/s normal cap, 13 MAP columns, 17 RPM rows,
  and a ten-point `293.15 / (IAT_C + 273.15)` density curve.
- Default validity windows are MAP 100–1600 mmHg absolute, RPM 0–7500, and IAT -50–150 °C.
  Boundaries are inclusive. NaN and infinity are rejected with self-comparison, range checks, and
  a fixed maximum-finite-float constant. RPM is prechecked first, so exact zero publishes zero
  even while other sensor/calibration data is uninitialized; a non-finite RPM uses the fail-safe.
- A fixed, non-definition-exposed 500 g/s fault value is stored at `0x7DD00`. The configurable
  normal maximum remains at `0x7DD0C`; invalid calibration cannot turn the fixed fault output into
  MAF fallback.
- Stock MAF curve bytes remain physically present in the ROM because erasing unused calibration
  data has no runtime benefit. They are unreachable from the patched periodic airflow path and are
  removed from the generated MAFless RomRaider definition.
- MAP scaling is intentionally outside this standalone component. Removing the MAF/IAT assembly
  requires a separately wired, fast post-intercooler IAT sensor on the verified stock IAT circuit.

## Binary and definition checks completed

- The builder requires the canonical 512-KiB root stock SHA-256
  `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`, patches an in-memory
  copy, refuses stock-alias output, and rechecks the root file after writing.
- Generated image: `speed_density/D2WD610H_speed_density.bin`, SHA-256
  `548fc5353338248c683098507aed79a6c5f377bb2462b65a091a2f02b0899467`.
- Exactly 1,695 bytes differ from stock. Ownership is limited to the final-airflow helper pointer,
  two raw-MAF calls, the raw-MAF limit/filter call, three MAF-dependent diagnostic-task pointers,
  two MAF DTC bytes, and dedicated allocation `0x7DD00..0x7E39B`. The helper is 528 bytes.
- The verifier deterministically rebuilds the whole image and checks the retained task pointer,
  exact `0x17398` helper-call/delay-slot/`B420` store sequence, final-airflow helper hook, both
  MAF-call NOPs, raw limit/filter NOP, diagnostic-task bypasses, DTC bytes, fixed fault value,
  descriptors, monotonic axes, constants, normal samples, cap, zero-RPM behavior, every
  invalid-input/calibration class, opcodes, code/pool boundary, balanced return, synthetic-state
  literals, and allocated bytes.
- The helper literal pool is required to contain MAP/RPM/IAT, table helpers, descriptors,
  final/synthetic airflow RAM, and the fault constant. The verifier separately rejects the stock
  task address `0x172A4` in that pool, preventing accidental recursion.
- Independent boost, single-front/rear-delete, rotational-idle, and MAFless speed-density builds
  have pairwise-disjoint changed-byte sets. Applying all four APIs in memory produces the exact
  union and preserves each independently generated byte.
- `build_definition.py` derives a two-ROM-file definition from metric
  `defs/D2WD610H_AVLS.xml`, removes inherited MAF limit/scaling/compensation and P0102/P0103
  entries, and emits target XMLID `D2WD610H_AVLS_SPEED_DENSITY_ONLY` for internal ID `D2WD610H`.
  It exposes only the relevant speed-density scalars, gates, VE surface, and IAT curve.
- The canonical root stock ROM remains unchanged.

## Remaining blockers and commissioning order

1. Produce and independently validate the required Subaru checksum on a disposable working copy.
2. Fit and verify the post-intercooler IAT circuit using the correct vehicle wiring diagram.
3. Pressure-calibrate the installed MAP sensor through vacuum and beyond the intended 5 psi range.
4. Confirm injector identity/latency/scaling, base pressure, and fuel-pressure differential.
5. First-start with no path into boost and immediate high-rate MAP/RPM/IAT/airflow/load/lambda/
   fuel-pressure logging. Shut down if running airflow pins near the 500 g/s fault value.
6. Calibrate idle and vacuum VE cells on a load-controlled dyno before atmospheric or boosted
   operation. Use the time-aligned external wideband; there is no retained MAF reference or
   in-ROM fallback.
7. Complete transient, restart, heat-soak, altitude, AVLS-transition, fuel-pressure, injector-duty,
   knock, and 5 psi wastegate validation before considering integration.
8. Merge only after standalone testing, then extend the combined definition, checksum workflow,
   and exact-union audit. This was the status at the standalone audit date; the later integrated
   master audit below now supersedes that merge-status statement.

# Integrated Master Patch Audit

Audit date: 2026-08-21. Target: D2WD610H / ECU ID `3C5A387116`, Renesas SH7055,
canonical stock `2005 BLE MT.bin`.

## Verdict

`master_patch/build_master_patch.py` now creates the requested single integrated development
image directly from canonical stock. It includes always-on MAFless speed density, exact Omni
Power MAP-SUP-3BR scaling, EVAP-output boost control and safeties, a former-MAF input calibrated
for the supplied seller-labelled 50-4110/30-4110-style P0/P1 output, logical removal of both
stock front A/F and both rear O2 paths, STI-pink factory
donor injector data, a base VE surface, and the conservative 5 psi / 98 RON / early-AVLS /
6800-RPM calibration.

The binary, free-space ownership, injected opcodes, hooks, sensor policy, fuel/timing/injector/
AVLS calibration, definition, logger fragment, checksum, and stock/SRF provenance pass static
verification. This is not a vehicle-tested result. It must not be treated as safe to flash or
enter boost solely because the automated audit passes.

## Artifact and provenance

- Input SHA-256: `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
- Output: `master_patch/D2WD610H_master_patch.bin`, 512 KiB, CALID `D2WD610H`.
- Output SHA-256: `00c34efc18ca65e0fd2619ed722b0bac236013b296adea7baf84ac9bf887a76b`.
- Subaru additive checksum: `0xB86A1DE4`, verified.
- The root stock BIN, `base_roms` copy, and original SRF `MEMD` payload are byte-identical.
- The builder refuses generated inputs and protected-source output aliases; every component is
  reconstructed on an in-memory copy of root stock.
- Exactly 3,635 bytes differ from stock, all inside declared hooks, diagnostic switches,
  calibration regions, and verified free flash. The separate rotational-idle reservation
  `0x7DB40..0x7DCEB` remains byte-identical to stock.

## Live Ghidra revalidation

- `map_sensor_voltage_to_pressure_process` at `0x7A14` confirms offset-then-multiplier floats at
  `0x72810` and native absolute-mmHg output at `0xFFFFABC4`.
- `map_sensor_raw_adc_range_classify` at `0x7A56` confirms the separate raw limits at
  `0x7B284/0x7B286`.
- `injector_battery_voltage_latency_lookup` at `0x98CC` confirms descriptor `0x608D8`, voltage
  axis `0x7B304`, and latency data `0x7B318`.
- `injector_flow_scaling_factor_update` at `0x1E0C8` confirms D2WD flow scalar `0x76014`.
- `ign_avcs_tracking_blend_factor_update` at `0x28354` builds and clamps factor `k` at
  `0xFFFFC17C` as summed measured left/right intake AVCS divided by summed commanded AVCS.
  This corrects the earlier IAM/advance-multiplier interpretation. `ign_base_timing_map_blend`
  at `0x28418` calculates each reachable pair as AVCS-tracking-ratio-1.0 endpoint `* k` plus
  ratio-0.0 endpoint `* (1-k)`.
- `ign_base_timing_select` at `0x284B8` confirms `0x78AA0/0x78E34` as the normal-cam pair and
  `0x78CD0/0x79064` as the AVLS-high-cam pair. The two other legacy surfaces require the callback
  at `0x27088`, renamed `constant_zero_return`, to return one; its exact body always returns zero.
- `knock_correction_advance_max_select` at `0x3EB68` confirms KCA A normal cam and KCA B AVLS
  high cam.
- `intake_avcs_target_by_avls_mode_update` at `0x353B0` confirms descriptor `0x60C34` / data
  `0x7C5B0` (legacy AVCS A) is selected in committed AVLS mode 1, low lift; descriptor `0x60C50`
  / data `0x7C764` (legacy AVCS B) is selected in mode 3, high lift. These are mode targets, not
  left/right-bank maps, and the ECU selects rather than blends them.
- `avls_threshold_curve_selector_state_update` at `0x3FFDA` and
  `avls_curve_selector_oil_temp_band_latches_update` at `0x400EE` show how the internal curve
  selector is formed. `engine_oil_temperature_sensor_process` at `0xF474` converts ADC AB12
  through descriptor `0x60950` (axis `0x7B748`, data `0x7B7C4`) to `0xFFFFB124` in degrees C;
  the table spans -40..150 C and P0197/P0198 identify the channel. Function `0x47000`, renamed
  `engine_oil_temperature_fallback_select`, publishes valid B124 or the stock 70 C fallback to
  `0xFFFFCF94`. Hysteretic 13/15 and 113/115 C bands select cold/fallback state 1, normal state 2,
  or hot state 3 subject to runtime/delay gates.
- `vehicle_speed_conditioned_source_update` at `0x188F4` starts with proven vehicle-speed signal
  `0xFFFFB538`, keeps its km/h units, caps it at 100.0, and writes `0xFFFFB4C0`. Functions
  `vehicle_speed_conditioned_filter_update` at `0x18A68` and
  `vehicle_speed_conditioned_snapshot_copy` at `0x18AEA` publish B4C8 then AVLS compare signal
  `0xFFFFB46C`. Therefore the `0x7D67C/0x7D6B4` AVLS tables are RPM-versus-vehicle-speed
  boundaries, and `0x7D480/0x7D484` are 10 km/h hysteresis values; none is engine load.
- Genuine table load is separate: the retained stock airflow task writes B420 in g/s, calculates
  raw B428 as `airflow_g_s * 60 / RPM`, and conditions it into B438 in g/rev. AVCS, ignition,
  fuel, and knock consumers use B438. The speed-density helper supplies B420 in g/s and retains
  this stock normalization, so calculated-load scaling remains correct.
- `speed_density/verify_speed_density.py` now pins the exact stock load instruction sequence at
  `0x1753C`, the 60.0 g/s-to-g/rev factor at `0x1761C`, the 4.0 g/rev limit at `0x17620`, and
  representative SD-to-load model samples. The standalone and master rebuilds retain all of them.
- Every D2WD610H-derived definition now inherits the corrected km/h AVLS curve/hysteresis names,
  the 13/15 and 113/115 degree-C selector table, and the 31-point engine-oil-temperature scaling
  from `defs/D2WD610H_AVLS.xml`; `defs/sync_avls_metadata.py --check` and XML parsing pass.
- `front_af_sensor_pair_signal_process` at `0xB690`,
  `front_af_sensor_lambda_condition_filter` at `0x18DAC`, and
  `closed_loop_fuel_control_bank_update` at `0x1EE74` confirm the lambda/readiness values consumed
  by stock closed-loop control.
- Static rear-path xrefs confirm B098/B09C belonged to rear monitoring/logging rather than a
  direct fuel consumer, allowing them to become explicit external-wideband logger mirrors.
- Every function opened during this pass was renamed using the existing underscore convention.
  The full list/evidence is in `master_patch/GHIDRA_AUDIT.md` and
  `docs/D2WD610H_RE_notes.md`; `ApplyMasterNames.java` makes it reproducible.

## MAP and speed density

- The exact supplied Omni endpoints are 0.60 V at 30 kPa and 4.75 V at 300 kPa. The resulting
  native transfer is approximately `487.991938 mmHg/V - 67.776658 mmHg`.
- The low raw-input threshold is 0.30 V and the stock high threshold remains approximately
  4.921 V. Output below the published 30-kPa endpoint is extrapolated and must be physically
  characterized before road use.
- The always-on 13x17 VE model uses MAP/RPM, 2.999 L displacement, a ten-point IAT-density curve,
  and the retained stock downstream load/fueling pipeline. It has no MAF fallback.
- Exact zero RPM returns zero airflow. Any other invalid input/calibration/arithmetic condition
  selects fixed 500 g/s as a shutdown-indicating rich/high-load fail-safe.
- Raw MAF conversion/filter paths, MAF diagnostic tasks, and P0102/P0103 switches are bypassed,
  while AB06 remains live as a shared ADC channel for the new wideband input.

## External-wideband input and four-stock-O2 removal

- The supplied controller's P0/P1 table is `gasoline AFR = 2*V + 10` and
  `lambda = (2*V + 10)/14.64`; P2/P3 are unsupported. Firmware accepts 0.50..4.50 V
  inclusive as an 11..19 gasoline-AFR plausibility window.
- Valid lambda is copied to both stock bank feedback values and both logger mirrors; readiness is
  50.0. Invalid input publishes a 0.0 logger sentinel/readiness, inhibits both closed-loop bank
  paths, and forces electronic boost duty to zero.
- The original front conversion entry, both bank-inhibit helpers, front pump-diagnostic pointer,
  rear conversion entry, five rear monitor-task pointers, and 18 mapped front/rear O2 DTC
  switches are checked byte-for-byte by the verifier.
- The four-wire controller is single-ended: white alone connects to B3-3/B136-23. Red uses a
  separate switched 10-18 V supply through a 10 A fuse; black carries gauge/heater current to a
  clean power/engine ground; blue is unused serial output. B3-2/B136-31 must not be connected to
  black. B3-4/B136-13 plus B3-5/B136-35 remain the post-intercooler IAT circuit.
- The supplied instruction sheet is not identical to genuine AEM 30-4110 documentation and no
  separate analog ground or dedicated fault output is present. In-range voltage/readiness cannot
  prove sensor health; cold, warmed-free-air, disconnected-sensor, and installed ground-offset
  measurements remain mandatory commissioning evidence.
- Both front and both rear factory sensor connectors must be physically disconnected and sealed.
  Their heater drivers are not electrically forced off by the firmware.
- One post-turbo sensor feeds both banks and cannot identify bank-specific mixture imbalance;
  exhaust transport delay and ground offset remain serious commissioning risks.

## Base calibration and safeties

- STI-pink scalar/deadtime data is translated from a SHA-pinned factory A4TE002B ROM. It displays
  as an estimated 552.47 cc/min, not a bench-flow guarantee for injectors marketed as 565 cc/min.
- Both Primary Open Loop maps and all timing/KCA load axes extend to 3.0 g/rev. High-load fuel is
  capped rich, all six timing surfaces are only held or retarded, high-load positive KCA is
  removed, and high-IAT retard is increased.
- AVLS minimum/release/engage are 2500/3000/3200 RPM. Below the hard crossover, the tuned
  oil-temperature-selected vehicle-speed curves are 100/100/25/20/15/10/5 km/h for normal oil
  temperature and 100/100/60/35/20/10/0 km/h for hot oil; hysteresis is 10 km/h. Rev cut/resume
  is 6800/6770 RPM.
- The target reaches 5 psi, but base WGDC, Kp, and final max duty are all zero. The generated
  baseline therefore relies only on the 5 psi mechanical spring.
- Throttle at/below native 30.0, rejected external-wideband voltage, MAP/RPM/IAT outside the SD
  windows, RPM
  below the first 1500-RPM boost-axis point, a 500 g/s SD fault sentinel, or MAP over 5.5 psi
  commands zero EBCS duty. MAP over 6.5 psi uses the verified stock fuel-cut aggregation path.
  Boost thresholds are relative to a fixed 760 mmHg, not barometrically compensated.
- None of these software checks can reduce boost below the physical spring or stop boost creep.

## Definition, logger, and verification

- `master_patch/D2WD610H_master_patch.xml` is self-contained and contains only metric base
  templates plus D2WD610H target tables relevant to the master architecture. Stock MAF/O2,
  diagnostic/readiness, fuel-temperature, and dormant timing B/E tuning entries are removed.
- Active timing maps are named by both Ghidra-proven cam role and their exact intake-AVCS
  tracking-ratio endpoint (1.0 or 0.0); the two KCA maps are named by normal/high-cam role. The
  legacy AVCS A/B targets are named by AVLS low/high-lift selection. The XML also exposes AVLS,
  SD, Omni MAP, injectors/fuel, active timing, boost, external-wideband transfer/range, and retained engine
  controls.
- All D2WD610H images retain the factory CALID. RomRaider must therefore be configured with the
  master XML alone for this image; selecting a standalone/legacy definition can make the same
  binary appear with anonymous A--F names and an incomplete table set.
- `D2WD610H_master_logger_ecuparams.xml` exposes E500 lambda/estimated AFR, E501 raw ADC/volts,
  and E502 readiness only for ECU ID `3C5A387116`. Its IDs, RAM addresses, lengths, storage
  types, formulas, and fault descriptions are verifier-checked.
- Run `python3 master_patch/verify_master_patch.py` from the repository root. A pass means the
  checked development baseline matches this audit; it does not approve a later RomRaider edit.

## Remaining physical work

Follow `master_patch/WIRING.md` and `master_patch/COMMISSIONING.md`. In particular, continuity-
check the actual market harness, bench-sweep both analog inputs, validate the Omni through vacuum
and positive pressure, compare ECU lambda with the controller gauge and an independent reference, verify
injectors/fuel pressure, scope the purge output and EBCS polarity/frequency, calibrate VE in
vacuum before boost, simulate all gates/cuts without deliberately overboosting, and complete
spring-only load-dyno validation. Stop on invalid airflow, sensor disagreement, lean mixture,
knock, fuel-pressure loss, or boost creep.

# Committed-state AVLS dual-VE and master integration audit

Audit date: 2026-08-21. This section supersedes the earlier single-13x17-VE and
vehicle-speed-selected AVLS descriptions for the current master image.

## Result

- The speed-density airflow wrapper now selects two VE surfaces from the
  Ghidra-verified committed AVLS byte `0xFFFFCD86`. Mode 3 selects high lift;
  all other values select low lift. Requested byte `0xFFFFCD87` is not used for
  fueling selection.
- The low-lift surface is 13x9 and exposes only 0..3200 RPM. The high-lift
  surface is 13x11 and exposes only 3000..7500 RPM. Their 3000..3200 overlap is
  the actual hysteresis region, selected by committed state.
- Both seed surfaces are resampled from the same conservative original VE model
  and agree in their overlap. This avoids deliberately introducing a fueling
  discontinuity, but it is not measured VE data.
- Both RPM-indexed AVLS speed-request maps and both fixed/fallback thresholds are
  110 km/h. Because the conditioned source is capped at 100 km/h, the old
  vehicle-speed/oil-band high-lift request is unreachable. High lift engages at
  3200 RPM and releases at 3000 RPM; actuation minimum is 3000 RPM.
- The stock request/commit sequencing, status checks, and OSV actuation gates
  remain. Continuous AVCS effect on VE also remains and must be tuned within
  each lift surface.

## Ghidra evidence and naming

- `FUN_000024b0` was inspected and renamed `float_minimum_select`.
- `FUN_0003fdbc` was inspected and renamed `avls_control_sequence_update`.
- Existing named functions `avls_cam_mode_state_machine` (`0x40168`),
  `avls_mode_commit_copy` (`0x405B2`), `avls_osv_actuation_gate` (`0x405CC`),
  `intake_avcs_target_by_avls_mode_update` (`0x353B0`), and the airflow hook at
  `0x172A4` were rechecked. The sequence calls the state machine, commits the
  requested mode, then runs the actuation gate.
- The merged `speed_density/ghidra_scripts/ApplyMaflessNames.java` and master
  naming script reproduce these names/comments.

## Artifacts and verification

- Standalone single SD/VE artifact: `speed_density/D2WD610H_speed_density.bin`, SHA-256
  `9cfcf45d075818c1a8320e540eb855979289ce25a6e03b8879a0c4767db49d16`,
  checksum `0x051694B7`.
- Master: `master_patch/D2WD610H_master_patch.bin`, SHA-256
  `e841cb315ae15643d5140cf4c484ab753d054c719579e09d560c0eb328f7458d`,
  checksum `0xBB4C8915`.
- Both generated XML files use the project's RomRaider SH float-endianness
  convention and omit the obsolete full-range VE entry and inoperative
  variable AVLS controls. The legacy single-VE bytes remain inert in flash but
  cannot be referenced by the new wrapper.
- The standalone and master verifiers independently rebuild from immutable
  stock, audit hooks/opcodes/descriptors/axes/calibration/XML, validate checksum
  and pinned hash, and confirm root stock/base/SRF provenance.
- Master free-space ownership is collision-checked byte-for-byte across boost,
  the speed-density core and its dual-VE segment, and wideband/O2 removal. The
  wideband reservation ends exactly at `0x7E63F`; the SD dual-VE segment begins
  at the adjacent `0x7E640`. Calibration
  ownership is independently checked, with only the six explicit boost tune-data
  regions permitted to overlap their component seed data. No calibration may
  enter injected code, descriptors, speed-density, wideband, or dual-VE data.
- Master logger parameter E503 exposes committed AVLS state so tuning samples
  can be assigned to the correct VE table.

Static verification passes; bench ECU, harness, AVLS actuation, fueling,
transition, and dyno validation remain required.

## Component consolidation

The dual-VE selector, tables, predictable AVLS calibration, definition, checksum
handling, Ghidra naming, and verifier are now part of `speed_density` itself.
`master_patch` calls only that one SD/VE component. The former `avls_ve` package
and duplicate ROM/XML artifacts were removed. This reorganization is byte-neutral
for the master ROM and retains its pinned hash and checksum.
