# patch/ — D2WD610H patch builders

This directory contains the canonical boost-control patch and a separate hybrid-O2 development
patch. The boost patch repurposes the EVAP purge PWM output as an electronic boost-control
solenoid driver. The hybrid-O2 patch retains one factory pre-turbo A/F sensor for closed-loop
control and adds a conditioned post-turbo AEM input for ECU logging. They are built independently
from stock and are not yet a merged flash image. Background and commissioning details:
[boost_repurpose_notes.md](../docs/boost_repurpose_notes.md),
[boost_donor_A2WC510N.md](../docs/boost_donor_A2WC510N.md),
[patch_build_guide.md](../docs/patch_build_guide.md),
[hybrid_o2_patch.md](../docs/hybrid_o2_patch.md), and [audit.md](../audit.md).

## Stock-ROM rule

`../2005 BLE MT.bin` is the canonical stock ROM and the Ghidra analysis image. Keep it stock.
Both patchers always read that fixed file, verify its known SHA-256, patch an in-memory copy, and
write a separate output. They refuse an output path that resolves to the stock file, including a
hard link.

Build the canonical image from the repository root:

```sh
python3 patch/patch_boost.py
```

The only normal output is `patch/D2WD610H_boost.bin`. An alternate output path may be supplied
for an experiment, but the input is deliberately not configurable:

```sh
python3 patch/patch_boost.py /tmp/D2WD610H_boost_test.bin
```

Build the standalone hybrid-O2 development image the same way:

```sh
python3 patch/patch_wideband.py
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
| `patch_wideband.py` | Canonical stock-ROM-to-standalone-hybrid-O2 patcher. |
| `verify_wideband.py` | Audits hybrid hooks, DTC edits, injected code, calibration math, and all changed offsets. |
| `install_aem_logger.py` | Adds the D2-only AEM parameters to a normal RomRaider logger XML while preserving its source. |
| `D2WD610H_wideband.bin` | Generated standalone hybrid-O2 ROM; development/commissioning image, not merged with boost. |

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

## Hybrid-O2 logger path

The hybrid patch leaves the retained RH/Bank-1 factory A/F sensor in control and mirrors its
processed lambda/current/readiness results into the Bank-2 paths. The removed LH/Bank-2 front
sensor diagnostics are disabled. AEM 30-0310 analog output is accepted only through an external
buffered/protected differential 0.2 V/V conditioner on the verified RH rear-O2 circuit:

```text
AEM white/brown -> external conditioner -> E61-3/E61-4
raw ADC FFFFAB20 -> calibrated lambda -> FFFFB098 (logging only)
```

Do not connect the AEM 0.5–4.5 V output directly to the stock 0–0.9 V rear-O2 input. For this H6
diagram, `E61-3` must have continuity to `B137-24`, and `E61-4` to `B136-35`; verify both on the
actual car before wiring because market diagrams differ. `B135-15` is ignition control #4 and
must not be used. The exact wiring, analog-interface boundary, and calibration procedure are in
[hybrid_o2_patch.md](../docs/hybrid_o2_patch.md).

Install the two project logger parameters into a normal RomRaider metric logger file:

```sh
python3 patch/install_aem_logger.py /path/to/logger_METRIC_EN_v370.xml
```

Use E500 for post-turbo AEM lambda and E501 for raw ADC counts. The standard E91/E109 channels
remain the mirrored factory A/F sensor. The ROM patch cannot reliably identify an open ECU-side
AEM wire because the stock rear-O2 input has a 0.2–0.5 V bias; see the hardware fail-low
requirement in the hybrid document.

## Before flashing the boost patch

This patch is binary-verified, not vehicle-verified. It already copies the A2WC510N MAP scaling
to `0x72810`; fit the compatible sensor and verify logged pressure against a reference. Verify
PWM frequency and output polarity on a bench, prove both overboost responses, deal with purge
DTCs if required, and produce a valid `subarudbw` checksum. Keep wastegate spring pressure as
the mechanical fallback during commissioning.

The hybrid-O2 image is likewise binary-verified, not vehicle-verified. Do not flash it until the
exact connector continuity/bias checks, external conditioner validation, three-point ADC
calibration, DTC review, and checksum correction in
[hybrid_o2_patch.md](../docs/hybrid_o2_patch.md) are complete.
