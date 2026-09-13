# Ghidra project and MCP audit trail

[Reference home](README.md) · [Exact mutation ledger](evidence/ghidra_changes.json)

The audit used the connected **Ghidra MCP server**, operating on the stock
`2005 BLE MT.bin` program in `Renesas_SH0755_modding`. Stock-program annotations
describe patched behavior only when explicitly scoped to main or v2. The
stock binary on disk was not patched.

Ten additional names and verified entry comments identify retained-ignition
validation `29570`, grid validation `3D9E8`, IAM initialization `3E9FC`,
reset qualification `3EC6C/3ECB6`, rough learning `3ED6C`, fault recovery
`3F020`, fine learning `3DC9C`, event counting `3DFD6` and mode reentry
`3EF74`. These distinguish protected storage from runtime corrections and
connect the changed load windows to native learning/reset behavior. Names
and comments were read back through MCP and added to the ongoing evidence;
the frozen September 9 ledger is unchanged.

The received-request extension adds eight names and verified entry comments
for `14374`, `3BEE4`, `3CE0A`, `3CE58`, `3D050`, `3D3A2`, `2EE6C` and
`3D48C`. These distinguish the startup CAN cut latch, periodic request
calculation, crank-phase publication, delayed diagnostic summary and
duration-based model alias. Their evidence is appended to the ongoing
`patch_process_flow_20260912.json` capture rather than the frozen historical
September 9 mutation ledger.

Three further verified names/comments identify `36190` common inhibit
reasons, `36370`'s warm-temperature exclusion of received cylinder cutting,
and the `3D28E` reentry delay. These qualify the earlier direct phase-pattern
fixtures, which explicitly supplied the mode-inhibit flags clear.

## September 13 AVCS corrections

The ongoing MCP process-flow audit renamed twelve OCV routines and read back
the names, then verified corrected instruction comments on those twelve
entries plus `B690`, `B8CC` and `11270`. The earlier rear-O2 interpretation
of `E0D0/DFB4/33964/33970/33AAC/33B12/34BE4/69568` is withdrawn.
Comments distinguish native current/integrator state from the relocated patch
RAM and trace normal, inhibited and override PWM publication. The repository
naming script also carries the corrected identities.

Seven additional routine names cover cam capture/queued delivery, the three
descriptor stages, learning convergence/permission and knock-grid reset.
Their names and instruction comments were read back too. The comment at
`644A6` identifies the six raw cam/OCV fault-latch sources of `D26F/10`, its
diagnostic gate, reset helper and cam/ignition/knock consumers. This later
work brings the September 13 additions described here to nineteen names;
it does not alter the frozen historical audit counts below.

The follow-on IAT trace adds three verified names/comments for `78AC`,
`685D2` and `6864C`: filtered-ADC electrical classification, high-voltage
reporting and low-voltage reporting. The `6270` comment records the native
cam queue consumer and its task-completion boundary. These are additional
process-flow annotations, not evidence of measured ECU scheduling.

The ignition output trace adds twelve names and verified entry comments for
record initialization, phase resynchronization, mask transitions, dwell,
device queues and coil timers. Additional comments identify `647BA`'s four
current cam-fault sources, `2A2BC`'s six-channel conversion and native timer
routing. `2A0C0/2A17A` accept instruction comments but still have no MCP
function body; their callback/release paths are explicitly decoded from
local bytes and executed in the instruction fixtures. No function creation
or explicit project save is claimed for those entries.

Four further names/comments, also read back, identify `7198C/719A8/71ADE/71D2C`
as the cam-performance diagnostic parent, qualifier, failure counter and
healthy counter. The annotation records the unchanged 12,800-RPM gate for
nonzero targets and distinguishes current recovery from retained history.

The AVLS follow-up adds ten verified names and entry comments: five for
electrical/switch qualification and reporting, three for current conversion
and native PWM, and two for GPIO debounce and switch publication. Corrections
at `41230` and `646B2` distinguish protected current status from raw history
and connect both actuator override and low-lift selection. `F2A2` and `6B08`
still lack MCP function bodies and are separately recorded as local native
instruction traces. The timer start register is **TSTR2 at F400**; its
AVCS `01/02` and AVLS `04/08` bits are checked together.

Three further names and comments, read back through MCP, identify `310D8`,
`30FD4` and `4EEC4`: ignition-off state transitions, initialization and the
queued protected-counter callback. Small message trampolines and the two
callback-counter entries have no MCP function body; their actual bytes are
decoded locally and executed in the shutdown suite.

Four diagnostic-readiness names/comments identify the six-gate parent
`5116E`, basic and battery publishers `565BE/565F8`, and minimum-temperature
history `1AE04`. All names and entry comments were read back. This closes
the previously supplied DB24/DB25 values for the tested monitor chains;
the entire diagnostic reset parent and snapshot transport remain separate.

