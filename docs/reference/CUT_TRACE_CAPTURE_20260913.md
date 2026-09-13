# Cut trace: normal sampled permissions during repeated loss of acceleration

[Reference home](README.md) · [Source CSV](../../logs/romraiderlog_cuttrace_20260913_143625.csv) · [Calculated evidence](../../logs/20260913_cut_trace_review.json) · [Comparison figure](../../logs/20260913_cut_trace_review.png) · [Reproduce](../../tools/analysis/analyze_20260913_cut_trace.py)

The user confirms repeated hard cuts, described as hitting a brick wall and
feeling as though only one or two cylinders fire while held. The sensation
does not identify individual cylinders. The cut remains unresolved. This
capture narrows the software-permission and task-activation branches; it
does not prove healthy physical outputs or establish a new firmware fix.

The user subsequently confirmed **stock EZ30R coils, wiring and plugs**
("stock stock stock"). No measured plug gap was supplied. Do not reopen an
aftermarket ignition-compatibility question or infer a measured gap from
that confirmation. The user also declined paid dyno testing.

## Capture integrity

There are **1,590 complete finite samples**, 24 channels, over **165.357 s**.
All names, units and ordering match the saved cut-trace profile and complete
definition. Intervals are **100–108 ms**, median **104 ms**, with no long gaps.
The engine is already running at 944 RPM in the first row, so startup is not
captured. Both missed-activation counters start at zero and remain zero.
The final engine-stop sequence is present; key position is not recorded.

CSV SHA-256: `3e62ab07eb7ee184ab43162debd7d97c3f829085399cf87742ca6c8997d85390`.
The offline comparison uses repaired v2
`fabceb54359aca76e6e15835a51aa5cfd008e570dc002e886eaa62a6cb020ce5`,
the image matched by the latest saved 13:28 FastECU verification. This CSV
contains no fresh image identity or ECU readback. The earlier verification
is documented in the [first repaired capture](AVCS_REPAIR_CAPTURE_20260913.md).

## What the new channels show

Select speed above 5 km/h, pedal at least 30%, RPM at least 2,500: **247
samples**. The more restrictive subset with plate at least 80% contains
**125 samples**.

| Signal | Result in all 247 high-demand samples | Meaning and limit |
|---|---|---|
| Spark mask C0DC | 0 | No sampled inhibition from this publisher. |
| Ignition mode C0E1 | 2 | Running mode remains selected. |
| Auxiliary mask C290 | 4032 / `0FC0` | Normal suppression of the secondary six phase slots; the primary six remain enabled. This is not a six-cylinder cut. |
| Synchronization AC16 | 1 | No sampled loss of native synchronization. |
| Timeout AC0C / runtime B52C | 0 / 0 | No sampled timeout/stopped publication or current-cam-fault secondary-spark request. |
| Missed task5 / task6 activations | 0 / 0 | No recorded failed activations, throughout all 1,590 samples. This is not a proof of every scheduler deadline. |
| IAM / FBKC / FLKC | 1 / 0 / 0 | No sampled knock retard or IAM reduction. |
| Added lean-cut state | 0 | The added protection does not reach its cut state. |
| Injector mask B744 | 246 zero; one `002A` | All **125** samples with plate at least 80% have zero injector inhibition. |

The injector exception is **118.333 s**, CSV line 1139: pedal has risen to
100%, but plate still reads 9.02%, RPM 2,672, and pulse 0.77 ms. The next
sample, 104 ms later, has plate 99.22%, B744=0 and pulse 6.40 ms. This is a
tip-in/overrun handover, not the sustained open-throttle plateau. Because
channels are not atomic, it must not be interpreted as a precisely timed
104-ms causal delay.

The channels also respond at the final engine stop: C0DC first becomes FFFF
at 162.133 s, mode becomes 1 at 162.551 s and 0 at 163.070 s. At 163.070 s,
AC16 becomes 0, AC0C becomes 1 and B52C becomes 128. These are separate from
the loaded events and show that the new state channels are not all frozen.

