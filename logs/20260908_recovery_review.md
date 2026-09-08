# September 8, 14:13 — candidate idle and rev-blip review

The candidate improves settled low-RPM fueling, but **rev recovery is not
resolved**. The user confirms it stayed running while nearly stalling, and
the final shutdown was intentional key-off. No new BIN was produced from
this capture.

## Capture identity and data quality

- Source: `romraiderlog_idle_diagnostic2_20260908_141335.csv`, SHA-256
  `7b5c3fda47a64d97ee0761333bff9b1b53516d4239565681049159b2bef6d855`.
- 2,510 complete numeric rows, 19 channels, 260.974 seconds; intervals
  101/104/107 ms minimum/median/maximum. CL/OL state stays 7 and committed
  lift mode stays 1 (low lift).
- The final 16 ECU flash-block CRCs at 14:13:11--14:13:15 independently match
  the `6af0d130...` candidate, including the changed final block
  `0xAC3F8F09`. The 10:30 baseline's final block is `0xEB8FF50D`. This is
  verification of recorded flash evidence, not a new ECU read.
- RomRaider wrote an unquoted comma inside `AVLS mode (1 low, 3 high)`,
  making the header appear to have 21 fields while rows have 20. The analysis
  repairs that exact label **in memory only**, then verifies every row and
  column. The original CSV is unchanged. This was a header-formatting defect,
  not another missing-channel capture.

## Settled fueling

Medians from windows clear of opening/closing transients:

| Seconds | RPM | AFR | MAP, kPa | Coolant, C | Net pulse, ms | B874 | B7DC factor |
|---|---:|---:|---:|---:|---:|---:|---:|
| 100--130 | 1262 | 14.61 | 41.95 | 36 | 2.3733 | 0 | 1.01 |
| 140--148 | 1230 | 14.61 | 41.08 | 39 | 2.3040 | 0 | 1.01 |
| 154--159 | 996 | 14.59 | 41.79 | 40 | 2.3158 | -0.0149 | 1.00 |
| 200--210 | 1003 | 14.13 | 41.00 | 43 | 2.2663 | 0 | 1.01 |
| 221--234 | 976 | 14.13 | 40.68 | 45 | 2.2465 | 0 | 1.01 |
| 253--256 | 966 | 14.12 | 40.68 | 47 | 2.2492 | 0 | 1.01 |

The previous capture recovered near 1069 RPM / 16.61 AFR. The sustained lean
recovery is absent from these settled windows. That supports the direction
of the VE repair; different temperatures and throttle events prevent treating
this as an exact controlled calibration comparison. Neither run reached full
operating temperature.

## Timing drop: principally during opening, not the RPM trough

The sharp drop occurs as throttle and modeled load rise. For example:

| Seconds | RPM | Load, g/rev | Throttle, % | Logged timing | D-map lookup with base floor |
|---|---:|---:|---:|---:|---:|
| 187.864 | 1345 | 1.11 | 88.24 | 0.5 degrees | 0.37 degrees |
| 187.969 | 1532 | 1.35 | 85.10 | 0.0 degrees | 0.04 degrees |
| 215.531 | 1258 | 1.06 | 31.37 | 1.5 degrees | 0.65 degrees |
| 215.635 | 1419 | 1.26 | 31.76 | 0.0 degrees | 0.04 degrees |
| 246.729 | 1582 | 0.91 | 12.55 | 12.5 degrees | 12.45 degrees |
| 246.834 | 1650 | 0.94 | 12.55 | 12.0 degrees | 12.21 degrees |

The last column is **a conditional lookup**, not logged base timing. It
assumes the normal timing-RPM input follows recorded RPM, AVCS tracking blend
`C17C = 0` (D endpoint), and off-idle base selection. Actual cam tracking,
`C134`, `C150`, and knock corrections were not logged. The numerical agreement
and retained code give a strong base-map explanation; they do not prove every
final correction or establish that this timing calibration is suitable.

Native path checked:

- `28418` looks up the timing surfaces using conditioned load `B438` and
  timing RPM `C178`; `28304` normally copies RPM to C178, with a separate
  transition-state alternative. A/D blend follows AVCS-tracking factor C17C.
- At `28776..2878A`, the selected base timing is bounded below by coolant
  lookup `5FC18`, using native max helper `24A0`. Below 50 C that lookup is
  **0.0390625 degrees**, explaining a near-zero rather than negative base
  value in this capture.
- `27DE8` sets idle/base blend `C134` using the debounced idle flag, RPM and
  speed. Native fixtures show that at stationary low RPM a blend already at
  either endpoint switches directly to 0/1 with the idle flag. Intermediate
  blends move by 0.008 per call. The earlier general description of a slow
  ramp on every stationary transition was incomplete.
- `28166` chooses/composes idle target C138 and base C150 into C130. Five new
  native execution groups cover the stationary flag transitions, partial
  blend step, low base versus idle target, return to idle, and a deliberately
  incorrect gate. Upstream base producers are explicit fixture boundaries.
