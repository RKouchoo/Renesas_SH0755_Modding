# Images, calibration and ownership

[Reference home](README.md) · [Original audit evidence](evidence/image_contracts.json) · [V2 repair](V2_LOAD_FALLBACK_FIX.md)

## Current saved images

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

## Main and v2 are different calibration and control contracts

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
| `7D4B0/7D4B4`, AVLS fallback pedal thresholds | 110 percent | Same; stock is 15 percent |
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
V2's verifier checks its checksum/layout/definition contract plus five local
load-fallback regression groups; coverage is still narrower than main's.
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
