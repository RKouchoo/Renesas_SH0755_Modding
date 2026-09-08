# D2WD610H logger connection and missing-data audit — September 8, 2026

The combined diagnostic profile was too large for the stock ECU receiver.
The earlier 84-address validation checked the SSM payload field but missed
this ROM's smaller receive buffer. Both the 79- and 83-address profiles were
invalid for this receiver. The later missing-data log also exposed a RomRaider
selection-queue bug. Both fixes are on the logging side; no ROM or adapter
firmware change was made.

## Observed failure

`~/.RomRaider/rr_system.log` at 12:00:55 records successful identification of
ECU `3C5A387116`, followed by an A8 continuous-read request with 83 byte
addresses: a 251-byte payload and **256-byte complete frame**. At 12:00:57,
the timeout log contains only the complete outgoing request echo, with no
ECU data response.

RomRaider's `SerialConnectionManager.send` returns on timeout without filling
the preallocated response array. `SSMResponseProcessor` then removes the
expected echo length and checks the remaining zero-filled array, producing
`Invalid header. Expected: 80. Actual: 00.` The log does not show the ECU
transmitting a zero header. Local upstream source is in `/tmp/RomRaider-src`.

An initial 81-address/250-byte retry was prepared before the native trace
finished. It is also too large and is superseded by the profiles below.

## Native limit

Stock `32CA4` consumes one received byte from `FFFFC7A4`. Its receive index is
the byte at `FFFFC7A9`, checksum accumulator is `FFFFC7AA`, and buffer starts
at `FFFFC7B4`.

- `32CBA` loads the index ceiling from `32D90`: **0x0089 / 137**.
- `32CE4..32CF8` and `32DC4..32DD6` increment through actual saturating-byte
  helper `2534`, then clamp the result to 137.
- `32D02..32D0E` compares the receive index with the unsigned payload length
  plus four. Only that exact index reaches checksum/header validation and
  accepted-command decode `32FEC`.
- For an A8 request with N byte addresses, payload length is `2 + 3*N`, the
  checksum index is `6 + 3*N`, and complete frame length is `7 + 3*N`.

Thus **N <= floor((137 - 6)/3) = 43**. A 43-address frame has 136 bytes and
checksum index 135. At 44 addresses, the checksum index would be 138, which
the receiver cannot reach. Larger packets keep overwriting the capped buffer
slot and never reach command decode. This is not a 256-byte-only boundary.
The traced code and literals are unchanged between stock and the master BIN.

`test_ssm_receive_execution.py` runs actual `32CA4` and `2534` instructions:

- 1-, 21-, 40-, 42- and 43-address requests reach command decode and transmit
  setup, then reset the receive index.
- 44-, 79-, 81-, 83- and 84-address requests reach neither boundary; their
  receive index stays at 137. The new profile budget check rejects them.
- A bad checksum or destination is rejected even at an otherwise valid size.

UART input is scripted. Diagnostic-mode helper `474AE` returns normal mode;
accepted-command decode `32FEC` and transmit setup `32F74` are recorded
boundaries. This proves the instruction-level receive-size gate, not a live
serial connection or peripheral timing. All three groups run in the master
verifier.

## Replacement captures

`logger_profiles.py` generates two separate profiles. Each selects the same
channels in Data and Dashboard and explicitly deselects the other capture's
entries and the old switches. Load **one profile at a time**.

| Profile | Selected channels | Addresses / complete request |
|---|---:|---:|
| `D2WD610H_idle_diagnostic_profile.xml` | 22 | 43 / 136 bytes |
| `D2WD610H_afterstart_diagnostic_profile.xml` | 17 | 43 / 136 bytes |

Start with the idle profile. It keeps RPM, MAP, IAT/coolant, airflow/load,
throttle/timing, immediate and learned bank trims, pump duty/battery, inclusive
and net pulse width/latency, and wideband AFR/raw/readiness.

The separate after-start profile keeps all six after-start terms, the composed
base fuel factor and runtime counter, plus RPM, coolant/IAT, battery, pump duty,
CL/OL state, wideband AFR and pulse width. It uses the standard one-byte MAP
parameter P7 and inclusive pulse P21 to fit. It does not carry the first
profile's raw/ready, load, high-resolution pulse/latency or trims.

These are separate captures, not a synchronized replacement for the former
combined set. Do not perform another engine start merely to collect the second
profile before reviewing the first run. Fan/purge commands, primary OL-map
detail and AVLS/switch diagnostics can be selected in later targeted captures
within the same 43-address limit. Actual fuel pressure still requires separate
measurement.

The full verifier checks both selections, units and expanded/deduplicated byte
budgets against the native limit. No BIN, calibration, logger definition,
serial setting or adapter firmware is changed by the profile repair. Establish
key-on/engine-off data reception before the planned idle capture.

## Header-only CSV and missing subscriptions

The new `logs/romraiderlog_firstidlelog1_20260908_121839.csv` contains 732 bytes:
the time heading plus all 22 idle channels, **zero data rows**. The earlier
`romraiderlog_20260908_120702.csv` is also header-only. These files cannot
establish AFR, pulse-width, load or fueling trends.

The corresponding serial log shows valid ECU data frames, but only for a
subset of the displayed selection:

| Time | Active request | Reply data |
|---|---|---:|
| 12:18:23 | P47 pump duty, P13 throttle | 2 bytes |
| 12:18:29 | Those two plus E502 wideband ready | 6 bytes |
| 12:20:14 | Those three plus P17 battery and E33 CL/OL | 8 bytes |
| 12:21:12 | Same five channels after reconnect | 8 bytes |

