# Resume checkpoint — September 13, 2026

[Reference home](README.md) · [Full flow register](PATCH_PROCESS_FLOW.md) · [Repair](AVCS_OCV_REPAIR_20260913.md)

**Paused at the user's request. The broader audit is incomplete and the loaded cut is not proven cured.**
The repository was clean at commit `a6e217c` (`more firmware tests`) before
this checkpoint. That commit includes the preceding audit work. This resume
session changed no runtime source, calibration, BIN, logger definition or
profile, and performed no ECU communication, flashing, commit or push.

## Objective and standing instructions

Find and fix the loaded bog/cut around 2,800–3,500 RPM by following every
patch touchpoint through its native producers, consumers, initialization,
qualifiers, latches, reset paths, computed writes and scheduling dependencies.
Use the actual saved images and logs. Do not infer physical state from an
unlogged flag, a software command, an empty DTC scan or a forced test fixture.

- Continue in the rolling repository; do not create candidate ROMs.
- Use the Ghidra MCP server and update its annotations as findings become
  established. Preserve the project database; no UI substitute is needed.
- Keep the user's independent dashpot experiment out of this work. Do not
  change MAP scaling, the `0.06` load filter or unrelated calibration to
  chase an unproven explanation.
- No subagents have been authorized for the resumed work.
- The user has now asked to pause and document progress. Earlier requests
  to continue indefinitely do not override this pause.

## Confirmed repair and exact artifacts

The old purported rear-O2 bypass disabled the **AVCS oil-control-valve
current-feedback/output process** and reused its RAM. The repair restores
the current converter, native current-reference/error/integrator/output
tasks and circuit monitors. Startup now calls native `33964` to initialize
`C85C/C860` to `1.0` before clearing the relocated patch state.

WB mirrors moved from `B098/B09C` to `AE8C/AE90`; lean counter/state moved
from `C85C/C860` to `AE9C/AEA0`. Native PWM now receives a nonzero command in
the tested enabled states. Merely restoring the output pointer while leaving
the old zeroed integrators still produces zero output in the negative control.
See the [repair evidence](evidence/avcs_ocv_repair_20260913.json) for all
72 changed bytes per rolling image and the native path.

| Artifact | SHA-256 |
|---|---|
| [Rolling v2](../../master_patch_v2/D2WD610H_master_patch_v2.bin) | `fabceb54359aca76e6e15835a51aa5cfd008e570dc002e886eaa62a6cb020ce5` |
| [Rolling main](../../master_patch/D2WD610H_master_patch.bin) | `3e95b7508427f544e30a96c7aa78298b32560a6f3caf5c180e7949b8c2adc388` |
| Captured loaded-drive v2, reconstructed by the pinned helper | `fd795813febf817c845fc922e81e498539a539efeeb6e4d11822af47098094a2` |
| [Complete logger definition](../../logger/D2WD610H_master_logger.xml) | `855b0af1620eb9efd6cc439945dec4fe5fc7dd957e9b79d506f8d1d1a099c71d` |

The repaired v2 Subaru checksum is `AA416B03`; main is `1ADC9F24`.
The captured image must continue to be reconstructed using
[`_captured_images.py`](../../tools/analysis/_captured_images.py), which
rejects unknown hashes. Do not substitute the repaired image for the image
that produced the loaded log.

