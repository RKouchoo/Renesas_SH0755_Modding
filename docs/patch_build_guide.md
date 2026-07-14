# Boost-Control Patch — Build and Commissioning Guide

The reverse engineering behind this patch is recorded in
[boost_repurpose_notes.md](boost_repurpose_notes.md),
[boost_donor_A2WC510N.md](boost_donor_A2WC510N.md),
[solenoid_subsystem.md](solenoid_subsystem.md), and [ram_map.md](ram_map.md).

## Objective

The single boost-control patch repurposes the EVAP purge PWM output (ATU-II register
`0xFFFFF590`) as a wastegate-solenoid driver. It implements stateless proportional +
feed-forward boost control with throttle gating and independent soft/hard MAP limits.

## Preserve the stock ROM

The repository-root `2005 BLE MT.bin` is the canonical stock image used by Ghidra. Never write
patches into it and never replace it with a generated ROM.

`patch/patch_boost.py` enforces this workflow:

1. It reads only the fixed root stock path.
2. It verifies SHA-256 `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
3. It makes a private in-memory copy.
4. It applies all tables, code, and hooks to that copy.
5. It writes `patch/D2WD610H_boost.bin` by default.
6. It refuses any output path that aliases the stock file.
7. It rereads the stock file after the build and fails if its bytes changed.

Build from the repository root:

```sh
python3 patch/patch_boost.py
```

To create a disposable comparison build, supply only a different output path:

```sh
python3 patch/patch_boost.py /tmp/D2WD610H_boost_test.bin
```

There is no configurable input and no patch-stacking workflow.

## Controller behavior

The tail-call pointer at `0x3FD8C` in `evap_purge_duty_compute` normally points to
`evap_purge_pwm_output_write` at `0xE8C4`. The patch points it to the injected controller at
`0x7D80C`; that controller computes a duty ratio and tail-calls the original output stage.

```text
base   = BaseDuty[rpm]
target = TargetBoost[rpm]
error  = target - MAP(0xFFFFABC4)
ratio  = clamp(base + Kp * error, 0, MaxRatio)

if throttle(0xFFFFB314) <= MinThrottle:
    ratio = 0
if MAP > SoftOverboost:
    ratio = 0

write ratio through output stage 0xE8C4
```

The controller reads RPM, processed throttle, MAP, and flash calibrations. It has no persistent
RAM state. A RAM audit found no word that can be proven free from direct and computed access, so
the integral term is intentionally omitted rather than risk corrupting another subsystem.

The generated default `Kp` is `0.0005 ratio/mmHg`, copied from the near-zero slope of the donor's
Turbo Dynamics Proportional table. For first hardware commissioning, set it to zero in RomRaider;
that disables proportional correction while leaving throttle gating, clamps, and hard fuel cut
installed. Restore or tune gain only after MAP and feed-forward duty are proven.

The target, base duty, maximum duty, throttle gate, and two boost limits are documented in
[boost_donor_A2WC510N.md](boost_donor_A2WC510N.md). The default target peaks at 5 psi relative to
the 760 mmHg sea-level reference; the patch does not implement atmospheric target compensation.

## Hard overboost protection

The patch also changes the rev-limiter task pointer at `0x11D3C` from the stock limiter at
`0x24B24` to a wrapper at `0x7D8AC`. The wrapper runs the stock limiter first, then compares MAP
with the hard limit at `0x7D8A8`. Above the limit it sets `0xFFFFBF6C` bit `0x80`; the factory
fuel-cut aggregator at `0x23FC0` propagates that request to injector cut.

This is separate from the soft limit at `0x7D808`, which commands zero solenoid duty. Neither
limit has hysteresis, so threshold and recovery behavior must be proven on a bench.

## Hardware and calibration prerequisites

- Fit the MAP sensor compatible with the A2WC510N donor. The patcher automatically replaces the
  stock `{-150.0, 250.0}` floats at `0x72810` with donor values
  `{-414.0, 514.199951}`.
- Validate `0xFFFFABC4` against a reference gauge across the full operating range. It stores
  native mmHg absolute; the RomRaider patch tables display psi relative to 760 mmHg.
- Wire the selected EBCS to the former purge-solenoid output.
- Verify that zero commanded duty produces minimum boost with the installed plumbing.
- Measure the actual PWM frequency and confirm it suits the solenoid; the stock period
  calibration alone does not prove the output frequency.
- Handle `evap_purge_flow_diagnostic` and P0458/P0459 if they trigger.

## Injected layout

The populated region remains inside the verified `0xFF` free run at `0x7D790..0x7FAF7`.

| Block | Address |
|---|---:|
| Base-duty descriptor | `0x7D790` |
| Shared RPM axis, float[8] | `0x7D7A4` |
| Base-duty data, uint8[8] | `0x7D7C4` |
| Target descriptor | `0x7D7CC` |
| Target data, float[8] | `0x7D7E0` |
| Kp | `0x7D800` |
| Maximum duty ratio | `0x7D804` |
| Soft overboost limit | `0x7D808` |
| Controller | `0x7D80C` |
| Minimum throttle | `0x7D8A4` |
| Hard overboost limit | `0x7D8A8` |
| Fuel-cut wrapper | `0x7D8AC` |

The donor MAP scaling is an in-place calibration change at `0x72810`, outside the injected
free-space block.

These addresses must remain synchronized with
[D2WD610H_AVLS_boost_patch.xml](../defs/D2WD610H_AVLS_boost_patch.xml).

## Toolchain

- `patch/patch_boost.py`: guarded patch builder.
- `patch/sh2_asm.py`: minimal two-pass SH-2E assembler.
- `patch/sh2_disasm.py`: injected-code disassembler.
- `patch/verify_regions.py`: flash/RAM region audit.
- `patch/verify_boost_donor.py`: donor-table and generated-default verifier.
- RomRaider/EcuFlash: calibration editing and a verified `subarudbw` checksum save before
  flashing.

## Commissioning checklist

- [ ] Root stock-ROM hash still matches the known project stock image.
- [ ] Generated ROM is exactly 512 KiB and differs only at the documented MAP scaling, injected
      tables/code, and two hooks.
- [ ] A2WC510N-compatible MAP sensor is fitted and the patched `0x72810` conversion is validated
      against a reference.
- [ ] Output pin, polarity, solenoid plumbing, and PWM frequency are bench verified.
- [ ] With `Kp = 0` and conservative base duty, throttle gating is logged and confirmed.
- [ ] Soft duty shutdown is proven with simulated MAP.
- [ ] Hard injector cut and recovery are proven with simulated MAP.
- [ ] Purge diagnostics are resolved.
- [ ] Final ROM checksum is valid.
- [ ] Initial running uses wastegate spring pressure as the mechanical fallback.

The current implementation is binary-verified but not vehicle-validated. Do not apply boost
until every safety-critical item above has been demonstrated on the actual hardware.
