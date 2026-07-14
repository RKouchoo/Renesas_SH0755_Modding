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

# Hybrid Factory-A/F + AEM Logging Patch Audit

Audit date: 2026-07-14. Target: D2WD610H / ECU ID `3C5A387116`, Renesas SH7055,
stock image `2005 BLE MT.bin`.

## Verdict

The standalone hybrid-O2 patch is structurally valid and the post-turbo AEM can be exposed as a
normal RomRaider ECU parameter. The retained RH/Bank-1 factory A/F sensor remains the only
closed-loop feedback source and its processed results are mirrored into both bank paths. The AEM
30-0310 value is converted to lambda at RAM `0xFFFFB098` and is logging-only; it does not trim
fuel, command enrichment, or protect against a lean condition.

This is not yet a vehicle-ready installation. Firmware analysis and the matching-generation H6
diagnostic manual converge on the RH rear channel, but the manual is not a VIN-specific ADM-MT
harness guarantee. The actual car must pass the connector continuity and key-on bias checks, and
a protected external analog conditioner must be designed and bench calibrated before the AEM is
connected to the ECM.

## Binary and definition checks completed

- The patcher always reads the fixed root stock image, checks its 512 KiB length and SHA-256, and
  refuses to overwrite or hard-link the stock file. The root image remains unchanged at
  `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
- The generated `patch/D2WD610H_wideband.bin` is 512 KiB with SHA-256
  `afc8569c49ddfb8f7897b482d387a3fb874c5ae203e56f822b2db22f58ef28f3`.
- All 319 changed bytes are confined to the four guarded hooks/task entries, nine explicit O2 DTC
  switches, and the allocated hybrid free-flash blobs at `0x7D900..0x7DB3F`. The standalone
  image leaves the boost allocation `0x7D790..0x7D8DF` byte-identical to stock.
- The front entry hook at `0xB690` runs the complete stock
  `front_af_sensor_pair_signal_process` through a prologue trampoline, then copies
  `AE60→AE64` (lambda), `AE68→AE6C` (pump-current-like result), and `AE70→AE74`
  (readiness/diagnostic metric).
- The stock front diagnostic task still executes. Its task-pointer wrapper refreshes
  `AE70→AE74`, and the Bank-2 inhibit entry at `0x6500C` tail-jumps to the unchanged Bank-1
  helper at `0x64FD0`. Retained Bank-1 front diagnostics remain enabled.
- The rear hook at `0xE0D0` runs the complete stock rear pair process, then overwrites only RH
  result `0xFFFFB098` with the AEM logging value. The LH rear path `AB0C→B09C` and its listed
  diagnostics remain stock.
- A direct Ghidra xref audit of `0xFFFFB098` found the stock bank-select getter, whose only call
  sites are `rear_o2_sensor_pair_diagnostic_update` and the small SSM/log conversion stubs at
  `0x31962/0x31978`. No direct B098 fuel-control consumer was found. This supports the
  logging-only classification, while leaving diagnostic/catalyst behavior as a physical-test item.
- The nine disabled switches are RH rear P0037/P0038/P0137/P0138 and absent LH/Bank-2 front
  P0051/P0052/P0151/P0152/P0154. RH/Bank-1 front and LH rear switches checked by the verifier
  remain enabled. Catalyst-monitor consequences outside those explicit switches are unproven.
- The verifier reproduced every blob and hook from source, rejected all unexpected changed
  offsets, decoded 90 injected SH-2E instructions with no unknown opcodes, checked the replayed
  stock prologues, and confirmed the stored analog formula and voltage-window endpoints.
- Shared assembler changes were regression-tested by rebuilding the boost patch; its canonical
  SHA-256 remained `6caca8c2ce8cc6522ee5e6e83808992ec7aa2920177f08c3856255405161cd0a`.
- `defs/D2WD610H.xml` remains the ADM/MT D2WD610H base. Each custom ROM definition parses and
  contains only the pruned `32BITBASE` template plus one D2WD610H target (`3C5A387116`). The
  AVLS-only definition has no boost/hybrid entries; the boost and hybrid variants contain only
  their respective patch-specific additions.
- `patch/install_aem_logger.py` was tested against the official RomRaider metric logger v370
  package. The generated XML parsed with exactly one E500 and one E501, both restricted to ECU ID
  `3C5A387116`; the source logger remained separate.

## Selected wiring variant and firmware agreement

The selected service material is the `21Z_EU` H6DO matching-generation RHD 3.0 L diagnostic and
wiring set. It identifies the same sensor roles and connector family used by the project ROM:

| Role | Harness/ECM assignment |
|---|---|
| Retained front A/F RH | `E47` black 4-pole; `B134-33` signal+, `B134-26` signal−, `B134-25` shield |
| Removed front A/F LH | `E24` black 4-pole; `B134-34` signal+, `B134-27` signal−, shared `B134-25` shield |
| Repurposed rear O2 RH | `E61` dark-gray 4-pole; `E61-3 ↔ B137-24` signal, `E61-4 ↔ B136-35` sensor ground |
| Retained rear O2 LH | `E25`; `B137-25` signal, shared `B136-35` sensor ground |

The H6 diagnostic continuity procedure explicitly pairs `B137-24` with `E61-3` and `B136-35`
with `E61-4`, and specifies 0.2–0.5 V at disconnected `E61-3` with the ECM powered. Independent
firmware tracing maps RH rear raw ADC `0xFFFFAB20` through
`rear_o2_sensor_pair_voltage_process` to RH result `0xFFFFB098`. This hardware/manual/firmware
agreement is why that channel was selected instead of relying on a generic Subaru pin list.

`B135-15` is explicitly excluded: the same H6 I/O table identifies it as ignition control #4.
It is not an analog input and must never receive the AEM signal.

## AEM interface and logging

The selected sensor/controller is AEM X-Series Inline 30-0310 with Bosch LSU4.9. Its analog pair
is white (positive) and brown (negative/reference), with the documented conversion:

```text
lambda = 0.1621 × AEM_volts + 0.4990
<0.5 V = not ready; 0.5–4.5 V = measurement range; >4.5 V = controller/sensor error
```

The ECU patch uses a nominal external-conditioner model:

```text
AEM white/brown -> protected differential 0.2 V/V conditioner -> E61-3/E61-4
AEM_volts = 0.0001274108854 × raw_AB20 - 0.175
lambda -> float RAM 0xFFFFB098
```

Direct connection is not approved: the AEM output is 0.5–4.5 V while the stock rear input is a
biased, conditioned 0–0.9 V circuit. The external conditioner is not part of the ROM patch. It
must be high impedance and differential at the AEM side, preserve the brown reference, limit
fault current into the ECM, tolerate the measured input bias, and include suitable automotive
input/transient protection. A passive 40 kΩ/10 kΩ divider is not an accepted final interface.

RomRaider logger channels are:

- E500: patched post-turbo AEM lambda, float at SSM address `0xFFB098`.
- E501: raw RH rear ADC count for conditioner calibration, unsigned 16-bit at `0xFFAB20`.
- E91/E109: unchanged factory front-sensor log paths `0xFFFFB4E8/0xFFFFB4EC`; both show the
  mirrored retained OEM A/F sensor after patching.

The ROM publishes `0.0` when reconstructed AEM voltage is outside the configured 0.5–4.5 V
window. That is not a complete continuity diagnostic. If `E61-3` is open, the stock 0.2–0.5 V
bias can reconstruct inside the valid window and appear plausible. A hardware fail-low output or
independently logged interface-fault signal is required if ECU-wire disconnect detection matters.

## Remaining blockers and commissioning order

1. Confirm the car is the expected connector variant: with ECM and E61 disconnected, prove
   `E61-3 ↔ B137-24` and `E61-4 ↔ B136-35`, with no continuity to adjacent cavities. Stop on any
   mismatch in connector colour, cavity numbering, or continuity.
2. Reconnect the ECM with the stock RH rear sensor disconnected and confirm the 0.2–0.5 V key-on
   bias at `E61-3` using a high-impedance meter. Stop if it differs.
3. Finalize and bench-test the protected differential conditioner. Confirm its power-off,
   disconnected-input, short-to-ground, and short-to-supply behavior before attaching the ECM.
4. With the engine off and a current-limited precision source, feed 0.5, 2.5, and 4.5 V into the
   conditioner, log E501, fit the raw scale/offset, and verify E500 at lambda 0.58005, 0.90425,
   and 1.22845. Confirm no clipping or non-monotonic region.
5. Verify actual AEM warm-up/error outputs produce E500 `0.0`. Test ECU-side disconnection
   separately; do not treat a plausible biased reading as proof of continuity.
6. Install the sensor at least 45 cm/18 in after the turbo, before the catalyst, in a leak-free
   section and at the AEM-specified orientation. Compare it with the retained factory sensor at
   steady stoichiometric operation while allowing for post-turbo transport delay.
7. Review unhandled rear catalyst-monitor behavior, correct the `subarudbw` checksum, and test
   the hybrid image independently before merging it with boost control.
8. After merging, repeat the complete binary audit and hardware tests as one system. The AEM is
   not currently a lean-protection input, so boost testing must not rely on it for automatic
   shutdown.
