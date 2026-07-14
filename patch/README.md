# patch/ — D2WD610H patch builders

This directory contains the canonical boost-control patch, the single-front-A/F development
patch, a separate rotational-idle development patch, and a two-component combined builder. The boost patch repurposes the EVAP purge PWM output as an
electronic boost-control solenoid driver. The front-A/F patch retains one factory pre-turbo A/F
sensor for closed-loop control, mirrors it into both bank paths, and logically removes both rear
narrowbands from the traced ADC/monitor chain. The rotational-idle component post-processes the
six stock final ignition angles only inside a bounded warm-idle window. It is intentionally not
installed by the current combined builder. Each standalone image and the combined image are
built directly from fresh stock; generated images are never stacked.

Background and commissioning details:
[boost_repurpose_notes.md](../docs/boost_repurpose_notes.md),
[boost_donor_A2WC510N.md](../docs/boost_donor_A2WC510N.md),
[patch_build_guide.md](../docs/patch_build_guide.md),
[single_front_af_patch.md](../docs/single_front_af_patch.md),
[rotational_idle_patch.md](../docs/rotational_idle_patch.md), and [audit.md](../audit.md).

## Stock-ROM rule

`../2005 BLE MT.bin` is the canonical stock ROM and the Ghidra analysis image. Keep it stock.
All patchers always read that fixed file, verify its known SHA-256, patch an in-memory copy, and
write a separate output. They refuse an output path that resolves to a protected stock source,
including a hard link.