- `279CC` subsequently adds the other corrections and publishes final
  cylinder timing. The rotational-idle enable byte remains zero, and all
  timing code/calibration is unchanged between baseline and candidate.

At the 215-second blip, timing returns to 15 degrees by 215.842 s and stays
there through the 673-RPM trough at 217.195 s. At the deepest trough,
**249.124 s / 558 RPM, timing is 15 degrees**. Therefore persistent low spark
through the trough is not the observed failure pattern. Do not blindly add
timing to address the near-stall, or classify the drop as measured knock
retard from this channel alone.

There is an overlapping re-opening at 236.744 s while RPM is already 607;
timing is 5.5 degrees there. Thus this is not a claim that timing is always
15 degrees at low RPM, or that low opening timing has no effect on recovery.

## Remaining recovery problem

E511 now directly records the signed transient subtraction previously inferred
from native replay. At 192.959 s, B874 is **-0.6097**, B7DC is **0.40**, load is
0.54 g/rev, and net pulse is **0.7630 ms**. This is a large programmed fuel
reduction after closure. Five samples during the late 247-second recovery
reach the stock 0.6000-ms composed-pulse floor.

E123/B7DC already includes B874 and the other summed fuel terms. Multiplying
it by `1+B874` again would double-count the correction. The simple check
`max(0.6, load * 3.2666667 * B7DC)` agrees with logged net pulse to a median
absolute error of 0.0098 ms over 145--256 s. This uses rounded, non-atomic
logger values and does not measure physical fuel delivery.

The minimum RPM occurs after pressure has recovered and B874 has switched
positive: at 249.124 s, MAP is 44.97 kPa, B874 is +0.5111, B7DC is 1.52,
net pulse is 2.3405 ms, and AFR reads 13.60. The preceding closure reached
16.29 kPa. The airflow channel then implies about **0.753 g/rev**, while
conditioned load is only **0.47 g/rev**. This is consistent with the retained
6%-per-update load filter lagging recovering airflow, with sampling alignment
also contributing. It is not a measured physical-airflow deficit.

Twelve SD-wrapper opcode replays support this distinction. At the
deepest trough, the wrapper gives 7.165 g/s from the recorded inputs versus
7.00 g/s logged, corresponding to about 0.770 raw g/rev versus 0.47 conditioned.
Rapid opening samples differ more, consistent with the unknown within-frame
epochs; replayed lookup helpers are mathematical models. Positive B874 already
partly offsets the lag at the trough, so the load difference must not be called
an equivalent percentage of missing fuel. Changing the filter alone would
also change the transient correction it drives.

The useful remaining investigation is the interaction of throttle/idle-air
catch, conditioned-load recovery and signed transient fuel compensation.
The log does not justify identifying the entire near-stall as a continuing
lean event, globally removing transient correction, or making another broad
VE increase. There are also brief opening lean indications; the two invalid
AFR samples in the recovery window coincide with raw input above 4.5 V.
Exhaust transport, sensor response and sample timing prevent point-by-point
AFR attribution to simultaneous injector commands.

No additional rev trial is needed to establish that recovery remains faulty.
The current candidate is retained as a diagnostic reference, not promoted to
a finished calibration. Neither BIN was changed by this review.

## Logger repair and reproducibility

The E503 and E504 units now use semicolons, preventing the discovered CSV
column split. Addresses, conversions, selections and the 43-byte-address
budget are unchanged. All three profiles were regenerated; reload the updated
master logger definition and profile together for a future capture. The source
of the issue is RomRaider's `FileUpdateHandlerImpl.Line.headers()`, which
joins names/units without CSV escaping; no further JAR change was needed.
E511's display minimum is widened to -1.0 so its gauge covers the negative
values seen in this run; the raw conversion and recorded samples are unchanged.

Logger SHA-256 at this header-repair stage:
`df6179c00a01dcf06a0f4be33e5c03efe7192359589b69627695dc1ec2097257`.
The new header regression fails the old recovery units and passes the repaired
ones. Real RomRaider queue/A8 construction still retains 19 channels within
43 addresses / 136 request bytes. The full master audit passes, including
the five added idle-timing execution groups. This is offline code/format
validation, not engine calibration approval.

```sh
python3 tools/analysis/analyze_20260908_recovery.py
python3 master_patch/test_idle_timing_execution.py
python3 master_patch/verify_master_patch.py
```

Numerical results: [20260908_recovery_review.json](20260908_recovery_review.json).
Plot: [20260908_recovery_review.png](20260908_recovery_review.png).
The plot can be regenerated with `--plot` when matplotlib is installed.

The subsequent [load/idle-air follow-up](../docs/archive/master_patch/IDLE_AIR_RECOVERY_AUDIT.md)
replays the stock load filter and B874 together, retains this BIN, and supplies
a new focused request-channel profile for the next capture. Its logger hash
supersedes the header-repair-stage hash above.