For example, the final request was
`8010F01AA80100003BFFDA4E00001C000015FFAE70FFAE71FFAE72FFAE7350`.
The reply `80F01009E8000192140000000018` has the expected eight data bytes
and a valid checksum. It does not contain the other 17 selected channels.
The missing fields were never requested; this is not an ECU response silently
omitting selected byte positions. Two empty identification replies at 12:21
preceded successful identification and streaming; their cause is not proven
by this selection-queue repair.

### Host-side cause and repair

The running Java process used `/Users/regan/Dev/RomRaider` and its
`build/linux/lib/RomRaider.jar`. Inspection of that JAR's bytecode confirms
the same queue behavior as the local source and
[upstream QueryManagerImpl](https://github.com/RomRaider/RomRaider/blob/master/src/main/java/com/romraider/logger/ecu/comms/manager/QueryManagerImpl.java).

`EcuLogger` clears and reloads selected parameters when the ECU identity is
first resolved. `QueryManagerImpl` puts additions and removals in separate
pending collections, then applies **additions first, removals second**. A
remove followed by a re-add before the next poll therefore removes the final
selection. UI brokers still consider the channel registered, so simply
reloading the same profile does not add it again. At 12:06:44 the log records
the clear/re-add sequence before the polling thread starts, followed by no
data requests. Later manual untick/retick actions while polling restore only
those individual channels. The 12:20:56 MAP untick/retick while disconnected
again fails to enter the next request.

`FileUpdateHandlerImpl.Line.isFull()` requires a value for every registered
column before writing a row. A 22-column selection with only three or five
channels polled therefore produces exactly the observed header-only file.

The local source now cancels pending removals when a query is added and
cancels pending additions when it is removed. The last selection action wins
for each view's subscription, including repeated removals and definition
replacement. No transport, ECU protocol or timeout code was changed.

Validation:

- Five offline regression tests run against the original installed JAR:
  three reproduce lost selections; the final-deselect and independent-view
  cases already pass. All five pass on the repaired JAR.
- The actual master definition and both profile XMLs are loaded in an offline
  Java check. After the same queued clear/re-add sequence, the idle profile
  retains 44 view subscriptions for 22 channels, and after-start retains 34
  for 17 channels. RomRaider's real SSM builder produces 43-address,
  136-byte requests with valid checksums for both.
- JAR contents were compared: only `QueryManagerImpl.class` changed. The
  previous JAR is backed up. The source patch, regression tests, integration
  check and installation hashes are in [romraider_query_fix](romraider_query_fix/README.md).
- Native receive tests and the complete master verifier pass; the BIN remains
  `48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0`.

The updated JAR is at the normal launch path. A full application restart is
needed to load the repaired class; the user subsequently restarted RomRaider.

## Live retest at 12:36: complete idle capture confirmed

`logs/romraiderlog_idle_diagnostic_20260908_123651.csv` contains 1,786 samples
over 185.698 seconds. All 22 channels are populated on every row, with 23
finite numeric fields including time. Intervals are 101--108 ms, median 104 ms.

After the ECU-identification callback reloads the definition and profile,
RomRaider sends the full 43-address, 136-byte request at 12:36:37. The serial
excerpt contains 2,295 subsequent full 49-byte responses, all with valid
checksums. This confirms the core profile and repaired subscription handling
on the live connection. The separate after-start profile remains checked
offline only.

The user reports the 10:30 BIN and throttle blips followed by near-stall RPM
and a lean indication on both the physical gauge and RomRaider. Those events
are captured successfully; they are now an engine-fueling investigation.
See the [idle and rev-recovery review](../logs/20260908_idle_review.md).
No additional engine run or reflash is requested by this logger retest.

The later [recovery investigation](IDLE_RECOVERY_AUDIT.md) adds a separate
19-channel profile, also 43 addresses. Its real RomRaider queue/reload/request
check passes offline. E511 now correctly names the signed transient load
correction; the original live-verified core profile still selects 22 channels.

## September 8, 14:13 — recovery capture and CSV units-label repair

The new recovery capture contains all 19 channels and 2,510 rows. Its apparent
header/row width mismatch is one unquoted comma inside the E503 units label,
not missing response data. RomRaider's header writer concatenates units without
CSV escaping. E503 and E504 units now use semicolons in the definition and all
three profiles; E511's gauge minimum now covers the observed negative values.
Addresses, conversion expressions and selections are unchanged. A new profile
check fails the old header and passes the repaired one. The actual RomRaider
queue/A8 builder still retains every selection within 43 addresses.

Complete logger SHA-256 at this header-repair stage:
`df6179c00a01dcf06a0f4be33e5c03efe7192359589b69627695dc1ec2097257`.
The source CSV is preserved, with the exact label normalized only in the
[read-only analysis](../logs/20260908_recovery_review.md). The engine's near-stall
recovery remains unresolved; this formatting repair changes no fueling.

## September 8 — idle-air request capture

E514/C468 records the effective idle RPM target, E515/C2B8 the combined
relative throttle request before learned offset/fault overrides, and
E516/B2BC the raw throttle/idle flags. P30 adds accelerator pedal position.
The new `D2WD610H_idle_air_diagnostic_profile.xml` selects 19 channels and
exactly 43 addresses. All four profiles clear each other's selections and
pass the actual RomRaider queue/reload/A8 builder, preserving 38 subscriptions
for this profile with a checksum-valid 136-byte request. The complete logger
regenerates identically and the full master audit passes. No JAR change or
ECU traffic was needed.

Current complete logger SHA-256:
`3ff3a49fb332551c411a635ddcac49d04fea5f3ee1c308d917fa0145b8d5925e`.
The profile is prepared for later use; the repeat rev test is withdrawn.
Leave the car off while the offline investigation continues. E516/B2BC alone
does not prove idle-air feedback is enabled. See
[the native load replay and request-channel evidence](IDLE_AIR_RECOVERY_AUDIT.md).
