# September 8 — load replay and idle-air investigation

**MAP-source correction:** E51 in these captures reads processed B2A0, while
SD reads ABC4. Earlier SD predictions using logged MAP are conditional proxy
calculations. This does not change the directly logged load/B874 evidence.
See the [native MAP and barometric audit](MAP_SOURCE_AUDIT.md) and its new
profile for distinguishing the sources and diagnostic substitutions.

**Evening follow-up:** the [18:01/18:11/18:15 review](../logs/20260908_dashpot_review.md)
adds opening timing and separate throttle-tip-in execution. A retained pressure
multiplier can suppress tip-in fuel near atmospheric MAP; its actual short
trigger window is unlogged. The user's reused dashpot filename was edited
again and flashed at 18:18, after all three captures. Both identities are
preserved in the report. No new engine repair is established.

The proposed repeat rev test is withdrawn after the user correctly points
out that the unchanged candidate is expected to nearly stall again. Leave
the car off; continue the stock idle-air/patch interaction trace offline.
The new profile is prepared for a later diagnostic decision, not a request
to reproduce the failure now. Both BINs and the original CSV remain unchanged.

## What the offline replay establishes

`test_load_conditioning_execution.py` executes the actual `1753A..1770A`
load-conditioning body and native scalar helpers. The earlier airflow
producer/caller frame are explicit fixtures; table interpolation is a
mathematical boundary. Four test groups cover rising/falling 6% response,
raw-load saturation and zero RPM, the alternate latched flag, and an in-memory
faster-filter negative control. All are integrated into the master verifier.

On the normal running route, `B428 = min(airflow * 60 / RPM, 4)` feeds the
6%-per-update filter at `73968`, publishing `B42C`. Descriptor `5EB6C` is
uniform 1.0, and the later normal-branch filter constants are all 1.0, so
`B438` follows `B42C`. The upstream `B444` bit-0x20 branch is not a viable
explanation for these low-RPM events: its entry rejects coolant below 160 C
and its release clears the bit below 10000 RPM (`173AA..173B2`,
`174A0..174D2`). This branch is tested as a fixture, not reconstructed state.

`11AD0` dispatches load task `172A4` via `11D20`, before transient task
`1E7E8` via `11D70`. The previously traced six crank-slot activations per
720-degree cycle give the usual interval `20/RPM` seconds. The replay does
not measure missed task activations or initial crank phase.

`replay_20260908_load_recovery.py` interpolates the existing 14:13 capture,
warms the model from 130 seconds and evaluates 145--256 seconds, excluding
the user's intentional shutdown. The source hashes are pinned. Running
the recorded load through native B874 gives median/mean absolute errors of
0.0020/0.0122 in the additive factor. Individual blip-window mean errors are
0.0175--0.0258; the whole-run median also includes settled samples.

The coupled native airflow-to-load-to-B874 calculation at stock alpha gives
median load error 0.0037 g/rev, mean 0.0092 g/rev, and median net-pulse error
0.0101 ms. Rapid samples differ more: at 215.635 s the model gives 1.132
g/rev versus 1.26 logged. These are rounded, non-atomic 104-ms samples, not a
synchronized record of every fuel-task input. Nevertheless, the calculation
supports retained stock filtering/transient behavior, rather than an unexplained
arithmetic failure in those paths.

## Why this replay does not justify a filter change

Two alternative constants exist **only in the replay's memory**. Each variant
uses the same recorded airflow/RPM trajectory and holds logged
`B7DC - B874` fixed. It does not recalculate changed primary targets or spark,
fuel-film transport, actual airflow or engine response. It is sensitivity
analysis, not a forecast of AFR or proof a flash would cure the dip.

| Alpha per update | Modeled minimum B874 | Modeled maximum B874 | Modeled net pulse at the recorded 558-RPM point |
|---|---:|---:|---:|
| 0.06, current | -0.5563 | +0.4868 | 2.3203 ms |
| 0.20 | -0.6546 | +1.1606 | 3.3774 ms |
| 1.00 | -0.7711 | +1.4107 | 3.4591 ms |

The measured pulse at that point is 2.3405 ms, with B874 +0.5111 and AFR
13.60. More calculated fuel at the trough does not establish that missing
fuel caused it. Faster response also produces larger corrections elsewhere,
and the locations of their extrema change. Do not interpret this as a
uniform improvement or use it to remove the stock transient routine globally.

Full calculated samples and boundaries:
[20260908_load_recovery_replay.json](../logs/20260908_load_recovery_replay.json).

## Pedal identity and native idle-air gates

The earlier project identification of `FFFFB46C` as vehicle speed was wrong.
Standard SSM P30 address `0x29` selects `4B6FC + 4*0x29 = 4B7A0`, whose
pointer is `3184E`. This getter reads B46C and calls `258C` with scale
`100/255` and zero offset. Native execution returns 0/51/255 for 0/20/100
percent pedal, independently of a different B538 vehicle-speed fixture.
`188F4` reads B538 as a condition, but its final minimum at `18A20` uses
**B470**, loaded in the call's delay slot, before publishing B4C0. The chain
continues through B4C8 to B46C. Confusing that condition with the output
previously gave the wrong units in the notes and AVLS metadata.

