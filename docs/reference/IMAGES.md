# Images, calibration and ownership

[Reference home](README.md) · [Original audit evidence](evidence/image_contracts.json) · [V2 repair](V2_LOAD_FALLBACK_FIX.md)

## Current rolling images

The [AVCS/OCV repair](AVCS_OCV_REPAIR_20260913.md) restores the native cam
current converter, feedback loop, output and circuit monitors incorrectly
removed by the former rear-O2 bypass. It also restores the native integrator
initializer and moves the conflicting wideband/lean state. Both builds retain
the preceding fuel-pump scaling repair. Neither repair has been flashed.

| Artifact | SHA-256 | Checksum |
|---|---|---|
| [Main BIN](../../master_patch/D2WD610H_master_patch.bin) | `3e95b7508427f544e30a96c7aa78298b32560a6f3caf5c180e7949b8c2adc388` | `1ADC9F24` |
| [V2 BIN](../../master_patch_v2/D2WD610H_master_patch_v2.bin) | `fabceb54359aca76e6e15835a51aa5cfd008e570dc002e886eaa62a6cb020ce5` | `AA416B03` |

The [exact repair evidence](evidence/avcs_ocv_repair_20260913.json) records
72 changed bytes in 16 spans per image relative to the pump-only builds below.
Use the updated logger definitions for E500/E504/E505 with these images.
The software defect is reproduced and repaired; the loaded cut is not proven
cured, and the broader process-flow audit remains in progress.

## September 12 pump-scaling images

The preceding v2 build had
SHA-256 `8ab70f32dce51857652fc2ab24e340dea9399f12d7042cf8f9afab851e0df6d5`
and checksum `4295EB4B`. The [fuel-pump demand scaling repair](FUEL_PUMP_SCALING_20260912.md)
pairs the separate pulse-to-consumption coefficient with the installed injector
calibration. Only `72D54` and the checksum word changed: eight byte positions
relative to the 14:42 drive image below. All ten v2 verifier groups pass.
The loaded bog remains unresolved; this repair has not been flashed or logged.

The matching main build had the same
coefficient repair: SHA-256
`697b9f3a48a95027cc048ed68967520e2de4692314d88cf1768564ef15471d3a`, checksum
`B3311F6C`. Its change is seven byte positions across the same two words.
The [word-level evidence](evidence/fuel_pump_scaling_20260912.json) reconstructs
the exact preceding images for historical log analysis.

## September 12 adjusted-VE drive image

