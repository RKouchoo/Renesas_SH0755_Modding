# patch/ — D2WD610H boost-control patch

This directory contains the single boost-control patch for repurposing the EVAP purge PWM
output as an electronic boost-control solenoid driver. Background and commissioning details:
[boost_repurpose_notes.md](../docs/boost_repurpose_notes.md),
[boost_donor_A2WC510N.md](../docs/boost_donor_A2WC510N.md),
[patch_build_guide.md](../docs/patch_build_guide.md), and [audit.md](../audit.md).

## Stock-ROM rule

`../2005 BLE MT.bin` is the canonical stock ROM and the Ghidra analysis image. Keep it stock.
`patch_boost.py` always reads that fixed file, verifies its known SHA-256, patches an in-memory
copy, and writes a separate output. It refuses an output path that resolves to the stock file,
including a hard link.

Build the canonical image from the repository root:

```sh
python3 patch/patch_boost.py
```

The only normal output is `patch/D2WD610H_boost.bin`. An alternate output path may be supplied
for an experiment, but the input is deliberately not configurable:

```sh
python3 patch/patch_boost.py /tmp/D2WD610H_boost_test.bin
```

Never patch a previously patched image. Every build starts from the root stock ROM.

## Controller

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
fuel-cut flag `0xFFFFBF6C` bit `0x80`, which is consumed by `fuel_cut_flag_aggregate` at `0x23FC0`.

## Files

| File | Purpose |
|---|---|
| `patch_boost.py` | Canonical stock-ROM-to-boost-ROM patcher. |
| `sh2_asm.py` | Minimal two-pass SH-2E assembler with a known-encoding self-test. |
| `sh2_disasm.py` | Minimal SH-2E disassembler used for binary verification. |
| `verify_regions.py` | Audits free-flash and scratch-RAM assumptions. |
| `verify_boost_donor.py` | Re-extracts A2WC510N tables and verifies the generated 5 psi defaults and MAP scaling. |
| `D2WD610H_boost.bin` | Generated boost-control ROM; never use it as patch input or as the Ghidra stock image. |

RomRaider calibration entries are in
[D2WD610H_AVLS_boost_patch.xml](../defs/D2WD610H_AVLS_boost_patch.xml), category
`Boost Control (patch)`.

## Injected layout

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
| Purge output hook | `0x3FD8C` → `0x7D80C` |
| Rev-limiter hook | `0x11D3C` → `0x7D8AC` |

## Before flashing

This patch is binary-verified, not vehicle-verified. It already copies the A2WC510N MAP scaling
to `0x72810`; fit the compatible sensor and verify logged pressure against a reference. Verify
PWM frequency and output polarity on a bench, prove both overboost responses, deal with purge
DTCs if required, and produce a valid `subarudbw` checksum. Keep wastegate spring pressure as
the mechanical fallback during commissioning.
