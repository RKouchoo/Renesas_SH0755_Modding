# Logger definitions and capture evidence

[Reference home](README.md) · [Signal meanings](SIGNALS.md)

The complete definition is
[D2WD610H_master_logger.xml](../../master_patch/D2WD610H_master_logger.xml),
with the [E500–E523 fragment](../../master_patch/D2WD610H_master_logger_ecuparams.xml).
The complete definition SHA-256 is
`595ab35b02e995aec3a82f017a028c7a839c9c4df6ae2fa307caf62fdd8eaff8`.
Their RAM addresses and storage formats remain compatible with the saved v2
image. This does not make main-only explanatory assumptions, such as the
`173FC` load-fallback bypass, true for v2.

## Native request budget

All five shipped profiles use **43 address bytes** in each worst-case selected
request. The A8 frame is 136 bytes at that budget. Native receiver `32CA4`
has a receive-index limit of 137; 44 addresses do not fit. An accepted profile
file does not establish that the ECU accepts its request size.

The separate local RomRaider queue/reload defect could leave ticked channels
out of a request. It produced CSV headers without corresponding data before
the local application fix/restart. Request construction was checked offline;
no serial connection was opened during this audit.

| Profile | Purpose |
|---|---|
| [Idle](../../master_patch/D2WD610H_idle_diagnostic_profile.xml) | General idle running signals. |
| [After-start](../../master_patch/D2WD610H_afterstart_diagnostic_profile.xml) | Separate early-running fuel components. |
| [Recovery](../../master_patch/D2WD610H_idle_recovery_profile.xml) | Signed transient correction, base factor and lift state. |
| [Idle air](../../master_patch/D2WD610H_idle_air_diagnostic_profile.xml) | Effective idle request, combined throttle request, pedal and feedback flags. |
| [MAP source](../../master_patch/D2WD610H_map_source_diagnostic_profile.xml) | ABC4, B2A0, ADC, selected baro and relevant flags together. |

## Added parameter register

All RAM addresses below include the full prefix, while the XML uses the
24-bit SSM representation. This table is also checked against the fragment by
the main verifier.

| ID | RAM / storage | Meaning |
|---|---|---|
| E500 | `FFFFB098`, float | Wideband lambda; AFR display multiplies by 14.64. Zero is a fault sentinel. |
| E501 | `FFFFAB06`, u16 | Wideband raw ADC; volts = word × 5/65536. |
| E502 | `FFFFAE70`, float | Synthetic sensor readiness. |
| E503 | `FFFFCD86`, u8 | Committed AVLS mode. |
| E504 | `FFFFC860`, u8 | Lean-cut state. |
| E505 | `FFFFC85C`, u16 | Lean confirmation/delay counter. |
| E506 | `FFFFBE38`, u8 | CL/OL flags. |
| E507 | `FFFFB688`, u16 | Engine-run counter; time conversion uses nominal 8-ms ticks. |
| E508 | `FFFFB834`, float | After-start group A. |
| E509 | `FFFFB854`, float | After-start group B. |
| E510 | `FFFFB868`, float | Retained startup-related compensation. |
| E511 | `FFFFB874`, float | Signed transient load-change fuel correction. |
| E512 | `FFFFBE40`, float | Group C enrichment. |
| E513 | `FFFFBE48`, float | Group D enrichment. |
| E514 | `FFFFC468`, float | Effective idle RPM request. |
| E515 | `FFFFC2B8`, float | Combined relative throttle request; percent = x/0.84. |
| E516 | `FFFFB2BC`, u8 | Debounced throttle/idle flags. |
| E517 | `FFFFC4D9`, u8 | Idle-air feedback flags; bit 3 permits feedback. |
| E518 | `FFFFABC4`, float | ADC-derived MAP, mmHg absolute or kPa via ×0.1333224. SD uses this channel. |
| E519 | `FFFFAB04`, u16 | MAP raw ADC, optionally displayed as volts. |
| E520 | `FFFFCFBC`, float | Selected atmospheric estimate; same pressure conversion. |
| E521 | `FFFFD26C`, u8 | Diagnostic flags including processed-MAP substitution. |
| E522 | `FFFFD26F`, u8 | Diagnostic flags including the retained v2 load fallback. |
| E523 | `FFFFCFD0`, u8 | Barometric sample/learning flags. |

E51 is **processed MAP B2A0**, not SD's direct input. P24 is a quantized
atmospheric estimate, not an independent physical reference. Raw pedal uses
AB08/AB0A, while P30's conditioned pedal is B46C. Neither is wideband AB06.

## What the historical captures establish

The [12:36 review](../../logs/20260908_idle_review.md) ties its capture to the
10:30 `48d63c…` image. The [14:13 review](../../logs/20260908_recovery_review.md)
ties its capture to the `6af0d1…` ten-cell VE image; near-stalls remained despite
improved settled fueling. The [later review](../../logs/20260908_dashpot_review.md)
uses the user's independent experiment and remains historical evidence.

Earlier SD replays that supplied B2A0 as a proxy for ABC4 are not recordings of
the actual SD inputs. Their observed pressure minima cannot prove margin to
SD's validity gate. The B438-to-B874 replay uses those directly logged channels
and retains its separate validity. No recorded airflow sample at 500 g/s does
not rule out an event shorter than the sampling interval.

The profiles do not latch brief faults, measure electrical injector duration,
make float reads atomic or expose every actuator override. These limits are
why code findings and physical conclusions remain separate in this reference.
