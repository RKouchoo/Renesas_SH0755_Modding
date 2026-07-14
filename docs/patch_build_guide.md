# Boost-Control Patch — Build Guide

How the EVAP-purge→boost-control patch will be built and flashed. This is the forward-looking
plan; the RE that backs it is in [boost_repurpose_notes.md](boost_repurpose_notes.md),
[solenoid_subsystem.md](solenoid_subsystem.md), [ram_map.md](ram_map.md).

## Objective
Repurpose the EVAP purge PWM output (ATU-II reg **0xFFFFF590**) as a wastegate/boost-control
solenoid driver, implementing **WRX-style boost control** (feed-forward duty + closed-loop
correction) as custom code in the ROM's 9 KB free space.

## Toolchain
- **Patcher**: a standalone `patch_boost.py` (planned) — reads the stock `.bin`, applies byte
  edits, writes a patched `.bin`. No Ghidra dependency at flash time.
- **Assembly**: SH-2E machine code hand-assembled in the patcher (verified against the same
  decode used throughout RE).
- **Def**: [defs/D2WD610H_boost_patch.xml](../defs/D2WD610H_boost_patch.xml) — RomRaider tables for
  the new maps (category "Boost Control (patch)"); iterate here.
- **Flashing**: EcuFlash / RomRaider (recomputes the `subarudbw` checksum on save — so the
  patcher can skip checksum; open+save in the tool before flashing).

## Hardware prerequisites
- Boost-control (wastegate) solenoid wired to the former purge-solenoid harness pin.
- **EJ255 (turbo EJ25) MAP sensor** fitted — same 2-bar+ Denso sensor the 32-bit WRX ECU uses;
  required for closed loop. Rescale MAP table **0x72810** to that sensor's curve so **0xFFFFABC4**
  reads positive boost.

## Free-space layout (0x7D790, 9 KB) — to be assigned
| Block | Contents |
|---|---|
| maps | boost duty map, target boost, max duty, turbo-dynamics gains, overboost limit |
| descriptors | 0x1C-byte table descriptors (reuse interpolator 0x209C / 0x2150) |
| code | boost-control routine + hijack stub |
(Exact offsets filled in once the patcher lays them out; update the `0x7D7xx` placeholders in
the def and the notes when assigned.)

## Phase 1 — open-loop feed-forward (works before the sensor)
1. Boost duty map (RPM × load → duty %%) in free space + descriptor.
2. Max wastegate duty clamp.
3. Hijack `evap_purge_duty_compute` @ **0x3FC0A**: overwrite 0xFFFFCD54 with the map result
   (clamped 0..100) just before the existing 0xE8C4 output call.
4. Neutralize purge gating: relax ECT enable (0xFFFFB3B8) / force state (0xFFFFCD77) / status
   (0xFFFFCD81 bit 0x80) so output is live across the boost range.
5. Verify/retune PWM frequency (period RAM 0xFFFFAB84) for a ~15–30 Hz boost solenoid.
6. **Overboost fuel cut** (fail-safe) — compare 0xFFFFABC4 vs a limit, force fuel/ignition cut.
7. Disable `evap_purge_flow_diagnostic` (0x46748) + mask DTCs P0458 (0x5BD85) / P0459 (0x5BD86).

## Phase 2 — closed-loop (after EJ255 sensor + 0x72810 rescale)
8. Target Boost map (RPM × load → kPa).
9. Boost error = target − 0xFFFFABC4.
10. Turbo Dynamics P/I correction → duty correction; final = clamp(base + corr, 0, max).
Reuse the WRX scalings already present in the def (32BITBASE templates).

## Verification checklist (before flashing)
- [ ] Datalog confirms purge duty tracks 0xFFFFCD54 (proves the output is the purge chain).
- [ ] Bench/scope the 0xFFFFF590-driven pin at a few commanded duties.
- [ ] Overboost cut proven on the bench before any boost.
- [ ] Checksum valid (EcuFlash/RomRaider save).

## Safety
NA EZ30R, no factory turbo. Only meaningful as part of a forced-induction build. Conservative
duty map + independent overboost fuel cut are mandatory.
