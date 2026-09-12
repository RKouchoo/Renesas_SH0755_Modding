# September 12: misfire near the AVLS transition

[Reference home](README.md) · [Comparison chart](../../logs/20260912_rotationaldelete_review.png) · [Derived data](../../logs/20260912_rotationaldelete_review.json)

The later [injector/pump-demand repair](FUEL_PUMP_SCALING_20260912.md) corrects
a separate stock consumption coefficient in both rolling images. The 14:42
log below remains tied to its original `fd795813…` image. Its sustained bog
is rich, and the pump correction is not established as the cause or cure.

## 14:42 adjusted-VE drive: loaded fault persists

The user reports that the engine still bogs/misfires near 3000 RPM under
load and reads very rich. **No further captures have been requested.** The
earlier neutral-only fueling adjustment was not a demonstrated cure for
this loaded fault; this drive confirms it remains unresolved.

- [New source CSV](../../logs/romraiderlog_adjustedvedrive_20260912_144204.csv):
  SHA-256 `347d10ce5e5c70d64f478e4bb6d124453697af07b1e074271ecbe1830d7efb33`.
- 2,747 complete finite samples over 285.779 seconds; coolant 65–76 C.
- All 16 FastECU post-flash CRC blocks at **14:41:30.926** match v2 SHA
  `fd795813febf817c845fc922e81e498539a539efeeb6e4d11822af47098094a2`.
- [Reproducible drive evidence](../../logs/20260912_adjusted_drive_review.json)
  includes loaded-window statistics, actual SD-wrapper replay, primary-table
  comparisons, MAP outliers and the explicit fresh-cut fixtures.

The 10–30 s stationary idle is mostly around AFR 14–15 after startup,
consistent with improvement from the idle change. There is no equivalent
settled neutral high-lift hold here with which to validate the vacuum trim.
The troubled driving points are at substantially higher pressure.

The sustained **77–85.8 s** window is entirely **low lift**, at 2502–2876 RPM.
With pedal at least 25% and absolute B874 below 0.03, its 81 samples have
median load **1.98 g/rev**, B7DC **1.18**, measured AFR **11.58**, and timing
**16.5 degrees**. IAM is 1 and the sampled knock corrections are zero.
At 84.398 s the plate is 85.49%, RPM 2857, MAP 108.504 kPa, load 2.17,
factor 1.21, B874 +0.0024 and P21 9.22 ms. Poor loaded performance therefore
cannot be assigned solely to the high-lift vacuum cells or transient fuel.

Native `1E0C8` multiplies B438 by the injector scalar at `76014`, clamps
through `24C0` and publishes B82C. Across the nine selected loaded windows,
the median gross-pulse residual after `load * 3.266667 * B7DC` is about
0.64–0.75 ms. This is compatible with the expected duration path; the
residual is **not** a measurement of latency or proof of delivered fuel.
Primary-table enrichment plus the small B874 term explains most of B7DC.
`14.64/B7DC` is roughly 12.4 in several of these windows, so the measured
mixture is richer still; that ratio omits separate bank multipliers and
does not independently establish physical air mass or injector flow.
[Ghidra MCP readback](evidence/adjusted_drive_20260912.json) records the native
base-pulse observation. The primary limiter has 6800/6770 and 5000/4800
RPM pairs. A separate native diagnostic cut does use 3000/2500 RPM;
its qualification and limits are recorded below.

Holding 80 captured low-lift bog points through every lean transport and
confirmation count, at barometric fixtures 90, 94.6855 and 100 kPa, produces
**zero fresh added cuts in 240 cases**. Stock fault flags are clear fixtures.
This does not rule out an unlogged native fault, an earlier latched cut or
excursions between SSM samples. Four isolated MAP readings above 260 kPa
are compatible with mixed float bytes at an exponent boundary; their
quarter-values are around 66–68 kPa and load/pulse do not track a fourfold
airflow event. They are not established physical overboost events.

