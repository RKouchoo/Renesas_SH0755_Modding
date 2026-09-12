# Logger definitions and capture evidence

[Reference home](README.md) · [Signal meanings](SIGNALS.md)

The complete definition is
[D2WD610H_master_logger.xml](../../logger/D2WD610H_master_logger.xml),
with the [E500–E527 fragment](../../logger/D2WD610H_master_logger_ecuparams.xml).
The complete definition SHA-256 is
`ea00d00a7fbe174c8292f4090bc01d939018725cb1637dcb11beaa52cfe5971f`.
The addresses and conversions of all 123 previously defined signals are
preserved. E524 is now generated from the canonical fragment and always
visible, matching the other project parameters. E525–E527 expose existing
injector and AVLS state; they allocate no RAM and require no ROM change.
Both current integrations include the [local load-fallback repair](V2_LOAD_FALLBACK_FIX.md).

## Native request budget

All seven generated profiles use **43 address bytes** in each worst-case selected
request. The A8 frame is 136 bytes at that budget. Native receiver `32CA4`
has a receive-index limit of 137; 44 addresses do not fit. An accepted profile
file does not establish that the ECU accepts its request size.

The separate local RomRaider queue/reload defect could leave ticked channels
out of a request. It produced CSV headers without corresponding data before
the local application fix/restart. Request construction was checked offline;
no serial connection was opened during this audit.