## AFR and the event sequence

The user correctly challenged treating the lean excursion as proof of fuel
starvation. The log does not establish that cause and does not justify
another fuel reduction. At the following points, pedal is 97.65%, plate is
100%, speed is 57 km/h, B744 and C0DC are zero, and ignition mode remains 2:

| Seconds / CSV line | RPM | AFR | Published injector duration | Published timing |
|---|---:|---:|---:|---:|
| 110.215 / 1061 | 3,152 | 11.56 | 10.75 ms | 15.5° |
| 110.319 / 1062 | 3,249 | 11.57 | 11.01 ms | 15.5° |
| 110.424 / 1063 | 3,016 | 11.57 | 11.52 ms | 15.0° |
| 110.632 / 1065 | 3,139 | 15.39 | 10.24 ms | 15.5° |
| 110.736 / 1066 | 3,155 | 16.59 | 9.73 ms | 16.0° |
| 110.840 / 1067 | 3,262 | 16.62 | 9.47 ms | 16.5° |

The first sharp sampled RPM drop happens while AFR remains rich and the
published pulse **increases**. The lean reading follows. Neither the exhaust
measurement nor the non-atomic logger establishes exact combustion timing,
but there is no evidence here of a preceding withdrawal of the published
fuel command. AFR alone cannot certify delivery to all six cylinders or
exclude every fueling fault. No fueling change was made.

There are 99 zero-AFR samples elsewhere in the capture. Zero is the patch's
rejected-input sentinel, not measured AFR=0. These values are omitted from
valid-AFR statistics and plotted as missing. The quoted event samples are
nonzero and are not based on those sentinels.

## AVLS correlation and checks against a table-switch explanation

Three loaded transitions occur at **57.211**, **104.899** and **110.215 s**.
At each logged RPM/MAP pair, the installed wrapper was executed twice,
changing only committed mode 1 to 3. The comparison was repeated with IAT
fixtures 10, 30 and 60 °C, because IAT is not logged here. The common IAT
factor cancels in the ratio apart from float rounding.

| Transition | Logged RPM / absolute MAP | Mode-only airflow change, 30 °C fixture |
|---|---|---:|
| 57.211 s | 3,204 / 112.953 kPa | −0.0738% |
| 104.899 s | 3,368 / 109.140 kPa | +0.0536% |
| 110.215 s | 3,152 / 113.905 kPa | 0.0000% |

These are emitted-wrapper opcode executions with image-sourced descriptors
and modeled lookup interpolation. They isolate VE selection, not the full
native fuel calculation or physical engine. They do not reveal a large
airflow discontinuity caused by choosing the other VE table.

The later **119.896–121.148 s** plateau is at **3,600–3,800 RPM**, with high
mode already selected and speed beginning and ending at 48 km/h. At
120.626 s, both pedal and plate are 100%, AFR 12.54, pulse 9.22 ms and timing
17°. This event is not confined to the instant of the 3,200-RPM transition.
The **63.148–64.085 s** full-throttle low-mode segment is also weak: RPM
2,483–2,615 with speed 45–46 km/h. Road gradient and torque are not measured,
so that segment is context, not an independent diagnosis of the same cut.

Battery voltage differs between events: 12.24–12.48 V in the 104.899-s
window, but 13.84–14.16 V in the 57.211-s and 119.896-s windows. A low
sampled ECU voltage is not common to every cut and cannot alone explain
them. Coil supply voltage/current are not logged. No boost value is inferred
from absolute MAP without simultaneous barometric pressure.

The committed AVLS byte precedes phased bank actuation. MCP reconfirms
`405B2` copies requested mode to CD86 and `405CC` separately performs bank
phase gates and output calls. Hydraulic response and both bank outputs are
absent from this profile. Neither AVLS nor the earlier Right-cam discrepancy
is established as the cause.

## What remains and the next discriminating check