Seven verified cam-sensor names/comments cover `69318`, `69394`, `69442`,
`694C2`, `E314`, `E6B0` and `E6DA`: capture publication, the independent
edge latch, both fault counters and reporting/recovery. Their names and
entry comments were read back. `53D10` has no MCP body; its native callback
entry and later workers are distinguished from queue publication tests.

Four more names/comments, all read back, cover `51124`, `567B4`, `51378`
and `5690E`: full diagnostic-mode dispatch, running selection, startup and
DB2A publication. The annotations distinguish the physical connector input
from the retained mode and identify the installed zero-return feature gate
that excludes `5652C`'s later full-reset call.

Three further names/comments at `2FDDC`, `81C0` and `8EDA`, plus the revised
`8AD6` entry comment, were applied and read back. These connect actual cam
selector refresh, periodic signal timeout and all-channel pending-injector
cancellation. The attempted rename at `813C` failed because no MCP function
exists there; its comment returned success but is not readable through the
function view. The reapplication script records the intended future name;
live success is not claimed. `813C` and queued callback `69C4` use explicit
local byte supplements and native execution evidence.

Four more record names/comments at `53DA8`, `54D60`, `55064` and `55518`
were applied and read back: class-0 promotion, snapshot selection, source
copy and reset. Comments at missing-function entry `53D10` and data byte
`5BDA8` returned success; the MCP view does not expose their text for an
independent readback. The latter corrects P0111 to **stock-disabled**, rather
than inferring a runtime monitor from its descriptor.

Three synchronization names/comments at `8298`, `29C08` and `A76C` were
applied and read back. Missing-function callback entries `69DE` and `11E84`
accepted comments but have no exposed comment readback; local byte supplements
and complete native execution are recorded separately.

Four phase/kernel names and comments at `87F2`, `8BE6`, `CF58` and `CF7E`
were applied and read back. They identify period publication, both task
activation wrappers and their tested finite-capacity behavior. The tests
separate native kernel execution from explicit interrupt arrival and the
bounded task-5 payload.

Seven decoder/observation names and comments at `8218`, `8248`, `8428`,
`84B2`, `1A0BA`, `D92C` and `DB50` were applied and read back. Missing
entries `D8EE` and `11ED2` are explicit local supplements. Capture waveform,
phase activation, IRQ frame and post-decoder workers remain separately
identified test boundaries.

Missing-function entries `1A368` and `1A428` accepted comments describing
the tested capture-inhibit startup and release paths. The MCP function view
cannot read these comments back; exact local byte supplements and native
execution are recorded without claiming a live function rename. The same
limitation applies to added comments at `D8EE/11ED2`.

Six native inhibit-source names/comments at `24C34`, `24CB0`, `24E0C`,
`2513C`, `4551C` and `25AC0` were applied and read back. They distinguish
digital input loss, stationary qualification/timing, vehicle-speed patterns,
the low-lift RPM limiter and the disabled received-torque pattern. Their
conditional tests retain explicit digital, fault and received inputs.

These additions are recorded in
[patch_process_flow_20260912.json](evidence/patch_process_flow_20260912.json),
separately from the frozen September 9 counts below. The server still has no
function bodies at several real native entries, including `DFE8`, `E174`,
`B49A` and `34194`; local bytes and instruction execution are explicitly
identified where they supplement the MCP view.

## Verified live updates

Readback confirms **38 routine names, 10 existing data labels, 67 instruction
comments and 4 decompiler comments** across **129 mutation attempts**. Two
additional descriptor comments returned success but the MCP
data listing does not expose their comment text for independent readback.

The routine updates cover the injector timer path, protected-record integrity,
coolant and paired-pedal processing, purge state and fuel compensation,
legacy-O₂ consumers, throttle requests, idle target and corrected FPU-stop
handling. Data labels cover the timer and feedback descriptor bases,
MAP raw/pressure channels, pedal, injector inhibit word and defined fan registers.

Comments record the verified ADC-word type, descriptor fields, fan/purge
distinction, corrected fan RAM literals, image-specific load fallback,
transient correction identity, barometric source, checksums, cut locking,
logger size limit and ignition arrays. Producers/readers are annotated where
the affected RAM object cannot currently be defined through MCP.

## Server limitations that matter

This server's `rename_data` implementation only renames an already-defined
Data item. It returns “Rename data attempted” even for a no-op. Eight attempts
could not be verified: ABC8, CD7F, CD80, F602, F640, F650, F652 and F444.
They remain explicit no-ops in the ledger rather than claimed successes.

The server has no exposed endpoint to create Data, create/split/join memory
blocks, create missing functions, execute a script or explicitly save a
program. A successful annotation transaction and readback establishes live
project state; it does not establish an explicit save/reopen cycle. Project
recovery snapshots are not described as a verified final save.

`set_decompiler_comment` writes a PRE comment, not a function PLATE comment.
Consequently, a decompile can still show an old plate interpretation above
the verified correction inside the body. The old vehicle-speed plate at
`17984` is an example. The repository naming scripts contain corrected plate
text for later reapplication; this audit does not claim MCP removed every
old plate comment. The new comments and names are independently read back.