| Profile | Purpose |
|---|---|
| [AVLS and fuel cut](../../logger/D2WD610H_avls_cut_diagnostic_profile.xml) | Both bank output paths, software modes, lean-cut state and injector inhibition; retains IAM and both knock corrections. See the [23-channel budget](../../logger/README.md#avls-and-cut-diagnosis). |
| [Road tuning](../../logger/D2WD610H_road_tuning_profile.xml) | IAM, feedback/learned knock, timing, native SD MAP, load and fueling, with speed, pedal and throttle. See the [18-channel budget](../../logger/README.md). |
| [Idle](../../logger/D2WD610H_idle_diagnostic_profile.xml) | General idle running signals. |
| [After-start](../../logger/D2WD610H_afterstart_diagnostic_profile.xml) | Separate early-running fuel components. |
| [Recovery](../../logger/D2WD610H_idle_recovery_profile.xml) | Pedal, signed transient correction, base factor and lift state. |
| [Idle air](../../logger/D2WD610H_idle_air_diagnostic_profile.xml) | Effective idle request, combined throttle request, pedal and feedback flags. |
| [MAP source](../../logger/D2WD610H_map_source_diagnostic_profile.xml) | ABC4, B2A0, ADC, selected baro and relevant flags together. |

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
| E522 | `FFFFD26F`, u8 | Native airflow diagnostic flags; both current builds bypass the local load-task consumer. |
| E523 | `FFFFCFD0`, u8 | Barometric sample/learning flags. |
| E524 | `FFFFB46C`, float percent | Conditioned accelerator pedal. |
| E525 | `FFFFB744`, u16 | Native injector-inhibit word; bits 0–5 select channels and 65535 inhibits all. |
| E526 | `FFFFCD89`, u8 | AVLS bank-index-0 software mode; same index as P123/P125. |
| E527 | `FFFFCD8A`, u8 | AVLS bank-index-1 software mode; same index as P124/P126. |

E51 is **processed MAP B2A0**, not SD's direct input. P24 is a quantized
atmospheric estimate, not an independent physical reference. Raw pedal uses
AB08/AB0A, while P30's conditioned pedal is B46C. Neither is wideband AB06.

## Test-mode indication and diagnostic cuts

Use standard **S2 Test Mode Signal**, SSM byte `61` bit 5. The complete
handler at `31A34` calls `19BE2`, which reads `B51E/80`. Generic **S70** at
byte `61` bit 1 remains clear in this ROM's handler. Both are inherited
standard definitions; S70 is not evidence that the connector is disconnected.
The input-poll and S2 mapping are now traced in
[MCP evidence](evidence/native_fault_cut_20260912.json).

`B744=003F` also inhibits all six injector channels; 65535 is not the only
all-six cut value. The separate native diagnostic path can produce 003F
at 3000 RPM under `D273/02`, with release below 2500. Standard P21 is
`round((C0B8 + C0D8)/256)` byte counts, displayed at 0.256 ms per count:
scheduled pulse **after** its record-inhibit check, plus independent latency.
A settled cut zeros C0B8 but leaves latency in P21. P21 must not be described
as entirely upstream of inhibition. Sustained 9–10 ms readings argue against
a continuous all-six cut after scheduler convergence; short/intermittent cuts
and actual electrical delivery remain outside that inference. An empty DTC
scan also does not directly measure the immediate cut request.
The [loaded-fault review](V2_AVLS_MISFIRE_20260912.md#all-cylinder-cut-test-connector-and-empty-dtc-scan)
explains why this path is not established as the cause of the latest drive.

## Native AVLS channel verification

[Saved checks and MCP comments](evidence/avls_logger_20260912.json) record the
image identity, sample callback results and Ghidra updates.

Standard SSM callback entries are u32 pointers at `4B6FC + 4*address`.
The following callbacks and their conversion literals are identical in stock
and current v2. Direct opcode execution with distinct bank inputs confirms
their address selection and scaling through native `258C`.

| ID / standard address | Callback | Source and conversion |
|---|---|---|
| P122 / `113` | `3253C` | `B124` converted oil temperature; byte = C + 40. This precedes fallback selection into CF94. |
| P123 / `114` | `3254A` | `CDF8` bank-index-0 duty percent; byte step approximately 100/255 percent. |
| P124 / `115` | `32558` | `CDFC` bank-index-1 duty percent; same scaling. |
| P125 / `116` | `32566` | `F298(0)` reads B11C amps; 32 mA per byte count. |
| P126 / `117` | `3257C` | `F298(1)` reads B120 amps; same scaling. |
| P127 / `11E` | `32592` | `CD86` software mode; the new profile instead uses direct E503. |

`F39C` copies raw AB24/AB1E into B118/B11A, then produces current floats
B11C/B120 using `max(0, ADC * 5/65536 * 72858 + 7285C)`. Installed slope and
offset are approximately 0.334 A/V and −0.035 A. `40CE6` publishes CDF8/CDFC
duty through `F12A(0/1)`. Upstream Right/Left labels therefore match software
indices 0/1; physical harness pin assignment remains a separate question.

Init-response builder `332B6` reads the pointer table at `4C458`. Capability
byte 42 is `7BDCF = FF` (P122–P126 bits 4–0 set); byte 43 is `7BDD0 = 02`
(P127 bit 1 set). RomRaider's capability indexing and the actual native
callbacks both support these channels. Ghidra comments were updated through MCP.

Offline checks passed for all seven profiles, native SSM receive execution,
the full main verifier and the five-group v2 verifier. The local RomRaider
query manager and packet builder also accepted AVLS/cut, recovery and road
profiles after remove/re-add reload, producing 136-byte requests with valid
checksums. No serial connection was opened. A brief cut or phased transition
can still occur between samples; software permission and coil current do not
measure actual valve motion or delivered fuel.

## What the historical captures establish

The [12:36 review](../../logs/archive/20260908_idle_review.md) ties its capture to the
10:30 `48d63c…` image. The [14:13 review](../../logs/archive/20260908_recovery_review.md)
ties its capture to the `6af0d1…` ten-cell VE image; near-stalls remained despite
improved settled fueling. The [later review](../../logs/archive/20260908_dashpot_review.md)
uses the user's independent experiment and remains historical evidence.

Earlier SD replays that supplied B2A0 as a proxy for ABC4 are not recordings of
the actual SD inputs. Their observed pressure minima cannot prove margin to
SD's validity gate. The B438-to-B874 replay uses those directly logged channels
and retains its separate validity. No recorded airflow sample at 500 g/s does
not rule out an event shorter than the sampling interval.

The profiles do not latch brief faults, measure electrical injector duration,
make float reads atomic or expose every actuator override. These limits are
why code findings and physical conclusions remain separate in this reference.
