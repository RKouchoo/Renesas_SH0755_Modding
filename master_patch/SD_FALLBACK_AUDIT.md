# SD fallback, filtering and transient-fuel claims — 2026-09-08

**Integrated repair:** [MAP lower-bound repair](MAP_BOUNDARY_REPAIR.md)
aligns the minimum with the unchanged native electrical classifier. It removes
the demonstrated mismatch in the rolling master while retaining the other fault
paths. The original capture replay and saved-image limits below describe the
pre-repair images; they do not establish an on-car trigger or complete cure.

The fixed 500 g/s fallback is a real discontinuity worth revisiting, but it is
not observed in the supplied captures. The strongest measured recovery lead
remains the slow negative load-history correction. The claimed filter
calculation breakdown is not supported by the executed ROM instructions.
No firmware, calibration, BIN or logger changed during this audit.

**Source correction:** the capture channel is E51 / B2A0 processed MAP;
SD reads ABC4. The following execution results use B2A0 as a proxy for the
unlogged SD input, not an exact input replay. The [MAP-source audit](MAP_SOURCE_AUDIT.md)
demonstrates both history processing and diagnostic MAP substitution. The
later logger update exposes the missing sources/flags without a BIN change.

## Fixed 500 g/s fallback: real mechanism, no observed trigger

The emitted wrapper at `7E18C` validates absolute MAP, RPM and IAT snapshots;
it has no rate-of-change gate. The saved images all contain these limits:

| Input | Accepted range |
|---|---|
| MAP | 100–1600 mmHg absolute, about 13.33–213.32 kPa |
| RPM | 0–7500; exact zero returns zero airflow before other input checks |
| IAT | −50 to 150 °C |

Invalid nonzero-RPM inputs, invalid calibration/lookup results and invalid
products load the fixed float 500 from `7DD00`. A separate valid-output cap
also equals 500, at `7DD0C`; the numerical value alone cannot distinguish
those paths. The replay identifies the fixed constant's actual ROM read.

Every row in the five relevant September 8 captures was supplied as a
**processed-MAP proxy fixture** to the saved wrapper and native SD lookup
instructions. The 14:13 capture supplies
committed AVLS. Where AVLS is unlogged, both low- and high-lift surfaces were
checked as conditional fixtures. This totals **7,719 rows / 12,928 native
invocations**, with zero fixed fallbacks and zero normal output caps.

| Capture | Rows | Lowest logged processed MAP, kPa abs | Highest logged airflow, g/s |
|---|---:|---:|---:|
| 12:36 | 1,786 | 20.43 | 38.20 |
| 14:13 | 2,510 | 16.29 | 47.27 |
| 18:01 | 1,112 | 29.64 | 51.43 |
| 18:11 | 1,813 | 33.69 | 18.38 |
| 18:15 | 498 | 22.33 | 52.30 |

The lowest recorded processed MAP is at 248.085 seconds in the 14:13 capture,
at 1,494 RPM. Its numerical difference from the threshold is 2.958 kPa,
but that **does not establish the unlogged ABC4 input's margin**. All recorded
running RPM and IAT values are within the gates; no recorded airflow is
500 g/s. The airflow observation argues against a sustained sampled fallback;
zero fallbacks in the proxy fixtures cannot exclude actual input-gate events.

The boundary test still demonstrates a severe discontinuity. At 1,500 RPM,
25 °C, low lift in the original idle candidate:

- Exactly 100 mmHg: **4.51549 g/s**, valid calculation.
- The next float below 100, 99.99999237 mmHg: **500 g/s**, fixed fallback.
- The next float above 100: **4.51549 g/s**, valid calculation.
- Consecutive 712→100→712→100 mmHg steps at 2,000 RPM remain valid.

Thus a sufficiently low absolute pressure could trigger the fallback even
without a broken sensor; a fast transition alone cannot. These captures do
not establish the lowest pressure possible at higher untested RPM. Nor do
they validate extrapolation of the installed MAP sensor below its published
calibration endpoints; see [the existing MAP calibration notes](CALIBRATION.md).
Blindly widening the gate would not resolve all invalid-input cases.

## Downstream effect of an injected fallback

The retained load path caps raw load at 4 g/rev and, under normal flags,
updates conditioned load by 6% of the remaining difference per call. It does
not immediately pass an unlimited 500 g/s fuel demand to the injector.
This filtering does not make the fallback benign:

| Conditional fixture | Peak conditioned load | B874 range over 100 updates |
|---|---:|---:|
| No fallback | 0.3000 g/rev | 0 |
| One 500 g/s call | 0.5220 g/rev | −0.1765 to +2.6380 |
| Five consecutive 500 g/s calls | 1.2846 g/rev | −0.4287 to +2.5844 |

These execute native load conditioning and transient arithmetic at fixed
1,500 RPM, 45 °C, initial steady load 0.30 g/rev, with one transient update
after each load update. After the injected calls, airflow returns to 7.5 g/s.
The very large positive B874 is a fuel-factor contribution, not a measured
injector pulse or AFR. Other fuel factors, cuts and engine feedback are not
composed in this fixture. It establishes a consequential interaction if the
fault occurs, not that it occurred in the car or inevitably causes a rich
stall. The later negative tail also means negative correction alone cannot
exclude an earlier unsampled positive disturbance.

## Filtering: predictable lag, not demonstrated numerical instability

