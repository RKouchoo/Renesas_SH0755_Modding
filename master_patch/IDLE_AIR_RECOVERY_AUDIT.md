# September 8 — load replay and idle-air investigation

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

`test_idle_air_execution.py` now executes `18B14`, `2C760`, `2CE50`, the P30
getter and their native scalar/getter helpers. Seven groups cover:

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
`7952D=0` feeds the C45C correction path. The latter correction limits,
learning, throttle actuation, scheduling and engine response are not covered
by this bounded execution test. Table interpolation is mathematical.

Both the pedal and air-eligibility routines run in the `10A28` task chain,
via `17984` and the direct `10E12` call respectively. **Counts are calls,
not milliseconds**; no measured release-to-feedback delay is inferred.
The relevant idle/throttle code `2AAAC..2F390` and its idle-control calibration
are stock-identical in the candidate. The existing capture does not include
P30, B484, C4D9, C468 or C2B8, so it cannot show which gate actually applied
during the dip. E516/B2BC alone would not settle that question either.

This establishes a concrete offline investigation path, not a verified
near-stall cause or repair. The next trace is the remaining pressure-correction
limits and pedal-to-feedback timing before choosing any calibration change.

Validation: all seven idle-air groups pass on the candidate, all seven
candidate integrity groups pass, and the complete master verifier passes
with idle-air coverage integrated. The master rebuild remains exactly
`48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0`;
stock, candidate, source capture and complete logger hashes are unchanged.
This verifies the scoped software work, not recovery on the engine.
The standalone speed-density audit and AVLS metadata synchronization check
also pass after the label/identifier corrections. The focused master ROM
definition regenerates byte-identically; its hidden AVLS controls stay hidden.

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

The useful comparison is the idle flag and request response as RPM falls:
does the ECU command more plate opening early enough, does measured throttle
respond, and how do calculated load, B874 and net pulse change alongside it?
AFR has transport/sensor delay and is not a simultaneous fuel-delivery probe.

The 19 channels are RPM, coolant, IAT, battery, MAP, airflow, throttle,
accelerator pedal, total timing, conditioned load, fuel-system state,
net injector pulse, B7DC factor, wideband AFR/raw ADC, B874 and E514--E516.
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
`3ff3a49fb332551c411a635ddcac49d04fea5f3ee1c308d917fa0145b8d5925e`.

```sh
python3 master_patch/test_load_conditioning_execution.py
python3 master_patch/test_idle_air_execution.py
python3 master_patch/replay_20260908_load_recovery.py --output logs/20260908_load_recovery_replay.json
python3 master_patch/verify_master_patch.py
```