The original ECU read is `../base_roms/2005 BLE MT.srf`. `extract_srf.py` parses its big-endian
chunk structure and extracts the single `MEMD` payload at file offset `0x1CD`. The payload is
exactly 512 KiB with SHA-256
`ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`, byte-identical to both
`../base_roms/2005 BLE MT.bin` and the canonical root stock image. The combined builder repeats
this SRF provenance check before every build.

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
python3 patch/verify_romraider_toggles.py
```

Build the separate rotational-idle development image:

```sh
python3 patch/patch_rotational_idle.py
python3 patch/verify_rotational_idle.py
python3 patch/verify_romraider_toggles.py
```

Its normal output is `patch/D2WD610H_rotational_idle.bin`. The enable byte is generated as `00`,
so installing the binary does not activate the timing effect. Its reusable `apply_to_rom()` API
is exercised against the other components in memory, but it is not imported by
`patch_combined.py` yet.

Build and verify the combined image:

```sh
python3 patch/patch_combined.py
python3 patch/verify_combined.py
python3 patch/verify_romraider_toggles.py
```

The normal combined output is `patch/D2WD610H_boost_single_front_af.bin`. It is the exact
non-overlapping union of both component patch sets applied to one fresh stock copy, not a patch
applied to either standalone generated image. It does not contain the rotational-idle component.

The conservative 5 psi / 98 RON calibration is kept separately in
[`base_turbo_map/`](../base_turbo_map/README.md):

```sh
python3 base_turbo_map/build_base_turbo_map.py
python3 base_turbo_map/verify_base_turbo_map.py
```

That builder also starts from the root stock ROM. It reconstructs and hash-verifies this combined
stage in memory before applying calibration changes; it never uses a generated ROM as patch input.
Its output commands zero EBCS duty for the installed 5 psi wastegate spring, translates the pinned
A4TE002B STI-pink injector calibration, moves AVLS earlier, and sets the requested 6800 RPM limit.
It is not flash-ready until injector identity/condition, MAF, fuel-pressure, MAP, and
external-wideband requirements are met.

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
| `extract_srf.py` | Parses the original SRF container, extracts/verifies its 512-KiB `MEMD` ROM, and refuses mismatched existing output. |
| `patch_boost.py` | Canonical stock-ROM-to-boost-ROM patcher. |
| `patch_combined.py` | Canonical stock-ROM-to-combined boost + single-front-A/F patcher; also verifies SRF provenance and zero byte overlap. |
| `sh2_asm.py` | Minimal two-pass SH-2E assembler with known-encoding self-tests. |
| `sh2_disasm.py` | Minimal SH-2E disassembler used for binary verification. |
| `verify_regions.py` | Audits free-flash and scratch-RAM assumptions. |
| `verify_boost_donor.py` | Re-extracts A2WC510N tables and verifies the generated 5 psi defaults and MAP scaling. |
| `verify_romraider_toggles.py` | Parses standalone and combined definitions and verifies target IDs, switch/table addresses, generated defaults, and isolated one-byte toggle edits. |
| `verify_combined.py` | Regenerates the combined image, audits exact union/change ownership, decodes all injected code, and checks the retained front/rear-delete paths. |
| `D2WD610H_boost.bin` | Generated boost-control ROM; never use it as patch input or as the Ghidra stock image. |
| `patch_single_front_af.py` | Canonical stock-ROM-to-single-front-A/F plus rear-O2-delete patcher. |
| `verify_single_front_af.py` | Audits front hooks, rear bypass hooks, 13 DTC edits, injected code, and every changed offset. |
| `D2WD610H_single_front_af.bin` | Generated standalone front-A/F development ROM. |
| `patch_rotational_idle.py` | Canonical stock-ROM-to-rotational-idle patcher with guarded `apply_to_rom()` component API. |
| `verify_rotational_idle.py` | Audits the exact binary, injected instructions, operating policy, changed-byte ownership, and future three-component compatibility. |
| `D2WD610H_rotational_idle.bin` | Generated standalone rotational-idle development ROM; enable defaults off. |
| `D2WD610H_boost_single_front_af.bin` | Generated combined development ROM; both runtime switches default on. |

RomRaider boost calibration entries are in
[D2WD610H_AVLS_boost_patch.xml](../defs/D2WD610H_AVLS_boost_patch.xml), category
`Boost Control (patch)`. Its `Boost Control Patch Enable` switch writes `01`/`00` at `0x7D80C`.
The matching front-A/F/rear-delete definition is
[D2WD610H_AVLS_single_front_af_patch.xml](../defs/D2WD610H_AVLS_single_front_af_patch.xml); its
`Single Front A/F Patch Enable` switch writes `01`/`00` at `0x7D91C`. Neither patch adds an
aftermarket-wideband ECU/logger definition.

The separate rotational-idle image must be opened with
[D2WD610H_AVLS_rotational_idle_patch.xml](../defs/D2WD610H_AVLS_rotational_idle_patch.xml). Its
`Rotational Idle Patch Enable` switch writes `01`/`00` at `0x7DB40`; all operating gates and six
timing offsets are in category `Rotational Idle (patch)`.

The combined image must be opened with
[D2WD610H_AVLS_boost_single_front_af_patch.xml](../defs/D2WD610H_AVLS_boost_single_front_af_patch.xml).
It contains the boost tables and both enable switches at their unchanged component addresses.

Boost and front-A/F switches default to `ON` in their generated images. Boost `OFF` forces zero
EBCS duty and bypasses the added hard overboost cut while retaining the stock rev limiter; it
does not revert the patched MAP scaling. Front-A/F `OFF` restores stock dual-front and rear-O2 runtime
logic, but the 13 generated DTC-byte edits remain off until P0051/P0052/P0151/P0152/P0154 and
P0037/P0038/P0057/P0058/P0137/P0138/P0157/P0158 are separately re-enabled in RomRaider.
Rotational idle defaults `OFF`; only exact `01` permits its bounded timing post-processing.

These are flash calibration bytes, not live logger controls. A RomRaider change takes effect only
after the edited ROM is saved with a valid checksum and flashed to the ECU.

## Boost injected layout

| Item | Address |
|---|---:|
| Base-duty descriptor | `0x7D790` |
| Shared RPM axis | `0x7D7A4` |
| Base-duty data | `0x7D7C4` |
| Target descriptor | `0x7D7CC` |
| Target data | `0x7D7E0` |
| Kp / maximum ratio / soft overboost | `0x7D800` / `0x7D804` / `0x7D808` |
| Runtime enable byte | `0x7D80C` |
| Controller stub | `0x7D810` |
| Minimum throttle | `0x7D8BC` |
| Hard overboost | `0x7D8C0` |
| Fuel-cut wrapper | `0x7D8C4` |
| Donor MAP scaling | `0x72810`: `{-414.0, 514.199951}` |
| Purge output hook | `0x3FD8C` -> `0x7D810` |
| Rev-limiter hook | `0x11D3C` -> `0x7D8C4` |

## Single-front-A/F and rear-O2-delete path

The separate front-sensor patch runs the complete retained RH/Bank-1 factory A/F processing,
then mirrors its processed lambda/current/readiness results into the Bank-2 paths. It also makes
the Bank-2 inhibit helper reuse the unchanged Bank-1 result and disables P0051, P0052, P0151,
P0152, and P0154 for the physically removed LH/Bank-2 front sensor.

Its enable byte is `0x7D91C`; front wrappers start at `0x7D920`, the runtime Bank-2 inhibit
selector is at `0x7DA20`, and rear selectors occupy `0x7DA60..0x7DB3B`. With the byte clear,
the wrappers stop mirroring/bypassing and restore the original front and rear runtime behavior.

With exact enable `01`, the hook at `0xE0D0` returns before converting raw rear channels
`0xFFFFAB20/0xFFFFAB0C`, and task-pointer selectors at `0x11488`, `0x1148C`, `0x11490`, and
`0x114A0` bypass the traced rear threshold, filter/delta, response-integrator, and paired
low/high-voltage diagnostic stages. The patch also disables P0037, P0038, P0057, P0058, P0137,
P0138, P0157, and P0158. Rear logger values are stale/undefined while enabled. The heater output
drivers are not electrically tri-stated, so disconnected harness terminals must remain insulated.

A post-turbo wideband must be logged externally; there is no ECU analog input, conversion
routine, RAM publication, patch calibration, or custom ECU logger parameter for it.

The standard RomRaider E91/E109 channels remain the later factory front-sensor log paths and
should both track the retained sensor after patching. See
[single_front_af_patch.md](../docs/single_front_af_patch.md) for the exact patch and harness
boundary.

## Rotational-idle path

The standalone component redirects periodic task pointer `0x11E30` from
`ign_final_timing_per_cylinder_update` at `0x279CC` to a wrapper at `0x7DB90`. The wrapper always
runs the stock task first. Only exact enable `01`, ECT 80–105 C, RPM 600–1050, throttle at or
below about 2%, vehicle speed at or below 1 km/h, and MAP 150–550 mmHg absolute permit the six
default offsets `{-6,0,-6,0,-6,0}` degrees.

Positive offsets cannot add advance, requested retard is limited to 8 degrees, final timing uses
a 5-degree-BTDC floor, and a final ceiling prevents the result from ever exceeding the original
stock angle. NaN sensor/gate data exits to stock, invalid offset/maximum-retard data produces
zero offset, and an invalid timing floor retains stock. The component occupies
`0x7DB40..0x7DCEB`, after the front patch's final byte at
`0x7DB3B`. It changes no fuel, airflow, AVLS, limiter, misfire-DTC, or persistent-RAM behavior.
See [rotational_idle_patch.md](../docs/rotational_idle_patch.md) for the complete policy and
standalone commissioning sequence.

## Before flashing

The boost patch is binary-verified, not vehicle-verified. It already copies the A2WC510N MAP
scaling to `0x72810`; fit the compatible sensor and verify logged pressure against a reference.
Verify PWM frequency and output polarity on a bench, prove both overboost responses, deal with
purge DTCs if required, and produce a valid `subarudbw` checksum. Keep wastegate spring pressure
as the mechanical fallback during commissioning.

The single-front-A/F image is likewise binary-verified, not vehicle-verified. Verify the exact
front-sensor connector variant, correct the checksum, and prove both-bank logging and retained
sensor fault behavior without boost. With the rear connectors safely isolated, confirm all eight
mapped rear DTCs remain inactive and neither fuel correction changes unexpectedly.

The rotational-idle image is also binary-verified only and must be commissioned separately with
its switch off first. Correct the checksum, log the complete warm idle and misfire behavior, then
test the mild default offsets while stationary and without boost. Uneven combustion torque and
retarded timing can increase vibration and exhaust/turbo temperature; stop on abnormal results.

The current combined artifact is structurally and binary verified, but it does not waive either
standalone commissioning plan. Prove the front-A/F behavior without boost and prove the complete
boost hardware/failsafe sequence separately before flashing the combined image. It also needs a
valid `subarudbw` checksum. Rotational idle remains outside that artifact until its own standalone
test plan passes and a later three-component combined definition/verifier is created.