The older blanket boost VE increases remain a calibration concern. A VE
table is an engine-filling calibration, and boost pressure already enters
the density calculation; nevertheless VE can also vary with boost.
It is not valid to infer that all of those cells must be reduced by 25%
without accounting for the resulting load and primary-target changes.
See [Haltech's explanation of VE and boost](https://www.haltech.com/news-events/tuning-with-ve-volumetric-efficiency/).
No new ROM change has been justified as a cure for this drive.

The user explicitly reports **no boost during the failure**. The earlier
boost-induced ignition explanation was unsupported and is withdrawn. The
drive records absolute MAP and does not include a simultaneous barometric
channel; no gauge-boost value is inferred here. Plug gap/spark delivery, fuel
pressure, actual cam motion and individual-cylinder combustion are not
measured by this log. Their absence is not evidence that a component failed.

The source rows show what changes as acceleration deteriorates:

| Time (s) / CSV line | RPM | MAP (kPa absolute) | Throttle (%) | Lift state | Load (g/rev) | P21 (ms) | AFR | Timing (degrees) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 68.353 / 659 | 2378 | 101.198 | 55.69 | 1 | 1.81 | 7.68 | 12.07 | 16.5 |
| 70.540 / 680 | 2904 | 103.739 | 78.43 | 1 | 1.94 | 8.19 | 11.86 | 17.0 |
| 71.894 / 693 | 3258 | 110.728 | 76.47 | 3 | 2.28 | 9.98 | 11.57 | 16.0 |
| 84.398 / 813 | 2857 | 108.504 | 85.49 | 1 | 2.17 | 9.22 | 11.56 | 16.0 |

IAM is 1 and both logged knock corrections are zero in all four rows. These
samples show increasing commanded fuel and rich measured AFR, without an
abrupt collapse of logged throttle opening or timing. They do not identify
the initiating cause or prove physical fuel/spark delivery. The separate
14:13 neutral hold at 28–31.85 s has 3267–3373 RPM, median MAP 39.251 kPa,
load 0.71, P21 3.07 ms, AFR 12.10 and timing 41.5 degrees. That is a different
load region and the preceding ROM; it is not a controlled isolation of gear,
ignition hardware or one calibration table.

### All-cylinder cut, test connector and empty DTC scan

The user clarified that all cylinders feel as though they stop firing around
2800–3500 RPM under load. With the test connector connected, the engine light
blinks slowly in neutral and faster in gear. With it disconnected the engine
light does not blink even during the cut, while cruise flashes. A separate
DTC scan returned no codes; the user subsequently confirmed it was performed
while the engine was running after the cut. IAM stays unchanged during the event. These are
user observations; the scan's raw response is not present in the reviewed
September 12 RomRaider/FastECU application logs.

Native `253A8` has a diagnostic cut independent of the primary rev limiter:

- Getter `6537A` returns 2 when `D273 & 02` is set.
- `BF93/80` sets at 3000 RPM, remains set at 2500 RPM and clears below 2500.
  Calibration `764C4/C8` is 3000 RPM with 500 RPM hysteresis.
- With that request active, `254FC..25544` sets `BF90=FE` and calls the native
  inhibit publisher. With other requests clear, `B744=003F`: all six channels.
- `64874` derives `D273/02` from masks 80, 40, 20, 10 and 08. Sources include
  local pedal/throttle/link diagnostics and validated received status. One
  explicit fixture, two accepted frames asserting `C6FC/10`, reproduces the
  complete received-status → diagnostic-summary → all-six-cut path.

This identifies a mechanism, **not the vehicle's active fault**. A second
replay deliberately holds `D273/02` active across every recorded RPM sample.
RPM falls to 2377 at **73.146 s**, releasing this path; it stays released
through the entire **77–85.25 s** bog window because RPM never returns to
3000. Therefore the observed sampled history does not support this path as
the complete explanation for poor loaded performance. Between-sample inputs
and the actual diagnostic request were not recorded.

The standard P21 getter was also traced through actual code: SSM `20` calls
`317B4`, which adds **C0B8 + C0D8**, then `258C` rounds/clamps the result to
256-us counts. `26F8C` has already zeroed C0B8 when its channel record is
inhibited, but the independent latency C0D8 remains. **P21 is not wholly
upstream of inhibition.** An execution fixture with 1000 us pulse and 1000 us
latency reports 2.048 ms before the cut and 1.024 ms after `B744=003F` reaches
the scheduler records. Consequently the repeated 9–10 ms bog readings argue
against a continuous all-six software cut at those sampled times. They do not
exclude rapid intermittent cuts or establish actual injector/coil delivery.

The test input is `B51E/80`, published from active-low `AAE8/0040` by `193D0`.
Getter `19BE2` feeds standard SSM byte `61` bit 5, **S2 Test Mode Signal**.
Generic S70 at byte `61` bit 1 stays clear in this ROM's handler and is not
the correct indication. `148EE/B28C80` instead reads ROM configuration byte
`737C9`; it must not be labelled as the connector. The native timing
substitution at `27A6C` additionally requires RPM below 2000 and other gates,
so it is not an unconditional timing lock at the reported cut speed.

Subaru's [service procedure](https://manualmachine.com/subaru/legacy2004/17608349-service-manual-engine-section-2/)
and EcuTek's [connector guide](https://ecutek.atlassian.net/wiki/spaces/SUPPORT/pages/11305208/Subaru+EJ+Programming+Guide)
establish that connecting the green plugs enables test mode and can blink
the MIL. They do not establish the cause of this car's cut or its particular
gear-dependent blink rate. The cut persisting with the connector disconnected
prevents treating connector removal as the cure.

The mapped P0301–P0306, throttle, pedal-pair and ECU communication/error
enable bytes remain stock `01` in current v2. Diagnostic reporting `50FF6`
has separate gates and mode-dependent publication; the immediate `D273/02`
cut is not gated by a stored DTC bitmap. No evidence establishes a reporting
gate suppressing this vehicle's codes. The imposed `C6FC/10` fixture also maps
to diagnostic record 2, P0604, through `65724`; **P0604 was not observed on
the vehicle** and is not a diagnosed RAM fault.

[Ghidra MCP comments and readback](evidence/native_fault_cut_20260912.json)
record the distinction. The seven native-cut execution tests pass on both
integrations, including connector-state independence and fault release.
The injector-scheduler suite now has 13 groups, including this P21 correction.
No protective cut was bypassed and neither ROM was changed by this review.

### Follow-up: other factory limp responses remain possible

The single `D273/02` replay above is not a complete model of limp operation.
The rest of `253A8` has additional responses, verified with native instruction
execution and deliberately imposed controller-link status:

| Accepted received status fixture | Result with other inputs fixed |
|---|---|
| `C6F7/40` | Getter `30B26` directly qualifies the `2564C` RPM/pedal pattern, even with `D273=00`. At 2700 RPM and 45% pedal, `B744=0015` inhibits three channels. Raising pedal to 80% releases that pattern; falling to 60% holds release, 50% restores the three-channel cut, and 20% gives `003F`. |
| `C6FA/02` | Aggregator produces `D271=80`, `D273=27`. At 45% pedal, it cuts all six at 3200 RPM, then still cuts three at 2400/2700 after the 3000-RPM latch clears. |
| `C6F8/01` | Aggregator produces `D271=00`, `D273=27`, allowing the earlier 1000/800-RPM branch. All-six inhibition can persist at 2400/2700 with 80% pedal. |

`2564C` uses **conditioned pedal B46C**, not vehicle speed. Rising boundaries
are 1000/1800/5000 RPM and 34.5/69% pedal, with 100 RPM and 13.8% falling
hysteresis. BF92 retains the selected region; the native switch uses bytes
`75E3A..75E43` to publish BF91 classification 0, 1 or 2. A fault must qualify
that classification before it becomes an injector cut.

The other pattern qualifier `6508E` reads **D26F/20**, distinct from the retired
MAF-load fallback `D26F/40`. Its producer at `63CE6..63D40` checks diagnostic
descriptor `5C5E8`: index 102, **P0519 idle-control malfunction**, current status
`8EA6/20`, enable `5BDBA=01`. P0519 was not reported by the vehicle; this is
the ROM's mapping, not a diagnosed idle-control fault. The direct received
`C6F7/40` route does not need this stored-status lookup. This does not establish
whether its remote producer would report a code in the circumstances of the
drive, or whether any reporting delay occurred.

The [expanded reproducible replay](../../logs/20260912_adjusted_drive_review.json)
holds each of the three received faults active throughout the recorded
RPM/pedal history. In the 80 samples from 77–85.25 s, the first two fixtures
produce 54 three-channel cuts and 26 clear samples; all 24 samples above 69%
pedal are clear. The severe third fixture cuts all six throughout. None is
an observed vehicle flag. Every nonzero mask in these fixtures includes the
P21 channel, whose logged pulse remains 7.94–9.47 ms in the window. Therefore
these tests keep intermittent limp responses open while arguing against
these particular faults being continuously active throughout the bog.

The loaded CSV omits these fault flags and the actual inhibit word. Existing
neutral captures contain the inhibit word, but cannot establish its state
during this loaded event. No new capture, flash or protection bypass was
requested. The two added regression groups pass against both rolling BINs;
the cause of the vehicle fault remains unresolved.

Ghidra MCP supplied the native disassembly for this follow-up, but subsequent
annotation writes and readbacks timed out. The four proposed comments and
failed readback responses are retained in the `limp_followup` section of the
[evidence file](evidence/native_fault_cut_20260912.json); those four updates
are **not confirmed in the Ghidra project** and remain pending retry.

### Follow-up: spark permission and dwell

The [focused ignition test](../../tests/test_ignition_permission_execution.py)
executes seven groups against both rolling ROMs. Fault inputs are explicit
fixtures, not states recovered from the drive. Native `27090` publishes spark
permission `C0DC` separately from injector inhibit `B744`: D94C's upper two
bits and D94D's lower four bits select paired permission bits, while CD50/80
or CE28/01 forces `FFFF`. Getter `2A262` also incorporates startup mode C0E1
and auxiliary mask C290. Consequently a nonzero P21 or logged ignition angle
alone does not prove that all coils were permitted to fire.

Under the logged warm-coolant and 2500–4144 RPM conditions, the tested startup
mode producer `2716C` releases its low-speed gate. Shutdown producer `3F5F0`
clears CD50/80 with ignition input B51E/10 on, irrespective of test-connector
B51E/80. Its old Ghidra name, `radiator_fan_state_timeout_update`, is misleading:
the traced branch times ignition-switch-off and then calls the spark-mask
publisher. Configured status producer `41698` has other qualifiers whose
physical role and vehicle state are not established by this review.

The dwell caller `9FEC`, descriptor `60998`, axes/data `7BBE0..7BCC5`, and
getter `2A3C0` are byte-identical to stock. With a **14 V fixture**, cached raw
dwell counts at 2500/2800/3000/3500 RPM are 752/713/688/624. There is no zero
or abrupt 3000-RPM cutoff in that lookup. The voltage is not logged in the
drive, and the lookup boundary is modeled interpolation; this does not
measure coil charge or simulate the full ignition scheduler. Separately,
native `3D824` clears the six learned CCC8..CCDC timing corrections at RPM
at least 2000; its below-threshold path clamps them to -5..+5 degrees.

These checks do not diagnose an ignition fault or justify a ROM change.
Ghidra MCP continued to time out, including a `3F5F0` read attempt. This
follow-up used local disassembly of the stock ROM plus execution against the
rolling images. No Ghidra annotation from this follow-up is confirmed saved;
the `3F5F0` naming correction remains pending.

### Verification changes from this review

V2 now runs the native primary-fueling and injector-scheduler suites as two
additional verifier groups, plus the native diagnostic-cut suite. Four initial
failures were **test assumptions**:
the ramp test required over 20% enrichment even though v2 selects 17.96875%
at its fixture, and three scheduler cases used 820 mmHg as a held lean cut
even though v2 correctly releases at that pressure. The tests now check the
selected positive ramp and derive the held-cut pressure from the installed
reset calibration. Their negative controls remain active. Both suites pass
on v1 and v2; all **nine** then-current v2 offline groups passed. These were
verification repairs, not a vehicle-fault fix. Both ROM images remained
byte-identical during that review. The later pump correction adds a tenth
v2 check group.

```sh
python3 -B tools/analysis/analyze_20260912_adjusted_drive.py
python3 -B master_patch_v2/verify_master_patch.py
```

## Earlier 12:26 capture and subsequent repairs

The later [13:16 neutral capture](V2_AVLS_NEUTRAL_20260912.md) stayed in low
lift and exposed an additional stationary oil-gate calibration mistake. That
report records the subsequent six-byte repair and current rolling identities.

The new capture links the reported disturbance to high-lift selection much
more closely than to IAM or a large speed-density table discontinuity. It does
not establish whether the physical lift transition, ignition, fuel delivery
or an unlogged intervention initiates the misfire.

## Capture identity

- Source: [rotational-delete CSV](../../logs/romraiderlog_rotationaldelete_20260912_122651.csv),
  SHA-256 `3c167a4ce61a7d503232a490157b47c4283385ec06268551ed125b1803080142`.
- 1,727 complete samples over 179.579 seconds, approximately 104 ms apart.
- Flashed ROM: `ca4516f5a3737cffc172e9f1771a78a1a4ee966703136281d65d275d77dad7ef`.
  All 16 FastECU post-flash block CRCs match the rotational-delete image in
  `log_fastecu_2026-09-12_11h31m48s.txt`, updated at 12:26 before this capture.
- The analysis script reconstructs that exact ROM from Git `5f0ba2a` plus the
  verified rotational removal and checks its SHA before interpreting tables.
  The rolling BIN now includes the separate lean-reset correction below.

## Repeatable loaded events

Three high-lift entries occur while the pedal remains approximately steady:

| Time, seconds | Pedal / plate | Software lift mode | Following RPM disturbance | Wideband reading |
|---|---|---|---|---|
| 80.724 | 65.1% / 76.5% | 1 → 3 | 3208 → 2998 → 3221 | 11.09, later 13.55 before substantial pedal release |
| 122.766 | 60.0% / 71.4% | 1 → 3 | 3222 → 3039 → 3296 → 3098 | 11.09 → 16.58 with pedal held at 60% |
| 129.010 | 60.0% / 71.4% | 1 → 3 | 3166 → 3028 → 3233 | 11.56 → 12.58, then higher as the driver starts lifting |

The ROM's high-lift engage/release settings are 3200/3000 RPM. Logger RPM and
mode are not an atomic snapshot; the first mode-3 row can show RPM below 3200.
Two later high-lift entries follow throttle blips/lift-off and do not provide
the same steady-pedal comparison.

IAM is **1** throughout these events, and FBKC/FLKC are **0**. Final timing is
approximately 15–19 degrees during the loaded transitions, with no timing
collapse. The previous `road1` drive had IAM 0 and about four degrees less
advance at comparable loaded points, so the subjective improvement cannot be
assigned solely to removing the disabled rotational-idle wrapper.

P21 calculated gross injector duration rises to about 11.3–11.5 ms around the
initial disturbance. It does not collapse at high-lift entry. However, this
channel includes latency and does not prove physical injector delivery.
The later native-code trace above corrects the earlier claim that P21 was
entirely upstream of inhibition: its scheduled-pulse term is zeroed for an
inhibited record, while latency remains. These readings therefore argue
against a continuous settled all-six cut, without excluding intermittent
intervention between samples.

The subsequent lean wideband reading does not identify the initiating cause.
Misfire can leave oxygen in the exhaust and produce a lean indication, as
described in the [manufacturer's wideband documentation](https://www.gtechpro.com/manual/EGS1.0.pdf).
Sensor transport and the SSM sample interval also limit event ordering.

## Checks against the flashed firmware

Executing the actual SD wrapper at each loaded entry with only its software
mode changed from 1 to 3 alters calculated airflow by **−0.186%, −0.241%, and
0.000%**, respectively. The lookup fixture decodes the actual descriptors and
tables and poisons caller-saved registers. It does not simulate physical valve
lift, sensor timing or the engine. There are larger differences between the
VE tables at other pressure cells, but those are not the loaded entry points.
This rules against a large arithmetic step at those points, not against a
high-lift fueling error: nearly equal calculated airflow does not prove that
the real engine takes in equal air on both lift profiles. High-lift VE remains
unvalidated, and a misfiring wideband trace cannot justify a reliable VE multiplier.

AVLS control/output code at `3FD9C..412BF` is byte-identical to stock. The
software decision is copied from `CD87` to `CD86` at `405B2`. The separately
scheduled gate at `405CC` updates bank copies `CD89/CD8A` at phase-qualified
boundaries and runs the bank output stages. **CD86 is not measured confirmation
that both banks completed their hydraulic lift change.** Ghidra comments now
make that distinction and correct the old pedal/vehicle-speed label at `40168`.

Using the engine-off MAP of **95.162 kPa as an assumed constant baro**, the
lean cut arms at 112.399 kPa absolute. All 20 captured pressure-qualified
samples read 11.09–12.11 AFR; none simultaneously satisfies the logged lean
or invalid-input condition. Runtime baro, lean-cut state and injector-inhibit
word were not captured, so this conditional check cannot exclude an unlogged
cut. The hard-overboost threshold is well above the capture's 117.717 kPa peak.

## Separate confirmed lean-cut reset defect: corrected

V2 sets arm/reset to **+2.5/+1.5 psi**. The old wrapper required reset to be
negative before releasing a latched cut. Instruction execution reproduced a
state-3 latch and injector inhibition remaining active at MAP 650 mmHg and
baro 760 mmHg, despite the engine being in vacuum.

The shared wrapper now requires **reset < arm**, accepting negative, zero or
positive reset settings and rejecting NaN or invalid ordering. It retains
the existing arming, confirmation, latch and stock-cut composition behavior.
Pressure, AFR, VE, AVLS and ignition calibration values are unchanged.

The regression first failed on the captured image, then passed after repair.
Five hysteresis tests cover the installed v2 settings, exact release boundaries,
invalid hysteresis, full arm/delay/trip/release, and simultaneous stock cuts.
Another 38 existing wideband, injector-gate, scheduler and interrupt tests pass
with the updated wrapper under the v1 calibration. Both rolling integrations
were regenerated because they share this component; each changes only 75
bytes in the lean wrapper and checksum relative to its preceding image.

The v2 verifier passes all five check groups. The full v1 verifier initially
stopped after its runtime checks at a pre-existing logger mismatch: its pin
predated the P30 target correction and manually added E524 pedal channel.
The follow-up diagnostic work below moved E524 into the canonical fragment,
preserved all 123 existing channel addresses/conversions/targets, and added
E525–E527. Generator, definition and verifier now agree; the **full v1 command
passes** as well. This logger repair changes no ROM bytes.

V2 immediately after the lean-reset repair had SHA
`c6528704472f396cf57c3d18b5e6ef14e46b6da376e9cf19f58f8739ca5c66bc` and
checksum `3FDAF389`. The user subsequently flashed it at 13:15 and captured
the neutral follow-up linked above. It fixes the release defect; it is not a
confirmed cure for the repeated high-lift misfire.

## Focused follow-up: AVLS output and actual cut state

Use the updated [complete logger definition](../../logger/D2WD610H_master_logger.xml)
and [AVLS/cut profile](../../logger/D2WD610H_avls_cut_diagnostic_profile.xml).
This selects 23 channels using 43 addresses, including both OSV duty/current
paths, both bank software copies, lean-cut state, the injector-inhibit word,
runtime baro, MAP, wideband, driver inputs, IAM and both knock corrections.
The [logger reference](LOGGER.md#native-avls-channel-verification) records the
native callback and capability-bit trace, verified through MCP and opcode
execution. The profile passes the real RomRaider offline packet/reload check.

The next vehicle step is **stationary diagnosis**:

1. Read and save stored/pending ECU fault codes before clearing anything or
   reflashing. Include any P0026/P0028 OSV range/performance codes. A code
   identifies the ECU's diagnostic result; absence of a code does not prove
   normal lift operation.
2. The rolling v2 BIN above includes the confirmed lean-cut release repair
   and keeps rotational idle removed. Use that file for the next flash if
   updating the car; the new profile itself needs no additional ROM changes.
   Keep the flash record with the capture so the reset behavior is identifiable.
3. With the engine warm and idling smoothly, record about 60 seconds using
   the focused profile. If it is already rough or shows an active fault, stop
   there for review. A steady low-lift baseline is useful for bank comparisons.
4. If the warm baseline is clean, make one gentle unloaded sweep through the
   approximately 3200-RPM changeover, then return to idle for about 30 seconds.
   Lift immediately if roughness starts; do not hold it in the misfire. An
   unloaded pass can check command/current response, but cannot clear the
   car's loaded high-lift calibration or ignition behavior.

Interpret the capture with these limits:

| Observation | Next branch |
|---|---|
| E504 reaches 3 and E525 shows global inhibition | Trace the lean-cut trigger using the simultaneously logged native MAP/baro/AFR. Check whether inhibition begins before or after the disturbance; a misfire can itself create a lean indication. |
| E525 indicates inhibition while E504 is not 3 | Trace the retained/native cut source; lean protection alone does not explain it. |
| Sustained bank-mode disagreement or unequal electrical response to comparable commands | Investigate the corresponding AVLS output/control path. Brief differences are expected from phase gates and non-atomic sampling. |
| Both output paths respond and no cut is sampled | Hydraulic lift, high-lift VE/fuel delivery and ignition remain open. A clean unloaded pass is not permission to keep driving through the loaded misfire. |

No software mode byte or solenoid current measurement proves physical valve
motion. No speculative VE increase, AVLS threshold move or timing increase
has been applied. Passing these checks does not establish a vehicle-validated
cure for the reported fault.

Reproduce the numerical review with:

```sh
python3 -B tools/analysis/analyze_20260912_avls_transition.py
# Add --plot in an environment with matplotlib for the comparison chart.
python3 -B master_patch_v2/verify_master_patch.py
```