## Memory-map correction prepared in the repository

Current MCP block listing:

| Block | Current range | Assessment |
|---|---|---|
| `ram` | `00000000–0007FFFF` | Saved flash. |
| `RAM` | `FFFF0000–FFFFBFFF` | Incorrect physical range. |
| `IO` | `FFFFE400–FFFFFFFF` | Broad peripheral analysis mapping. |

The corrected physical RAM range is **`FFFF6000–FFFFDFFF`**. The
[setup helper](../../ghidra_sh7055_setup.py) now uses it. For a fresh import,
it creates that range. For an existing overlapping block, it stops with a
specific error rather than silently keeping the wrong geometry or deleting
analysis. It does not pretend to migrate the open project.

A later block migration must preserve existing RAM labels/comments while
removing the falsely mapped prefix and adding `C000–DFFF`. It should be
followed by checking key Cxxx/Dxxx state and the `FFFFDFA0` stack label,
then an explicit save/reopen check. This remains a tooling limitation under
the requested MCP-only workflow; no UI workaround was used after that request.

## Evidence files

The September 13 process-flow continuation read back six updated native fan
comments and eight knock-feedback function names/comments through MCP. The
`65168` comment now correctly states that main, v2 and captured v2 each bypass
only the local airflow call; its knock-control caller remains native. The
repository naming script also preserves the already-correct live name for
the ignition-off spark-inhibit routine `3F5F0`. Comment publication at native
fan period reload `E8B4` succeeded, but MCP has no function there for independent
disassembly readback. Its bytes are checked by the native execution test.
`3E1B0` and fall-through `3E1C8` remain separate Ghidra fragments; the test
executes the complete initializer. Captures are retained in
[process-flow evidence](evidence/patch_process_flow_20260912.json).

Seven further timing/idle function names and comments were independently read
back, along with the corrected held-temperature comment at `16B04`. These
identify the `C1BC` feedback loop, its idle-air path through `C3F8`, the
2,000-RPM gate in `28A82`, and the identical monitor gain families. The
repository naming script contains the same seven names.

Twelve knock-event, phase/window and serial-transfer names/comments were
then read back through MCP. The connected trace identifies `A76C` as knock
sample-history initialization and `A9A8` as reference/window-parameter
publication. Both former narrow names are replaced in the live program and
repository naming script. The updates cover the complete `AA50 -> 17914`
event handoff, six-cylinder index producer, AN24 completion callback and
SCI0/window timer paths, with explicit hardware-input limits.

Five idle-feedback names/comments were also read back: `2C760`, `2CE50`,
`2CF9C`, `2D0AC` and `2D1FC`. Their comments distinguish the eight-call
divider from a mode, identify prior-cycle headroom inputs, and state the
native pedal-release and final-throttle test limits. The same names are
preserved in the repository script.

Eight startup/retained names and comments were independently read back at
`F5F6`, `F710`, `FD5C`, `10690`, `30A84`, `4C7C`, `4C82` and `F950`.
The two former hardware-register initializer labels now identify retained-bank
header invalidation and validation/reset. `10690` is the complete cold-reset
chain; the comments distinguish it from ordinary task startup at `FEF4`.
MCP still has no defined function at `F820`, `F754` or `F6D6`; their exact
local byte windows and native execution results are recorded separately.

Thirteen further names/comments were read back for the serial input,
retained reset request and SSM receive/decode/read/write/transmit paths.
The `193D0` comment was corrected and read back: AVLS PE14/15 publish to
`B51C/20,10` and `B51E/04,02` with the same polarity. `B51A/04` instead
inverts serial channel 2 bit 2. The old inverse-AVLS claim was wrong.
Native execution now connects the separate reset request and proves the
saved A8 profiles do not invoke its B8 setter. MCP has no defined function
at `32894` or `319E2`; exact bytes and executed entries are recorded locally,
without claiming those functions were created through MCP.

| File | Purpose |
|---|---|
| [ghidra_snapshot.json](evidence/ghidra_snapshot.json) | Final September 9 MCP inventory: 2,764 functions, 304 scoped data labels from 30,572 listed items, and observed segments. |
| [ghidra_evidence.json](evidence/ghidra_evidence.json) | Captured disassembly and address xrefs, including corrected producer comments. |
| [ghidra_changes.json](evidence/ghidra_changes.json) | Every mutation, response, readback and no-op. |
| [fixture_accesses.json](evidence/fixture_accesses.json) | Existing verifier's bounded access observations, separated by image variant. |
| [local_instruction_supplement.json](evidence/local_instruction_supplement.json) | Explicit local SH-2E byte windows where MCP had no defined function; not mislabeled as MCP disassembly or execution. |

The evidence is retained in the repository so a new chat can inspect the
reasoning without relying on unsaved conversation history or existing names.