The old raw MAF conversion calls at `639C` and `66D8`, and the raw MAF
limit/filter update call at `107F8`, are NOPs in all four checked project
images. SD writes synthetic airflow and its three mirrored states. The
retained downstream engine-load filter is a separate operation.

For the normal fixture, its relation is approximately:

`new_conditioned = previous_conditioned + 0.06 × (raw − previous_conditioned)`

All 300 injected-fault/control updates remain finite and between the prior
conditioned value and new raw value. Large deltas do not make this filter
"struggle" or produce an unexplained mathematical result. Actual timing
targets can still change because load changes which table cells are used.
The existing [load recovery replay](../logs/20260908_load_recovery_replay.json)
shows why lag matters as airflow recovers near idle. Increasing this filter's
speed also changes the downstream signed fuel correction; it is not an
independent response-speed adjustment.

## Transient subtraction: strongest measured lead, narrower than the claim

The native `1E7E8` family uses **conditioned engine load and its history**,
not a direct raw-MAF derivative. In the 14:13 capture, at 792 RPM, logged
B874 is −0.5275 and replay gives −0.5334; the fast term is zero and the slow
negative history term accounts for the entire replayed subtraction. Net
pulse is at the 0.600 ms floor. The negative-only gain is `76030`, separate
from the positive branch. The earlier [component audit](TRANSIENT_COMPONENT_AUDIT.md)
contains the native path, gain isolation and fixed-input sensitivity results.

This supports excessive persistent subtraction as a calibration lead. It
does not prove a physical wall-film mass model, missing arithmetic result,
or a single explanation for the entire symptom. At the later 558-RPM minimum
the correction is already positive. Low opening timing and the unexplained
zero-pulse samples in the evening capture also remain distinct observations.

The cited [PCM of NC article](https://www.pcmofnc.com/2012/01/20/speed-density-sd-vs-mass-air-flow-maf/)
is a general comparison of MAF and SD. It does not document this Subaru ROM's
filter or demonstrate the claimed numerical failure. The linked YouTube page
could not be fetched through the browser provider, so its contents have not
been verified here. Conclusions above come from project bytes and captures.

## Reproduction and limits

```sh
python3 master_patch/analyze_sd_fallback.py --output /tmp/d2wd-sd-fallback.json
```

[Full numeric report](../logs/20260908_sd_fallback.json) includes input SHA-256
identities, boundary results, filter fixtures and per-capture counts. The
12:36 capture uses baseline `48d63cf3…`, 14:13 uses `6af0d130…`, and all three
evening captures use the reconstructed first dashpot image `7590b6ce…`.
The later `2f80b8e5…` image has matching wrapper/gates/filter paths but no
corresponding capture in this set.

MAP is the processed B2A0 channel, not the ABC4 input. Samples are rounded
and asynchronous, typically 104 ms apart. Some evening
captures have much longer gaps. The replay does **not** exclude a shorter
MAP excursion, sensor/RAM fault, corrupt calibration or fallback between
samples. It does not reproduce CPU deadlines, interrupt interleaving,
physical fuel delivery or combustion. A latched fallback reason/count would
be needed to close the logger's blind spot; adding that instrumentation
would require a separately checked RAM allocation and logger change.

## Required direction for a fallback repair

**Later offline implementation:** the [SD fault repair prototype](SD_FAULT_REPAIR_PROTOTYPE.md)
now executes an in-memory repair with native boundary, latch, cut/scheduler and
interrupt tests. It removes the fixed-fallback discontinuity for 575 counts
accepted by the existing electrical classifier. It is not integrated firmware
or a flash candidate; physical fault bounds and the immediate latched response
still require resolution. The saved BINs remain unchanged.

The current fallback must not be described as an established safe engine
response. Replacing 500 with another fixed airflow, holding an old airflow
indefinitely, or merely widening the gate does not address the entire fault
path. The intended repair needs distinct normal and fault behaviour:

1. Establish the installed sensor's valid pressure/voltage range. A valid
   low pressure should remain a normal SD calculation even below the first
   VE-axis knot; clamp the lookup position to the table edge while retaining
   actual validated MAP in the air-mass product. The calibration-table domain
   and electrical/physical fault limits serve different purposes.
2. For a true invalid input/calculation, publish an explicit SD fault and use
   a verified fault response. Without a validated backup air model, the
   proposed response is injector inhibition with defined latch/reset rules,
   rather than pretending maximum air is entering the engine. Zero airflow
   alone is not an injector inhibit: downstream minimum pulses and other
   corrections still exist.
3. Record a latched reason and count so a short event survives between logger
   samples. Include these with B874, load, MAP, RPM, final fuel factor, pulse
   and cut reason in a profile within the verified SSM request-size limit.
4. Execute the complete cut-publication/scheduler path under fault, recovery,
   startup, competing cut reasons and interrupt fixtures before exporting a
   candidate. Preserve the stopped-engine zero-airflow path and prove every
   reset/clear cannot cancel another cut source.

The full fault-response specification remains **unintegrated**. The later
prototype allocates state and hooks only in memory. The separate boundary
portion is now in the rolling master; no new RAM state, fault-inhibit hook or
logger change from that prototype has been installed. The
independent low-RPM transient calibration comparison is in
the [component audit](TRANSIENT_COMPONENT_AUDIT.md#narrower-remedy-comparison-reduce-the-low-rpm-negative-multiplier).
