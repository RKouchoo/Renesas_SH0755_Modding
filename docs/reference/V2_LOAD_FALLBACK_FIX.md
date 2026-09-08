# V2 local MAF-fault load bypass

[Reference home](README.md) · [Image comparison](IMAGES.md)

The September 9 repair carries main's existing local load-fallback bypass into
v2, preserving v2's timing and MAP-pressure tip-in corrections. The normal v2
artifact has been rebuilt; no separate candidate ROM is introduced.

## Change and image identity

In the retained airflow/load task, the literal at `173FC` now points to the
stock constant-zero helper `27088`, replacing `65168`. The native status getter
at `65168` remains intact, as does its `FFFFD26F` fault byte. Only this task's
decision to substitute processed-MAP load is bypassed. The builder checks the
original literal and the zero-helper instructions before accepting the ROM.

| Field | Before | After |
|---|---|---|
| SHA-256 | `2fe5f9cc7f960bff1efd784bb29e6c984ccbc025f1d8029c920fd52a3ce25ac9` | `3ad3f0708843961ad54175e40236521990ed8b2ed60d082dcc51368e1c75b7b7` |
| `173FC`, local status pointer | `00065168` | `00027088` |
| `7FB88`, additive checksum | `ECD02DF7` | `ECD40ED7` |

The output is
[master_patch_v2/D2WD610H_master_patch_v2.bin](../../master_patch_v2/D2WD610H_master_patch_v2.bin).
Exactly six byte positions change: `173FD–173FF` and `7FB89–7FB8B`.
Everything else is byte-identical to the previous v2 ROM, including timing,
MAP tip-in, VE, injector data, load filters, existing air-decay calibration and
the build marker. Use the SHA-256 to distinguish these revisions. Definitions,
logger addresses, flash allocation and RAM allocation are unchanged.

The builder's stale +6-degree timing description now reports the existing
2000-RPM +10-degree cap from its calibration constant. This corrects the
description only; no timing value changes in this repair.

## Regression evidence

[Five test groups](../../tests/test_v2_load_fallback_execution.py) are now part
of the v2 verifier. They execute the caller's literal load, helper call and
delay-slot status store at `172E2–172F0`, then the retained conditioning body
at `1753A–1770A` with that captured status byte.

- A 36-case sweep combines four fault-byte values, three processed pressures
  and three airflow inputs. V2 follows airflow with the existing 0.06 filter
  whether the MAF fault bit is clear or set.
- The pre-fix image and a deliberately restored native pointer both reproduce
  the defect: with bit 40 set and processed MAP at 250 mmHg, load is 0.5749 g/rev
  for both 12.5 and 20 g/s airflow. Repaired v2 gives 0.5000 and 0.5180 g/rev.
- The native diagnostic helper still returns its original fault status and
  leaves the fault byte intact.
- A whole-image comparison permits changes only in the pointer and checksum
  words, protecting all existing v2 calibration bytes.
- An unexpected original status pointer is rejected by the component builder.

The new regression failed on the old ROM and passed after the repair. The
caller frame, upstream fault production and the later `1D228` state getter
are explicit fixture boundaries; interpolation is modeled. These tests do not
establish whether the fault was active during the historical near-stall.

Run from the repository root:

```sh
python3 -B master_patch_v2/build_master_patch.py
python3 -B master_patch_v2/verify_master_patch.py
python3 -B tests/test_v2_load_fallback_execution.py
```

The existing checksum, layout and definition checks remain, with the new
regression as a fourth group. The final message reports offline verification.
The [verification record](evidence/v2_load_fallback_fix.json) contains the exact
byte differences, representative before/after values and check results.

The original [audit evidence](evidence/image_contracts.json) remains pinned to
`2d95301`. Audit readers retrieve those images and definitions from Git, so
rebuilding v2 does not erase the evidence of the original omission. The
production builder still builds from pinned stock files without Git input.
