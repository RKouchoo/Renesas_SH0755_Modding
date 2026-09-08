# MAP source and barometric estimation — 2026-09-08

The installed SD wrapper reads sensor-converted MAP at `FFFFABC4`.
The supplied high-resolution MAP captures instead record **E51 / FFFFB2A0**,
the factory-processed MAP. This is a logging/analysis mismatch, not evidence
that SD should move to another source. The factory barometric path exists,
but does not clamp or overwrite ABC4.

No BIN, MAP calibration, SD fallback implementation, slow-negative multiplier
or 0.06 load filter changed. Logger channels and a separate diagnostic profile
were added. Runtime flags and independently measured pressure remain missing;
no single engine-recovery cause is established.

## Three pressure states

| State | Producer and consumers | Meaning |
|---|---|---|
| `FFFFABC4` | ADC converter `7A14`; SD input | Sensor voltage converted to native mmHg absolute |
| `FFFFB2A0` | Processing `1496C`; E51, retained fueling | Pressure-history selection or diagnostic load-derived substitute |
| `FFFFCFBC` | Selector `47DB2`; guards and compensation | Selected barometric estimate, currently from stored `FFFF8E04` |

The converter takes ADC copy `FFFFAB04`, from hardware `FFFFF804`, through
`FFFFABC8`. Coefficient `72818 = 256` passes the new count through exactly.
FMAC at `7A4A` applies voltage × multiplier + offset; `7A4C` writes ABC4.
`72810` contains −67.7766571 mmHg; `72814` contains 487.9919434 mmHg/V:

`MAP_kPa ≈ 65.06024 × volts − 9.03614`

All **65,536 ADC codes** execute through the unchanged native converter
and helpers with strictly increasing output. There is no 33.77-kPa floor.
Rounded ADC fixtures yield 10.481 kPa at 0.30 V, 16.989 at 0.40 V and 23.496
at 0.50 V. These are transfer results, not validation of physical accuracy
below the published sensor endpoints. Lowering the intercept shifts the
atmospheric and boosted readings too.

Electrical classifier `7A56` reports low input below approximately 0.30 V
and high input at or above approximately 4.921 V. SD's separate pressure gate
rejects below 100 mmHg / 13.332 kPa. Thus 0.30 V is electrically in range but
enters the fixed SD fallback at nonzero RPM. This remains a fault-path design
issue, not proof that the event occurred in a capture.

## Processed MAP can follow engine load

Normally `1496C` uses recent MAP extrema/history, a two-value average and a
delta selector; larger deltas can select current ABC4 directly. Even normal
processing can therefore separate the two channels.

With **D26C mask 0x10** set, getter `64FBC` returns 2 and `1496C` instead forms:

`intermediate_MAP_mmhg = (conditioned_load_B438 + 0.0851) / 0.00264`

B2A0 gets the average of this and the prior intermediate MAP. Native execution
with supplied load held at 0.58 g/rev demonstrates:

| Fixture | Settled B2A0 | ABC4 |
|---|---:|---:|
| Normal status; supplied source pressure 15 kPa | 15.000 kPa | 15.000 kPa |
| D26C/0x10; same pressure and load | 33.588 kPa | 15.000 kPa |

The diagnostic writer `63174`, at `63308..63390`, consults these current-status
records under its diagnostic-mode gate:

| DTC | Descriptor | Current status | Enable in saved candidate |
|---|---|---|---|
| P0068 | `5C5C0` | `8EA6 & 0x08` | `5BDB8 = 0` |
| P0107 MAP low | `5C50C` | `8E86 & 0x10` | `5BDAF = 1` |
| P0108 MAP high | `5C520` | `8E86 & 0x20` | `5BDB0 = 1` |

Classification alone does not establish diagnostic activation: debounce and
status producers are outside these execution fixtures. The exact 18:11
sample is 29.857 s, 992 RPM, E51 33.77 kPa and load 0.58 g/rev. Its proximity
to the equation is a lead, **not a flag measurement**. Only about 7% of that
capture's running samples agree within 0.015 g/rev. Rounding, asynchronous
reads and the native two-task average also limit this comparison.

**Definition correction:** D26F mask 0x40 makes shared getter `65168` return 2,
but the installed SD patch already redirects this load task's local helper
at `173FC` to constant-zero routine `27088`. The old stock substitution
`max(B2A0 × 0.00264 − 0.0851, 0)` is therefore bypassed in this task.
The first description of E522 overstated its effect on the patched task;
it now correctly describes diagnostic state retained for other consumers.
See [the existing implementation trace](GHIDRA_AUDIT.md). D26C's distinct
processed-MAP substitution remains intact. Moving SD to B2A0 would create
a possible load → MAP → SD → load feedback path. ABC4 is retained.