The definitions and reusable Ghidra names now identify pedal percent.
The ten corrected names and focused comments were also applied to the live
stock Ghidra project; no ROM contents were modified.
The master AVLS curves remain numerically 110, above the 100-percent cap;
correcting their units does not change the existing 3200/3000-RPM policy or
any ROM byte. This naming error is not evidence of a lift transition during
the recorded idle dips; logged committed lift remained low.

The initial seven groups in `test_idle_air_execution.py` execute `18B14`,
`2C760`, `2CE50`, the P30 getter and their native scalar/getter helpers:

- P30 source/scaling and output saturation, independently of vehicle speed.
- Pedal-release qualification: `18B14` sets B483 bit 2 below its selected
  near-zero pedal threshold, then qualifies B484 bit 7 after three calls
  (`u16@73802 = 3`). Pedal opening clears that state.
- Separate air-feedback eligibility: under explicit running fixtures, `2C760`
  requires another 38 eligible calls (`u16@79538 = 38`) before C4D9 bit 3
  permits pressure feedback. B484 resets the qualifier; B51A/B51C, startup,
  other conditions and D26C/D272 fault flags can inhibit it. These switch
  producers are fixtures, not decoded log evidence.
- Independence from ignition-idle B2BC bit 1: that bit can be true while
  air feedback remains disabled, and changing it alone does not enable air
  feedback. Disabling eligibility clears the C45C/C4AC corrections at the
  controller update boundary. C4D6 is a cycling update counter, not a mode.
- Active pressure demand responds to RPM error and the native B54C RPM-delta
  input. With a 1000-RPM target and 300-mmHg baseline, the fixture demands
  298.203125 mmHg at 1400 RPM, 304.796875 at 558 RPM, or 330 at 558 RPM with
  B54C=-50. B54C's physical time base is not established by this test.
- When feedback is gated off, the pressure-demand routine retains C498.
- The real mode byte `7952C=0` selects C47C+C49C pressure demand. An in-memory
  negative control selects the unused C4F8 alternative and gives a different
  result. Do not change this byte or interpret the inactive mass-like path
  as a unit mismatch in the active controller.

The active feedback uses MAP: `2CB60` conditions ABC4 into C47C; `2CE50`
forms pressure demand C498, `2CF9C` builds corrections, and `2D0AC` with
`7952D=0` feeds the C45C correction path. The output-limit extension below
now executes those corrections and `2D1FC` under explicit fixtures. Learning,
throttle actuation, scheduling and engine response remain outside the test.
Table interpolation is mathematical.

Both the pedal and air-eligibility routines run in the `10A28` task chain,
via `17984` and the direct `10E12` call respectively. **Counts are calls,
not milliseconds**. The timer follow-up below establishes a nominal 8-ms
task period at a 40-MHz CPU clock, not a measured release-to-feedback delay.
The relevant idle/throttle code `2AAAC..2F390` and its idle-control calibration
are stock-identical in the candidate. The existing capture does not include
P30, B484, C4D9, C468 or C2B8, so it cannot show which gate actually applied
during the dip. E516/B2BC alone would not settle that question either.

This establishes an offline investigation path, not a verified near-stall
cause or repair. The output-limit follow-up below narrows that investigation;
actual gate state, feedback timing and physical response remain unresolved.

Initial validation: all seven idle-air groups pass on the candidate, all seven
candidate integrity groups pass, and the complete master verifier passes
with idle-air coverage integrated. The master rebuild remains exactly
`48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0`;
stock, candidate, source capture and complete logger hashes are unchanged.
This verifies the scoped software work, not recovery on the engine.
The standalone speed-density audit and AVLS metadata synchronization check
also pass after the label/identifier corrections. The focused master ROM
definition regenerates byte-identically; its hidden AVLS controls stay hidden.

## Primary-issue follow-up: release recovery, not a pedal code repair

The pedal work corrected identification and metadata. It did not alter ECU
behavior, and no evidence ties that naming error to the near-stall.
The leading unresolved mechanism is the transition from released throttle
back to idle torque: base/feedback air delivery and the retained fuel
transient act together. This is a hypothesis, not a diagnosed cause.

The worst event in the unchanged 14:13 capture has this recorded order:

| Time, seconds | RPM | Actual throttle, % | Net pulse, ms | B874 additive | AFR | Timing, degrees |
|---:|---:|---:|---:|---:|---:|---:|
| 248.188 | 1288 | 4.31 | 0.6000 | -0.4257 | 14.61 | 15 |
| 248.604 | 792 | 5.10 | 0.6000 | -0.5275 | 13.58 | 15 |
| 248.708 | 689 | 7.06 | 1.0330 | -0.4182 | 13.76 | 15 |
| 248.813 | 627 | 7.06 | 1.4093 | +0.2989 | 13.62 | 15 |
| 249.124 | 558 | 5.88 | 2.3405 | +0.5111 | 13.60 | 15 |

