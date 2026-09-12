# September 12 neutral AVLS captures: oil-gate repair and warm fueling

[Reference home](README.md) · [Earlier loaded misfire](V2_AVLS_MISFIRE_20260912.md) · [Derived data](../../logs/20260912_avls_neutral_review.json)

**Later result:** the [14:42 drive](V2_AVLS_MISFIRE_20260912.md#1442-adjusted-ve-drive-loaded-fault-persists)
confirms the adjusted image was flashed and the loaded bog persists.
No further captures are requested; the stationary observations below are
not evidence that the loaded fault is fixed.

The later [pump-demand scaling correction](FUEL_PUMP_SCALING_20260912.md)
advances both rolling BINs. Hashes below identify the historical captures and
VE adjustment; [Images](IMAGES.md) lists the current artifacts.

The **14:13 warm fueling capture reproduces the rich high-lift hold** at
82–85 C coolant with reported fuel-system status 7 throughout. Transient
enrichment ends before the sustained AFR near 12.1. Logged load and gross
injector duration rise together. This strengthens the high-lift vacuum VE
calibration lead; it does not establish the cause of the earlier loaded
misfire. Following review, the user requested the VE adjustment below.

## Requested idle and high-lift fueling adjustment

The v2 ROM produced by this VE adjustment had
SHA-256 `fd795813febf817c845fc922e81e498539a539efeeb6e4d11822af47098094a2`,
checksum **43191A9F**. It changes **34 byte positions** relative to the
captured `4808414b…` image: ten VE cells and the checksum. The v2 generator
contains the correction, so rebuilding preserves it. V1 is unchanged.

| Table / knot selection | Adjustment | Reason |
|---|---:|---|
| Low lift: 800 and 1200 RPM; 150 and 250 mmHg | +5% VE, four cells | Settled idle at 860–875 RPM / 29–30 kPa reads about 15.6 AFR initially and 15.1 later. |
| High lift: 3000, 3200 and 3500 RPM; 250 and 350 mmHg | −12% VE, six cells | Both warm high-lift vacuum holds settle near AFR 12.1 after transient enrichment ends. |

The full high-lift ratio correction toward `14.64/1.01` would be about
−16.5%; this first adjustment removes 12%. The 3000-RPM hysteresis row gets
the same percentage as 3200 RPM. Native interpolation blends toward the
unchanged 150/450-mmHg and 4000-RPM high-lift knots. Idle enrichment blends
toward the unchanged 500/1600-RPM and 350-mmHg knots. These are table
regions, not new runtime RPM/MAP gates: some effect extends between the
edited knots and their neighbours. The correction changes no boost-region
cells, timing-table bytes, target-AFR tables, injector calibration, filters,
cut protections or CL/OL policy. SD-derived load also feeds timing and AVCS;
their selected operating points can move even with unchanged table bytes.

The [saved adjustment evidence](../../logs/20260912_fueling_adjustment_review.json)
records every cell address, old/new value and original four-byte word.
Its actual-wrapper replay predicts +5% calculated airflow at the captured
idle points and roughly −10.8% to −12% during the high-lift holds. **If
physical air and other fuel factors stayed fixed**, that corresponds to
median AFR around 14.4–14.85 at idle and 13.74–13.75 on high lift. These are
conditional estimates, not measured post-change AFR or an engine simulation.
Using steady-state AFR error to adjust the base VE surface follows the
[manufacturer's VE tuning method](https://support.haltech.com/portal/en/kb/articles/tuning-base-tables);
the particular percentages here come from this ROM and capture, not a
Haltech calibration applied to the Subaru ECU.

All six v2 offline verifier groups pass. The independent adjustment check
confirms the ten-cell/checksum-only byte scope, executes 203 captured
steady points on both images, verifies 102 unaffected airflow controls,
and checks increasing modeled airflow across the high-lift vacuum blend.
The old 13:16/13:37 capture images remain reconstructable to their exact
SHA-256 values, without adding another selectable ROM file.

The next physical comparison is on this updated image, using the existing
road-fueling profile: warm stationary idle and a gentle neutral high-lift
hold comparable to the source capture. This adjustment has not been flashed
or vehicle-tested here. It does not establish a cure for the earlier loaded
misfire near 112–115 kPa.

```sh
python3 -B master_patch_v2/build_master_patch.py
python3 -B master_patch_v2/verify_master_patch.py
python3 -B tools/analysis/analyze_20260912_fueling_adjustment.py
```

## 14:13 warm fueling: sustained enrichment follows calculated load

The [source CSV](../../logs/romraiderlog_neutralfuelingtest_20260912_141321.csv)
has SHA-256 `fae81a50f56f74c2d6d725db1ec1619e409e1e821324dae6328d817dde226dff`:
618 complete, finite samples over 64.203 s, with monotonically increasing time.
All 16 blocks in the latest pre-capture FastECU verification, at 13:37:18,
match the captured, pre-adjustment `4808414b…` v2 image listed below. Vehicle speed stays zero;
IAM stays 1 and both logged knock corrections stay zero. This profile omits
injector inhibition and added lean-cut state, so their absence cannot be
established from this capture alone.

Values below are medians over the stated windows:

| Window | RPM | MAP, kPa absolute | Load, g/rev | B7DC factor | B874 transient | Gross pulse, ms | AFR |
|---|---:|---:|---:|---:|---:|---:|---:|
| Low lift, 24.554–25.074 s | 3154.5 | 33.533 | 0.57 | 1.01 | 0 | 2.56 | 15.595 |
| First high-lift hold, 28–31.85 s | 3306 | 39.251 | 0.71 | 1.01 | 0 | 3.07 | 12.10 |
| Second high-lift hold, 49–52.15 s | 3486 | 39.886 | 0.73 | 1.01 | 0 | 3.07 | 12.10 |

Pedal and throttle plate remain 9.8% / 14.9% across the first comparison.
Both high-lift holds have IAT 39 C. First sampled high-lift entries are
25.177 and 45.996 s; short positive transient corrections peak near +0.065
and +0.062, then return to zero by 26.638 and 47.246 s respectively.
They cannot explain the later sustained rich holds.

Replaying the SD wrapper with logged RPM, MAP, IAT and committed mode gives
median raw loads of 0.7089 and 0.7305 g/rev in the two settled windows.
Median absolute differences from logged conditioned load are 0.0052 and
0.0043 g/rev. Primary A/B table lookups using actual logged load/RPM add
zero in the first window and at most 0.00249 in the second. Neither result
reveals a commanded AFR-12 step or an SD arithmetic fault. The observations
support an airflow-calibration mismatch around 3200–3550 RPM and 39–40 kPa;
they do not uniquely identify individual VE cells or justify a boost-region
adjustment. A measured rich mixture also does not independently measure
cylinder air or delivered fuel.

### Open-loop status and fuel-factor interpretation

E33 reads the second-bank status byte `DA4E` and displays `x+6`. All 618
samples display **7**, with no reported CL transition. Native updater
`4EF96` retains raw status 1 while that bank has not entered CL, even after
warm-up. Thus the logger's generic “insufficient ECT” label does not prove
that 82–85 C coolant was insufficient. The status is not a bank-trim reading.
The native routine and its updated Ghidra annotation are retained in
[MCP evidence](evidence/neutral_fueling_status_20260912.json).

B7DC/E123 is the composed **additive fueling factor**, including primary and
transient terms. It is upstream of separate multiplicative bank corrections
and the hot-IAT factor. Consequently 1.01 must not be called measured CL
feedback, nor does it prove that every unlogged correction equals unity.
The actual-opcode composer cases in
[the existing fueling suite](../../tests/test_primary_fueling_execution.py)
exercise those terms independently.

The older turbo-table document incorrectly treated front-sensor retirement
as proof of permanent OL. The wideband component retains native feedback
consumers and valid-input readiness; the fueling-safety component forces OL
near barometric pressure, not at every load. This capture reports OL, but a
global permanent-OL guarantee has not been established. No active CL switch
is evidenced as the cause of this rich step. Further OL tracing or an
identical neutral capture is not needed to establish these observations.

## Earlier command/current checks

The **13:37 follow-up confirms two stationary high-lift transitions** on the
corrected v2 image. Both bank software modes follow and both solenoid current
channels respond. The driver reports that it felt fine. No injector inhibition
or knock correction is sampled during the pedal-applied transitions. This
completes the stationary command/electrical check; loaded operation remains
unvalidated. No further BIN or calibration change was made from this capture.

The earlier **13:16** run stayed in low lift throughout. It exposed a concrete
calibration mistake: the
patch had raised two **stationary oil-temperature thresholds** from stock
15 C to 110 C after misidentifying them as pedal thresholds. The rolling v1
and v2 builds now restore both values to 15 C. The loaded misfire remains
unresolved; this correction allows the intended stationary changeover check.

## 13:37 follow-up: changeover now occurs

- [Source CSV](../../logs/romraiderlog_avlslog2_20260912_133746.csv), SHA-256
  `d7252e1205e2ad8e8c4106dc166747c3ce2ac091de86c1d4428af5969ad57fd0`.
- 1,676 complete, finite samples over 174.267 seconds; median interval 104 ms.
  All 24 CSV columns match the earlier capture, including time. Speed is zero
  throughout; peak RPM is 3412.
- All **16** pre-capture FastECU post-flash block CRCs at **13:37:18** match
  current v2 SHA `4808414b01f3ede952197422f75a791f5325595a27bc810ca610b82d3954d67e`.
- [Derived follow-up JSON](../../logs/20260912_avls_neutral_followup_review.json)
  retains transition summaries, cut/invalid windows and the conditional replay.

| Observation | First pass | Second pass |
|---|---|---|
| First sampled committed mode 3 | 127.222 s | 138.370 s |
| First sample with both bank copies at 3 | 127.326 s | 138.475 s |
| Last committed mode-3 sample | 130.557 s | 143.374 s |
| Settled current, Left / Right | 992 / 992 mA | 992 / 960–992 mA |
| Settled duty, Left / Right | 64.7 / 65.1% | 64.7 / 65.1% |
| Settled AFR median with pedal held | 12.57 | 12.10 |

The initial current pulses reach 1504 mA Left and 1440 mA Right, then settle
near 1 A. The preceding low-lift baseline is 192 mA on both channels. There
are only three rows where bank copies and committed mode differ, all at
changeover boundaries. Phase-gated scheduling and non-atomic SSM sampling
limit timing interpretation; the one-row differences are not measurements
of hydraulic delay. Software mode and electrical current do not prove actual
valve lift.

IAM is 1 throughout both passes, FBKC/FLKC are zero, and both injector inhibit
and added lean-cut state are zero. After the final pedal release, inhibit is
63 for six rows at 143.479–144.002 s, then clears at 1764 RPM. This fits native
overrun cut, with the individual source flags unlogged. RPM returns below
1000 at 145.251 s and stays running until the final shutdown sequence; the
lowest RPM before shutdown is 834. Global inhibition begins at 171.564 s as
the engine winds down, with key-off itself unlogged.

AFR zero at 1.143–7.278 s and three rows at 144.628–144.835 s is the patch's
invalid-data sentinel. The latter follows the overrun/lean excursion; it
cannot be assigned an exact AFR or called a serial dropout from this log.
Oil reaches only 56 C and coolant 61 C, so this is not a fully warmed test.

## Why AFR becomes richer after high lift

The repeatable measured sequence is a pressure rise and more calculated
injector duration despite nearly unchanged pedal/plate. For representative
rows just before entry and about two seconds afterward:

| Pass | MAP, kPa absolute | RPM | Gross pulse, ms | AFR |
|---|---|---|---|---|
| First: 127.118 → 129.306 s | 37.396 → 43.381 | 3154 → 3313 | 2.82 → 3.33 | 15.59 → 12.58 |
| Second: 138.267 → 140.455 s | 38.615 → 44.600 | 3138 → 3362 | 2.82 → 3.33 | 15.58 → 12.08 |

The SD-wrapper instruction replay, with recorded MAP/RPM/mode and IAT held
at an explicit fixture, increases **modeled raw air per revolution by 23.0%
and 24.0%**. Holding IAT at 0, 25 or 60 C gives the same relative increase.
Those temperatures are sensitivity fixtures: IAT and conditioned load were
not logged. The pressure rise and the VE surface account for most of the
modeled increase; changing only the mode at an unchanged operating point
does not produce a comparable step. The 18% increase in gross pulse includes
unlogged injector latency and must not be equated exactly with fuel mass.

This makes the SD estimate/high-lift VE calibration a leading explanation
for this **light-load richening**: the model can request more fuel than the
actual cylinder air requires after the pressure change. It is not yet proof
of a particular bad VE cell, an appropriate percentage adjustment, or the
cause of the earlier loaded misfire.

Two ROM checks narrow the explanation:

- Native primary routine `22454` looks up A/B using **B438 conditioned load
  and RPM**, not a direct high-lift target selector. At the illustrative raw
  loads above, both current tables give approximately 13.93–14.64 AFR across
  the three IAT fixtures, rather than the observed 12–12.6. These are table-only
  outputs, not reconstructed live targets; native delays, feedback, transients
  and other corrections are not reproduced by this comparison.
- The added pressure-forced-OL threshold is about **91.715 kPa absolute** at
  the recorded baro. High-lift MAP peaks at 46.189 kPa, so its pressure
  comparison cannot cause this transition. Native CL/OL status was not logged.

The separate native `207AC` auxiliary feedback-entry branch does read CD86,
but stock and current v2 both have its counter bounds `75E62/75E64 = 0/0`.
Its strict lower/upper interval is empty and it publishes B908 zero. That
branch does not supply this rich step. The relevant Ghidra comments were
updated and read back through MCP; see [saved notes](evidence/avls_neutral_followup_20260912.json).

The remaining distinction is between an airflow-estimation error and the
contribution of native fuel corrections/loop state. The existing road-tuning
profile includes load, IAT, composed fuel factor, signed transient correction
and CL/OL status for that question. This capture uses the AVLS/cut profile
instead and cannot supply those missing values retrospectively.

## 13:16 baseline capture and firmware identity

- [Source CSV](../../logs/romraiderlog_avlslog_20260912_131657.csv), SHA-256
  `77863ac12f459d1092aba57f0d65cded033d1730c600c4ac6d1f550051a42265`.
- 1,278 complete samples, 23 selected channels, 132.816 seconds, median
  interval 104 ms. Vehicle speed is zero throughout.
- Captured ROM SHA-256
  `c6528704472f396cf57c3d18b5e6ef14e46b6da376e9cf19f58f8739ca5c66bc`.
  All 16 FastECU post-flash block CRCs at **13:15:38–13:15:42** match this
  image. This is the lean-reset repair with rotational idle removed.
- Source flash record: `log_fastecu_2026-09-12_11h31m48s.txt` in the local
  FastECU syslogs directory. The analysis selects the last verification before
  the capture, so a later flash does not silently change its identity.

## What the 13:16 baseline establishes

| Signal | Observation |
|---|---|
| RPM | Peak **3442**; 26 samples at or above 3200 RPM, from 101.084 to 103.688 s. |
| Committed mode and both bank copies | **1 throughout**, with no high-lift entry. |
| Both OSV current channels | **192 mA** throughout the pedal-applied high-RPM portion. |
| OSV duty | Right **16.1%**, left **15.7%**, steady in that same portion. |
| IAM / knock | IAM **1** during the rev; FBKC and FLKC **0**. IAM returns from startup 0 to 1 at 61.356 s. |
| Added lean cut | State **0 throughout**. |
| Injector inhibition | **0 while revving with pedal applied**. |
| Temperatures | Converted oil 48–51 C and coolant 49–55 C; oil is about 50 C during the rev. |
| Pressure | Selected baro 95.162 kPa throughout. Native MAP reaches 7.150 kPa during lift-off; this channel is not clamped at the historical claimed 33.77-kPa floor. |

There are two inhibitor windows. At **103.793–104.314 s**, after pedal release,
the word is **63** (six low channel bits set), then clears at 1778 RPM. This
fits native overrun cut; its individual source flags were not logged. At
**131.049 s** the word becomes 65535 as the engine winds down to zero at the
end of the capture. That is consistent with intentional shutdown; key-off
itself is not a logged channel. Neither event is an added lean-cut latch.

The balanced current/duty readings establish a low-lift electrical baseline.
They are not evidence that either bank completed a high-lift hydraulic change.
P21 remains a calculated gross pulse channel, and the new inhibit word is a
software gate, not measured injector delivery.

## The confirmed calibration error

The native state machine at `40168` reads:

| Instruction | Operand |
|---|---|
| `40228` | RPM from `B544` into FR15. |
| `4022A` | Vehicle speed from `B538` into FR13. |
| `40232` | Conditioned pedal from `B46C` into FR14. |
| `40264` | Selected oil temperature from `CF94` into **FR6**. |
| `40396` / `4039A` | Scalar `7D4B0` / `7D4B4` into **FR5**, selected by `19C68` / B51C bit 7. |
| `403C4` | `fcmp/gt FR6,FR5`: compares **oil temperature** with the selected scalar. |

With the normal stationary qualifier (`148EE` returns 0 and B538 < 1 km/h)
and RPM latch CD9E/04 set, the path reaches this comparison. If oil is below
the scalar it writes requested mode 1 at `403D4`; otherwise it writes mode 3
at `403CA`. `405B2` then copies the request to committed CD86. Moving normal
operation can select high lift through a different path without this comparison.

The old helper named these addresses `AVLS_FIXED_PEDAL_A/B_ADDR` and wrote
the pedal-disable value **110** to both. Existing audits verified that chosen
byte policy without executing this operand comparison. That identity and
its old “verified” address-index entries are retracted.

The actual pedal curves at `7D67C/7D6B4` remain 110 percent. The RPM band
remains 3200 engage / 3000 release. Only the two misidentified scalars return
to their stock 15 C values; native cold/fault conditions remain active.

## Execution evidence and corrected artifacts

The new [native AVLS tests](../../tests/test_avls_oil_gate_execution.py) execute
the state machine, its diagnostic/stationary getters and committed-mode copy.
Table interpolation, upstream selector state and three unlogged qualifier
returns are explicit fixtures. There is no hydraulic or engine model.

| Fixture at 3400 RPM / 50 C oil | Old 110 C scalars | Restored 15 C scalars |
|---|---:|---:|
| Stationary | Low lift, mode 1 | High lift, mode 3 |
| Moving at 30 km/h | High lift, mode 3 | High lift, mode 3 |

Independent oil/pedal sweeps verify both scalar selections and exact equality
boundaries. Other cases cover cold oil, the native low-lift fault override and
the 3200/3000 RPM hysteresis sequence. Four test groups failed against the
captured image; all five pass after correction. The full v1 verifier and all
six v2 verifier groups pass, with the new regression integrated into both.

| Artifact after the oil-gate repair, before the later v2 VE adjustment | SHA-256 | Checksum |
|---|---|---|
| [V2 BIN](../../master_patch_v2/D2WD610H_master_patch_v2.bin) | `4808414b01f3ede952197422f75a791f5325595a27bc810ca610b82d3954d67e` | `42B2F389` |
| [V1 BIN](../../master_patch/D2WD610H_master_patch.bin) | `db33aad398d6335411c36f5c0e0f1338095b89821a4111370f5d16101fcf6089` | `B3B44EC0` |

Each differs from its preceding rolling image at only **six byte positions**:
`7D4B0`, `7D4B1`, `7D4B4`, `7D4B5`, `7FB88`, `7FB89`. No executable code,
VE cell, timing cell, load filter or fueling threshold changes in this repair.
Editor descriptions now distinguish the RPM latch from native eligibility
gates. Ghidra comments were updated through MCP and the state-machine comments
read back; [saved evidence](evidence/avls_oil_gate_20260912.json) records this.

## 13:37 decision, before the warm fueling capture

The requested stationary command/current check is complete, and the driver
reports that it felt fine. No new BIN, speculative VE change or protection
change follows from this log. The earlier loaded fault occurred around
112–115 kPa; the neutral high-lift portion reaches only 46.189 kPa. Loaded
fueling, ignition and hydraulic behavior therefore remain unvalidated.

The earlier neutral instruction overlooked the incorrect oil gate. The
13:16 capture provides its low-lift baseline, and the 13:37 capture verifies
the correction's stationary effect. It does not establish a cure for the
loaded misfire or justify driving through it.

```sh
python3 -B tools/analysis/analyze_20260912_avls_neutral.py
python3 -B tools/analysis/analyze_20260912_avls_neutral.py --followup
python3 -B tests/test_avls_oil_gate_execution.py
python3 -B tests/verify_master_patch.py
python3 -B master_patch_v2/verify_master_patch.py
```
