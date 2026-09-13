# First repaired-v2 capture: loaded cut persists

[Reference home](README.md) · [Source CSV](../../logs/romraiderlog_AVCSREPAIR1_20260913_132958.csv) · [Calculated evidence](../../logs/20260913_avcs_repair_review.json) · [Reproduce analysis](../../tools/analysis/analyze_20260913_avcs_repair.py)

**The user confirms that the over-3,000 RPM cut remains. Restoring AVCS did
not cure it.** The cam discrepancy below is a separate observation, not an
established explanation of the cut. No further firmware or calibration change
is justified by this review alone.

## Capture and image identity

The capture contains 7,697 samples over 809.843 seconds. All 20 selected
channels are present and numeric. The usual interval is 104 ms; the only gap
over 200 ms is 60.123–69.527 s, during stationary warm-up. Driving starts at
677.667 s, reaches 63 km/h and 3,331 RPM, with coolant 64–69 °C.

FastECU's post-flash verification completed at **13:28:58.243**. Recomputing
its custom CRC against every one of the 16 verified ECU blocks matches the
rolling repaired v2, SHA-256
`fabceb54359aca76e6e15835a51aa5cfd008e570dc002e886eaa62a6cb020ce5`.
The CSV SHA-256 is
`190ede240179e3560e12f7cafe7fffd1f9d88d872648504d58748f6c4d18918b`.
The evidence preserves the block CRCs and source syslog identity.

User observations: test connectors disconnected, no reported DTCs, cruise
light flashing, and the same loaded cut still present. No raw DTC response
is included in this capture.

## What occurs during the cut

There are **268 samples** with speed above 5 km/h, pedal at least 30% and
RPM 2,500–3,500. All have injector-inhibit word **`B744=0000`**, IAM **1.0**,
and zero feedback/fine knock correction. The narrower 2,800–3,500 RPM group
has 109 samples with the same results. The added lean guard reaches delay
state 1 once, but never reaches monitor state 2 or cut state 3 anywhere.

A sustained high-throttle event is particularly useful:

| Seconds | RPM | Pedal | Throttle | AFR | P21 pulse | Timing | B744 |
|---|---:|---:|---:|---:|---:|---:|---|
| 763.640 | 3,132 | 95.29% | 100% | 11.56 | 11.52 ms | 14.5° | `0000` |
| 764.472 | 3,110 | 94.12% | 100% | 16.57 | 9.47 ms | 16.0° | `0000` |
| 764.576 | 3,152 | 94.12% | 100% | 16.60 | 9.22 ms | 16.5° | `0000` |

Speed is 56 km/h at all three points. This is not a uniformly rich event.
The AFR excursion alone does not distinguish insufficient fuel delivery from
failed combustion. P21 and P10 are ECU publications, not electrical pulse or
spark measurements.

The mask channel does record nonzero events: mostly closed-pedal deceleration,
then `FFFF` at final shutdown. One tip-in at 780.407 s retains `002A` with
45.88% pedal and 2,019 RPM; it is zero 105 ms later. That transition must not
be reported as a total absence of cuts, but it is outside the sustained
high-demand event above. IAM is zero during stationary warm-up from
2.910–362.858 s, then 1.0 throughout driving.

**These samples argue against sustained B744-based inhibition during the
loaded event. They cannot exclude short events between samples, a separate
spark inhibit, synchronization loss or dropped output scheduling.**

## AVCS observation and its limits

The saved definition maps bank **0 to Right**, bank **1 to Left**. The CSV
sorts Left before Right, so column order must not be used as bank order.

| Software bank / saved label | Actual-angle publication | Current publication | Normal-output publication |
|---|---|---|---|
| 0 / Right | P48, `C8C8` | P52, `B098` | E528, `C91C` |
| 1 / Left | P49, `C8CC` | P53, `B09C` | E529, `C920` |

At 764.472 s, Right reports **0°**, **672 mA**, **47.81%** normal duty;
Left reports **17°**, **576 mA**, **40.17%**. Right is zero in every one of
the 268 selected high-demand samples. Left reaches 28° elsewhere in the
capture. Both current and normal-output channels now respond, unlike the
removed publication reproduced in the pre-repair ROM.

This does not prove a stuck physical solenoid. Native `34304` publishes
`max(0, corrected capture - protected learned offset)`, before SSM's one-degree
quantization. For Right, the relevant raw observation is `B0B0`, corrected
observation `C8B0`, and learned offset `8264`. These values, target angle and
capture validity are unlogged. Existing native tests produce distinct nonzero
angles for both banks, and the callbacks read distinct verified addresses.

Both normal-output duties also drop near 7% at 732.095 s despite high pedal,
followed by loss of the Left reported advance. Later current can exceed what
the normal publication suggests. Native `DF00/E174` supports temporary output
overrides; the profile does not capture those states. This withdrawal is
another bounded follow-up, not proof of why the later cut persists while
both normal commands remain active.

## Flashing cruise and no reported DTCs

There are **42 zero-AFR sentinels while moving**. In the installed WB code,
zero denotes rejected input, not measured AFR. The configured 0.5–4.5 V window
rejects values outside the project's 11–19 AFR span, including possible valid
sensor extremes. Raw ADC is absent, so the side of the rejection is unknown.

The previously executed native path is
`WB rejection -> 64FD0/6500C -> 44B14 -> CEC4/80 -> 37B32 -> CAA8/40`.
It revokes cruise permission independently of the disabled O2 DTC enables.
Under the documented ignition/permission fixture, `3B760` subsequently toggles
an output. This is a concrete possible explanation for a flashing cruise
light with an empty scan. This capture does not record the intermediate flags
or establish the physical lamp wiring, so the lamp's cause is not proven.
See [the full status trace](PATCH_PROCESS_FLOW.md#wb-status-through-native-fault-summaries-and-output-state).

## Cut-focused follow-up through MCP

The follow-up revisited the actual sources beyond B744:

- `27090` independently publishes spark mask **C0DC** from CD50/80,
  CE28/01 and the six configured cylinder bits. `2A262` combines it with
  **C0E1** running mode and **C290** auxiliary masking. None is logged here.
- Security-source publishers `4162C` (fuel) and `41698` (spark) have the same
  `B289/80 && (8546==1 || CE54/06)` qualifiers. Both native task pointers
  (`11420`, `10DF4`) remain installed. Their existing tests do not establish
  the source state or relative task timing in this capture.
- The additional mode writer `27330`, still called through `117E4`, can reset
  **C0E1=0** when **B52C/80** is set. `1A16E` publishes that stopped/timeout
  flag from **AC0C**; `19F9C` clears it on an engine event. `2716C` is the
  separate phase-task running-mode update. These code/data ranges are stock.
- Existing timeout/synchronization tests already establish cancellation of
  pending injector and coil requests without relying on B744. Existing phase
  tests also establish loss of activation when the queue is full. They supply
  those conditions deliberately; this CSV does not identify them on the car.

The next cut investigation therefore needs to establish the actual spark,
synchronization and scheduler state during the event, or a connected patch
defect that produces it. A forced offline inhibit fixture, another VE change,
or the Right-cam discrepancy alone is insufficient. No new causal defect was
found in this bounded follow-up. The full dependency audit remains incomplete.

MCP reads and three accepted annotations are saved in
[the follow-up evidence](evidence/avcs_capture_followup_20260913.json).
The CSV, both rolling ROMs and logger profiles remain unchanged. The existing
355-group test report is historical and was not rerun or incremented here.