## Barometric mechanism

Selector `737D9 = 0` selects stored estimate `8E04`. `47DCC` prioritizes:

1. D26C/0x10: use 760 mmHg.
2. CFD0/0x80: sample ABC4 directly.
3. CFD0/0x40: filter B2A0 plus pressure-loss compensation CFC4.
4. CFD0/0x20: add 2.5 mmHg to the previous estimate.
5. Otherwise hold the previous estimate.

The result is clamped to **570..770 mmHg** (about 76.0..102.7 kPa), then
written by the native protected-float writer and selected into CFBC.
Supplying 15-kPa MAP with the sample flag produces 570-mmHg baro while
**ABC4 stays at 15 kPa**. The diagnostic flag selects 760-mmHg baro.
A running-learning fixture with prior baro 712, B2A0 680 and pressure loss 20
executes the native coefficient lookup and updates baro to 706 mmHg.

Sample and learning eligibility come from separate routines `47EA6/47F84`.
Their static trace does not validate their assumptions on the modified engine.
A biased estimate could affect guards and compensation, but does not explain
an ABC4 pressure floor. P24 reports a quantized estimate and cannot serve as
an independent reference for calibrating the MAP sensor.

## Correction to earlier SD conclusions

The 7,719-row / 12,928-call SD audit supplied **B2A0 as a proxy for ABC4**.
It was incorrectly described as replaying recorded SD inputs. The script and
report now qualify this. The 16.29-kPa minimum is processed MAP, not proof of
an ABC4 margin above the SD gate. No recorded airflow sample reaches 500 g/s,
but brief input/fallback events remain unresolved.

This applies to earlier SD predictions driven by logged MAP. The separate
slow-negative component replay remains valid within its stated limits: it
uses directly recorded B438 and compares directly recorded B874. See
[SD_FALLBACK_AUDIT.md](SD_FALLBACK_AUDIT.md).

## Logger and verification

The updated complete [logger definition](D2WD610H_master_logger.xml) and
separate [MAP-source profile](D2WD610H_map_source_diagnostic_profile.xml) record
both MAPs, MAP ADC voltage, selected baro, D26C/D26F/CFD0, RPM, airflow, load,
throttle, coolant, IAT, timing, CL/OL state, AVLS, B874, net pulse and AFR:
**19 channels / 43 addresses**. No BIN change is required. Old profiles retain
their selections and explicitly clear the new channels when loaded.

This prepares the missing measurement; it is not a recommendation to repeat
higher-RPM blips or a claim the fault is repaired. The profile does not latch
sub-sample events or make multi-byte RAM reads atomic.

Completed offline: all 65,536 ADC counts; 28 MAP/status cases; normal/fallback
step histories; 20 baro cases plus running learning with native lookup,
protected write, selector and caller-register preservation. XML/conversions,
deterministic generation and all profile budgets pass. The native SSM receiver
passes three acceptance/rejection groups. The installed RomRaider queue/reload
and A8 builder produce valid 136-byte requests for all five profiles, without
opening serial or starting a query thread.
The full `verify_master_patch.py` audit also passes, including all retained
execution groups, binary provenance, calibration and logger verification.

Reproduce with `audit_map_intercept.py` and `audit_map_sources.py`, each taking
`--output <report.json>`. Reports: [conversion](../logs/20260908_map_intercept.json),
[MAP/barometer](../logs/20260908_map_sources.json).
Candidate remains `2f80b8e5cb80361cdee170655bc26aa8ed8a41bcf4cd7f7249fe3f8c8eaa1f1c`.
Logger is `595ab35b02e995aec3a82f017a028c7a839c9c4df6ae2fa307caf62fdd8eaff8`.

The definition follow-up links both VE pressure axes to E518, retained
load/cranking pressure axes to E51, and the CL/OL barometric axis to E520.
These axes now display kPa absolute to match the selected logger conversions;
RomRaider forwards formatted logger values to highlighting without unit
conversion. MAP transfer rows now display kPa offset and kPa/V multiplier.
Only definition/display metadata changed; ROM storage addresses and BINs
remain identical. E51 and P24 are explicitly named processed MAP and
atmospheric-pressure estimate to prevent the prior source ambiguity.
