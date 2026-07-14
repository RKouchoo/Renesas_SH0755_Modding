# patch/ — D2WD610H patch builders

This directory contains the canonical boost-control patch and a separate single-front-A/F
development patch. The boost patch repurposes the EVAP purge PWM output as an electronic
boost-control solenoid driver. The front-A/F patch retains one factory pre-turbo A/F sensor for
closed-loop control and mirrors its processed results into both bank paths. They are built
independently from stock and are not yet a merged flash image.

Background and commissioning details:
[boost_repurpose_notes.md](../docs/boost_repurpose_notes.md),
[boost_donor_A2WC510N.md](../docs/boost_donor_A2WC510N.md),
[patch_build_guide.md](../docs/patch_build_guide.md),
[single_front_af_patch.md](../docs/single_front_af_patch.md), and [audit.md](../audit.md).

## Stock-ROM rule

`../2005 BLE MT.bin` is the canonical stock ROM and the Ghidra analysis image. Keep it stock.
Both patchers always read that fixed file, verify its known SHA-256, patch an in-memory copy, and
write a separate output. They refuse an output path that resolves to the stock file, including a
hard link.

Build the canonical boost image from the repository root:

```sh
python3 patch/patch_boost.py
```

The normal output is `patch/D2WD610H_boost.bin`. An alternate output path may be supplied for an
experiment, but the input is deliberately not configurable:

```sh
python3 patch/patch_boost.py /tmp/D2WD610H_boost_test.bin
```

Build the standalone single-front-A/F development image the same way:

```sh
python3 patch/patch_single_front_af.py
python3 patch/verify_single_front_af.py
```

Never patch a previously patched image. Every build starts from the root stock ROM.

## Boost controller

The injected controller runs through the former purge output path and commands the stock PWM
output stage at `0xE8C4`:

```text
base   = BaseDuty[rpm]
target = TargetBoost[rpm]
error  = target - MAP(0xFFFFABC4)
ratio  = clamp(base + Kp * error, 0, MaxRatio)
if throttle(0xFFFFB314) <= MinThrottle: ratio = 0
if MAP > SoftOverboost: ratio = 0
```

It is stateless proportional + feed-forward control. No safe persistent scratch-RAM word has
been proven, so an integral term is intentionally omitted. Defaults are reduced from A2WC510N
to a 5 psi peak target; `Kp` is `0.0005 ratio/mmHg`. Set Kp to zero for the first hardware
commissioning pass, then restore/tune it only after MAP and feed-forward duty are proven.

A second hook wraps the stock rev limiter. When MAP exceeds the hard limit, it sets the factory
fuel-cut flag `0xFFFFBF6C` bit `0x80`, which is consumed by `fuel_cut_flag_aggregate` at
`0x23FC0`.

## Files

| File | Purpose |
|---|---|
| `patch_boost.py` | Canonical stock-ROM-to-boost-ROM patcher. |
| `sh2_asm.py` | Minimal two-pass SH-2E assembler with known-encoding self-tests. |
| `sh2_disasm.py` | Minimal SH-2E disassembler used for binary verification. |
| `verify_regions.py` | Audits free-flash and scratch-RAM assumptions. |
| `verify_boost_donor.py` | Re-extracts A2WC510N tables and verifies the generated 5 psi defaults and MAP scaling. |
| `D2WD610H_boost.bin` | Generated boost-control ROM; never use it as patch input or as the Ghidra stock image. |
| `patch_single_front_af.py` | Canonical stock-ROM-to-single-front-A/F patcher. |
| `verify_single_front_af.py` | Audits front hooks, DTC edits, injected code, preserved rear paths, and every changed offset. |
| `D2WD610H_single_front_af.bin` | Generated standalone front-A/F ROM; development image, not merged with boost. |

RomRaider boost calibration entries are in
[D2WD610H_AVLS_boost_patch.xml](../defs/D2WD610H_AVLS_boost_patch.xml), category
`Boost Control (patch)`. The front-A/F patch adds no calibrations and needs no separate ROM or
logger definition.

## Boost injected layout

| Item | Address |
|---|---:|
| Base-duty descriptor | `0x7D790` |
| Shared RPM axis | `0x7D7A4` |
| Base-duty data | `0x7D7C4` |
| Target descriptor | `0x7D7CC` |
| Target data | `0x7D7E0` |
| Kp / maximum ratio / soft overboost | `0x7D800` / `0x7D804` / `0x7D808` |
| Controller stub | `0x7D80C` |
| Minimum throttle | `0x7D8A4` |
| Hard overboost | `0x7D8A8` |
| Fuel-cut wrapper | `0x7D8AC` |
| Donor MAP scaling | `0x72810`: `{-414.0, 514.199951}` |
| Purge output hook | `0x3FD8C` -> `0x7D80C` |
| Rev-limiter hook | `0x11D3C` -> `0x7D8AC` |

## Single-front-A/F path

The separate front-sensor patch runs the complete retained RH/Bank-1 factory A/F processing,
then mirrors its processed lambda/current/readiness results into the Bank-2 paths. It also makes
the Bank-2 inhibit helper reuse the unchanged Bank-1 result and disables only P0051, P0052,
P0151, P0152, and P0154 for the physically removed LH/Bank-2 front sensor.

Both rear narrowband channels, their processed RAM values, their diagnostics, and the rear
processing entry at `0xE0D0` remain stock. A post-turbo wideband must be logged externally; there
is no ECU analog input, conversion routine, RAM publication, patch calibration, or custom ECU
logger parameter for it.

The standard RomRaider E91/E109 channels remain the later factory front-sensor log paths and
should both track the retained sensor after patching. See
[single_front_af_patch.md](../docs/single_front_af_patch.md) for the exact patch and harness
boundary.

## Before flashing

The boost patch is binary-verified, not vehicle-verified. It already copies the A2WC510N MAP
scaling to `0x72810`; fit the compatible sensor and verify logged pressure against a reference.
Verify PWM frequency and output polarity on a bench, prove both overboost responses, deal with
purge DTCs if required, and produce a valid `subarudbw` checksum. Keep wastegate spring pressure
as the mechanical fallback during commissioning.

The single-front-A/F image is likewise binary-verified, not vehicle-verified. Verify the exact
front-sensor connector variant, correct the checksum, and prove both-bank logging and retained
sensor fault behavior without boost before considering a merged image. Confirm both stock rear
sensors and their diagnostics still operate normally.
