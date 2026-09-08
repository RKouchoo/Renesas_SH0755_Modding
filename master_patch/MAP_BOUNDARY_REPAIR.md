# MAP lower-bound repair — 2026-09-08

The rolling [D2WD610H_master_patch.bin](D2WD610H_master_patch.bin)
repairs the disagreement between native MAP electrical acceptance and the SD
minimum. It is rebuilt from canonical stock with the earlier idle-VE correction.
The user's independent dashpot experiment is excluded: both DBW maps, axes and
dashpot constants retain their original values. Git records previous master
versions; there is one current build output. The vehicle's near-stall remains
unresolved.

## What changed

The native classifier accepts ADC 3932 (about 0.300 V), which the installed
converter reports as 10.48113 kPa absolute. The old SD gate rejected any
pressure below 13.332 kPa, so 575 electrically accepted ADC codes instead
produced the fixed 500 g/s fallback. At 1500 RPM, 25 °C, low lift, the new
master calculates 3.54985 g/s at ADC 3932.

Only these three words differ from the historical 14:13 idle-VE image (`6af0d130…`):

| Address | Previous | Current master |
|---|---|---|
| `7DD10`, SD minimum | 100 mmHg / 13.332 kPa | 78.6149597 mmHg / 10.4811326 kPa |
| `7FB88`, checksum | `16CB75E9` | `16F63B0D` |
| `7FC4C`, build marker | `FFFFFFFF` | `26090804` |

There are **10 changed bytes** from that image, or **41 bytes** from the previous
10:30 master (`48d63cf3…`), including the ten carried-forward idle-VE cells.
The minimum is the exact native SH-2E converter
result, encoded as `429D3ADC`; using ordinary host rounding can give a different
boundary. The existing native VE helper already clamps lookup coordinates below
its first pressure knot while retaining actual pressure in the air-mass product.
No replacement assembly is necessary, and no runtime instructions are added.

MAP still comes from ABC4. The ADC thresholds, slope/offset, slow-negative fuel
multipliers and 0.06 load filter remain byte-identical. The earlier idle plateau
is now part of `master_calibration.py`, so ordinary rebuilds preserve it.
The current master ECU definition already exposes the
changed scalar in kPa; no additional definition or logger edit is required.

## Shared lean-cut limit

The existing lean-cut wrapper uses the same minimum. A latched lean cut can
now release when MAP falls into the newly accepted deep-vacuum band and valid
barometric pressure satisfies the existing release rule. Previously this band
was considered invalid, holding the latch. Pressure below the new minimum or
invalid pressure still holds a latched cut. The release does not cancel the
independent rev-limit cut; native execution checks cover that interaction.

## Verification and limits

The master checks execute the native ADC converter, SD wrapper, native VE
lookup helpers and retained lean/rev-limit chain. All 1918 accepted ADC codes
below the first VE knot produce increasing airflow, including the repaired 575
codes. Across 180 normal-domain RPM/MAP/IAT/AVLS combinations, old and new
airflow results are bit-identical. Adjacent-float boundaries, rejected inputs,
stopped-engine behavior, shared lean-latch release and independent cuts pass.
The complete master verifier passes on the current saved BIN, including SD,
fueling, idle air, DBW, pedal, cut/scheduler, interrupt and logger checks.
Native boundary regressions run as part of that verifier. Standalone execution
tests now default to the rolling master, rather than an old candidate file.

This fixes a reproduced code defect; **the supplied captures do not establish
that it caused the near-stall**. They logged B2A0 processed MAP instead of the
direct ABC4 SD input. The ADC converter has no 33.77-kPa floor, and an incorrect
sensor offset has not been demonstrated. See [the source audit](MAP_SOURCE_AUDIT.md).
The logged slow-negative fuel correction remains a separate measured lead.

Pressure below 10.48113 kPa and other rejected inputs/calculations still use
the existing 500 g/s fallback. This repair aligns two existing limits;
it does not solve the entire fault-response design or independently validate
the installed sensor's physical low-voltage accuracy. The immediate latched
injector-inhibit [prototype](SD_FAULT_REPAIR_PROTOTYPE.md) is not installed.
No engine response, hardware deadline, flash or ECU connection was tested.

## Artifact and reproduction

- Master SHA-256: `154760a5f2fdadbf6d9221480595f58dc77c6a4eccc492f50899c815aca79e4d`
- Subaru checksum: `0x16F63B0D`; size: 524288 bytes; CALID: `D2WD610H`.
- [Deterministic builder](build_master_patch.py) and [calibration source](master_calibration.py).

```sh
python3 master_patch/build_master_patch.py
python3 tests/verify_master_patch.py
```

The builder starts from canonical stock and declares every calibration write.
The verifier independently checks composition, exact change scope, current
output identity, checksum and exclusion of the dashpot experiment.
[Historical replay support](historical_roms.py) reads the old 10:30 ROM from
pinned Git history, so advancing the master does not change the ROM used to
interpret the 12:36 capture. Raw captures and the user's test BIN are untouched.