Five consecutive samples from 248.188 through 248.604 report the 0.60-ms
floor. Throttle and fuel increase before the minimum RPM, so neither remains
completely absent through the trough. The recorded rich AFR at the trough
does not establish a lean stall; exhaust transport and non-atomic 104-ms
sampling also prevent assigning instantaneous cylinder mixture from this
table. The comparison at 216.571 seconds similarly shows 836 RPM, -0.5545
transient, 0.8173-ms pulse and 15-degree timing; the minimum follows at
217.195 seconds with 673 RPM, +0.1522 transient and 2.4775-ms pulse.

Thus the fuel reduction is a repeatable feature worth investigating, but
its size alone does not prove inappropriate fueling for the reduced air.
The air response's timing and magnitude are the other concrete lead.
Spark retard ranks lower as the common explanation for the closing dips:
timing has recovered in these events while RPM is still falling. This does
not exclude the separate low-timing opening/reopening events.

Four additional native-execution groups extend the idle-air suite to eleven:

- `1A4F8` publishes B54C as `0.5 * (previous B54C + current RPM - previous
  RPM)`, then stores current RPM in B67C. Its pointer is `11D28` in task 6,
  separate from the air-control task. B54C is a filtered change per call,
  not RPM/second. The known usual crank cadence is RPM-dependent; these
  tests do not infer an actual B54C history from the CSV derivative.
- `2D1FC` only writes a new C45C correction at counter C4D6=8 with C4D9
  bit 3 active. Off-boundary/ineligible calls retain C45C; the separately
  executed eligibility routine can clear it. Gate and controller order
  therefore matter.
- Positive C4EC correction is capped at 6.0 by `79718` when the native
  `36986` getter reports CA64 bit 6 clear, and is further constrained by
  base-air headroom. The later BF20 fuel-cut getter is **not** this ceiling
  selector: native tests vary the two independently. Six is an internal
  correction value, not six percent throttle. The physical meaning and
  recorded state of CA64 have not been established here.
- The complete pressure demand/correction/output chain `2CE50 -> 2CF9C ->
  2D0AC -> 2D1FC` produces positive C45C under an eligible underspeed
  fixture. At 558 RPM, target 1000 RPM, MAP baseline 300 mmHg, prior C4AC
  0.5, gain-counter C4D4=0 and fixed base-air terms, B54C values 0/-25/-50
  produce C45C about 2.0807/4.2072/6.0. The last request is 10.3859 before
  limiting. These fixture values are **not** recovered controller states
  from the car; changing the gain, baseline, history or switches changes
  the result.

The trace establishes that the native output path can request extra air;
it does not prove the gate was available soon enough, the cap was reached
in the capture, or that increasing it would fix the engine. No evidence yet
justifies altering these stock constants. The existing profile's ignition
idle flag also cannot substitute for C4D9 feedback permission.

The eleven candidate execution groups and the complete master verifier pass
(`idle-air-output-master-verify.log` in `/tmp/d2wd-fuel-trace`). Stock, baseline,
flashed candidate and source-capture hashes remain pinned and unchanged. No flash
or repeat blip is requested; further work must distinguish feedback
eligibility, base-air delivery and transient fueling before selecting a
repair.

## Timer and stationary deceleration-air handover

The earlier roughly 10-ms task estimate is superseded by the timer-register
and native divider trace. `D390` initializes CMT1: CMCSR1 (`FFFFF718`) is
`0xC0`, CMCOR1 (`FFFFF71C`) is 2499, CMCNT1 is zero and CMSTR becomes 2.
The CMT1 handler at `5F54` dispatches `D3C2`. Native execution of 1024
divider calls activates task 9 on ticks 3, 11, 19, ... . Descriptor `4A2C`
selects entry `684C`, whose `6A40` pointer calls `10A28`.

Renesas specifies peripheral clock Pphi = CPU clock phi / 2, CMT clock
selection 00 = Pphi / 8, and a compare period of CMCOR + 1 clocks. Thus the
project's **nominal 40-MHz CPU clock** gives a 1-ms interrupt and an 8-ms
task-9 interval. This does not measure oscillator frequency, interrupt losses
or task latency. See the [SH7055S hardware manual](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual),
printed pages 74, 450 and 452.

`test_idle_air_handover_execution.py` adds five bounded groups: timer setup
and native activation division, pinned task call order, all eight initial
controller phases, imposed inhibit flags and release, and distinct MAF/speed
fallbacks. The actual order matters: pedal qualification precedes `2C760`
at `10E12`; pressure output `2D0AC` runs at `10E54`; then deceleration air
`2B9F2` runs at `10E5A`. The fixture executes these retained bodies in that
order, with explicit pressure, shaped RPM, gain history, target and switches.
It does not execute every other producer in the task or simulate the engine.

The stationary deceleration-air branch is now executed through `2B9F2 ->
2BB26 -> 2BA10`. At zero speed, C43C is zero and C438 follows C440. With
normal diagnostic states, 40 C coolant, a 1000-RPM target, fixed underspeed
and previously open pedal, the results are:

| Calls after pedal release | C438 deceleration-air term | Air feedback permission |
|---:|---:|---|
| 1--39 | approximately 0.666 | off |
| 40--47 | approximately 0.066 | on |
| 48 onward | 0 | on |

The native positive pressure correction is already available at call 40 in
this fixture. Qualification therefore takes about 0.32 seconds nominally;
the remaining deceleration term reaches zero about 64 ms later. These are
internal air terms, not throttle percent. The candidate's code and constants
in this path match stock. No guaranteed period without either correction is
demonstrated by the normal handover. Its nominal delay alone is a weaker
explanation for an RPM decline continuing for more than a second; the actual
pedal release and permission state are absent from the capture.

Setting D26C bit 0x10 or D272 bit 0x80 inhibits feedback while the same
deceleration allowance still reaches zero. Clearing only the imposed flag
restores feedback in the fixture. This establishes a diagnostic distinction,
**not that either flag was set on the car**, and does not justify bypassing
fault protection. The D26C/0x10 builder at `63174` references the P0068,
P0107 and P0108 descriptor states; P0068's switch `5BDB8` is already zero
in stock and candidate, while P0107/P0108 are retained. D272/0x80 aggregates
D271 bits 1--7 at `64D6C..64DF6`; some inputs come through C6FA/C6FB from
the checked C73C receive block (`30718/30790`). Its complete physical fault
mapping and the run's state remain unresolved.

The MAF fallback itself is a different case: D26F/0x40 via `65168` raises
the stationary deceleration-air minimum to 1.0 and does **not** directly
inhibit air feedback in the executed pair. The speed fallback D26C/0x80 via
`64F7C` also enforces that minimum but inhibits feedback. Consequently an
unplugged-MAF explanation cannot simply substitute one fault flag for another.
Unexecuted fault producers and other consumers remain outside this check.

The surrounding base-air trace adds another exclusion. `2B570` normally
sums C438, C424, C524, C534, C568, C5B4, C5B8 and C5CC into C2E8.
Its alternative reduction route requires at least 255 km/h and 65 C coolant,
among other gates, so it does not fit this stationary cold capture. C424's
normal target comes from four coolant tables through `2B7E8`, with a
0.01-per-call slew in `2B846`. This is a static data-flow trace, not a native
reconstruction of base air or learned values from the log.