These restored routines are **AVCS cam phasing**. AVLS is the separate lift
system; the shared timer interactions have also been checked. This distinction
matches [Subaru's description of the 3.0-litre H6](https://www.subaru.ca/WebPage.aspx?ArticleID=1528&WebPageID=4749&WebSiteID=282).

## Testing advice and completed logger follow-up

The user asked whether testing was worthwhile now. The answer given was
**yes, a controlled validation of repaired v2 is worthwhile**, while keeping
vehicle causality unproven. No flash or vehicle test was performed.

After the pause, the user requested a logger profile. That bounded task is
now complete: use [D2WD610H_avcs_repair_profile.xml](../../logger/D2WD610H_avcs_repair_profile.xml)
with the updated [complete definition](../../logger/D2WD610H_master_logger.xml).
The [usage and 20-channel budget](../../logger/README.md#avcs-repair-validation)
and [native evidence](evidence/avcs_logger_20260913.json) are saved. All eight
profiles fit 43 byte addresses and pass native continuous exchanges.

The six standard AVCS callbacks and capability bits were verified. P50/P51
read upstream demand at C914/C918, so the final profile uses new E528/E529
at C91C/C920 to observe the restored normal-output stage. It retains P48/P49
actual angles and P52/P53 measured currents, plus IAM, both knock corrections,
AFR, MAP, driver inputs and injector/lean-cut context. Later diagnostic
output overrides remain separate, and target angles are not selected.

The earlier proposed selection and pending status in the checkpoint JSON
are historical; its `logger_follow_up` field supersedes them. The original
seven profile selections and both ROMs are unchanged. The full temperature
and dependency audit remains paused; **do not redo this logger preparation**.

## Completed verification baseline

The [consolidated report](evidence/process_flow_tests_20260912.json) records
**355 passing groups in 64 result rows**, covering 62 registered modules
with three image variants of the cylinder-disable module. It is a cumulative
report with explicit incremental validation, **not a fresh complete-suite run**.
The paused audit baseline was 354; the later logger task added one group and
reran the seven-group SSM suite, including all eight profiles.

The latest completed additions are below. Runtime/reset were already in
`a6e217c`; SSM was extended and rerun for the logger follow-up:

| Suite | Passing groups | Recorded run |
|---|---:|---|
| [Runtime switch publication](../../tests/test_runtime_switch_process_flow.py) | 4 | 13.659 s |
| [Retained reset requests](../../tests/test_retained_reset_process_flow.py) | 5 | 33.523 s |
| [Native SSM command/exchange](../../tests/test_ssm_command_process_flow.py) | 7 | 16.698 s |

Key results to preserve:

- PE14/PE15 through `F754 -> AAE6` publish **same-polarity** `B51C/20,/10`
  and `B51E/04,/02`. The old inverse-AVLS description of `B51A/04` was wrong.
  `B51A/04` and `B51B/02` are instead `!(AAEC & 04)`, from serial mux channel
  2 through `766C`; the physical external serial-device identity is unknown.
- Retained reset path `48830 -> 4892C -> 313F2/F5F6` requires its installed
  feature, packed `8E0C` latch, shutdown state and serial-input conditions.
  It writes `8262=4055` and header `8000=55AA`; learned records change only
  at the later startup reset. The tests include native serial transport with
  supplied hardware completion/input bytes.
- Include the complete feature-initializer prefix `10140..10184`. Starting
  at `10148` omits `147C0/B289` and falsely excludes the reset feature.
- All seven saved 43-address A8 profiles execute native receive, getters,
  echo handling and two complete 49-byte responses on main/v2/captured.
  They never reach `336E6`, `32894` or `F5F6`. Explicit B8 parameter `0060`
  is the separate reset writer; raw B0 writes to `8000/8262` are denied.

The [full flow register](PATCH_PROCESS_FLOW.md#coverage-register) remains
the authoritative per-family closure list. Do not rerun completed suites
merely because a new chat starts.

## Exact interruption point: temperature consumers

The following work is **exploratory**, not included in the passing groups.
Its MCP disassembly/xrefs are saved in the cumulative evidence. The three
temporary probe sources and their limitations are preserved in
[`audit_resume_20260913.json`](evidence/audit_resume_20260913.json), so resuming
does not depend on `/tmp` surviving.

### IAT spark and hot timing qualification

- `289E0` writes `C1A4`: load `B438 >= 0.6` selects table `5FC90` using
  `B3B8`; lower load writes zero. The 50–110 C axis gives 0 through about
  -5.98 degrees. **IAT at or below 50 C gives zero**, including the logged
  36–37 C and the native 20 C substitute. Its identified final consumer is
  `279CC`. A native exploratory execution reached all six final angles.
- `27480` sets hot-transient qualifier `C121/01` only with its pedal/change,
  counter, speed and RPM gates and **ECT >= 119.4 C** (`77DB4`). The log's
  66–67 C excludes that hot qualifier. `C110` is 5 below IAT 50 C, otherwise
  zero; `C11C` is gear-dependent via `19D96/B51C/01` and `CD48`.
- Sequence `27480 -> 2769C -> 27728 -> 2777C -> final spark` was explored
  with real CPU callees. An explicitly imposed old `C104=-10` ceiling and
  old flags can recover by 0.7 degrees per call until `C128` reaches 18,
  then reset to 69.65. This demonstrates bounded handling of the supplied
  stale state; **it does not establish that state occurred in the car**.
  The loaded log showed approximately 16–17 degrees in the sustained event.
- `C118` remains an open input to final spark. A missing identified writer
  is not permission to call it spare RAM; startup clearing is a separate fact.

### Temperature-dependent idle air

- `2E55C` initializes `C588` while cranking (`B748/80`) from ECT, adding an
  IAT term only above the 80 C coolant threshold. Native startup and slow
  dispatcher pointers are `10520/117F0`.
- Periodic `11094 -> 2E5B6` decays `C588` toward zero. `11098 -> 2E684`
  updates second post-start term `C58C` with native counters `C5AC/C5AE/C5B0`,
  flags `C5B2`, ramp limits and zero-clamped decay. Both reach the `2B570`
  base-air sum and the existing final DBW path.
- The corrected exploratory fixture produced final driver requests around
  60 degrees at explicit 70% pedal while post-start air varied. An earlier
  3-to-1.5-degree result was a **fixture error**: the timing parent had left
  `B51E=0` and unrelated digital states. Set ordinary ignition-on `B51E=10`,
  `B51C=0`, `B51A=80`, `B484=0`, and initialize prior `C5B8` compensation.
  Prefer the established `IdleFeedbackMachine` and native pedal conditioning
  when converting this into a formal integration test.

### Hot-IAT fuel multiplier — unfinished first

- `23482` filters `B3B8` into `BE8C` with coefficient `762F0=0.0078`.
  `234A0` handles the two-call gates `BEB1/BEB2`; `2331E` can clear BEB1.
- `2333C -> 235D6/236D4/2354C` publishes
  `BE88=clamp(1 + BE94*BE90*BE98*BE9C, 0.5, 1.5)`, subject to native
  diagnostic/start/status/RPM exclusions. `1DD04` consumes BE88 in the
  actual fuel composer. Complete the connected producer-to-composer test.
- `5FAD4` is a 6-by-2 table: prior bank fuel values `B7E4/B7E8` are its
  first-axis input, filtered IAT its second. The 60 C row is all zero;
  the 80 C row ranges from zero to 0.05078125. `5F434` scales by RPM
  (2800/3000/3200 -> 1/.6015625/.296875); `5F448`'s ECT factors are all 1.
  The publisher uses unity at RPM >= 4000. These are byte/table observations,
  not a completed proof over all prior filter/weight states.
- Eligibility uses `B420` airflow hysteresis 20/22 g/s, ECT 45/50 C and
  speed 250/255. At the supplied 100 g/s, a forced weight of 1 started
  decaying by about .0488; low-flow positive controls reached weight 1.
- **Last probe failure:** on the second call, `235A4` reads uninitialized
  `FFFFB7E8`. The probe explicitly forced `CC4E=C0` to reach the bank-table
  branch. First establish the installed feature byte through its native
  initializer, initialize/produce the prior bank pulse values, then continue
  through `1DD04`. Do not mistake this fixture failure for an ECU defect.

All CPU callees in these exploratory probes use
`StartupRetainedMachine.call_lookup`. Their temporary broad `BANK_WRITES`
allowance must be replaced by precise output sets for formal tests. Restore
proper image/byte pins, native parent order, positive/negative controls and
explicit physical boundaries before registering any new suite.

## Resume order and evidence limits

1. Read this checkpoint, inspect Git status and recheck artifact hashes.
   Preserve later user edits and any newly supplied flash/log evidence.
2. Resume the hot-IAT fuel fixture above, then formalize the timing and
   post-start-air consumer checks where useful. The AVCS logger follow-up is
   complete; use its saved evidence if the user supplies a new capture.
3. Continue the remaining per-family edges in `PATCH_PROCESS_FLOW.md`:
   secondary MAP/load consumers; purge/feedback diagnostic and retained-record
   parents; timing/idle/learning inputs; every upstream inhibit/reset source;
   crank-to-run state; computed entries; and full task/event interleavings.
4. Keep physical unknowns separate: cam/OCV response, fuel pressure, actual
   electrical pulses, received CAN requests, retained trims, task occupancy,
   missed deadlines and sensor sample ages were not measured by these tests.
   Forced queue overflow and stale timestamps are counterexamples, not
   evidence that the patch caused them in the car.

The latest loaded capture remains
[`romraiderlog_adjustedvedrive_20260912_144204.csv`](../../logs/romraiderlog_adjustedvedrive_20260912_144204.csv),
SHA-256 `347d10ce5e5c70d64f478e4bb6d124453697af07b1e074271ecbe1830d7efb33`.
It has 2,747 rows. In the sustained 77–85.25 s event: RPM 2502–2876,
MAP 102–110 kPa absolute, load about 1.97 g/rev, pulse 7.94–9.47 ms,
AFR 11.06–12.17, timing 16–17 degrees, IAM 1, logged knock 0,
ECT 66–67 C and IAT 36–37 C. The earlier acute transition includes
AFR 13.07/14.07; do not call the whole event uniformly rich. There is no
captured proof of boost, actual cam tracking, fuel pressure or electrical
injector/spark delivery. The wideband gauge and log agree per the user.

## Ghidra and durable evidence

The connected program is stock `2005 BLE MT.bin`. The cumulative
[`patch_process_flow_20260912.json`](evidence/patch_process_flow_20260912.json)
now contains **3,359 MCP captures**: 48 previously unpersisted temperature,
fuel and proposed AVCS-logger queries were appended at this pause. Historical
captures were preserved; later corrections are explicit additions.

The latest 13 reset/SSM names and entry comments plus the corrected `193D0`
mapping were already applied and read back before this resume session, and
are in [`ApplyMasterNames.java`](../../master_patch/ghidra_scripts/ApplyMasterNames.java).
The paused audit session added reads only. The later logger task adds six
callback comments, accepted by MCP but without independent readback because
those entries have no exposed function bodies; its separate evidence and
reapplication script preserve them. Temperature-consumer conclusions have not yet
been promoted into new live annotations or claimed formal test coverage.

MCP cannot create missing functions, migrate memory blocks or explicitly
save/reopen the project. The live RAM block remains wrong at
`FFFF0000..FFFFBFFF`; physical RAM is `FFFF6000..FFFFDFFF`, and the repository
setup helper is corrected. Preserve the database and the
[documented limitation](GHIDRA.md); do not claim migration or a disk save
was performed. Resume from the saved evidence instead of repeating thousands
of queries.

Checkpoint validation confirms the linked files, artifact hashes, embedded
probe syntax/source hashes, existing report totals and preservation of all
3,311 earlier MCP captures. A wider Markdown scan also found 46 pre-existing
broken links in unchanged archive/older documents. Their exact locations are
recorded in the checkpoint JSON for later cleanup; this pause does not claim
a repository-wide link check passed.

The audit's `caffeinate -i` process is released for this user-requested pause.
Start a fresh task-owned keepawake process if sustained auditing resumes;
do not terminate another application's sleep assertion.