This capture argues against **sustained sampled** software cut permissions,
sync loss and failed task5/task6 activation as the explanation. It does not
clear the ECU's downstream per-cylinder timing/dwell, phase scheduling,
timer outputs or physical ignition. The existing
[coil-device tests](../../tests/test_ignition_device_process_flow.py) execute
those paths under explicit phase/timer fixtures; they are not a recording of
the running engine. Another pass of the same fixtures cannot supply the
missing physical output evidence.

A possible physical ignition check compares the ECU trigger with coil charging
and the resulting spark, before and at the fault, across both banks. This
distinguishes a missing/incorrect trigger from failure after a trigger is
present. Pico's primary guides describe the relevant comparisons:
[COP trigger versus primary current](https://www.picoauto.com/library/automotive-guided-tests/ignition/coil-on-plug/AGT-162-trigger-vs-primary-current/)
and [COP trigger versus secondary ignition](https://www.picoauto.com/library/automotive-guided-tests/ignition/coil-on-plug/AGT-137-trigger-vs-secondary/).
This is a proposed measurement, not a finding that any coil is defective.
The user has declined a paid dyno session. A dyno is **not a requirement**
for continuing the investigation, and no paid test or equipment purchase is
assumed. Any physical reproduction would need controlled conditions; further
prolonged road holds against the misfire are unnecessary for this review.

No BIN, runtime source, calibration, logger selection or input CSV was
changed. The full audit remains paused/incomplete. MCP accepted updated
comments at `2A262` and `D156`, both independently read back and preserved
in the reapplication script. The raw reads and annotations are in
[the bounded follow-up evidence](evidence/cut_trace_capture_20260913.json).
The cumulative 355-group test report was not rerun or incremented.

## Offline ignition follow-up after the cost constraint

The [reproducible follow-up](../../tools/analysis/analyze_20260913_ignition_followup.py)
and [calculated evidence](../../logs/20260913_ignition_followup_review.json)
close two narrower questions without changing the ROM or asking for another
capture. They do not replace the missing physical evidence or establish a cure.

1. **Requested dwell at the recorded voltages.** The earlier dwell test
   modeled the lookup and used 14 V. This follow-up executes native
   `9FEC -> 21B0 -> 27D0/26B0`, including the lookup instructions, at all
   125 high-demand/open-plate RPM and battery pairs. Requested dwell remains
   **600–840 timer counts**. At 3,152 RPM / 12.72 V it is 760 counts; at
   3,016 RPM / 12.48 V it is 795; at 3,800 RPM / 14.08 V it is 600.
   There is no zero-dwell result at these held inputs. This does not measure
   actual coil supply, charging time or spark energy.
2. **Late-start timer programming.** For each point, six native coil
   enqueue/device paths were exercised at counter snapshots 1,000 and
   65,500, supplying the native-derived dwell. All **1,500** cases program
   a nonzero down-counter and compare separation at least half the requested
   dwell. The deliberately late angle is ten degrees ahead of the snapshot.
   These are held-point device fixtures, not live phase-cycle or interrupt
   replay, and a nonzero compare separation does not prove physical firing.
3. **What P10 measures.** The installed callback pointer for parameter
   `0011` is `31684`; its literal at `3174E` selects **C0EC only**, the first
   final timing array element. Native callback execution with distinct
   angles confirms that changing the other five elements does not change
   P10. It is not an average or a six-cylinder timing trace.
4. **Ordinary per-cylinder correction above 2,000 RPM.** Producer `3D824`
   reads B544 and clears all six **CCC8–CCDC** offsets when RPM is **at least
   2,000**, even with enable CCE0/40 forced on. Below 2,000, that forced enable
   copies six records at `82EC+8*n`, clamped to stock **−5..+5°**. Native
   execution with distinct prior 99° offsets verifies clearing at the exact
   boundary and through 3,800 RPM. Installed task pointer `11E20` still calls
   it before `11E30 -> 279CC`. Thus no new retained-offset cut mechanism was
   found; the vehicle's actual offsets and producer timing remain unlogged.

The affected code, tables, callback and task pointers remain stock in repaired
v2. Three Ghidra comments (`9FEC`, `3D824`, `4F1C4`) were accepted, independently
read back and added to the reapplication script. See
[MCP evidence](evidence/ignition_followup_20260913.json). These are bounded
instruction-analysis cases, not new registered regression groups; the
historical 355-group cumulative report remains unchanged. The full audit
remains incomplete, and no BIN or calibration change is justified by these
results alone.

## Injector refresh requests and the separate cranking flag

The [native follow-up](../../tools/analysis/analyze_20260913_crank_refresh_followup.py)
connects the documented crank-state producer to another injector-scheduler
consumer. [Calculated results](../../logs/20260913_crank_refresh_followup_review.json)
retain all 125 high-demand/open-plate RPM/ECT pairs. Their coolant range is
**58–62 °C**, including 61 °C at the rich-at-onset event.

Native task `11958` calls `19F9C`, `1C920`, `2716C`, then `26E64` in that
relative order, with other work between them. The last entry tests
**B748/80** through `1D228`. If set, `2705E` writes 1 to offset `+06` in
all six 40-byte injector records: **BFBE + 28h*n**, n=0..5.
**Ignition mode C0E1=2 is independent of this flag.** A deliberately cold
20 °C fixture with insufficient injector event count demonstrates running
ignition mode and these six request marks simultaneously.

Tracing the consumer corrects the initial description of these marks as
scheduler resets. They are **pulse-duration refresh requests**. In enabled
record stage 1, `263EE` at `266EE` reads the flag, calls `26E9A` to refresh
the duration, then calls the mode-specific callback. Running descriptor
`4B680` selects `26C50`, which reaches `90F8` for a pending pulse.
A six-channel positive control changes the pending effective counts from
4,000–6,000 to 8,000–10,000, clears the request flags and makes **no
cancellation calls**. With the flags clear, the prior counts remain.
The native update/device instructions execute; the inherited bounded
integer-division model remains, and physical delivery is not simulated.

At every recorded RPM/ECT pair, the native `1C972` event-delay lookup
returns zero. Its RPM thresholds remain 500/300. Even with both start flags
and the low-RPM hysteresis forced on beforehand, and event count `C0AC=0`,
the next phase divisible by four clears B748/80 and /40 **before** the
later `26E64` call. Starting in each of the four phase classes produces
0, 3, 2 or 1 refresh-marking calls respectively, then no further requests
from this gate in the supplied sequence: **500 fixtures / 4,000 phase calls**.
The 20 °C positive control retains the flag at event counts 0 and 9, and
releases at 10; ignition mode is 2 throughout.

No new cut mechanism is established. B748, event counts, per-phase RAM
values, interruption timing and actual delivered pulses remain unlogged.
The script executes selected entries in installed relative order, plus a
separate scheduler/device consumer control; it does not execute the full
`11958` payload. The phase fixtures begin with the logged ignition mode 2;
a startup mode-0 fixture would hold that mode at nonzero phase modulo four
until the next native mode update. Neither fixture reconstructs startup.

MCP annotations at `26E64`, `2705E` and `266EE` were independently read
back and copied into the Ghidra reapplication script. The
[MCP evidence](evidence/crank_refresh_followup_20260913.json) preserves the
native reads and final annotations. No ROM or calibration changed. The
355-group historical total is unchanged; this bounded analysis is not a
new registered regression suite.

## Individual-cylinder fuel terms and active pulse updates

The [next native follow-up](../../tools/analysis/analyze_20260913_cylinder_fuel_followup.py)
traces individual-cylinder inputs that the single pulse-width channel cannot
fully expose. [Calculated results](../../logs/20260913_cylinder_fuel_followup_review.json)
preserve the explicit fixtures. This extends the producer-to-device connection;
it does not reconstruct the car's six pulse widths or establish a cure.

| Native term | Installed behavior and verification |
|---|---|
| Additions `CC88..CC9C` | `3CBC0` clears all six at RPM **>=2,000**, even with enable `CCA0/40` forced on. Below that threshold, six protected records at `82BC+8*n` are scaled and clamped to **−0.03..+0.03**. These are fuel-factor additions, separate from the previously traced spark offsets. |
| Multipliers `BECC..BEE0` | `23864` uses selector **75E2B=0** in the saved image. It writes six **1.0** values and clears `BEB8/BEBC/BEC0`, including from deliberately nonneutral prior values. Cranking and accounting-state fixtures do not change that result. This does not remove the separate `B874` transient term. |
| Pattern multipliers `D050..D064` | Native initialization `48D12 ->48E32` sets all six to unity. The five identified publishing branches use only **1, 1.05, 0.90, 1.025, 0.95**. Their common parent can also hold the previous pattern. Actual qualification and vehicle pattern are not reconstructed. |

The running task calls `26E80` through `11E54` at `11CF4`, after
`1DD04` at `11B96` and `1CA38` at `11BA8`. Unlike the crank-side `26E64`
gate, this entry marks all six duration-refresh requests when **B748/80 is
clear**. Thus refresh requests are also part of normal running operation.

The connected fixture executes the native modifiers, composer, six-duration
selector, running refresh and `263EE` scheduler through `90F8` device
updates. The unlogged common and bank inputs are held neutral, with an
explicit **10,000 µs effective base** and 3,152 RPM. Across all five pattern
publishers, targets remain approximately **9,000–10,500 µs**. All six
pending requests update without cancellation, and all six early active
requests retain nonzero down-counters. The fifteen cases cover the five
patterns with pending, early active and near-complete active states.

In the near-complete control, a prior 12,000 µs effective pulse has only
100 timer counts left. Its supplied elapsed gross time already exceeds
every revised target; the native shortening operation correctly finishes
that pulse. A positive logged duration therefore does not mean a timer
must be active at that instant. This is not evidence of premature termination
or sustained lost delivery. At the quoted 110.424-s onset, logged pulse
width **increases**, so a decrease in that logged target does not explain
the first sharp RPM drop.

All CPU callees in the connected execution are native, including fixed-point
division `21CC`; eight independent quotient controls agree with integer
arithmetic. The local interpreter needed XOR-register and SHAL support to
enter that helper. Their flag behavior follows the
[Renesas software manual, sections 5.1.3 and 6.1.55](https://www.renesas.com/en/document/mah/sh-1sh-2sh-dsp-software-manual).
Those additions are analysis support, not ECU modifications. Device setup
uses the existing explicit fixture; the final native chain does not use its
modeled division helper.

No hidden cylinder-cut command was identified in these branches. Bank
histories, actual per-cylinder values, complete task interleavings and
electrical outputs remain separate gaps. No ROM, calibration or logger
profile changed. Four MCP annotations were independently read back and
preserved in the reapplication script; see
[the native evidence](evidence/cylinder_fuel_followup_20260913.json).
The historical 355-group regression total remains unchanged.

## Patch workload compared with stock

The user directs the investigation toward a patch interaction. The existing
checks do not clear the patch or establish an external cause. The
[paired workload comparison](DENSO_SCALING_AND_FPU_MATH.md#paired-stockv2-task-comparison-september-13)
now executes the full airflow task on stock and v2 over 72 input combinations.
Restoring only the two SD call pointers in an in-memory control reproduces
stock traces. V2 adds 382–494 executed instructions, without raising the
supplied zero interrupt mask. Across six native-initialized WB cases, the
mask-9 section uses fewer instructions than stock.

These are workload differences, not elapsed-time or deadline measurements.
No case loops or hangs, but complete task occupancy, interrupts and total
stack use remain open. No new causal fix is established or ROM generated.
