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
**Status: implemented in `patch/patch_boost.py` (steps 1 & 3); binary-verified, not yet
hardware-tested. Steps 4–7 pending.**

The implemented hijack is simpler than "overwrite 0xFFFFCD54": `evap_purge_duty_compute`
@0x3FC0A tail-calls its output stage through a pooled pointer @**0x3FD8C** (`=0x0000E8C4`),
passing the duty ratio in fr4. The patch repoints that one literal to a stub @0x7D7CC that
looks up the boost duty (RPM → duty via interpolator 0x209C) and tail-calls the real output
stage — driving the solenoid from the map without touching 0xFFFFCD54.

1. ✅ Boost duty map (RPM → duty %%) + descriptor in free space (0x7D7C4 / 0x7D7A4 / 0x7D790).
2. ⬜ Max wastegate duty clamp (map is u8 0–100, inherently clamped; explicit clamp optional).
3. ✅ Hijack via literal repoint @0x3FD8C → stub @0x7D7CC.
4. ⬜ Neutralize purge gating (ECT 0xFFFFB3B8 / state 0xFFFFCD77 / status 0xFFFFCD81) — not
   required for output (hijack overrides the final duty regardless), but tidy for Phase 2.
5. ⬜ Verify/retune PWM frequency (period RAM 0xFFFFAB84) for a ~15–30 Hz boost solenoid.
6. ⬜ **Overboost fuel cut** (fail-safe) — compare 0xFFFFABC4 vs a limit, force fuel/ignition cut.
7. ⬜ Disable `evap_purge_flow_diagnostic` (0x46748) + DTCs P0458 (0x5BD85) / P0459 (0x5BD86)
   — the diagnostic watches the still-running stock duty (0xFFFFCD54), so it may not trip;
   toggle via RomRaider DTC switches if it does.

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