The 14:42 drive used v2
SHA-256 `fd795813febf817c845fc922e81e498539a539efeeb6e4d11822af47098094a2`
and checksum `43191A9F`. The requested
[warm fueling adjustment](V2_AVLS_NEUTRAL_20260912.md#requested-idle-and-high-lift-fueling-adjustment)
adds 5% to four idle VE cells and removes 12% from six high-lift vacuum cells.
It changes 34 byte positions across those ten floats and the checksum;
all other bytes match the captured image below. The independent calibration
check and all nine then-current v2 verifier groups passed. The
[14:42 driving follow-up](V2_AVLS_MISFIRE_20260912.md#1442-adjusted-ve-drive-loaded-fault-persists)
matches this historical image and reproduces the loaded bog; offline checks are not
a driving clearance. The earlier [lean-reset correction](V2_AVLS_MISFIRE_20260912.md),
stationary oil-gate repair and rotational-idle removal are retained.

## September 12 oil-gate and warm fueling capture image

Both **13:37** and **14:13** captures use the pre-adjustment image with SHA-256
`4808414b01f3ede952197422f75a791f5325595a27bc810ca610b82d3954d67e`,
checksum `42B2F389`. All 16 pre-capture FastECU post-flash block CRCs at
13:37:18 match it. The [neutral follow-up](V2_AVLS_NEUTRAL_20260912.md)
records two stationary high-lift command/current transitions, then a warm
capture confirms the sustained rich high-lift hold and lean idle baseline.

This captured image restored two misidentified stationary AVLS oil thresholds
from 110 C to stock 15 C. That repair changed six bytes across `7D4B0/B4`
and the checksum relative to the 13:16 capture image. Its RPM thresholds,
pedal curves, VE, timing and other fueling calibration were identical.

The main image at the oil-gate repair was:
SHA-256 `db33aad398d6335411c36f5c0e0f1338095b89821a4111370f5d16101fcf6089`,
checksum `B3B44EC0`. It received the same six-byte oil-gate correction. Its
other code/calibration and default-off rotational-idle component are unchanged.
It does not receive the later v2-only VE adjustment.

## September 12 neutral capture image

The 13:16 neutral capture used v2 SHA-256
`c6528704472f396cf57c3d18b5e6ef14e46b6da376e9cf19f58f8739ca5c66bc`,
checksum `3FDAF389`; all 16 recorded 13:15 post-flash block CRCs match. This
was the separate lean-reset repair: 75 changed bytes in the wrapper/checksum
relative to the rotational-delete image below. The stationary oil thresholds
were still erroneous at 110 C. Its dependent v1 image was
`42b516c80e95a531834ce090c4da4713fd60538e9e6e9bffe3951caa805d0f30`,
checksum `B0DC4EC0`.

## September 12 rotational-delete capture image

The September 12 rolling [v2 BIN](../../master_patch_v2/D2WD610H_master_patch_v2.bin)
used for the rotational-delete capture had SHA-256 `ca4516f5a3737cffc172e9f1771a78a1a4ee966703136281d65d275d77dad7ef`
and additive checksum `A5F4DFD6`. Rotational idle is removed: task pointer
`11E30` calls stock `279CC` directly, and `7DB40..7DCFF` is erased. Its matching
[v2 definition](../../master_patch_v2/D2WD610H_master_patch_v2.xml) omits the
12 rotational-idle controls.

Compared with the preceding v2 image at `5f0ba2a` (SHA-256
`c8d858135df670f2730d5abca727c2f40a6736183049edef8a17d31c200311ed`),
changes are confined to that pointer, the former component allocation and the
checksum word. All other code and calibration bytes are identical. The earlier
image produced the September 12 `road1` log. The rotational-delete image was
subsequently flashed and produced `romraiderlog_rotationaldelete_20260912_122651.csv`.

## September 9 saved images

All three images are 512 KiB and share CALID D2WD610H. CALID alone cannot
identify a patch revision. V2 below includes the September 9 load-fallback repair.

| Image | Path | SHA-256 |
|---|---|---|
| Stock | [2005 BLE MT.bin](../../2005%20BLE%20MT.bin) | `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee` |
| Rolling main | [master BIN](../../master_patch/D2WD610H_master_patch.bin) | `154760a5f2fdadbf6d9221480595f58dc77c6a4eccc492f50899c815aca79e4d` |
| V2 | [v2 BIN](../../master_patch_v2/D2WD610H_master_patch_v2.bin) | `3ad3f0708843961ad54175e40236521990ed8b2ed60d082dcc51368e1c75b7b7` |

Main's additive checksum is `16F63B0D`; v2's is `ECD40ED7`. Both retain marker
`26090804` at `7FC4C`, so use the hash to identify the repair. Stock, its base
copy and the extracted SRF payload are checked for equality.

The original audit at `2d95301` used v2 SHA-256
`2fe5f9cc7f960bff1efd784bb29e6c984ccbc025f1d8029c920fd52a3ce25ac9`, checksum
`ECD02DF7`. Those historical bytes remain available through the audit readers
and Git. The later repair changes only the local pointer and checksum; no
calibration or definition XML changes.

## September 9 calibration comparison

Values below are decoded from the saved bytes, rounded for display.

| Address / behavior | Main | V2 |
|---|---|---|
| `173FC`, local load-status helper | `27088`, constant zero | Same; repaired from native getter `65168` |
| `3FD8C`, fan output literal | `E8C4`, stock | Same |
| `72810/72814`, MAP offset/slope | −67.7766571 mmHg; 487.9919434 mmHg/V | Same |
| `7DD10`, SD lower valid pressure | 78.6149597 mmHg | Same; old 100-mmHg limit was repaired |
| `73968`, conditioned-load response | 0.06 per update | Same |
| `76030`, slow-negative transient gain | 0.04 | Same |
| `7D4B8/7D4BC`, AVLS release/engage | 3000/3200 RPM | Same; stock is 3800/4000 |
| `7D4B0/7D4B4`, stationary AVLS oil thresholds | Erroneously 110 C in these saved images | Same; both restored to stock 15 C in the September 12 follow-up |
| `76050`, falling transient history response | 0.01 | 0.08 |
| `76AC8`, tip-in MRP factors | Retained stock pressure-dependent curve | Eight unity factors |
| `7963C`, native air-decay decrement | About 0.6, stock | About 0.15, already present in v2 |
| Low-lift VE | Integrated ten-cell idle plateau | Separate v2 smoothing |
| Timing | Main's existing resampling/caps | A/D low-RPM floors and different boost caps |

V2's `FULL_BOOST_TIMING_CAP` begins at **+10 degrees**; the final table also
depends on the original/resampled value and load offset. The bypass repair
corrects its stale +6-degree header/output without changing timing calibration.
The cap is not a universal 10-degree output.

The user's independent dashpot experiment was not merged into main. Recording
the already-present v2 value above does not adopt that experiment.

## Local load-fallback repair in v2

`65168` returns 2 when `D26F & 40` is set. In the audit-baseline v2 load task
that selects `max(B2A0 * 0.00264 - 0.0851, 0)` instead of the SD-derived load
path. Both current builds bypass that getter locally. The native diagnostic
getter and fault byte remain intact.

Main's bypass was already present in commit `ead14bb` on September 8; it was
not added during the documentation audit. The [September 9 v2 repair](V2_LOAD_FALLBACK_FIX.md)
combines it with v2's existing timing and MAP-pressure tip-in corrections,
preserving every calibration byte.

The original eight audit cases execute each getter and retained load body.
The new v2 regression also executes the caller's actual pointer load and
status store before feeding `1753A–1770A`. At 1500 RPM, initial load 0.5,
ECT 45 C and processed MAP 250 mmHg:

| Image / flag | 12.5 g/s input | 20 g/s input |
|---|---:|---:|
| Main, D26F clear or bit 40 set | 0.5000 g/rev | 0.5180 g/rev |
| Audit-baseline v2, D26F clear | 0.5000 g/rev | 0.5180 g/rev |
| Audit-baseline v2, D26F bit 40 set | 0.5749 g/rev | 0.5749 g/rev |
| Repaired v2, D26F clear or bit 40 set | 0.5000 g/rev | 0.5180 g/rev |

This establishes a conditional software difference. It does not establish that
the bit was set during any historical near-stall. The existing main fixture
supplies a zero local getter result; the new v2 test explicitly supplies the
executed caller result and reproduces failure when the bypass is removed.
See [repair evidence and boundaries](V2_LOAD_FALLBACK_FIX.md).

## Ownership and reproducible commands

Shared components live under `patches/{core,speed_density,wideband_o2,
fueling_safety,purge_delete}`. Master assembly, calibration, ROMs and profiles
remain in `master_patch/`. V2 retains its own directory and component-specific
SD/calibration sources. The [memory layout](../../master_patch/MEMORY_LAYOUT.md)
is the detailed main allocation contract, checked by the full verifier.

The old standalone front-mirror/rear-delete wrapper area `7D920–7DB3B`
is erased in current main/v2. Their permanent wideband design instead hooks
`7E440/7E520`, and the retired rear tasks point directly to `66C2`. Historical
component entry addresses must not be treated as installed main code.
Current emitted sizes are 88 bytes for the hard-cut wrapper, 536 for SD,
348 for rotational idle and 512 for the composed lean-cut wrapper. Earlier
64/72, 528/552 and 488/500-byte boundaries are historical; the current
contiguous free tail begins at `7EE00` and contains 3,320 bytes.

Run from the repository root:

```sh
python3 -B tests/verify_master_patch.py
python3 -B master_patch_v2/verify_master_patch.py
python3 -B tools/audit_image_contracts.py
```

The first command rebuilds in memory and checks main's saved image, ownership,
calibration, definitions, logger, arithmetic and retained-routine fixtures.
V2's nine verifier groups cover checksum, layout, definition, rotational-idle
removal, lean-cut hysteresis, AVLS oil gates, primary fueling, injector
scheduling and the separate native diagnostic cut. Coverage remains narrower
than main's. Load-fallback execution also has its own focused test script.
The image-audit command reproduces the pre-fix evidence from Git at `2d95301`.
Build commands remain
`python3 -B master_patch/build_master_patch.py` and the corresponding v2 script;
these commands write their normal output files.

V2's final verifier message now reports offline verification. Physical engine
behavior remains outside the scope of these checks.

## Calibration assumptions still requiring physical evidence

The main MAP transfer is for the documented Omni MAP-SUP-3BR endpoint pair
30–300 kPa at 0.60–4.75 V. The IAT curve assumes an HT-010206 thermistor and
1.00-kohm ECU pull-up. The seller-labelled wideband must actually supply the
configured P0/P1 analog transfer. Injector data comes from the pinned
A4TE002B application for 16611AA510; operating fuel pressure and installed
hardware remain physical conditions. None is validated merely by plausible
logger readings or a successful binary build.