E517 now exposes C4D9 directly and replaces E516 **in the prepared idle-air
profile selection**. E516 retains its original meaning and remains available
separately. E507's optional derived-seconds conversion changes from x/100
to x*.008 with the clock assumption explicit; every prepared profile still
selects raw task calls for E507. Earlier 3750/5000-count estimates become
nominal 30/40 seconds, and the old pump-timing exclusion is withdrawn in
[the historical audit correction](GHIDRA_AUDIT.md#engine-runtime-timer-cross-reference-2026-09-03).

Validation: all five handover groups pass on the flashed candidate; its seven
integrity groups pass. The complete master verifier includes these groups,
and the actual repaired RomRaider queue/reload/A8 checks pass for all four
profiles. The idle-air profile still has 19 channels, 43 addresses and a
136-byte checksum-valid request. This narrows the diagnostic plan; it is
not a new ROM repair or an instruction to reproduce the near-stall.

## Base-air request propagation and fault-input follow-up

The user's capture-or-continue question is answered **continue offline**.
An idle-only capture could establish steady feedback availability, but not
its state during the troublesome release. No capture, reflash or rev blip is
requested during this pass.

Six groups in `test_idle_air_request_execution.py` now execute the native
dependency chain `2B570 -> 2B432 -> 2B408 -> 2AC16 -> 2AB06` under explicit
driver-request, switch and learned-state fixtures. The corresponding task-9
pointers and relative order are pinned. Native `2B728`, `2B73C` and `2B762`
produce the barometric multiplier and bounds; their tables are unchanged.
Their effective-barometer input CFBC is a fixture, not a logged value.

With base C424=7, deceleration C438=.666, zero other adders and barometer
760 mmHg, C45C corrections 0/2/6 survive into C3FC and produce combined
relative throttle requests about **4.479/5.611/7.606 percent**. The stock
6075C conversion is increasing through this range; the normal selection
does not silently discard the extra air. These are controlled fixtures,
not reconstructed commands or predictions of recovered RPM from the capture.
An imposed reduced air ceiling and an alternate C2DC selection demonstrate
different outcomes. Their real producers/states remain outside this replay.

Native coolant selection `2B7E8/2B8AC` covers modes 1--6. At 40 C, modes
1--3 produce C428=8.500671 and modes 4--6 produce 7.000732. `2B846/2B908`
execute startup initialization and subsequent 0.01-per-call movement toward
the selected target. Stock startup mode supplies the target immediately in
the bounded case; a fresh all-zero fixture is not the running car's base air.

The final selector `2AAAC` is also executed. Normally it adds learned offset
80F0 to C2B8, bounds the result by 80D8 and publishes C2B4. C640 bit 0,
C618 bit 0 and the D274/0x40 getter can select separate retained requests.
Fixtures exercise each override without changing a ROM byte. This confirms
the logger boundary: E515 is the combined relative request before these
overrides, not the final absolute target or motor duty. Override producers,
actuator tracking and physical engine response are still not established.

The D271 fault-input trace now reaches native `C688`: the 8138/813C diagnostic
paths call it with selector 0/1, reading raw AB08/AB0A against bounds copied
by `2FDDC` from `7B270..7B276` (1311 minimum, 64225 maximum). Boundary tests
and independent variation of repurposed MAF ADC AB06 show that this helper
does not read AB06. This excludes a direct channel substitution in these
particular branches; it does not establish sensor validity or exclude every
indirect fault interaction. The other receive-derived C6FA/C6FB inputs remain
unlogged. `4711E -> 56E64` selects monitor dependencies, including callback
lists for selectors >=84: its argument must not be used as a DTC record
index. Likewise, the zero P0068 DTC switch alone is not proof that every
associated raw monitor state is inactive. The earlier D26C descriptor trace
and the direct C688 input trace are separate evidence.

The six groups pass on the candidate, the seven candidate integrity groups
pass, and the complete master verifier includes the new suite. Stock,
baseline, candidate, original capture and prepared logger remain unchanged.
This pass finds no normal request-propagation defect. Fault/override state,
air-command adequacy and its interaction with transient fueling remain the
unresolved distinctions; passing these bounded cases does not prove a cure.

## Final-request override producers and pedal-pair fault path

The next offline pass adds seven groups in
`test_idle_air_override_execution.py`. The producers, scalar helpers and
getters execute stock-identical native instructions; digital inputs, received
status and learned state remain explicit fixtures. This pass changes no BIN
or capture profile and does not request another engine run.

Two previously unclassified overrides now have concrete exclusions:

- **C618 bit 0:** `2F03C` first updates C638's RPM hysteresis. It sets the
  low-speed qualifier below 200 RPM, holds its prior state at 200--299, and
  clears it at 300 RPM or above. Without that qualifier it clears C618 bit 0
  before either activation route. Native tests activate the override below
  the boundary, then clear it at 300, 558, 673 and 1000 RPM. This stopped-engine
  path does not fit the sampled running dips under normal task execution.
- **C640 bit 0:** `2F684` clears it whenever `19C04` reports ignition on.
  The complete native SSM-62 getter `31AE4`, selected by pointer `4B884`,
  puts that getter's result into bit 3, the existing S7 Ignition Switch.
  This establishes identity independently of a guessed function name.
  `193D0` copies raw AAE8 bit 0 into B51E bit 0x10 at `1964E..19666`.
  The override can qualify with ignition off while C614 is below 375 and
  additional stock conditions pass. `2EFB8` resets C614 with ignition on,
  otherwise increments it with saturating helper `251C`. It also sets
  C618 bit 3 from count 6. The 375-count window is nominally 3 seconds at
  the previously established 8-ms task cadence, not a post-start timer.
  A stale imposed override clears before final request selection with
  ignition on. Actual switch glitches are not established by the old log.

Native task-9 order is pinned: C640 producer at `10F44`, C614 update at
`10F56`, C618 producer at `10F5C`, then final selector at `10F7A`.
With ignition off and other permissive fixtures, the C640 branch selects
C63C=3 at count 374; the subsequent counter update reaches 375 and the next
producer call clears it. Saturation does not wrap and reopen that window.

The remaining D274/0x40 route is built by `64874`: D273 bit 0x10 is the OR
of the following inputs and is copied into D274 bit 0x40 at `64F18..64F36`.
Each selected bit and each unrelated one-bit control is executed, including
clearing the aggregate again when its inputs clear.

| Source | Selected mask | Native getter / source |
|---|---|---|
| C6F7 | 0x08 | 30AEA |
| C6F9 | 0x10, 0x40 | 30BCE, 30BF6 |
| C6FA | 0x01, 0x08 | 30C30, 30C66 |
| C6FB | 0x04 | 30CEC |
| C6FC | 0x01 | 30D28 |
| 8134 | 0x01 | Native pedal-pair agreement monitor 61A08 |

The r13 lifetime matters: `64B8E` replaces its earlier C6FB/8 getter value
with 8134 bit 0. The later `64D44` test therefore reads the pair-monitor
result, not the earlier received bit. C6FB/8 alone does not set D274/0x40
in the execution test. The seven receive-derived bits come through retained
`30790/30A2A` from the C73C receive block; their originating physical checks
and actual vehicle values remain unresolved.

For the local pair monitor, `C5C8` reads AB08/AB0A, validates the raw range,
and scales the pair into AF80/AF84 using the native gains copied by `2FDDC`.
`180C6` subtracts learned 8110/8118 offsets and bounds at zero into B464/B468
before its later percent normalization. These are pedal-sensor inputs, not
the speed-density airflow outputs. The misleading Ghidra name
`cylinder_airflow_pair_update` at C5C8 is corrected to
`accelerator_pedal_adc_pair_update`.

`61A08` compares the pair and a separate reference D1FC under its retained
diagnostic selection. `619DA` produces D1FC as
`max(AF84 - 8110 + 8120, 0)`. With monitor D200 bit 0 enabled and the normal
8128 selection, the mismatch threshold is 9.109 internal units at 74FE0.
Tests hold equal inputs without a fault, then deliberately impose a 12-unit
difference: count 28 remains clear and count 29 sets 8134 bit 0, using the
29-count calibration at 74DC2. This count is not assigned the idle-task time
base without tracing its own scheduling. Executing the aggregate and final
selector then replaces an imposed combined request with C2D4 plus 80F0.
The C2D4 value itself is a fixture, not a reconstructed vehicle command.

The native ADC producer and the normal pair-monitor branch give identical
results at AB06=0 and 65535. Changing AB08 alone changes AF80 while AF84
stays fixed. This excludes a direct repurposed-MAF input in these tested
paths; it does not establish real sensor agreement, received fault status,
or the diagnostic enable state. No fault protection is disabled.

All seven override groups and seven candidate-integrity groups pass; the
full master verifier passes with the new suite integrated. Hash checks keep
the stock, 10:30 baseline, flashed candidate, original capture and complete
logger unchanged. The remaining unlogged distinctions include fault state, alternate
C2DC request selection, learned state, requested versus actual plate motion,
and air/fuel adequacy during release. No stock-routine replacement or new
calibration is justified by these exclusions alone.

## Throttle-link follow-up

The later packet trace executes validation, receive-history filtering and
the full received-fault-to-final-override path. See
[THROTTLE_LINK_AUDIT.md](THROTTLE_LINK_AUDIT.md). Seven groups pass;
physical incoming status remains unlogged.

## DBW tables and dashpot follow-up

The user suggested untouched DBW tables and then asked about speed-density
"dashpot protection". Direct comparison finds **zero changed bytes** in
both the 10:30 baseline and flashed candidate across:

- DBW/idle code `2AAAC..2F38F`;
- both visible DBW maps and their complete axes `7A6AC..7AD23`;
- their descriptors `607D4..6080B`;
- the traced idle/DBW constant block `79524..797D7`.

The pedal-request table is `7AA2C`, 19 pedal columns by 20 RPM rows,
descriptor `607F0`. Native caller `2B35A` publishes C3DC. The throttle
target table is `7A738`, 15 request columns by 20 RPM rows, descriptor
`607D4`; caller `2AF5C` reads arbitrated C3D4 and publishes C3D0.
The intermediate `2AF74` arbitration remains an explicit test boundary.

Five groups in `test_dbw_table_execution.py` pin these bytes, execute both
lookup callers, check released-pedal composition and compare dashpot
sensitivity in memory. At zero pedal, requested torque is zero across
558..2500 RPM. With other torque requests inactive, target C3D0 is also
zero. Native `2ADEC/2AD6C` clears a deliberately stale driver component
C2C8, yet normal idle air survives: base 7, decel .666 and feedback 0/2/6
produce combined requests approximately 4.479/5.611/7.606 percent. The
visible pedal maps therefore do not act as a zero-pedal cap on this normal
idle-request route. Actual alternative selections, learning and actuator
response are not reconstructed.

In general, dashpot/throttle-follower control temporarily retains extra idle
air after throttle closure and tapers it away to help catch idle; this is
described in [Haltech's idle-control documentation](https://support.haltech.com/portal/en/kb/articles/idle-control).
That source explains the concept, not this Subaru implementation. A link
to the user's particular "protection" reference was requested; until supplied,
no specific aftermarket algorithm is assumed.

This ROM already has a comparable retained deceleration-air path
`2B9F2 -> 2BB26/2BA10`. The stationary hold allowance is approximately
.666 at `79638`, with decrement .6 at `7963C`. Those are internal air
terms, not throttle percentage. Crucially, the 38-count value at `79538`
is shared by the deceleration hold and air-feedback eligibility.

With fixed 558 RPM, 40 C and other explicit handover fixtures, these
**in-memory-only** alternatives give:

| Fixture | First feedback call | First decel-air reduction | Decel air reaches zero |
|---|---:|---:|---:|
| Stock 38-count hold / .6 decrement | 40 | 40 | 48 |
| 76-count shared threshold | 78 | 78 | 86 |
| Stock threshold / .1 decrement | 40 | 40 | 88 |

Increasing the shared threshold delays feedback as well as holding air.
Changing the separate decrement extends taper without changing feedback
eligibility in this fixture. These comparisons establish control effects,
not a preferred calibration or an engine-response prediction. They do not
recalculate the changed physical airflow, RPM, fuel transient or AFR.
Normal stock handover has no demonstrated missing-air gap, but the amount,
decay rate and live feedback state could still be unsuitable for the modified
engine. Unchanged tables alone cannot establish their suitability.

No ROM or logger change, new capture or flash is requested. Dashpot/base-air
adequacy and requested versus actual throttle remain concrete leads alongside
the recorded stock transient fuel reduction.

The user's experimental `candidates/D2WD610H_slight_dashpot_candidate.bin`
appeared during this check. At inspection its SHA-256 was
`7590b6ce79b41caea9d8bb850a31c41318708687120e45a584ad5030c1c47b8f`.
It differs from the flashed candidate by 19 bytes: six zero-request throttle
table cells at 1000..2000 RPM, the valid checksum `0D556987`, and the word
at 7FC4C changed from FFFFFFFF to 26090802. All earlier firmware fixes are
retained. The shared hold and separate decel-air settings remain unchanged.

The fifth DBW test reproduces those six table cells in memory. Their mapped
targets rise to approximately 0.50/1.20/2.00/2.50/3.00/3.50 percent, but
native `2AD6C` bounds the driver component by pedal times `7959C/100`;
7959C is 84. At zero pedal, C2C8 remains zero and normal combined request
remains 5.611138 percent for the explicit base/decel/feedback fixture. The
new table values are read, but do not supply extra idle-catch air through
this normal zero-pedal path. Effects at nonzero pedal or alternate request
modes are not claimed absent. The user's file was inspected, not rewritten.

The user clarified this was an experiment and asked whether earlier fixes
require a new BIN. They do not: the earlier firmware fixes are already in
`D2WD610H_idle_recovery_candidate.bin` and retained in this experiment.
This investigation changes test/audit files only. No new firmware fix or
validated dashpot calibration has been produced. All twelve new packet/DBW
groups pass on the baseline and flashed candidate; the full verifier passes.

## Follow-up: do patches mistakenly use the pedal signal?

No mistaken substitution of pedal for MAP, engine load or vehicle speed was
found in the **current `6af0d130...` candidate**. This statement covers the
current built components and the checks below; it is not approval of older
BINs or a claim that retained stock logic never reads pedal position.

| Current component | Signal use and evidence |
|---|---|
| Speed density | MAP ABC4, caller-saved RPM, IAT B3B8 and committed lift CD86. The wrapper neither reads nor writes B46C/pedal state. Its nearby B448/B458/B45C outputs are airflow state: native 17726 copies ABE4 into B448, with 172A4 and 17726 consuming the two filters. They are separate from pedal B46C/B470. |
| Wideband/O2 delete | ADC AB06 becomes lambda/readiness outputs. Neither this decoder nor the readiness helper uses pedal. The retained auxiliary O2 adder has a legitimate pedal-release selector 18CF4, but both selected constants are zeroed, so the deletion works in either pedal state. |
| Added pressure OL / lean and overboost cuts | Added decisions use MAP, barometric pressure, wideband readiness/lambda, switches and counters. Native limiter behavior is retained. Pedal changes do not alter these added decisions with their real inputs fixed. Stock fuel-target/CL logic can still legitimately depend on pedal. |
| Rotational idle | Uses processed throttle B314 and **vehicle speed B538**, not pedal B46C. The current switch is zero. Enabling it only in the test's memory confirms that actual speed controls the gate independently of pedal. |
| Purge deletion | Zeroes B6D4/B6D8/B720 and bank subtraction outputs; its generated entries contain no pedal-state input or destination. |
| Predictable AVLS | This patch does modify **pedal-based** thresholds, previously mislabelled as speed. Both seven-point curves and both fallback thresholds remain 110 percent, above the 100-percent conditioned-pedal cap. That still disables the alternate engagement route as intended, leaving the existing 3200/3000-RPM override policy. It does not command 110-percent pedal or throttle. |

The full candidate rebuild remains pinned and the code regions
`17984..18DAC` and `2AAAC..2F390`, the pedal-conditioning calibration
`73A2C..73B54`, and DBW/idle calibration `79500..7B000` match stock.
The installed blobs for all six code components contain no literal address
in the B46C..B4CF pedal-state block. Literal absence alone does not prove the
absence of every computed address or dependency through a stock callee.

Five new `test_pedal_patch_dependencies.py` groups complement that inventory:
native P30/P9 getters distinguish pedal from vehicle speed; the actual SD,
wideband, pressure-wrapper, lean/overboost and rotational-idle instructions
execute with pedal 0/20/100 and independently fixed engine inputs. Access
tracking detects no pedal-block reads or writes in these added paths. Vacuum,
near-atmospheric/lean and hard-cut scenarios are included. In-memory negative
controls deliberately replace the SD MAP pointer or rotational-idle speed
pointer with B46C and demonstrate the unwanted dependency. No altered image
is written to disk.

P9 reads pre-selection speed B53C (`4B73C -> 31678`); stock `1A2A2` normally
copies B53C to B538 at `1A336..1A33A`, with its retained validity/fallback
gates. P30 independently reads B46C (`4B7A0 -> 3184E`). The pressure wrapper's
stock target calculation and rotational idle's stock final timing are explicit
fixtures in these new tests; SD interpolation is mathematical. The engine's
physical response to pedal is deliberately outside this comparison.

The five groups pass on the candidate and the complete master verifier
passes with these checks integrated. Stock, baseline, candidate and original
capture hashes remain unchanged. The remaining stale AVLS description in the master-definition
generator and the misleading 2AD6C Ghidra function name are corrected; 2AD6C
filters throttle request C2CC into C2C8 and uses pedal B46C in its limit.
These are metadata changes, not a new firmware repair. The near-stall remains
unresolved and the live test remains withdrawn.

## Newly traced request channels

| Channel | RAM | Evidence and interpretation |
|---|---|---|
| E514 Effective Idle Speed Target | `FFFFC468`, float RPM | `2BD5C` chooses among six coolant tables and publishes C460; `2C2D8` applies adjustments to C4E8; `2C510` applies further limits/decaying contribution and publishes C468 at `2C70E`. Multiple idle-control consumers read this, including `2CCD0` at `2CCDE`. It is a request and does not itself prove idle control is active. |
| E515 Combined Throttle Request | `FFFFC2B8`, float / 0.84 percent | `2AC16` sums C3F8 and C2C8, with an optional history selection, into C2C4. `2AB06` clamps this and applies native mode selection into C2B8. The native upper bound is 84 degrees. `2AAAC` later adds the learned offset and can select fault overrides before C2B4. This diagnostic is the combined relative request, not final motor duty or a complete actuator fault trace. |
| E516 Throttle and Idle Flags | `FFFFB2BC`, byte | Written by throttle processing `14DCC`; bit 1 (mask 2) is the ignition-idle flag returned by `15192`, already executed in the idle-timing tests. It does not establish C4D9 air-feedback eligibility. Decode the raw byte offline. |
| E517 Idle Air Feedback Flags | `FFFFC4D9`, byte | Bit 3 (mask 8) permits pressure feedback; a new output also requires C4D6's update boundary. Bit 0 is eligibility. Written by `2C760` and the output limiter. This replaces E516 in the idle-air profile, preserving 43 addresses. |

The six coolant target descriptors `6041C..60480` reference 16-point tables
on -40..110 C. At 40 C, A/B/C request 1200 RPM and D/E/F 1050 before further
adjustments; therefore one cannot infer the commanded idle speed from coolant
and measured RPM alone. C468 is chosen over an earlier unadjusted target.

Existing E57/C3D0 is only the earlier requested-torque map output from
`2AF5C`. It does not capture the combined idle path above, so merely adding
E57 would leave an important ambiguity. E515 also has a stated boundary:
later fault overrides and the motor's physical tracking still are not logged.

## Prepared profile — live test currently deferred

The updated complete
[D2WD610H_master_logger.xml](D2WD610H_master_logger.xml) and
[D2WD610H_idle_air_diagnostic_profile.xml](D2WD610H_idle_air_diagnostic_profile.xml)
are prepared for a later capture. No engine run or reflash is requested now.
The already-flashed `candidates/D2WD610H_idle_recovery_candidate.bin`, SHA-256
`6af0d130b585abf9c9b275840ddb0b237485d84f8f8adf7b15df8462adc72433`,
was confirmed by the previous recorded flash CRCs.

The earlier 60--90-second idle / single 1500-RPM release proposal has been
withdrawn. A revised logger alone does not change the near-stall behavior.
The next action is offline tracing of the idle request, air command and
remaining stock sensor assumptions before selecting another vehicle test.

The useful comparison is air-feedback permission and request response as RPM falls:
does the ECU command more plate opening early enough, does measured throttle
respond, and how do calculated load, B874 and net pulse change alongside it?
AFR has transport/sensor delay and is not a simultaneous fuel-delivery probe.

The 19 channels are RPM, coolant, IAT, battery, MAP, airflow, throttle,
accelerator pedal, total timing, conditioned load, fuel-system state,
net injector pulse, B7DC factor, wideband AFR/raw ADC, B874, E514, E515 and E517.
MAP uses the stock 1-kPa channel to fit the budget; this is not the best
profile for precise steady VE fitting. Pump duty, injector latency, the
redundant total pulse and lift state are omitted from this capture.

The profile uses exactly **43 SSM byte addresses**, a 136-byte request with
checksum at index 135, within the native limit. All four profiles explicitly
clear each other's selections; use them separately. The actual repaired
RomRaider queue and A8 builder retain all 19 channels/38 view subscriptions
and produce a valid checksum. XML/header checks and the full master audit
pass. No serial connection or new ECU/engine operation was performed.

Current complete logger SHA-256:
`f225b9688b05823941f6939e71f22a08deb0f11f898eb5bb477f0657f5b97d2e`.

```sh
python3 master_patch/test_load_conditioning_execution.py
python3 master_patch/test_idle_air_execution.py
python3 master_patch/test_idle_air_handover_execution.py
python3 master_patch/test_idle_air_request_execution.py
python3 master_patch/test_idle_air_override_execution.py
python3 master_patch/replay_20260908_load_recovery.py --output logs/20260908_load_recovery_replay.json
python3 master_patch/verify_master_patch.py
```
