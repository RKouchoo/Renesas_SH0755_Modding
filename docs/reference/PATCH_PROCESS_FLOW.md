# Patch dependencies and native process flow

[Reference home](README.md) · [Every build assignment](PATCH_TOUCHPOINT_REGISTER.md) · [Loaded-cut evidence](V2_AVLS_MISFIRE_20260912.md)

**This broader process-flow audit is in progress. A real AVCS output defect has been repaired; the loaded cut is not yet proven cured.**

Work is paused at the user's request. Continue from the
[September 13 resume checkpoint](AUDIT_RESUME_20260913.md), including its
unfinished temperature-consumer traces and completed AVCS logger follow-up.

The full-flow trace found that the former rear-O2 bypass actually removed
OCV-current feedback and normal cam-solenoid PWM publication. See the
[repair, complete handoff and RAM migration](AVCS_OCV_REPAIR_20260913.md).
The earlier address audit did not establish the physical identity of that loop.
The September 8–9 address audit reviewed documented contracts. It did not
establish the complete state-machine behavior of every transitive dependency.
An unchanged native routine can still receive a changed value, run in a new
state, or consume state whose former producer was bypassed.

## Scope and image identity

The new inventory records actual ROM assignments while independently rebuilding
both rolling images in memory. It includes unchanged writes, overwritten seed
values, hooks, calibration, injected code, retired reservations and checksums.
It accounts for every final differing byte; it does not equate that coverage
with completed dependency analysis.

| Image | SHA-256 | Build assignments | Final changed bytes from stock |
|---|---|---:|---:|
| Current main | `3e95b7508427f544e30a96c7aa78298b32560a6f3caf5c180e7949b8c2adc388` | 162 | 6,154 |
| Current v2 | `fabceb54359aca76e6e15835a51aa5cfd008e570dc002e886eaa62a6cb020ce5` | 170 | 6,833 |
| Captured loaded-drive v2 | `fd795813febf817c845fc922e81e498539a539efeeb6e4d11822af47098094a2` | Historical image | Reconstructed with the exact OCV and pump repair reversals |

Both current in-memory builds equal their saved BINs. The OCV repair changes
72 bytes per rolling image, restoring native tasks and relocating WB/lean RAM.
Calibration is unchanged by this repair. The captured image remains the reference
for explaining the event; later repairs must not be silently included.

For each touchpoint, closure requires its producer and units, every identified
consumer and writer, call ordering, initialization, entry/exit conditions,
fallbacks, latches, reset paths, computed aliases, ABI and scheduling effects.
Tests with forced flags cover those explicit states, not the flag's upstream
cause. A pointer search is a discovery aid, not proof of complete consumers.

## Coverage register

The linked assignment register maps every written span to the family below.
The evidence column describes reviewed edges; the last column names work that
still prevents claiming full process coverage.

| Family | Native flow and reviewed dependencies | Remaining closure work |
|---|---|---|
| MAP | `AB04 -> 7A14 -> ABC4` in absolute mmHg. Affine transfer and low-input acceptance feed SD and both pressure cuts. `B2A0` and `CFBC` are separate processed/estimated channels. Accepted lower pressure and lookup clamping have native execution evidence. | Complete all processed-MAP/barometric consumers, diagnostic substitutions and cross-task sample ordering. |
| IAT | `AB3A -> 786C -> ABB0 -> 609B8 -> ABAC` converts filtered ADC to C using `72960/729D8`. `16D1C` selects ABAC or 20 C into `B3B8`, conditionally captures `B3BC`, and maintains voltage histories `B3C4/B3C0`. Four conversion/consumer groups and three electrical-fault groups cover raw thresholds, P0112/P0113 qualification, current-status publication, native fallback aggregation and healthy recovery. | Complete other temperature-dependent consumers, retained-record parents and diagnostic source sampling; P0111 is stock-disabled and its report/status masking is verified. Same-task conversion precedes publication, but preemption and actual sample ages remain unmeasured. |
| SD | Seven groups execute the entire `172A4` task, its SD wrapper, old-history snapshots, native load filters, startup/stopped resets and cranking/event-state publishers. Caller FR15 supplies the same RPM used by load division. Wrapper publishes `B448/B458/B45C`; old `7C30/17726` producers are bypassed. | Close the remaining secondary consumers and full-task/event timing integration. Passing the complete airflow task does not close every subsequent load consumer. See [full task flow](#the-complete-airflow-task-and-its-other-writers). |
| WB | `AB06 -> B690/7E440 -> AE60/AE64`, readiness `AE70/AE74`, zero synthetic currents `AE68/AE6C`, logger mirrors `AE8C/AE90` after the OCV repair. Native feedback tests expose a real readiness mismatch: valid 50 disables bank feedback and scheduled updates reset its corrections to 1.0. Connected checks include heaters, ADC handoff, cruise/pedal/overrun, readiness histories, diagnostic qualification and both retained legacy-O2 workers. | Complete remaining computed diagnostic-state consumers, full diagnostic/snapshot parents and scheduling before repairing the shared convention. The readiness finding is not established as the loaded cut's cause. |
| PURGE | `1BAF0` zeros `B6D4/B6D8/B720`, then retains output writer `B182`; native PWM service `57DA` consumes its request. `2300A` still advances filter/ratio states; `23054` independently zeros `BE60/BE64`. Connected tests now include the shared `D94B/20` monitor, `D852` reset/hold effects and bounded histories adjacent to cylinder-disable configuration. | Complete circuit/bank diagnostic parents, retained-record commit/reset and remaining feedback-learning consumers. Zero duty does not remove these routines. |
| CUT | `11D3C -> 7EC00 -> 7D8C4 -> 24B24`; retained and added decisions compose under `3AF4/3B08`. `BF6C` feeds `23FC0`; `B744` controls injector scheduling. Lean state is `AE9C:u16/AEA0:u8`, initialized by `7EBA0` after calling native `33964` to preserve AVCS integrators. Pressure-OL wrapper runs native `22454` first, then may clear `BE38/80`. | Complete upstream generation and reset of every native inhibit request, and all interrupt/task publication interleavings. The low-RPM producer finding below closes one previously missing edge. |
| INJECTOR | `76014` affects native base duration; `7B318` supplies latency; four cranking maps enter cranking selection. Effective duration `C0B8` also feeds `13CA8/B1C4`, pump demand and received-torque calculations. Native enqueue/promotion/update, active pulses and end callbacks execute to timer-register stores in bounded fixtures. An imposed stale timestamp exposes a native counter wrap. | Complete remaining secondary consumers, crank-to-run producers and scheduling bounds. Establish whether the timestamp counterexample is reachable under patch-driven conditions; it is not a diagnosis. |
| FUEL | OL axes/maps, CL load axis and delay feed retained target selection. Five additional groups execute airflow-region selection, the whole long-term trim pair publisher, signed learning, retained application, pressure-forced OL and final composition. V2's 500 g/s boundary does not guarantee zero learned trim in OL. | Complete upstream feedback eligibility/counters, later diagnostic-triggered resets, other trim consumers and task interleavings. The complete shared startup validator/reset is now covered below. The loaded capture does not contain applied/retained trim values. |
| TRANSIENT | Signed load histories feed `B874`, then normal duration. Separate tip-in tables/activation/MRP multiplier feed `23BAE -> C700 -> 11EF4 -> 2689C -> 268E8 -> 96FC`, an immediate supplemental pulse. Both paths now have connected native execution evidence. V2 falling-history coefficient is `0.08`; native load alpha remains `0.06`. | Close initialization, all mode-dependent multipliers, history writers and real task/sample timing. Near-zero logged `B874` alone does not exclude supplemental tip-in. |
| TIMING | Six timing maps share load-axis storage at `780BC`; A/D and C/F selection depends on lift and AVCS tracking, with other native corrections retained. Final per-cylinder publication reaches `C0EC+4*n`. Nine additional groups trace the native paired scheduler, dwell, timer setup, all six coil descriptors, cut/release, phase resynchronization and the separate current-cam-fault/secondary-spark mask. Ten feedback groups add C1BC qualification/release, idle-air compensation, held temperature and monitor gain consumers. | Complete remaining blend/correction inputs, physical crank-event delivery and task timing. Cam performance and sensor fault qualification now have connected native tests. Explicit timer matches are modeled; electrical spark delivery is not established. |
| KNOCK | Seven changed load boundaries feed `3DAA6`, an eight-by-eight cell selector; `3DB90 -> CCF8 -> 3F386 -> CD44 -> 279CC` consumes the result. Eighteen further groups execute retained validation/resets, IAM/fine learning and mode reentry; nine feedback groups add the actual permission parent, load filter, final-cylinder selection, transition/event timers and initialization. Nine event-source groups connect phase/index selection, SCI0/AN24 acquisition and adaptive thresholds to that feedback. Computed writes preserve grid bounds and adjacent IAM. | Complete hardware/event scheduling and remaining cam/digital-input producers. The complete shared startup validator/reset is now covered below; physical power retention is separate. The identified software knock-event producer now has connected tests. Learned vehicle history and physical knock are not reconstructed; see the grid and feedback sections. |
| AVCS | **The old O2 bypass removed the OCV feedback/output loop. The repair restores it and moves WB/lean RAM.** Twenty-nine groups cover targets, current feedback, PWM, overrides, RAM ownership, all 21 consecutive periodic controller stages, rest learning, cam-event enqueue/dequeue/task callbacks, OCV diagnostic publication/latching and P0011/P0021 qualification/recovery. Six additional cam-sensor groups and shared mode/readiness suites connect P0340/P0345, distinct edge latches and current/raw recovery. `D26F/10` links cam/OCV raw fault latches to learning permission, duty fallback, ignition and knock-grid state. **Low target descriptor `60C34` also feeds `498B0 -> D0FC -> 496C8/49960 -> D0F8 -> final spark`**, with IAM gating. | Complete physical capture/RTOS delivery, aging-triggered reset workers and task timing. The shared startup bank validator/reset is now covered below. The native mode dispatcher and capture callbacks now execute in connected tests. A forced full cam-event queue drops callbacks; actual queue occupancy and cam angles are absent from the loaded capture. See the [connected controller and repair](AVCS_OCV_REPAIR_20260913.md). |
| AVLS | Twenty-two groups cover mode/phase sequencing, current conversion, timer initialization/updates, electrical and switch diagnostics, current-fault recovery/low-lift fallback, and GPIO/debounce/published switch inputs. SD selects high VE for `CD86=3` before bank actuation. Shared AVCS/AVLS timer writes and WB-status/AVLS port bits preserve each other in connected tests. | Complete received-status reset production and hardware scheduling bounds. The shared startup bank validator/reset is now covered below. Class-0 snapshot workers are now executed. Shared special-message, shutdown, readiness and mode paths now have connected execution evidence. Neither software mode nor calculated duty confirms valve motion. See the full sequence below. |
| IDLE_DBW | Native groups execute driver maps, rate/received-limit arbitration, CAN timeouts and final `C2B4` composition, plus tracking-monitor enable, position-based tolerance/delay, fault retention, measured-angle selection, injector inhibit and the bounded `80A8` learning writer. WB-triggered cruise cancellation is now connected through pedal selection and native overrun delays. Final-timing compensation also executes through the base-air sum and final throttle request. Four additional groups connect native pressure/output bounds, all eight update phases and pedal-driven feedback release. | Complete other idle/learning and digital-state producers, diagnostic reporting/retention and scheduling bounds. Physical blade and received samples remain inputs. No independent dashpot experiment is incorporated by this audit. |
| ROT | Six dormant-patch groups execute native `279CC` through the main wrapper, its enabled control, gate boundaries and invalid calibration. Saved main is OFF; v2/captured call native directly and erase the allocation. Repeated calls restore stock angles before bounded retard, without accumulation. | Final-angle feedback consumers and interrupt/scheduling effects remain in TIMING. Removed v2 code cannot explain the captured v2 event. |
| RETIRED | Actual retired entries execute only RTS/NOP without RAM access. Six fan groups cover all eight duty modes, all 36 computed mode-table entries, five consecutive native parents, period/output writes and poisoned retired data. The only external retired-address literal is the checksum's exclusive end. | Known native entry paths are covered; arbitrary corrupted control flow and physical fan/timer behavior are not claimed. See [retired allocations](#dormant-and-retired-patches). |
| IMAGE | Build marker, Subaru checksum and injected-flash extents. Native `F5FE/F97C` accepts the exact captured image; corrupt in-memory controls fail. Separate `4FB8C/4FB46` accumulation and protected-record checking now execute through completion. | Complete scheduler integration and computed entry analysis; checksum success does not establish execution time or RAM headroom. |

## Initialization is an actual native dependency

Application entry `F50C` sets FPSCR from `F5CC=00040001`, selects stack
`FFFF7304`, and enters `CC80`. That startup path calls `F820`; its final
`F8B4` stage writes zero at `FFFF9300`, programs source/destination to that
address, and sets a transfer count of `0x133F` longwords from the bounds at
`FA04/FA08`. The resulting extent is **`FFFF9300–FFFFDFFB` inclusive**.

`CHCR0=001F0129` selects fixed-source, incrementing-destination, longword,
automatic burst transfer. The code waits for completion before disabling the
channel. These register meanings follow the
[Renesas manual, section 10.2](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual).
This is a traced initialization contract, not a measurement of DMA hardware.

The range includes obsolete `ABE4`, diagnostic selector `B1F8`, wideband
publications, new lean scratch `AE9C/AEA0`, native AVCS `C85C/C860` and cylinder-disable `D93E..D99C`.
Consequently, a successful normal startup provides a clear state before
individual task initializers run. A missing direct write xref at one byte
would have missed this computed hardware write.

`7266C` formerly set `B1F8/01` only for coolant -30..-20 C, IAT 100..120 C,
very low MAF ADC and particular digital inputs. `13394` uses that bit to
select an alternate diagnostic branch once per ten calls. Both calls to
`7266C` are bypassed. Its initialized zero selects the ordinary branch;
the other ten-call and fifty-call tasks still run.

### Retained-bank validation and global reset

The [seven startup groups](../../tests/test_startup_retained_process_flow.py)
execute the complete retained-bank validation and cold-reset chains, plus
the RAM self-test, in current main/v2 and the captured image. CPU helpers run
native instructions. DMA completion and deliberately corrupted RAM readbacks
are explicit test events; they do not establish hardware timing or retention
across a power interruption.

`F820` first runs the two-pattern `F950` test over **`9300..DFFB`**. If that
passes, `4C7C` temporarily moves SP to **`DFF8`**, saving the old SP there.
It copies **`6000..7FFF`** into `9300..B2FF`, tests the low region, restores
the copy and returns to the old stack through `4C82`. It then clears the work
region through `F8B4`. A first-region readback fault produces `B135=1` and
skips the low-region test; a low-region fault produces `B135=2`. The tests
inject errors at both ends of both regions. Neither path tests or clears
**`8000..92FF`**. The word **`DFFC..DFFF`** also stays outside the self-test
and DMA-clear ranges. Stack writes below the temporary SP are separate from
the saved-pointer word itself.

The retained-bank state machine is separate from that work-RAM clear:

| Stage | Native operation |
|---|---|
| Work reset `F6D6` | Clears `B134`, `B13D` and `B13E`. The startup parent calls this before retained validation. |
| Validation entry `F710` | Requires u16 header `8000 == AA55`. A mismatch sets `B134=1`; an otherwise clear flag calls `CE0C -> 65F8 -> FD5C`. |
| Complete validator `FD5C` | Calls all 18 validator entries through `FE8C..FED0`, stopping at the first nonzero result. With all passing, protected byte `8260` must differ from `A5`. Tail `F5F0` publishes failure into `B134`. |
| Begin reset `F710` | With `B134==1`, writes the **invalid marker `55AA`**, then `CE18 -> 6604 -> B536` initializes protected floats `803C/8044`. This does not yet make the bank valid. |
| Complete reset `F754` | With `B134==1`, `CE12 -> 65FE -> 10690` executes all **58** cold initializers through `108BC..109A0`, then writes `AA55` as its final store. With a clear flag it preserves the bank. |
| Explicit invalidation `F5F6` | Writes only `8000=55AA`; it is not a hardware-register initializer. The next validation requests the same reset. |
| Link-status publication `30A84` | Sets `C6F6/01` when the header differs from `AA55` or `8260==A5`; otherwise clears that bit. The other seven bits are preserved. This store alone is not an injector-cut request or proof of a remote response. |

The native startup ordering is `633C -> F6D6`, `6396 -> 66B4 -> F710`,
then `6512 -> F754`, followed by `6518 -> FEF4` ordinary task initialization.
The `67DC -> F710` and `6620 -> F754` pointers are native in all three
images. The tested retained sequence must not be described as an invocation
of every intervening hardware initializer or all of `FEF4`.

Valid warm-bank fixtures retain nondefault values at `803C`, fuel trim
`81D0`, cam offset `8264`, knock cell `831C`, IAM `851C` and barometer
`8E04`. Corrupting either one of a float record's two checksum copies repairs
that copy without a global reset. Corrupting **both** copies at any of those
six records makes the native parent request the **entire cold-reset chain**.
It then restores zero trims/cells, cam defaults of 40 degrees, barometer 760
mmHg and the image's IAM default: 0.5 in main, 1.0 in v2/captured. Thus a bad
record in one subsystem can reset learning in another; record integrity is
a cross-subsystem dependency.

The complete cold-reset chain preserves canaries in the new WB/lean scratch
and native OCV integrators. Their ordinary startup initialization is a
separate dependency covered by the repaired `1055C -> 7EBA0 -> 33964` checks.
No additional alias or patch defect was found in this retained-bank sequence.
This path preserves internal RAM; a bulk EEPROM save/restore mechanism is
not established by it. Actual retained contents during the loaded capture
and power-loss behavior remain separate questions. Later explicit invalidation
requests and their logger interaction are traced below.

### Later retained-bank invalidation requests

The [five reset groups](../../tests/test_retained_reset_process_flow.py) connect
native input sampling, feature configuration, shutdown callbacks and the
`48830 -> 4892C` request sequence in all three images. CPU helpers execute
native instructions; SCI0 completion bytes, GPIO levels and selected shutdown
states are supplied test inputs.

Installed `737C8=81` passes through `147C0` to **`B289=C4`**. The complete
feature-initialization prefix `10140..10184` then produces **`CC4D=07`**,
so `3BC1E` enables this path. Starting a fixture at `10148` would omit the
first initializer and falsely disable it.

The actual request source is **serial input channel 2, bit 2**:
`766C -> AAEC/AAFA -> 6BB4 -> 193D0 -> B51A/04 -> 19C90`.
Two matching samples publish the bit's inverse. `B51B/02` carries the same
inverse. This is separate from AVLS PE14/PE15, which publish to `B51C/20,10`
and `B51E/04,02` with the same polarity. The earlier statement that
`B51A/04,02` were inverse AVLS switches was incorrect. Neither the external
serial device's wiring identity nor its state during the cut is established.

| Stage | Native condition and effect |
|---|---|
| Cold `4898C` | Sets the top two-bit field of retained `8E0C` to **1**. This blocks `4892C`, regardless of the serial level. |
| Rearm `48830` | With the feature enabled, `C778 != 0` and serial bit 2 high, sets that field to **2**. Tracks `D04C/D04D/D04E` and emits native shutdown accounting events through `C700 -> 11EE8/11EEE -> 3107C/31094`. |
| Request `4892C` | Requires the feature, `C778 == 0`, serial bit 2 low, and the field's low bit clear. Writes `8262=4055`, then `8000=55AA`, then field **1**. Preserves the lower six bits of `8E0C`. |
| Following calls | Field 1 blocks another request until rearmed. Existing learned floats remain unchanged. The next startup validation/reset performs the complete cold-reset chain. |

The periodic task invokes `48830` and `4892C` consecutively at `11612/11618`
through `117D0/117D4`. Their code and pointers are native in the captured and
repaired images. The tests cover every two-bit field value and the separate
feature/shutdown/serial gates, plus an actual rearm/request sequence and
its subsequent global startup reset.

Invalidation makes `30A84` publish `C6F6/01`. With the native ignition-on
input present, 100 complete `310D8` updates retain `C778=0`; the invalid-bank
flag does not initiate shutdown. The other identified `F5F6` caller,
`4F6F4`, is excluded by its sole installed parent `5652C`: `3BC38`
unconditionally returns zero, as covered by the diagnostic-mode suite.
These paths reveal no additional patch-induced reset or direct cut.

### Logger reads and the explicit reset-write handler

The [six SSM command groups](../../tests/test_ssm_command_process_flow.py)
extend the receive-size tests through `32BB4`, `32CA4`, `474AE/47A08`,
`32FEC`, first-byte timer service `32B24`, and response/echo progression
`32DE8 -> 3322C`. All CPU helpers, standard parameter getters and integer
division execute native instructions. Clean SCI1 receive/completion events,
matching echoes and timer ticks are supplied; baud timing and interrupt
arrival remain outside this test.

Every saved profile selects **43 byte addresses**. Each produces two complete
continuous responses, with native **49-byte frames** and correct checksums,
in main, v2 and captured v2. Direct RAM bytes match the supplied memory;
standard indexes execute their actual getters. Protocol writes remain in
the enumerated communication workspace. Retained records are unchanged,
and no profile reaches `336E6`, `32894` or `F5F6`.

The distinction is in the native command and dispatch tables:

| Request | Native path |
|---|---|
| **A8 read**, including parameter `0060` | `C846/10 -> 334B8 -> 33668`; getter table **`4B6FC`**. Index 60 points to **`319E2`**, which reads the high byte of `8262`. |
| **B8 parameter write** to `0060` | `C846/04 -> 33418 -> 336E6`; setter table **`4BD3C`**. Entry **`4BEBC -> 32894`** writes the high byte of `8262`, then invalidates the header unless the complete word equals `AA55`. |
| **B0 raw write** to `FF8000` or `FF8262` | Native address classification denies those writes. This does not substitute for the explicit parameter-write operation. |

Positive controls execute the B8 writer and verify that exact marker condition.
Bad-checksum and oversized 44-address requests do not reach command dispatch.
This closes the saved profiles' suspected read-to-reset interaction; it does
not infer which other commands a host sent during an unrecorded session.

## The complete airflow task and its other writers

The [seven native airflow groups](../../tests/test_airflow_task_process_flow.py)
execute the complete `172A4` body from main, v2 and captured v2. The two
changed pointers within this body are `173FC -> 27088` (zero-returning
MAF-fault query replacement) and `1743C -> 7E18C` (SD wrapper). The remaining
instructions and load-conditioning constants match stock in all three images.

The entry snapshots RPM `B544` into **FR15**, processed MAP `B2A0`, coolant,
IAT, runtime, selected plate, speed, crank status and prior load. Before the
SD call it still moves previous `B458/B45C` into `B414/B418`, copies `B448`
into those two synthetic inputs, and averages `B414/B418` into `B41C`.
Two native IAT/old-airflow lookups (`5EB88/5EBA4`) publish `B44C/B450`.
Those results, old airflow and purge contribution still enter the legacy
pre-hook arithmetic. The wrapper replaces that arithmetic's result and
publishes current SD to `B420/B448/B458/B45C`; the caller stores the returned
value into `B420` once more. After another invocation, the old-history
snapshot therefore contains the previous SD sample, not sensor MAF.

Stale histories from 0 through 500 g/s, nonfinite synthetic histories and
all reviewed legacy load-latch combinations do not override final SD in
these tests. Invalid native MAP or IAT reaches the installed fallback even
though the old lookups ran first: **500 g/s for main, 12 g/s for v2/captured
v2**. The value-model checks do not emulate FPSCR sticky exception flags or
FPU timing. No fault state is inferred from the loaded capture by these tests.

The later stock special-load branch is not an ordinary 3,000 RPM mode.
Setting `B444/20+80` needs coolant at least 160 C, RPM at least 10,000,
selected plate at least 125, speed at least 300, plate delta below -125,
other qualifications, and `737CE=FF`; the installed byte is **00**.
Normal inputs clear `B444/80`, and the reviewed normal branch clears `/20`.
The separate `177DC` service resets `B454` when `/80` is set, otherwise
increments it with byte saturation. The low five bits of `B444` survive the
tested updates. This is a retained native latch, not the patch's lean-cut state.

For positive RPM, normal raw load is `min(B420 * 60 / FR15, 4)` at `B428`.
`B42C` applies the unchanged **0.06** coefficient at `73968`; `B430` includes
the `5EB6C` correction published at `B434`. The reviewed map returns 1.0 in
the tested low-pressure and loaded fixtures. The subsequent `B438` selection
uses stock coefficients `73974/78/7C/80`, all 1.0. `B43C` records its change
from entry load, and `B440` applies a separate 0.5 filter. At exact zero RPM
SD publishes zero airflow, while the native division branch holds `B428`.

`177BE` maintains **a different history**, slow airflow `B424`, with
`73964=0.5`. It is not the 0.06 load filter. Its identified readers include
`217B8`, `21C50`, `2212C`, `2FFA8`, `673C6` and logger converter `4F1FA`.
The first three feed retained O2/learning state; `2FFA8` feeds front-A/F
calculation work `C6AC/C6B0`, whose identified direct consumer is inside the
replaced sensor processor. `673C6` supplies diagnostic thresholds
`D29C/D2A0` to `66C3A/66EB2` and the retained IAT/purge timer `672E4`.
These secondary edges must be distinguished from the tested core SD task.

Startup `1780A` uses coolant lookup `5E9C8` to seed airflow and all three
synthetic inputs/histories, and `5E9DC` to seed `B428/B42C/B430/B438/B440`.
Stopped reset `1785C`, called from `10A28`, only runs for `B52C/80`. It resets
those five load values and `B414/B418/B41C/B420/B424`, and clears the three
special-load flags. **It does not rewrite `B448/B458/B45C`.** The following
complete SD task owns those three publications again.

The native producer `1A16E` copies event-timeout state **`AC0C == 1`** to
`B52C/80` while holding interrupt mask 14. A timeout also clears `/40` and
the native event qualification through `80FE`; no timeout clears only `/80`.
Native crank-event publisher `19F9C` clears `/80`, publishes phase 0..23
to `B528` and phase modulo four to `B529`, and converts `AC04 >> 2` to float
`B530`. All 24 phases and both timeout states execute with the caller's
interrupt mask restored. Producing a hardware timeout is a separate edge:
`8AD6` selects `AC4E` or `AC4F` using `AC20`, then latches `AC0C`.
The [connected timeout trace](#engine-signal-timeout-and-queued-reset)
now executes its startup, periodic parent and reset callback. Physical timer
events and actual queue occupancy are not reconstructed from the log.

Cranking flag `B748/80` has its own producer. `1C920` calls `1C972` only
at phases 0, 4, 8, 12, 16 and 20. It evaluates coolant tables
`5F498/5F4AC`, which yield **500/300 RPM**, and `5F134`, an event-count
delay. RPM strictly above 500 clears hysteresis byte `B797`; RPM at or
below 300 sets it, and the band holds it. The crank flag clears, together
with `/40`, only when that byte is zero and injector event counter `C0AC`
meets the delay. The delay is **zero at the logged 66–67 C**, versus 10
events at 20 C. Other `B748` bits are preserved. Tests enter, hold and leave
this state, including count 9/10 at 20 C and the loaded RPM range.

While `/80` is set, the native airflow task selects the coolant initialization
load. This is now connected to its actual phase/RPM/count producer rather
than supported only by forced-flag tests. Injector initialization and
resynchronization can clear `C0AC`; its normal `26944` updater saturating-
increments it. At the capture's zero delay, a counter reset alone cannot
re-enter cranking when RPM remains above 500. This does not prove that
hardware crank events or task execution remained continuous during the cut.

## MAP and barometric state transitions

`47D92` runs these native stages in this order, then falls through to `47DB2`
to publish `CFBC` after restoring its caller's PR:

1. `48134`: overrun qualification from **`BF20/40`**, stored estimate at most
   733 mmHg and `CFD6 >= 625` controls `CFD0/10`.
2. `481BC`: speed 5–80, `B2BC/02`, `CC6D/08` clear, selected gear 2–5,
   non-decreasing quantized speed and `CFD8 >= 188` qualify `CFD0/08`.
3. `47EA6`: a rising result from `312E0` or stopped-state `B52C/80` with
   **entry counter exactly 625** qualifies `CFD0/80`. It increments or resets
   `CFD4` after that comparison, and saves the current edge state.
4. `47F84`: computes pressure-loss allowance `CFC4` and throttle threshold
   `CFC8`, then qualifies `CFD0/40` after 63 prior eligible calls. The gates
   include ECT above -30 C, RPM strictly between 1,000 and 6,500, selected
   throttle above the lookup threshold, `D272/02` clear, and the stored-minus-
   processed-pressure residual within 50 mmHg. Disqualification clears the
   flag and its `CFDA` counter.
5. `480B8`: resets `CFCC` at 200, while stopped, or during running-pressure
   learning; otherwise `/10` or `/08` permits adding `B538/225`.
6. `4803C`: qualifies `CFD0/20` from the **updated** `CFCC >= 200`, provided
   `D272/02` is clear.
7. `47DCC`: applies fault substitute, direct sample, running update, +2.5,
   or hold in that priority order; clamps the stored estimate to 570–770 mmHg.

`312E0 -> 4244` extracts the packed field using selector `0202` from `825C`
and returns its low bit, equivalent to `825C/10`. `31002` initializes this
field; `310D8` changes it through its own state transitions. Calling it a
physical pressure switch or an independent barometer is not justified.

All [six native barometric test groups](../../tests/test_barometric_process_flow.py)
pass on main, v2 and captured v2, including the table helpers and protected
record writer: deep-vacuum hold, the packed-state edge, stopped sampling and
restart reset, MAP-fault priority, running eligibility/fault recovery, and
both distance qualifiers. The distance increment produces one +2.5 update
before the next pass clears its accumulator. Every test also verifies that
this complete update path leaves **ADC-derived `ABC4` unchanged**.

This closes the estimator's reviewed internal ordering and conditional paths.
It does not establish every upstream cause of `825C` or every later consumer
of processed MAP/estimated barometric pressure. There is still no basis for
changing the sensor intercept from a logged pressure minimum.

## IAT conversion, substitution and voltage histories

The IAT conversion routine starts at **`786C`**; `7898` is the descriptor-load
instruction inside it. It reads unsigned raw ADC `AB3A`, prior filtered word
`ABB0` and `72878=0040`. Native `25CC` implements the Q8 coefficient 64/256:
the new word is raw plus the truncated 75% prior-minus-raw difference.
`257C` converts it to volts using `5/65536`, then native `209C` evaluates
the 30-point float table at descriptor `609B8`, voltage axis `72960` and
temperature values `729D8`, and publishes Celsius at `ABAC`.

Task 13's descriptor at `4A6C` points to entry `68E2`, software priority 1.
Within that task, `786C` precedes `11860 -> 16D1C`. The latter uses
`64FA8`, which returns nonzero for **`D26C/20`**, to select `ABAC` or a
20 C substitute into `B3B8`. `1D228` returning 1 (`B748/80`) also captures
the selected value in `B3BC`. Otherwise `B3BC` holds its prior value.
Initializer `16DA8` directly seeds both temperature destinations from `ABAC`.

The tail of `16D1C` reads **the same raw IAT ADC `AB3A`**. It scales the
unfiltered word to volts, applies a 0.25 filter into `B3C4`, then a 0.0625
filter into `B3C0`. These are IAT **voltage** histories, not Celsius and not
SD's temperature input. Their previous description as a separate tail must
not imply an unrelated sensor. Only the initializer/update and self-history
reads appear in the direct xrefs; further computed consumers are not proven.

All [four native IAT groups](../../tests/test_iat_process_flow.py) pass on
main, v2 and captured v2: full ADC range and filter step, the two voltage
histories, start/fault combinations with raw-temperature export, and the
retained timer below. Native table helpers execute opcodes. A step from
16,384 to 49,152 gives filtered word 24,576; starting from 1.25 V, the
voltage histories become 1.875 V and 1.2890625 V. Even when conditioned
`B3B8` substitutes 20 C, raw export `4F1E0 -> DA5A` still uses `ABAC+40`.
Conversion/publication ordering does not prove every consumer sees the same
sample epoch: the higher-priority crank tasks can preempt this task.

One retained dependency is `672E4`: ECT 30..119.3 C, IAT **strictly below
70 C**, positive RPM/load and `4714E` (`DB27==1`) can qualify a counter,
subject to its other bank-state comparisons. After 39 preceding qualifying
calls, it reloads `D2A4` to 703. Losing the IAT prerequisite clears byte
`D2CA` and decrements the timer; it does not instantly clear the timer.
The traced consumer `1B15E` requires that timer to be zero before qualifying
purge operation. This is a purge-inhibit dependency, not an injector cut.

Other identified temperature consumers include after-start and hot-IAT fuel,
feedback learning, spark corrections, idle air, cam-control qualification and
fan control. They are not all closed by the four tests above, and the
upstream fault monitors remain a separate edge. The aggregate publisher
`63174`, subject to its common enable gates, sets `D26C/20` if any of the
P0112/P0113/P0111 descriptor bits is present: `5C458/5C46C/5C480` share
protected current-status byte **`8E84`**, masks `01/02/04`. P0112/P0113
enable bytes `5BDA6/5BDA7` are 1, but **P0111 at `5BDA8` is 0 in stock
and all three reviewed images**. The earlier statement that all three were
enabled was incorrect. The address follows the descriptor index multiplied by two from
`8E58`; it is not a direct unscaled byte-array offset.
The common gate is `470F4 != 0` (`8FA0` is `FF` or `A5`) or
`47198 == 1` (`DAA4`). Otherwise the aggregate explicitly clears the bit.
`4FD2C` produces `DAA4` from diagnostic-mode and common operating qualifiers;
the separate `46F52` call returns `D952/10`. These are native diagnostic
state gates, not a direct electrical measurement of the IAT sensor.

The [three connected electrical-fault groups](../../tests/test_iat_fault_process_flow.py)
now execute the upstream P0112/P0113 path. `78AC` classifies **unsigned
filtered ADC `ABB0`**, independently of the calibrated Celsius result:
`7B28A = 2150` is the lower bound and `7B288 = 61814` the upper bound.
Below the lower value returns 2; at or above the upper value returns 1.
The patch's neighboring MAP-boundary write at `7B286` leaves both words stock.

Dispatcher `685C8` runs high-voltage monitor `685D2` and low-voltage monitor
`6864C`, gated by `DB24 == 1` and native group `20` eligibility. Counters
`D338/D339` reach the installed threshold of 8 before the ninth eligible call
reports P0113/P0112 through `50FF6`. The tests follow protected status into
the complete `63174` aggregate and `16D1C`'s 20 C substitution. Healthy
confirmation immediately calls `5108C`, clears current status and restores
the calibrated temperature. The separate raw latch at `DACC` can remain
without retaining IAT substitution. Readiness loss resets qualification.
The [record suite](../../tests/test_diagnostic_record_process_flow.py)
executes both native P0111 reporters: they return before reading mode
`8FA0`. Full `511F8` constructs mask `03` for status offset `16`, removing
P0111 bit `04` from both raw and all three protected banks. An explicitly
seeded current bit can temporarily request the 20 C substitute; after the
native mask, the aggregate releases it. A descriptor alone therefore does
not establish an active P0111 plausibility monitor. Its earlier open-producer
entry is closed for these installed bytes. Snapshot transport and actual
sensor faults remain separate from the electrical fixtures.

## Configured cylinder-disable flow

`6A156` initializes six configuration bytes from `74CFD/74CFE/74CFF/74D00/74D02/74D03`.
All are zero in stock, current main/v2 and the captured v2 image. **`74D01`
is skipped**, so its nonzero byte is not an enabled cylinder request.

`11AD0` calls `6A636` with its phase argument. The routine calls `6F4B8`,
`6FA3E`, then `6FAD4` only when `B544 <= 1000`. The first producer controls
the upper two bits of `D94C` and low four bits of `D94D`; `27090` turns them
into paired spark inhibition at `C0DC`. The second pattern producer copies
`D996` low six bits into `D94C` low six bits and calls `1C5D4` to publish
injector inhibition at `B744`. These are configured disable patterns;
neither a cam-command identity nor an injector-circuit-fault identity is justified.

The RPM gate is an early return, **not a clear**. An imposed request can set
a channel below 1,000 RPM and retain it at 2,800–3,500 RPM. Clearing its
configuration while above the gate does not update the publication until the
producer runs below the gate again. This is native behavior shared by stock
and patch. No patch path that creates the request has been established.

The [three native execution groups](../../tests/test_cylinder_disable_process_flow.py)
cover zero configuration over stop/idle/running transitions, all six imposed
single-channel requests, persistence above the gate, and release below it.
They pass for current main, current v2 and the exact captured v2 image.
The engine is not simulated. The additional shared-state trace below checks
the identified configuration writers and neighboring computed arrays.

## Purge, WB and the shared diagnostic/cylinder-disable workspace

`D94B` is not a single cut flag. Its identified writers have these masks:

| Bit | Writers and meaning established by the native flow |
|---|---|
| `02` | `6DA94` publishes a cell-validity result from `D9AB/02` and adjacent-cell checks. `6C088` consumes it as one diagnostic qualifier. |
| `20` | `6E338` publishes monitor eligibility and updates `D852`. Stopped-state reset `6A9B8`, gated by `1A256`, clears this bit and reloads that counter. |
| `40` | Initializer `6A156` sets it; configured spark-pattern sequencer `6F4B8` sets/clears it. |
| `80` | `6FA3E` evaluates configured injector patterns when `D800==600`; `6FAD4` can clear it when a pattern expires. |

Each identified writer preserves the other bits in its read/modify/write
sequence. This is not a proof that all possible task/interrupt interleavings
preserve simultaneous updates. More directly, `6FAD4` first checks all five
injector configuration bytes: if their low six bits are zero, it clears
`D810/D996` and the published cylinder mask irrespective of `D94B/80`.
The only identified non-initializing writers of `D93E..D943` clear existing
pattern bits; they do not create a request. Startup copies all six from zero
ROM bytes. Tests across all 256 supplied `D94B` values leave the default
patterns and both injector/spark publications clear. An independently supplied
pattern remains effective when `6E338` clears only bit `20`.

Two native RPM gates matter. Sensor task `11860 -> 6A618 -> 6E5F4` updates
the stability counters only at `B544 <= 1000`. Parent `6A6AC` snapshots RPM
into `D96C`, copies channel `B058` and six timing samples under mask `E0`,
then also skips its diagnostic body above 1000. Its final `D96A` publication
still runs. Therefore, the `6E338 -> 6DE50 -> 6DA94 -> 6E704` sequence is
in the low-RPM body, not a new monitor transition at 3,000 RPM. The entire
low-RPM parent has not been executed in this fixture. Ghidra has no function
body for `6A6AC`; the entry/gate/snapshot path executes the original ROM bytes.

`6E5F4` maintains three separate saturating byte counters. `D993` requires
both the previous and current `B51E/08` classification to be clear; `D994`
does the same for `BF1C/80`. `D995` resets when purge duty crosses the
near-zero classification boundary (`24FC`, tolerance `0.000244140625`),
otherwise increments. Their required counts are 8, 16 and 8. At zero duty,
qualifying `6E338` can set `D94B/20` and count `D852` from 12 down to zero.
Its other prerequisites include elapsed `B688 >= 2500`, ECT at least 70 C,
sampled RPM 500–7000, `D94A/80`, and native bank readiness getter result 2
(`1932C`, plus `19358` when `CC4E/10` selects both banks). These are additional
conditions, not just a purge-duty comparison.

Installed external WB 50 or invalid WB 0 makes that native readiness
condition fail: `6E338` clears only `/20` and reloads `D852=12`.
`6DE50` then resets its current-span extrema/counter and `D94F/04`.
`6E704` instead **holds its previous learned samples and cell counts**.
The native-ready positive control can count the timer down; returning to
the actual WB publisher revokes eligibility again. None of these transitions
creates a default cylinder-disable request.

The computed histories deserve independent bounds checking. `6E704` uses
channel `D9AC` and cell `D851` to address float samples
`D438 + 156*channel + 4*cell` and byte counters
`D853 + 39*channel + cell`. Their extents are `D438..D7DF` and
**`D853..D93C`**, immediately before `D93D` and the configuration at `D93E`.
There is no local index clamp in this writer. The identified producers are:

- `D8EE` initializes channel source `B058` to zero. Running writer `D92C`
  stores its loop index only inside a six-iteration loop, hence 0..5. The
  snapshot copies that byte; its later `D96A` clamp is not the bounds proof.
- `6DA4C -> 20E0` maps sampled RPM through 13 byte values 0..12 at descriptor
  `5EDF0`. Processed MAP `B2A0` adds 0 below 400 mmHg, 13 from 400 to below
  600, or 26 at/above 600. Native lookup clamping and these bands produce
  cell 0..38; neither the descriptor nor its data was changed by the patch.

All [five connected groups](../../tests/test_purge_monitor_shared_state_flow.py)
pass on main, v2 and captured v2. They cover stability/reset/hold transitions,
the native high-RPM parent exit, readiness-to-monitor reset, shared-bit
preservation, and first/repeated writes to all 234 history cells. Adjacent
configuration bytes and native AVCS `C85C/C860` (the former, incorrect lean allocation) remain untouched. The bank
producer's loop bound is an assembly trace; actual crank event delivery,
retained-record commit/reset and other low-RPM diagnostic stages remain open.

## Retained legacy O2 workers and their protected offsets

The slow dispatcher `1152C/11532` still calls complete workers **`217B8` then
`2212C`**, even though the patch replaces front-A/F input and disables O2
diagnostic reporting. The [five native groups](../../tests/test_legacy_o2_process_flow.py)
execute these complete workers, their native table helpers and protected
record writes on main, v2 and captured v2.

`21774` initializes the analog-voltage histories from `ABCC/ABD0`, the rear
reference `BD0C` from `761EC` (approximately 0.6), the airflow integral
`BD28` from a temperature table, and `BD04/BD08` from protected offsets
**`8200/8208`**. Each protected record is eight bytes, comprising the float
and the two validation words. They are separate from four-region long-term
fuel learning at `81C0..81FF`.

`217B8` snapshots RPM, load, coolant, filtered airflow and elapsed count.
Its bank worker `218F0` needs an active bank `B90D/E == 1`, RPM below 6,000,
conditioned lambda from 0.891 to below 1.041, load at least 0.15, ECT at
least 40 C, the retained rear-readiness getter result 2, diagnostic getter 0,
elapsed-count qualification and `B91D == 1`. It then sets `BD1C/D /80` and
increments the corresponding word counter; any failed prerequisite clears
`/80` and resets that counter.

Subsequent native stages still filter raw `ABCC/ABD0`, build the rear
reference and calculate the controller's intermediate states. When the bank
is ineligible, `21F0C` publishes the saved offset unchanged into `BD04/BD08`,
zeros its integral contributions and updates the history. Consequently,
disabled feedback does **not** imply those published offsets are zero.

Two pre-existing Ghidra labels were misleading: **`21AC0` and `21B1C` read
vehicle speed `B538`, not airflow or RPM**. Their names are now corrected.
The first maintains a 10/30-speed hysteresis and `BD14`; the second uses
255/254-speed hysteresis and a 32-prior-call delay for `BD1E/80`, then adds
approximately 0.059 through `BD10`. These qualifiers do not trigger in the
recorded speed range. Native boundary tests exercise both latches.
`21C50` separately accumulates slow airflow `B424` into `BD28`, clamps the
sum to 0..76,800, and holds it while `B748/80` indicates cranking. This is
a bounded scalar accumulator, not an index into adjacent RAM.

`2212C` snapshots slow airflow to `BDEC` and ECT to `BDE8`, then calls both
offset learners using descriptors `4B3F4/4B40C`. Their eligibility requires
the previous worker's active `/80`, `B910/B914 < 0`, the bank count at least
3,750, airflow at least **299 g/s**, ECT at least **110 C**, and the other
native inhibit flags clear. Failed qualification clears the local learner
permission and timer, while preserving the protected offset. Successful
qualification filters `BD04/BD08`, counts a further delay, and eventually
steps the saved offsets, clamped to -0.5..0.5, through native `49530`.

Installed external WB, valid or invalid, causes `B90D/E=0`; the complete
legacy pair clears eligibility and holds both records in the tests. The
loaded capture's temperature and calculated airflow also fall below this
additional learner's thresholds. A separately supplied eligible positive
control executes the active controller and changes both records after 150
calls, then confirms that returning to installed-WB qualification holds
those records again. This is conditional native behavior, not a claim that
the driving ECU had those retained values.

The two `BD04/BD08` loads in primary feedback preparation at `202CC/202D0`
are already replaced with `FLDI0`. Connected tests run the complete legacy
pair, phase-selected main feedback and final OL fuel composition with
offset pairs `(0,0)`, `(+0.5,-0.5)` and `(-0.5,+0.5)`; the resulting fuel is
identical. Other identified direct readers export these offsets or feed the
same legacy learner. This closes this specific path for reintroducing rear
fuel correction; it does not remove the separate readiness incompatibility
or establish the cause of the loaded cut.

## Scheduling and stack coverage

Task 6 (`49FC`, entry `696C`, priority 2) reaches the added cut, SD and target
wrappers through `11AD0`. Task 5 (`49EC`, entry `6938`, priority 4) reaches
the injector scheduler. The cut publication lock prevents task dispatch
between native clearing and reassertion of a continuing added cut. Higher
hardware interrupts remain possible.

The kernel uses a shared descending task stack: `3CAC` loads R15 from
`4944=FFFF719C`; `3930/3A1C` dispatch using saved stack positions. The first
task-state record begins at `FFFF719C`. Descriptor byte `04` selects floating
register context handling; it is not a 1,024-byte private stack allocation.
The physical lower RAM boundary is `FFFF6000`, but **4,508 addressable bytes
below the stack top are not a proven free stack budget**. Kernel data and
all nested task/interrupt frames require a complete interval/depth review.

Existing tests check register preservation, local frame balance and selected
IRQ/resumption cases. Their 512-byte model stack is a fixture, not a measured
ECU allocation or worst-case depth. SD's extra native-call depth is bounded
locally, but total scheduler headroom remains open.

## Retained wideband and diagnostic dependencies

The stock initializer sets both raw impedance values `AE78/AE7C` and both
conditioned readiness values `AE70/AE74` to **16,384.0**. This overrides the
earlier startup DMA zero. The external-wideband publisher subsequently owns
readiness, current and lambda; it does **not** own raw impedance.

| State | Native producer that changed | Retained consumers established in this pass |
|---|---|---|
| `AE70/AE74` readiness | Stock `B658 -> B8CC` task bypassed; external WB publishes 50 or 0 | `12F10/13014` heater control, `1331E` startup history, `18FDC/1903A` feedback readiness, `1EE74` feedback (read at interior `1EE96`), `6174A` monitor, `70B5C` monitor, logger export and replaced bank inhibit helpers. |
| `AE78/AE7C` raw impedance | Computed producer inside bypassed `B8CC`; native initialization remains | `BAE0` hysteresis and hardware selection; `12F10/13014` heater-state thresholds. They retain their initialized values in the traced normal flow. |
| `AE68/AE6C` synthetic current | WB publishes zero | Native conditioning, `6DE50` current-span monitor and diagnostic/logger exports. These private monitor states require review separately from stored DTC bits. |
| `AE8C/AE90` logger lambda | WB publishes lambda or 0; native startup B49A zeros these former front-current samples | Repaired lean guard and logger use AE8C. **B098/B09C are native OCV current**, restored with E0D0/DFB4/33AAC. The earlier claimed rear-sensor deletion was wrong. |

`B62A`, called by the sensor task, raises the native interrupt mask to `0x90`
before calling `B690`, then restores it. The new publisher stays inside this
lock. This prevents ordinary task interleaving between the two bank publications;
it does not exclude interrupts above priority 9. The parent does not use the
publisher's scratch return registers.

The four traced caller families of `64FD0/6500C` are `12C8C`, `18FDC`,
`44B14` and `45908`. They consume the returned integer status; their observed
live values do not depend on the helper preserving `R1`, `FR0`, `FR1` or T.
The latter two also retain control-state effects independent of stored DTC
enables; see the connected status-flow section below.
The retained heater path `12F10 -> 13014 -> B2C4` still writes native output
state. Deleting diagnostic enables does not delete this control path.

`6174A` compares readiness with 500 and updates descriptor-based status
`D1E0/D1E1`. The WB-ready value 50 takes the below-threshold path, clearing
bit `08`, setting bit `04`, and resetting its counter when prerequisites allow.
`61858/6186E` routes these bank status bits to diagnostic indices
`4C/4E/69` and `4D/4F/68`. All six enables are zero in the patch.

`70B5C` uses readiness to establish `DA1E/DA1F`; `70CD6` combines them
with airflow, temperature, timing and other qualifiers into `DA0E/DA0F/80`.
Subsequent monitor stages reach `70FB8` and `713DC`, which call diagnostic
set/clear reporters for indices `4B/6F` and `50/70`. Those enables are also
zero. This is a traced reporting chain, not a blanket claim that all private
monitor state is irrelevant.

### Native feedback readiness mismatch and phase-dependent clearing

The September 13 continuation found a **real compatibility defect**, reproduced
on main, v2 and the exact captured image. The external publisher's convention
is **50 = valid, 0 = invalid**, and its replacement `64FD0/6500C` helpers
return clear for values above 35. Native `1903A` uses the metric differently:
at exactly 50 it clears both feedback status bits `C0` in `B512/B513`.
The native low-readiness condition uses 35/40 hysteresis, while the alternate
qualification requires readiness strictly below 50 and additional lambda
history conditions. An invalid external value also clears both bits through
the new inhibit helper. Previously set status/history bits do not rescue the
installed valid-50 path.

The connected flow is:

1. `18DAC` reads the two external lambdas, applies the patched unity
   atmospheric table `5EA2C/73E08`, clamps and publishes `B4E8/B4EC` plus
   filtered `B4F0/B4F4` and slower histories. Its stopped/initialization
   qualifiers use `B52C/80`, `B748/80` and `B19C/80`.
2. `18FDC` calls shared worker `1903A` for descriptors `4B0C4/4B0CC`,
   which own `B512/B515` and `B513/B516`. The second bank falls through
   after the pair wrapper restores its frame.
3. `1EE0C` samples `1932C/19358` status getters, runs conditional stopped
   initialization `1F1DC` and common qualification `1F3AC`, then `1F380`,
   `1F354` and `1F2AE` for both bank descriptors `4B2AC/4B2BC`.
   Status zero leads to **`B90D/B90E=0`**, even with other prerequisites true.
4. Crank-task `11958` calls `1EE74`, which selects bank 0 at phases
   **0/8/16** and bank 1 at **4/12/20**, from `75E12..75E17`.
   Each selected bank runs purge/legacy-target handling, target composition,
   native coefficient generation, `1FCD4` delay feedback and `1FE4A` filters.
   With its active flag zero, `1FCD4` clears that bank's 21-float error
   history and writes **`B8D4` or `B8D8 = 1.0`**. The other bank retains
   its preceding publication until its own phase. `1DD04` subsequently
   consumes those short-term factors separately from retained `BCB8/BCBC`.

These are different tasks: lambda conditioning is called at `107FE`, status
at `11280`, qualification at `11514`, and phase feedback at `1198E`.
Their relative delivery/age is not proven by their ROM address order. A
permission/qualification update alone does not immediately erase an old
bank correction. Tests follow the subsequent selected phase explicitly.
With the actual enriched target for 2 g/rev/2,800 RPM, native target update
and the pressure wrapper also remove common feedback eligibility; the old
short-term factor still clears only on its scheduled bank update.

Computed memory ownership is now executed: **22-float coefficient arrays**
`B9D0..BA27` and `BA28..BA7F`, **21-float error histories** `BA90..BAE3`
and `BAE4..BB37`, and **29-float pulse histories** `BB74..BBE7` and
`BBE8..BC5B`. The latter use the native calibrated index; coefficient helper
`208A6` clamps its selected index to 1–20. These spans do not enter fuel
learning at `BCB8` or patch scratch `AE9C/AEA0`. The phase sequence still
calls `6A128`: under a native priority-11 mask it consumes and clears the
selected byte at `D954 + bank`. Disabling feedback does not remove that
diagnostic-event consumption.

[Six native test groups](../../tests/test_wideband_feedback_process_flow.py)
cover valid/invalid WB, barometric conversion, prior status bits, all 24
phases, native positive controls, correction clearing into actual composed
fuel, and array bounds across 500–8,000 RPM and 2–500 g/s. The positive
control supplies readiness 20 and a clear inhibit directly to native worker
`1903A`; it proves the retained controller can execute and is **not** a
proposed replacement calibration. Changing this shared convention requires
the remaining heater/readiness consumers to be traced first.

This explains why preserving the controller's instructions did not preserve
normal closed-loop operation. It does not establish a 2,800–3,500 RPM cut:
the installed path suppresses feedback broadly, and the existing capture
does not measure bank-active states or every task transition. No firmware
or calibration value is changed for this finding.

### Retained heater qualification, cold impedance and timer writes

The external publisher does not replace the raw impedance records
`AE78/AE7C`. Native indexed initialization at `B4DA/B4DE`, with constant
`B560=16384.0`, seeds both readiness and raw impedance; the bypassed `B8CC`
producer no longer refreshes the latter. This differs from readiness, which
the external WB task refreshes to 50 or 0.

`12C8C` still owns the common heater qualifier `B19C/80`. It uses battery,
coolant, elapsed counters, `B748` start qualifiers and both replaced bank
inhibit helpers, together with the retained diagnostic/start-mode branches.
With the installed `72ABC=0`, a rejected WB causes both helpers to inhibit
and clears the common enable. `B198/B19A`, stored `807C` state and
`B194` selection remain part of that native state machine.

`12F10`, called at `118A0` from `11860`, evaluates load/RPM, timer and
battery compensation and invokes `13014` for `4AF0C/4AF28`. It supplies
**raw impedance as FR4 and readiness as FR5**. The worker's `50/45` and
`49/44` hysteresis tests use raw impedance and set `B1BF/B1C0` bits `80/40`.
Consequently retained raw impedance 16,384 keeps both cold-state bits set
even when external readiness is valid. That path takes the native
time/temperature table result `B1B4`, multiplies by battery compensation
`B1B0`, filters with `72AF0=0.25` and publishes `B174/B178`, bounded 0–100.
Common-enable loss publishes zero duty; it does not pretend raw impedance
has become a hot sensor measurement.

Output delivery is a separate gate. Native `B1E8` initializes `AE54/AE58`
fraction requests and `AE5C/AE5D` activation bytes to zero, and establishes
the two timer register sets. `B366` activates one pending bank per call,
sets its period to **32,000** in `AB8A/AB88`, and sets its activation byte
to 1. `B280` maintains the active periods. The `12F10` publisher holds a
native priority-1 mask and calls `B2C4` twice. Each call stores the duty
fraction in Q16 at `AE54/AE58`; with its activation byte exactly 1 it uses
native `2390` to publish **period minus floor(period * fraction / 65536)**
to bank 0's **`F596/BFR7D`** or bank 1's **`F594/BFR7C`**. These are
buffer registers; the hardware transfers them to `F59E/DTR7D` and
`F59C/DTR7C` at the corresponding cycle match. The native stores alone
do not establish immediate physical output. The initialization/activation
paths preserve the other bits of shared **`F400/TSTR2`**, changing only
the relevant 7D/7C start bits. Register identities and transfer behavior
follow Renesas table 11.3, sections 11.2.22–24 and 11.3.9.

[Three native heater groups](../../tests/test_wideband_heater_process_flow.py)
cover initialization, deferred per-bank activation, actual table/control
execution and final compares on all three images. The supplied 67 C,
2,800 RPM, 13.5 V, 2 g/rev fixture settles near 7% command with retained
16,384 raw impedance. Explicit raw-impedance controls produce different
native branches while external readiness remains 50. Rejected WB and the
tested start-state override clear common enable and return both compares
to their period value. These are software output commands, not measurements
of heater current, external wiring or physical PWM polarity.

MCP provides the controller and `B366` disassembly but currently has no
defined function bodies at `B1E8/B280`; local saved-byte disassembly and
native execution cover those entries. Available MCP operations cannot create
or merge their bodies. Their caller/consumer comments record that limitation.
The connected ADC/excitation path is covered below. Other readiness and
diagnostic-state consumers remain under review before a shared-convention repair.

### ADC ownership, normal scan and retained front-sensor handoff

The WB source is **AN3 -> ADDR3/F806 -> AB06**. Native `6CE4` initializes
all three ADC modules, polls completion and copies their 32 unsigned,
left-aligned 10-bit results to the 32 words `AB00..AB3F`. In normal task
`66C6`, `6EAC` first calls `6FF2/70A8/7138` to collect the preceding scan,
then schedules the next one. The retained order is `6EAC -> 7A14 -> B62A`:
native MAP conversion and patched WB publication therefore use the RAM
results just collected, not an assumed future conversion. The bypassed
`7C30` raw-MAF call originally sat between collection and MAP conversion.

`AB45..AB4D` are three 3-byte scan-control records. Their final bytes
select copy widths; module 0 copies 1, 4, 8 or 12 channels into `AB00`.
The ordinary sequence always selects at least four module-0 channels,
including WB AN3 and MAP AN2. Every fourth call widens module 0 to eight;
every sixteenth selects all 12 channels on modules 0/1 and eight on module
2. Every fourth such full scan, `AB41=1` enables the extra front-sensor
measurement after module 1's normal completion interrupt. These are call
counts, not claimed millisecond periods.

ADI1 entry `5F64` clears its hardware completion flag and dispatches `6FBE`.
With `AB43=0, AB41=1`, this calls retained `BAE0`, which alternates the
bank using `AECF` and records it in `AECE`. It snapshots channels
**AN11/23 for bank 0, AN10/22 for bank 1** into `AE84..AE8B`.
Raw impedance `AE78/AE7C` controls separate `AECC/AECD` hysteresis:
at/below 1,000 sets 1, above 1,200 clears it, and the middle band retains
state. The installed raw-impedance seed 16,384 takes the cleared branch.

`7372` stops conversion before changing both modules' channel/mode settings.
It programs `F818/ADCSR0` to `0B/0A` and `F838/ADCSR1` to `4B/4A`,
then arms single conversions by external trigger, with ADI1 enabled only
on module 1. **`F76E/F72E` are ADTRGR0/ADTRGR1 trigger selectors, not
interrupt-status RAM.** The arm sets `AB43=1`. On the second ADI1,
`6FBE -> BCB4` copies the selected two ADC results into
`AEC0/AEC2` and `AEC4/AEC6`, sets its bank byte `AEC8/AEC9`, clears
`AED0`, then clears `AB43`. This path does not write AN3's result or `AB06`.

`BBF0` retains the accompanying excitation timer updates under a priority-14
lock. It reads shared `F440/TCNT1A` without resetting it, then uses `D744`
to write **DCNT8G/8H/8P** at `F64C/F64E/F65E`, with compare registers
`F450/GR1G`, `F452/GR1H` and **`F622/OCR2H`**. Its cold/hot selection
changes the assigned pulse counts; it does not write the six injector
down-counters at `F640..F64A`, their `F444..F44E` compares or `F666/DSTR`.
The native publisher remains active despite the bypassed impedance calculation.

The next `6EAC` explicitly clears `AB43`, stops/reprograms the ADCs and
starts normal scanning. A missing second trigger/completion therefore does
not permanently leave AN3 unselected in this executed sequence. The
one-off `740C` measurement is separate: it samples AN24 on module 2,
restores that module's prior scan selection/completion state and restarts a
previously running conversion. Its caller `A7EA` publishes `AD98`.

[Six native groups](../../tests/test_adc_handoff_process_flow.py) execute
startup, each module-0 copy width, 129 scan cycles covering both front banks,
missing front completion, assigned timer outputs and the one-off module-2
handoff. They pin unchanged native bytes across main, v2 and the exact
captured image. All register reconfiguration stops conversion first in these
fixtures; ADC completion and external triggers are explicitly supplied.
The tests check peripheral identities/semantics against Renesas sections
17.1.4, 17.2.1–5 and table 11.3. They do not establish real conversion times,
interrupt latency, simultaneous conversion completion, electrical trigger
delivery or worst-case task preemption. Other diagnostic acquisition paths
at `74BA` onward still need their full callers and recovery flow traced.

### WB status through native fault summaries and output state

The replaced `64FD0/6500C` helpers return 0 for accepted external WB and
2 for rejected WB. Two native consumers sit outside bank feedback/heater
control. `44B14` snapshots 28 native getter results on its stack, then
updates **`CEC4/80`**. The front-A/F status checks are conditional on
`CC4E/80` (set by native feature setter `3BA68`); the second-bank group
also checks `8140/01`. `DB2A==1`, read by `47178`, suppresses this fault
summary. Deleting O2 diagnostic enables does not remove these status checks.
The replacement helpers' scratch-register behavior preserves the caller's
delayed stores of previous getter results in the executed sequence.

`3771C` calls `37B32` after its other state updates. With `CAAA/01`
enabled, `37B32` responds to `CEC4/80`, `CBFE` status and protected
`8144/8148` by clearing **`CAA9/02`** and setting **`CAA8/40`**.
It also maintains `CAAC/80` from `CAA9/01`. Removing WB rejection clears
`CEC4/80` on the next aggregate update, but does not necessarily restore
the prior permission or clear `CAA8/40`: in the tested `CAAC/80` hold
state those stay latched. Upstream user/state transitions matter.

`3B760` consumes both `CAA9/02` and `CAA8/40`, together with ignition,
start, test and feature states. Under the supplied normal-ignition fixture,
the latter selects a native toggling output: `CC46` counts to
`7CAEA=125` calls, `CC48` tracks entry, and **`CC44/40`** toggles.
The routine publishes inverted `CC44/80` and `/40` to **`F754/PEDR`
bits `08/04`** through `4BC8` under priority-14 masks. The other port
bits are preserved from the read value. This establishes software output
state, not external wiring, pin-mode configuration or identification of
the lamp seen by the user. `C778!=0` clears both command bits in the
executed branch. The GPIO identity follows Renesas section 21.6.2.

The other caller, `45908`, records the qualifying fault in **`CF2D/80`**
without clearing it when the fault disappears. Parent `456C0` clears the
`CF2C..CF2E` workspace before selected status workers and publishes
snapshots at `CF30..CF3B`; `32858/3285E` provide direct diagnostic reads
of `CF2C/CF2D`. A repeated isolated worker call therefore differs from
the entire caller's sequencing. That parent and the other `CAA8/CAA9`
consumers are not yet fully instruction-executed in this audit.

[Three connected native groups](../../tests/test_wideband_status_dependency_flow.py)
cover valid/rejected WB, every called getter, summary/permission retention,
the snapshot's explicit clear boundary and 251 output updates on main,
v2 and captured v2. These paths leave the seeded injector mask `B744`
unchanged. This is a concrete additional dependency of WB validity, not
proof that the loaded cut came from WB rejection or that all downstream
permission consumers are harmless. Existing captures do not record these
flags; valid 50 also has the distinct feedback-suppression defect above.

### WB fault, cruise cancellation, pedal and overrun dependencies

The native cruise subsystem shares those permission flags. SSM index `121`
uses handler `326F0` to export the main-button and set/coast/resume states
from `CAA8`; memorised cruise speed at index `10A` uses `324F0` and
protected float `82AC`. This establishes the subsystem from native exports
and existing definitions, rather than guessing from the status lamp.
`CAA9/02` is a permission latch, distinct from raw main-button `CAA8/01`.

```mermaid
flowchart LR
  WB[Rejected external WB] --> AG[44B14: CEC4 bit 80]
  AG --> PER[37B32: clear CAA9 bit 02]
  PER --> QUAL[39CFC: clear CBFE bit 04]
  QUAL --> ACTIVE[3A482: clear CC00 bit 01]
  ACTIVE --> PED[181EA: select driver B498]
  PED --> MAP[182AC: mapped pedal B470]
  MAP --> REL[1831A and 183CE: release qualifier]
  REL --> CUT[2483C and 24570: timed overrun cut]
```

`39CFC` requires permission before its other run gates can set `CBFE/04`.
Its reviewed gates include selected gear `CD49` 2–6, RPM below 6,950,
cruise speed `CAC4` in 32–255, and separate brake/switch/fault states.
The task calls it at `111F4`, before the set/resume edge workers and active
latch `3A482` at `11218`. With qualification clear, the latch clears
`CC00/01` unconditionally; otherwise `/02` or `/04` can set it. A valid
WB recovery under the held permission fixture does not reengage cruise.

With both pedal-channel fault bits `D271/18` clear, **`181EA` selects
`B498` normally, or `max(B498, CB60)` while cruise is active**. Cancellation
therefore restores the driver sample. The 5.9 substitute at `73A14` belongs
to a separate pedal-fault branch. When `D274/80` qualifies and exactly one
pedal channel is faulty, that branch selects `min(B498, B49C)` instead.
These fault choices are independent of the cruise flag. `182AC` maps the
selected sample through `5EB54` and multiplies its separate `B478` factor
into `B470`, which produces the native pedal-release flags.

Cruise also changes the retained `24374/2483C` overrun conditions. The
connected tests execute the native threshold and six-channel delay publisher
`240F6`, mapping/scalar helpers, release qualification, `24570` and its
`1C5D4` injector-mask tail. At supplied RPMs 2,500–4,144, WB cancellation
does not start overrun with a nonzero driver sample. Pedal release is the
positive control: normal gear-2 cut delays are 13/38/56/75/94/113 calls
in the lower tested RPM band, and 13/25/38/50/63/75 at 4,144.
Reapplying pedal restores mask `002A` for 12 calls, then `0000` on call 13,
using the native restoration words `75EBC..75EC7`. Counts are invocations,
not measured time; periodic producers are explicitly refreshed in the fixture.

The shared cruise-active getter `3B430` also enters AVLS `40168` at
`40240`. Its extra high-lift branch requires both `CD9E/08` and `/10`.
Those use unchanged **speed 10,000/9,000** and RPM 512/510 hysteresis.
The speed gate disables this extra path in ordinary operation. Native AVLS
execution at 2,800 RPM gives mode 1 with cruise on or off at speed 30, 53
and 9,999; the intentional 10,000 boundary control produces modes 3/1.
That control tests the code, not a possible state of the vehicle.

[Five additional test groups](../../tests/test_wideband_cruise_process_flow.py)
cover these edges on main, v2 and captured v2. The AVLS subtest retains its
documented lookup-model boundary. Other cruise command/history producers,
CAN/status consumers (`135C4/138D8/30328`) and diagnostic snapshot sequencing
remain separate closure work. This chain does not establish the loaded-cut
cause or actual cruise/WB fault state.

### Readiness history, activity diagnostics and rear-monitor qualification

The readiness/resistance proxy `AE70/AE74` has additional consumers beyond
feedback, heater control and the two replaced status getters. Startup
`1331E` copies it into `B1A4/B1A8`. Each `13014` bank call also updates
that history through **descriptor field `+10`**, at `13270/13272`.
The computed stores are missing from the direct RAM xrefs; the variables
are not startup-only constants. SSM indices `44/45` use `319AE/319BA`
and native `258C` to export the proxy as an unsigned byte at unity scale.
MCP has no defined function at `319AE`; saved-byte execution establishes
that export without claiming the database body was repaired.

Parent `6145E` sequences another native diagnostic as `614B0 -> 6166C ->
616CE -> 61858`. `6166C` accumulates heater duty `B174/B178` in
`D1D8/D1DC`, capped at 104,857,600, or zeros the sums when common heater
enable `B19C/80` is clear. These are **duty sums per invocation**, not a
measurement of physical heater energy. `616CE/6174A` has separate gates:
run permission `DB25==1`, prerequisite queries 11/14 and heater-on timer
`D1EC >= 523`. The installed prerequisite lists for these two queries
are empty; native `56E64/56E96` returns 1 without examining a fault record.

After those gates, proxy **below 500** clears private status bit08 and
sets bit04 in `D1E0/D1E1`. Thus installed valid 50 passes this check while
failing the separate feedback convention. Failure at or above 500
also needs the duty sum at least 30,000 and bank counter `D1EA/D1F6`
already at least 102. Turning the heater off resets the sums, timer and
bank counter but can retain the prior result bits. Losing `DB25` or
prerequisite permission clears both result bits. The tests cover these
different reset paths and controlled failure boundaries.

`61858/6186E` reports the private results as P0134/P0154 (indices
105/104), alongside P0131/P0132/P0151/P0152. All six stored-report
switches are disabled in the saved images. The native reporters return
without publishing even for the controlled failure case; private diagnostic
state and stored DTC state remain different layers. The other voltage
checks in `614B0` are outside these readiness-specific fixtures.

Rear-O2 diagnostic worker `70B5C` also reads both proxies. Native `209C`
uses descriptor `5F2C0`: nine float breakpoints 0–256, **u8** cells at
`76860`, scale 1/128. It floors the result at `76090 ~= .7` before
comparing bank feedback `B8D4/B8D8` against that lower bound and
`B920/B924` upper bounds. It copies bank-active `B91E/B91F` into
`DA1A/DA1B` and rear status getters into `DA1C/DA1D`; it copies `BD0C`
into both `DA10/DA14`, as the native instructions specify.

`70CD6` consumes these through the two 15-pointer descriptors
`4CC48/4CC84`. Settled installed WB feedback produces inactive bank
flags, so this worker clears `DA0E/DA0F` bit80 while **retaining** its
counter `DA00/DA02`. A stopped-state `1A256` result clears both the bit
and counter. An explicit positive control with active banks, qualified
rear state, airflow at least 10 g/s, ECT at least 77 C, `D804 < 5`,
valid prerequisite records and the remaining descriptor gates increments
the counter to 3,125 and sets bit80. This is diagnostic qualification,
not a direct injector-cut command. The sustained bog's logged 66–67 C
does not meet this temperature gate.

[Four additional native groups](../../tests/test_wideband_readiness_diagnostics.py)
pass on all three images, including the prerequisite-list walker and
disabled activity reporters. Tested writes stay within the declared
diagnostic/heater histories and leave `B744` unchanged. Full rear-monitor
parent `70AE0` additionally selects normal/reset branches and runs other
workers before reporting; those histories and global mode producers remain
separate closure work. No runtime or calibration change follows from these
tests, and they do not identify the loaded-cut cause.

### Shared diagnostic readiness, reset and temperature history

Slow-task call **115AA**, through **1178C**, enters **5116E**. The six
native publishers run in order and copy private state **DC0A..DC0F** to
public enable bytes **DB24..DB29**:

| Publisher | Public byte | Exact dependency |
|---|---|---|
| `565BE` | DB24 | `C778 == 0` and `DB2B == 0` before decrementing DB2B |
| `565F8` | DB25 | DB24's private state and battery ABB4 at least approximately 10.9 V |
| `56668` | DB26 | DB25's private state and barometric CFBC at least 563 mmHg |
| `56694` | DB27 | DB26's private state and either B3D0 at least approximately 9.6 or `1487E == 0` |
| `566D4` | DB28 | DB25's private state and minimum-temperature history B6C0 at least -7 C |
| `56700` | DB29 | DB24's private state and both BF9C/04 and CCBB/04 clear |

The B3D0 condition is configuration-dependent: native **147C0** copies
**737C8=81** into B288 and publishes B289/04. That makes **1487E return
zero**, so installed configuration bypasses B3D0's threshold in this gate.
It does not bypass DB26's separate barometric threshold. B3D0 has its own
conversion/averaging chain `16E04 -> 16EA0`; it is not the IAT publication.
Its physical identity is not inferred from this numeric comparison.

Reset helper **50E16** loads **7C95C=63** into DB2B. **56748** clears only
the six public bytes; it does not clear private DC0A..DC0F. The next ordered
publisher recomputes both. The first 63 calls after reset remain unqualified;
the 64th permits basic readiness if shutdown is zero. Both reset helpers
are called consecutively by **4F6F4** at `4FA9E/4FAA4`. Their execution is
tested; that larger reset parent is not represented as a returning stub.

OCV and AVLS electrical diagnostics consume DB25, while IAT electrical
diagnostics consume DB24. Connected tests show that readiness loss resets
unfinished fault counts but **preserves already acquired current and raw
status**. Restoring readiness with healthy measurements clears current
status only after the native healthy qualification, leaving raw history.
Lower battery can disable the two actuator-current monitors while IAT
electrical monitoring continues. No low battery is inferred from the log.

**1AEFC** initializes B6C0 to **120 C**. **1AE04** selects minima from
coolant B3AC, selected IAT B3B8 and optional AD8C when CC4C/10 is enabled.
Cold/start qualification can capture the previous history in protected
float **812C..8133**. Otherwise the result is also bounded by previous
B6C0 and the retained value plus **2 C**. It can therefore preserve a low
minimum after instantaneous IAT rises. Native tests connect a supplied low
IAT through this history to DB28 and confirm release after reinitialization.
The supplied low is a boundary test, not a claim about the car. The same
history is read by AVCS target selection and heater qualification.

[Six groups](../../tests/test_diagnostic_readiness_process_flow.py) pass on
main, v2 and captured v2 with strict write extents. The captured OCV monitor
is called directly for gate tests; its historical periodic pointer still
bypassed it. Snapshot transport, reset-mode production, physical signals
and actual task timing remain outside these fixtures.

### Diagnostic mode, connector latching and raw-fault reset

The complete native **51124** order is **567B4 -> 56856 -> mode branch ->
5690E**. Protected byte/complement **8FA0** is the active mode; **DB2C**
is its requested value, **DC08** the previous value and **DC11** the
running-selection latch. These differ from physical connector **B51E/80**.

Startup **51378** clears DC11 and DB2C, samples the connector and selects
FF if connected, unless retained **8260=A5**. It writes 8FA0 and DC08.
Later **567B4** forces A5 from 8260, or makes one running selection when
DC11 is clear, **RPM >= 400**, **battery >= 8 V** and **B688 > 62**.
That selection is FF for connector-on and zero for connector-off; an
already selected A5 holds. The stopped flag **B52C/80** rearms DC11.
Changing the connector alone while DC11 remains set does not change mode.
This is conditional software behavior, not a recovered state from the log.

Mode zero selects **564B0**. On a mode transition it preserves/report-checks
the separate P0604 raw condition, calls **5339C** to clear eligible raw
status under descriptor metadata, clears **DAB4/DAB5**, then executes
`569F0/56AA2/56B54/56C14/56CAE/56D60` history/reset qualifiers. The
connected test clears recovered cam/OCV raw history while retaining a
supplied current OCV fault word. A subsequent actual fault report can
publish raw state again; this mode reset does not prove healthy hardware.

FF selects **5652C -> 53408** on transition; A5 selects
**565A2 -> 534F0**. These walk all 153 descriptors, respect the installed
enable bytes, and apply descriptor byte **+7** or **+8** respectively to
the raw bank. The independent test derives expected results from each
descriptor and checks the complete native dispatcher. The conditional
later **4F6F4** call in 5652C is excluded by unchanged **3BC38**, which
returns zero in all three images. Normal-mode history qualifiers execute
with their explicit clean retained counters; their aging-triggered reset
workers are separate from that fixture.

**56856** maintains **DB22:u16**. Stopped status or entry into A5 resets
it; nonzero mode with no raw faults sets it to FFFF. Otherwise it
saturating-increments in nonzero mode at **RPM >= 2000**. **5690E**
publishes **DC10 -> DB2A**: FF requires a raw fault and a count no greater
than **156** when heater-selected temperature **B194 > -15 C**, or **313**
otherwise. A5 uses 156; normal zero clears DB2A. Getter **47178** makes
this a separate diagnostic inhibit, including throttle-monitor gating.

The mode transition from clear raw state seeds the enabled starter/neutral
diagnostic bits **P1518/P0512/P0851/P0852** in FF/A5 according to their
descriptors. It does not set the current-status bank. Connected native
fallback aggregation remains zero in that controlled case. Transferring
the actual mode, DB2A, connector, raw and current outputs into native
**64874 -> 253A8** with the other endpoint faults clear produces **no
injector inhibit at 2500..4144 RPM**. The retained-mode finding therefore
does not itself explain the cut.

[Seven groups](../../tests/test_diagnostic_mode_process_flow.py) cover
startup, running latch/rearm, thresholds, all mode branches, current/raw
separation, timer expiration and cut-selection handoff. Diagnostic records,
communication-state production and physical scheduling remain separate
from the supplied inputs.

### Synthetic current and computed diagnostic arrays

`6DE50` monitors the span of `AE68/AE6C` when `BDF8 >= 0.25`, `D852=0`
and its `D944` counter is below 180. It keeps maxima in `D7EC/D7F0` and
minima in `D7F4/D7F8`. The comparison uses the extrema present at function
entry: a newly observed excursion can set `D94F/04` on the following call.
Loss of prerequisites or expiry of the window clears that bit, resets the
counter and seeds maxima to -2 and minima to +2.

External WB publishes zero current on both its valid and invalid paths.
All [three native monitor test groups](../../tests/test_wideband_monitor_process_flow.py)
pass on main, v2 and captured v2: zero current across 365 calls, a positive
control that sets and retains the span flag, and both prerequisite resets.
This closes this specific synthetic-current input behavior, not the complete
misfire monitor or physical combustion behavior.

`6DF70` can propagate `D94F/04`, together with other eligibility failures,
into `D94E/02` when `D80C` is nonzero. At the subsequent `D80C=0` gate,
`6E804` consumes `/02` to discard six-by-39 temporary learning cells at
**`D438..D7DF`** and byte counters at **`D853..D93C`**, then clears the bit
and reloads `D80C`. Its ordinary path updates protected eight-byte records
from `8560`, with bank stride `0138`. These computed spans do not overlap
the native AVCS integrators `C85C/C860` (the former, incorrect lean allocation). `D94E/02` is not the injector mask `B744`.
The full set of learning-update prerequisites remains separate closure work.

### Disabled diagnostics and retained report state

`511F8` reads 153 enable records at `5BD54`, with 20-byte descriptors at
`5BDF0`. Enabled records are those whose enable byte is exactly 1. It builds
a 54-byte mask at `DBC6`, then masks two raw status banks (`DAB6`, `DAEC`)
and three protected status banks (`8E58`, `8EC4`, `8F30`). Each protected
record is packed as a status byte and its complement using `24DC`, under
the native interrupt lock. The periodic dispatcher reaches it through
`11954/11A78`.

The mask is OR-accumulated from its startup zero; it is **not cleared for
live edits of enable bytes**. Normal boot after flashing is the initialization
boundary used here. All 22 changed enables are 1-to-0, and none shares its
descriptor status bit with an enabled record. `50FF6/5108C` both return
before reading reporting mode `8FA0` when the requested diagnostic is disabled.

[Native execution tests](../../tests/test_diagnostic_enable_flow.py) seed every
prior status bit as set, run the real masker and packing helper, and verify
that disabled bits clear while enabled bits survive. Both groups pass on
current main/v2 and the exact captured image. This does not emulate every
physical monitor or establish its upstream fault cause.

## Separate runtime ROM accumulation

`4FB74` seeds two cursors and sums. Repeated `4FB8C` calls accumulate and
rotate 16-bit words from **`727A0..7D78F`** and **`2034..72667`**, 128 words
per call. `7D790` is an **exclusive boundary**, not a call or a read into the
retired boost reservation. Completion packs the results and their complements
into protected records `8E50/8E54`, sets `DAA0`, and clears the busy state.

`4FB46 -> 2068` checks those records' complement integrity; it does **not**
compare the patched calibration against a hidden stock ROM sum. The result
reaches `5B754` and the periodic integrity aggregation. The separate boot
checksum `F5FE/F97C` covers the injected code as part of its additive range.

All [four native checksum groups](../../tests/test_runtime_rom_checksum_execution.py)
pass: stock and captured image acceptance, deliberately corrupted ROM failure,
complete captured accumulation with valid records after every iteration, and
protected-record corruption detection. Watchdog service and physical DMA are
explicit hardware boundaries.

## A cam table also feeds ignition correction

The low-lift AVCS table at descriptor `60C34` is a shared calibration.
`498B0` looks up its load/RPM target into `D100`, takes the minimum of actual
bank cam angles into `D104`, then writes `D0FC=max(D100-D104,0)`.
When its running gate permits, idle-status `18CF4=1` or committed high lift
`CD86=3` clears all three. At 6,000 RPM or above it returns without clearing.

`496C8/49960` convert this deficit through timing tables `5FF24/5FF38`,
multiply by an IAM-dependent table `5FF4C/5FF60`, and publish `D0F8`.
The alternate paths include a 25/60-call counter at `D108`, explicit status
gates and a 6,000-RPM early return that can retain old state. Both IAM factors
are zero at IAM 1.0. Normal startup DMA clears `D0F8/D108`.

`279CC` adds `D0F8` to every cylinder's final timing. Standard logger P10
at SSM `000011` calls `31684` through pointer `4B740` and reads **`C0EC`,
the first final cylinder angle**, with half-degree resolution. Therefore this
common correction is included in the logged 16–17-degree bog samples.
The log still cannot resolve between-sample events or all six physical outputs.

All [four cam/IAM native execution groups](../../tests/test_cam_iam_timing_process_flow.py)
pass on main, v2 and captured v2. Fixtures cover 2,500–3,500 RPM, both committed
lift states, imposed cam angles, both counter periods, clearing on high lift,
and retention/recovery at the 6,000-RPM gate. A positive control at 2,800 RPM,
IAM 0 and imposed zero cam angle produces approximately -14.274 degrees;
IAM 1 produces zero. The correction reaches all six final angles in the test.
[Recorded examples](evidence/cam_iam_timing_20260912.json) preserve the image
identities and explicit fixture limits.

This is an additional dependency of our changed AVCS calibration. It is not
evidence that the correction caused the loaded cut. The sustained bog has IAM
1.0; its actual cam positions and `D108` are not captured.

## Calibration aliases and storage widths

The [descriptor discovery tool](../../tools/analysis/audit_calibration_dependencies.py)
intersects plausible native descriptors with every assigned native calibration
span, including retained identical values. It finds **39 descriptors**, each
with captured MCP references, and validates the current axes as finite and
strictly increasing. It leaves **21 scalar/array spans** for separate review.
The [machine-readable register](evidence/calibration_dependencies_20260912.json)
retains each descriptor, overlapping assignment, immediate native references
and those uncovered spans. A bounded format scan cannot prove absence of
computed or differently encoded aliases.

| Shared data or contract | Identified native consumer relationship |
|---|---|
| Timing load axis `780BC` | Shared by all six descriptors `60108..60194`, consumed by `28418`. |
| Low-lift cam table `60C34` | Used by cam target control `353AA` and the separate `498B0` ignition-correction chain above. |
| Injector latency `608D8 -> 7B318` | `98CC` calls integer-return lookup `2118` at `98D4`; `28A4` reads five unsigned words, exactly **10 bytes**. |
| CL-to-OL delay `5F8FC -> 772DC` | `22948` calls the same integer-return helper at `22A14`; two unsigned words, exactly **4 bytes**. |
| AVLS pedal thresholds `60F58/60F64` | `40168` instead calls float-return `209C` at `4024A/40258`; each data array has seven floats, **28 bytes**. |

The last three cases all have a zero format field in their descriptor. Their
actual lookup call determines whether the cells are unsigned words or floats.
Reading the field alone would invent an overlap in the latency/delay tables.
The builder's existing spans match the native contracts; no width correction
to the BIN is warranted by this finding.

The rev-limit pair `7644C/76450` is also read by `29128`, which publishes
the separate final-timing term `C1D0`. Above the upper threshold it selects
`77ED0`; below the lower it clears; between them it holds. **`77ED0` is zero**
in stock and both current images. This secondary consumer is retained and is
distinct from the `24B24` fuel-cut path.

## Knock cell selection and adjacent retained state

`3DAA6` reads `B544` RPM and SD-fed `B438` load. Seven RPM boundaries via
`4C75C` and seven load boundaries via `4C740` divide each axis into eight
cells. It applies descending hysteresis from `78020` and `7801C`, stores row
`CD0C` and column `CD0D`, and publishes `CD0E=row*8+column` only if below 64.
V2 changes the seven load boundaries at `78050..78068`, not the cell count.

`3DB90` uses `831C+8*CD0E` to read a protected learned value, adds `CCFC`,
and clamps against the IAM-dependent upper bound and `78088` lower bound.
The result is `CCF8`. The full grid occupies **`831C..851B`**, immediately
before the **IAM record at `851C`**. `3D9B4/3E044` clear exactly 64 records;
`3D9E8` checks exactly that extent. Conditional reset `3DF56` uses the same
64-record bound. A changed axis is not permission to enlarge the storage.

`3F386`, called before final timing in task 6, normally combines `CCF8`,
`CD14` and `CD34` into `CD44`; its status overrides remain native. `279CC`
includes `CD44` in final spark, so this is another complete value path to the
timing channel, not just a logger-only value. `CCF8` also feeds IAM learning
decisions at `3EF74` and native telemetry at `483FC`.

The changed range arrays have distinct consumers: `3E0B0` publishes the fine
RPM/load gate bits in `CD11`, while `3F256` publishes the rough equivalents in
`CD40`. `3DEF0` and `3EBDC` combine those gates into learning eligibility.
Initial IAM `77FD8` is used by explicit initializer `3E9FC`, conditional reset
`3ECB6`, and fault-state recovery `3F020`; it is not an unconditional override
of IAM on every task execution.

All [four native knock-cell test groups](../../tests/test_knock_cell_process_flow.py)
pass on main, v2 and captured v2. They cover both axis directions, load/RPM
boundaries, the last cell adjacent to IAM, range-gate writes and a selected
learned correction reaching all six final spark values. Learned contents are
imposed signatures, not recovered vehicle history. The following extension
connects their learning/reset dependencies without assuming physical knock.

### Protected knock records, IAM resets and mode handoffs

The [eleven retained-state groups](../../tests/test_knock_retained_process_flow.py)
and [seven learning groups](../../tests/test_knock_learning_process_flow.py)
execute the native instruction paths on main, v2 and captured v2. Their
protected-record writers and validators also execute native code. Upstream
feedback permission and the `B460/80` knock-event input remain explicit
fixtures, as do previous learned values and diagnostic states.

`29570`, called by startup validator `FD5C` through `FEB8`, checks these
groups in order and returns at the first nonzero result:

| Validator | Checked state |
|---|---|
| `273EC` | Complemented byte pair `8224` and the two-bit status at `8226` |
| `292FC` | Protected float record `8228` |
| `3D916` | Six protected records `82EC+8*n` |
| `3EA2E` | IAM `851C`, learning step `8524`, and both low two-bit fields in `852C` |
| `3D9E8` | Exactly 64 protected grid records `831C+8*n`, ending at `851B` |

These are integrity/status checks, not tests for active timing correction.
Each float record has a complemented halfword-sum checksum duplicated at
offsets `+4/+6`. `4963A` accepts either matching copy and repairs both;
neither matching returns failure. It does not independently establish that
the float is physically plausible. Grid validation stops at the first bad
record and never reads the adjacent IAM record. The native writer `49530`
rejects NaN and publishes each accepted record under the native interrupt
lock. The complete startup bank-selection/save/restore path is outside
these record-validator executions.

`3E9FC` initializes IAM from `77FD8` and step from `78000`, then sets the
two status fields to `2/2`. Main and stock start IAM at **0.5**; v2 and the
captured v2 start it at **1.0**. The initial step is **0.5** in all images.
This calibration also affects conditional initialization and fault recovery.

The reset parent connects the changed load gate to these records:

1. `3EBDC -> 3F256` derives the RPM/load window from `B544/B438`, publishing
   `CD3A/01`. V2 raises the upper load hysteresis pair from **2.1/2.2** to
   **3.9/4.0 g/rev**; tested load 3 qualifies in v2 and is excluded in main.
2. `3EC6C` requires that window, clear `CD22/01`, clear `852C/01` and
   `CD30 >= 4`. It sets `CD3A/02` and clears the saved temporary correction
   `CD00`. It clears eligibility when any prerequisite fails.
3. `3ECB6` resets only while eligible and the low bit of `852C[3:2]` is
   clear. It initializes IAM/step, marks that field `1`, clears exactly 64
   grid records through `3E044`, and clears temporary offsets/counters.
   Repeating a qualified call preserves new learning until another mode
   transition rearms the reset.

`3ED6C` updates IAM while `CD3A/02` is set. Diagnostic `D26D/04` suspends
learning; the native `B460/80` event selects immediate decrement. Clean
recovery uses the RPM-dependent count from `5FFEC`: **255** in the tested
2,800-RPM case, with the change on the following qualified invocation.
Direction changes can halve the retained step, while subsequent changes in
the same direction reuse it. Native bounded controls reach IAM 0 or 1
without crossing either bound, and both protected checksums remain valid.
These are event-call counts, not elapsed seconds.

A separate path, `3F020`, uses `CC4C/40`, which native startup helper
`3B9E8` sets. With this feature enabled, missing `8274/01` AVCS rest-learning
permission or any selected fault (`D26D/02`, `D26E/04`, `D270/80`) forces
IAM to zero and resets its step/status. Recovery edges in `CD3C..CD3F`
restore the image's calibrated initial IAM. Healthy repeated calls preserve
later learning. With the feature disabled, the worker holds IAM but still
consumes the history transitions. This is distinct from `3DF56`, whose
cam/OCV fallback transition clears only the grid. It establishes another
dependency of the cam repair; it does not show that IAM caused the capture.

Fine learning `3DC9C` requires clear `CD22/01`, fine mode `852C/01`, and
the native fine load/RPM window `CD06/04`. A knock event decrements only
`831C+8*CD0E` using RPM descriptor `600FC`, with a **-5-degree** grid floor,
and also changes shared offsets `CCFC/CD00`. The separate published
correction is bounded at **-7 degrees** by `3DB90`. Recovery requires the
same cell as `CD0F` and **125** clean calls accumulated by `3DFD6`; a cell
change restarts this qualification. The event counter saturates at 65,535
and clears on knock. Recovery removes the shared offset before increasing
the selected grid record. Other grid cells and IAM remain unchanged in
these executed paths; the writer relies on the native selector's checked
index rather than adding another local bounds check.

Large fine correction can switch control back to rough/IAM learning.
`3EF74` consumes the selected cell, `CCF8`, `CD30`, IAM and mode bits; when
its thresholds qualify, it sets status fields back to `2/2` and clears the
fine-update flag. The next qualified `3ECB6` then resets the grid and IAM.
At supplied `CD30=5`, IAM 0.75 and prior `CCF8=-4`, a native knock update
qualifies this return; the `-3` control does not. This is intentional native
state-machine behavior, not an overlap with the patch's scratch RAM.

Task ordering also matters: `11DDC -> 3DB90` publishes `CCF8` **before**
`11DEC -> 3DC9C` changes the selected record. `3F386` therefore sees that
pass's earlier publication; the new cell and temporary correction enter
`CCF8` on its next update. Tests execute this ordering through `CD44` and
show the expected one-publication delay. No measured task deadline or
physical spark delivery is inferred from it.

## AVLS request, phase and actuator process

The native periodic parent `1081A` calls `3AF4(0x10)` and then, consecutively,
`3FDBC`, `3FE14`, `40D94`, `40764`, and `40E0A`, before restoring the mask
with `3B08`. The task entry is `6820`, descriptor `4A1C`, software priority 2.
The mask prevents immediate ordinary task dispatch: activation routine `3A28`
checks the saved SR mask before dispatching queued work. Higher hardware
interrupts remain possible; this establishes ordering, not deadline margin.

`3FD9C` initializes requested mode `CD87`, software mode `CD86`, previous
edge state `CD88`, and both bank copies `CD89/CD8A` to 1. `3FDBC` updates
the oil-dependent selector state, calls `40168`, copies `CD87 -> CD86`, and
resets the bank copies to 1 while stopped. Its `CD8F/80` hold requires RPM
at least 6,000 and both adaptation flags `CDD8/CDD9 /80`; below 6,000 it clears.

The moving selector is **not a universal RPM-only 3,200/3,000 switch**.
RPM entry sets `CD8F/08`; pedal-driven entry uses `CD8F/10`. Clearing the RPM
latch `CD9E/04` below 3,000 alone need not request low mode. Below that threshold,
`B484/40` or `/80`, read by native `18D08/18CF4`, can qualify forced low mode.
The separate pedal release path requires `/10` history. With speed 30, oil
50 C and those pedal flags clear, native execution retains mode 3 on a
3,200-to-2,800 RPM change; setting `B484/80` then requests mode 1. The earlier
stationary selector test did not cover this moving dependency. This is not
evidence that the flags took those values in the captured event.

`3FE14` calculates transition phase targets using two independent inputs:

- RPM, rounded/clamped by native `258C` in 50-RPM units, selects through 21
  byte boundaries at `4C808` into four 22-element byte tables. Results are
  `CD90/CD91` for entry and `CD92/CD93` for release.
- Conditioned cam phases `C8B0/C8B4` select offsets `CD8D/CD8E` through six
  boundaries at `4C9BC` and seven-element tables at `4C9D4/4C9F0`.

The cam phases have computed writers: `34208`, using bank descriptors
`4C618/4C64C`, conditions `B0B0/B0B4` plus temperature offsets into these
values. `34304` subsequently subtracts learned offsets `8264/826C` to form
the separate cam-angle channels `C8C8/C8CC`. The phase inputs are not AVCS
target requests. Stopped reset `3440A -> 34472` also writes them through the
descriptors.

On a `CD86` edge against `CD88`, helper `406A4` subtracts the selected cam
offset from the selected base phase, adds **24** if negative, and writes
`CD8B/CD8C`; then `CD88` is updated. Direct xrefs to `CD8B/CD8C` missed these
computed stores. No edge leaves the old targets; `CD8F/80` holds all state.

The crank-event task `11958` first calls `19F9C` to publish `B528`, then
eventually calls `405CC`. Bank 1 may update `CD8A` when its phase matches
`CD8C`. Bank 0 requires its phase `CD8B` **and bank 1 already matching the
requested software mode**. At or above 3,000 RPM the first eligible bank-0
opportunity sets `CD9D=1` and defers; the next eligible opportunity clears
it and switches. Below 3,000, that extra deferral is skipped. Each successful
bank update calls `40C94`, `40798`, and `40CE6` for that bank.

| Stage | Native dependency and publication |
|---|---|
| `40C94 / 40D94` | `F298` reads OSV current `B11C+4*bank`; `40F8C` chooses initial-duration flags from bank mode and `CE0C..CE12`; `4108E` publishes base duty `CDF0/CDF4`. Initial high mode uses 100%, initial low mode 0%; ordinary bases are 71% and 20%. |
| `40798 / 40764` | `40C2C` maps base duty to a target current through `60F30/60F44`. `40B1A` conditions measured current and forms error; `407C6` updates bounded correction factors in `CDA0/CDB0`, subject to flags and counters. Periodic `40A30` advances those counters. |
| `40CE6 / 40E0A` | `41160` selects diagnostic duty, stopped/start inhibit, initial duty, or factor times base, then clamps 0–100 and publishes `CDF8/CDFC`. |
| Native output | Transition helper `F12A` configures/restarts bank PWM and writes compare registers `FFFFF514/FFFFF516`. Periodic `F0C0` updates the same compare registers using cached periods at `AB84+0C/+0E`. Both protect register writes with the native priority-14 lock. These are software output commands; pin identity and hydraulic behavior are separate. |

The retained diagnostic stage **`41230` can override output without itself changing
the software mode bytes**. Bank 0 reads current DTC index 151 (`5C9BC`,
`8EBC/80`); bank 1 reads index 150 (`5C9A8`, `8EBC/40`). Both enables remain
1 in all three patched images. A persistent current bit, after the native
250-count threshold, qualifies `CE08/CE09 /20`; `41160` can then use the
0/100% diagnostic sequence at `CE00/CE04` even while `CD86/CD89/CD8A` stay 3.
Separate special diagnostic entry paths have additional RPM/configuration,
cranking-state and temperature prerequisites. Their full activation and
message effects remain open. Disabled O2/MAF/purge DTC enables do not alias
these two AVLS enable entries.

All [eight native AVLS process test groups](../../tests/test_avls_phase_process_flow.py)
pass on main, v2 and captured v2. They execute initialization, the full mode
parent, phase calculation, both bank command chains, and periodic output
through their PWM-driver entry boundary. Cases include all 24 starting
phases, both transition directions, cam-offset boundaries, deferral/recovery,
moving release history, stopped output, initial/running current-control
intervals and imposed current-bank faults. The later suites below close the
normal GPIO input, report/recovery and PWM-driver boundaries. Interpolation,
peripheral timing and hydraulic response remain explicit inputs. No
persistent bank mismatch was found in the tested normal transition sequences;
the imposed diagnostic override is a positive control, not a vehicle finding.

### AVLS current feedback and shared timer ownership

`F39C` copies **AN18 `AB24` and AN15 `AB1E`** to `B118/B11A`, then writes
`B11C/B120 = max(0, counts * 5/65536 * scalar[72858] + offset[7285C])`.
The installed constants are approximately .334 A/V and -.035 A. `F298`
selects that bank current; `40B1A` publishes conditioned measurements at
`CDC0/CDC4` and reference-minus-measurement error at `CDC8/CDCC`.
`40C2C` supplies the reference currents at `CDD0/CDD4`. These inputs and
states are distinct from both the WB AN3 source and repaired AVCS feedback.

Native startup `F2A2`, locally decoded where MCP has no function body, sets
both AVLS periods to **6666 counts** (`72854`) and initializes zero buffers.
`F12A` restarts a selected channel on a lift transition; `F0C0` updates its
buffer periodically. Both convert the fraction to Q16 and call native `2390`
to multiply by the period. Priority-14 locks preserve the caller's mask.

| Function | AVCS bank 0/1 | AVLS bank 0/1 |
|---|---|---|
| Timer-6 channels | A / B | C / D |
| Cached periods | `AB8C / AB8E` | `AB90 / AB92` |
| Buffer registers | `F510 / F512` | `F514 / F516` |
| Duty registers | `F518 / F51A` | `F51C / F51E` |
| `TSTR2` at `F400` start bits | `01 / 02` | `04 / 08` |

Renesas sections 11.2.22–24 define the buffer-to-duty transfer at cycle match.
Five [actuator groups](../../tests/test_avls_actuator_process_flow.py) execute
the native initialization, current converter, phase transition and periodic
output through the actual register writes. They also interleave repaired
AVCS and AVLS initialization/updates: each preserves the other's buffers
and start bits. Cycle matches are supplied hardware events; no physical
waveform or hydraulic response is inferred.

### AVLS electrical, switch and recovery paths

The periodic parent `11270` retains `114A4 -> 69CA8` for electrical checks
and `114A8 -> 705FA` for switch-response checks. Their reporting enables
are unchanged. `DB25`, feature `CC4D/01`, and native diagnostic-group
eligibility qualify both monitors; the switch monitor additionally requires
oil `CF94 >= 0`, runtime `B688 >= 750`, and `7D461 == 0`.

| Monitor | Native qualification and counter | Current status |
|---|---|---|
| `69CB2`, low current | Duty `CDF8/CDFC >= 30`, measurement `CDC0/CDC4 < .026`; report on the 126th qualified invocation. | P0076/P0082, IDs `91/8F`, `8EBA` masks `20/04`. |
| `69EF4`, excessive current | Duty `< 7`, measurement `>= .465`; report on the 126th qualified invocation. | P0077/P0083, IDs `90/8E`, `8EBA` masks `10/02`. |
| `706DE`, absent high-state response | Duty `>= 62`, 13-call settling count, then 49-count mismatch threshold; report on invocation 62 from zero. | P1026/P1028, IDs `97/96`, `8EBC` masks `80/40`. |
| `706DE`, stuck high response | Duty `< 33`, 188-call settling count and 188-count mismatch threshold; report on invocation 376 from zero. | Same two switch-performance codes. |

Electrical recovery needs 126 healthy invocations: reference/measurement
error below .08, with reference at least .11 for the low-current monitor.
Switch recovery is different: bank flags `D9D9/D9DA` accumulate successful
high and low responses as `20/10`. `70852` calls `5108C` only when **both**
have occurred. A single good lift state cannot clear the current fault.
Raw histories `DAE7/DAE8` survive healthy confirmation.

This also closes the other consumer of those faults. `63174`, at `646B2`,
reads the six **protected current** entries, gated by `470F4` or `DAA4 == 1`,
and publishes `D26E/04`. `65208 -> 40168` then requests low lift. Recovery
clears that fallback on the next aggregation despite retained raw history.
Thus the isolated `41230` override does not establish that the complete
state machine would indefinitely keep `CD86=3`. Six
[diagnostic groups](../../tests/test_avls_diagnostic_process_flow.py) execute
both consumers, fault/reset transitions and their distinct latches.

### Port-E input publication and the WB output on the same port

`6B08` initializes digital snapshots from GPIO. `6BB4` reads `F754/PEDR`
into the two-sample debounce process: `AAE6` is the conditioned word and
`AAF4` the preceding sample. A bit changes only after two consecutive
matching samples. The complete `193D0` publisher maps **PE14 -> B51C/20**
and **PE15 -> B51C/10**; **`B51E/04` and `/02`** receive the same states.
The earlier claim of inverses at `B51A` was wrong. `B51A/04` and `B51B/02` instead
publish the inverse of **serial channel 2, bit 2**, after `766C -> AAEC`
and the same two-sample debounce. The reset consumer `19C90` reads that
separate serial input; it does not read either AVLS port-E switch.
`19E4C/19E74` read the two B51C bits for the switch monitor. The relevant
GPIO definition is Renesas section 21.6.2; external harness identity and
electrical pressure-switch behavior are separate from these software banks.

Four [switch-process groups](../../tests/test_runtime_switch_process_flow.py)
execute startup, all four input combinations, both debounce transitions,
isolated glitches and the subsequent AVLS monitor. Native WB-status output
`3B760 -> 4BC8` changes PEDR bits `08/04`; interleaved checks preserve
PE14/PE15 through both debounce and publication. The unrelated `766C`
serial transaction returns are explicit peripheral inputs. This closes
the shared GPIO dependency without asserting the actual vehicle inputs.

### AVLS message modes, shutdown accounting and queue boundaries

The special branches of `41230` share the native shutdown event interface.
Its mode 1 requires nonzero shutdown state `C778`, RPM within the installed
`7D520/7D524` range **[0, 0]**, and **`7D464=FF`**. The installed enable is
**00 in main, v2 and captured v2**. Mode 2 instead requires cranking
`B748/80`, feature `CC50/80`, `7D462=FF`, and oil temperature within
**[10, 150] C**. Only mode 1 sets `CE0A/CE0B` bit20, which permits the
group 0/event 2 and event 3 callbacks. Mode 2's bit08 does not emit them.

Those events use zero payload bytes and immediate descriptors
`FD14/FD1C`: `11EE8 -> 3107C` increments **C779**, while
`11EEE -> 31094` increments **C77A**. Both are ordinary wrapping bytes
under `3AF4/3B08`; they neither write `C778` nor consume queue storage.
An in-memory positive control changes only `7D464` to FF. At zero RPM and
shutdown state 1, the native 100/0 duty sequence emits one start and one
completion event per bank; the installed-byte matrix emits neither.
This control creates no alternate BIN and makes no claim about valve motion.

`30FD4` initializes `C778=0`, remembers the `C618/08` and `C774/80` inputs
in `C780/C781`, and sets `C77B=1`. Separate `31002` initializes the packed
two-bit fields in `825C`. Slow-task call `11568`, via `11760`, enters
`310D8`. In the normally initialized state, ignition-on **B51E/10** keeps
`C77C`, `C779` and `C77A` clear. This is distinct from test-connector
**B51E/80**. After ignition-off, six prior invocations qualify the seventh
to set `C778=1`, reset `C77E` and queue event 1/6 through `CFA4`.

With state 1 and ignition off, the saturating `C77E` counter must reach
six and **C779 == C77A** with stopped `B52C/80`, or reach timeout
**18,750 invocations**, before state 2 and nonreturning `CCBA` entry.
An independent received-status/reset branch uses `C6F5/C6F6` and `DA90`;
these tests keep that branch unqualified. Packed `825C` changes also reach
the barometric eligibility getter `312E0`. Ignition on is not a universal
reset of a shutdown state that is already active.

Event 1/6 uses descriptor **FA24**, queue **3**, task **4**, capacity
**255 records of 20 bytes**. Its buffer is **96F8..AAE3 inclusive**,
ending immediately before the digital-input workspace at **AAE4**.
Native `6170` writes the last record at AAD0..AAE3 and wraps the head;
when full it returns 2, translated to 1 by `C700`. `CFA4` ignores that
return. The boundary tests find no out-of-bounds write, but do not establish
that ignoring a full queue is safe in every possible scheduler state.

Native task `C898` dequeues through `6270` into **AFCC..AFDF**, calls
the record callback and repeats until empty. Shutdown callback
`6A06 -> 11E64 -> 4EEC4` updates protected byte/complement word **8E34**:
`DA8A==1` clears it; otherwise `DC06==1` saturating-increments it through
`2534`; otherwise it holds. `24DC` rebuilds the complement before the
store. The worker then reaches its `3F2C` task-completion boundary.

[Seven groups](../../tests/test_shutdown_process_flow.py) cover these paths
on all three images, including native callbacks, queue drain, full/last
records and both special-mode branches. Hardware power-down, EEPROM
transport, received-status reset production and the additional diagnostic
accounting caller `50F64` remain separate edges. These results do not
identify the vehicle cut or remove the need for scheduler analysis.

## Crank-phase queue and missed activation dependency

`87F2` advances phase `AC17` modulo 24 and submits task-5 phase work through
`CF58`. It also uses the native phase mapping at `FA7C` to submit task-6 work
through `82B6 -> CF7E`. `CF58/CF7E` call `3A28` to activate the task before
queueing its phase via `D0D0`. A failed activation instead calls `D156` and
does not enqueue that phase.

`D0D0/D106` implement two longword slots per 12-byte record from `AFEC`, with
separate producer and consumer byte indices. Task 5 (`6938`) consumes record
0 and passes the result to `11958/19F9C`; task 6 (`696C`) consumes record 1
before `11AD0`. `D156` increments a saturating counter at `B007+taskID`:
**`B00C` for task 5 and `B00D` for task 6**. These are computed writes, again
absent from direct destination xrefs.

This connects execution time to missed native phase work, rather than treating
FPU instruction count as a standalone question. The captured log has neither
counter, and static instruction fixtures do not establish a deadline breach.
The full priority, queue-capacity, interrupt-arrival and worst-case execution
time proof remains open. No scheduling or AVLS bypass is justified yet.

### Native phase activation, publication and capacity

[Five connected kernel groups](../../tests/test_phase_activation_process_flow.py)
now execute stable-state `87F2`, `8BE6`, both activation wrappers, native
IRQ entry/exit, `3A28`, priority queues, dispatch, `D106`, the actual `263EE`
phase consumer and `3F2C` completion. The accepted crank edges are explicit;
the rest of task 5's engine payload is not substituted into this claim.

`8BE6` copies `AC24 -> AC04`, `AC34 -> AC1C`, and publishes
`AC18 = phase * 30 - 10` with negative angles wrapped by 720. It writes
one of four period words at `AC50..AC5F`, indexed by `AC61`. After at least
four samples, `AC08` receives their sum and `AC00` receives the native float
constant at `8CE4` divided by that sum. `AC60` saturates at 255. These
computed extents stop before the next native signal fields.

The producer executes within an explicit IRQ frame. `3A28` reserves an
activation, but native dispatch waits until IRQ return; `D0D0` therefore
publishes the phase before its consumer can run. Both task descriptors have
activation capacity **2**, including any running instance. Task 5 consumes
two supplied pending phases in FIFO order, drops a third through `D156`,
and accepts a new phase after native completion returns its capacity. The
missed-phase byte saturates at 255. No rejected phase overwrites the queued
values, and the phase state itself still advances.

The corresponding task-6 limit matters differently: an already running
task 6 has one activation remaining. An explicit fixture that holds that
task across 24 incoming phases queues mapped phase 0, then counts the next
five mapped activations as missed while task 5 continues all 24 phases.
This is a conditional demonstration of starvation effects, not evidence
that the vehicle remained in that task for a full cycle. A higher caller
interrupt mask defers consumption until the caller unlocks; the published
slot and full register context remain intact.

### SD and WB resumption through real kernel context handling

[Three preemption groups](../../tests/test_patch_preemption_process_flow.py)
interrupt every reached non-delay instruction address in selected SD and WB
paths, one interrupt per run. SD includes both lift modes with interior
interpolation, the low-pressure boundary, invalid MAP and stopped exits.
WB includes accepted and rejected ADC values. The actual native SD lookup
helpers execute, including their multiply/divide work.

Each injected interrupt runs the phase producer and kernel dispatch above;
task 5 consumes the actual queued phase and executes `263EE`, then returns
through native context restoration. It deliberately changes scratch and
floating registers so preservation is observable. Every final patch result
matches the uninterrupted baseline on main, v2 and exact captured v2.
SD's callee-saved RPM/MAP/IAT values and MAC registers survive, as does the
scripted FPSCR context change. The stopped SD fixture retains the caller's
zero-RPM snapshot even when the supplied IRQ period now indicates running.

These checks close register-preservation and publication-before-dispatch
edges for these paths. They do not emulate FPU exception flag generation,
measure CPU interlocks or deadlines, or establish atomic visibility of all
SD/WB fields to every other task. Full engine-task execution and interrupt
arrival bounds remain required for an execution-time conclusion.

## Ignition timing, permissions and the coil timer state machine

The [nine connected ignition groups](../../tests/test_ignition_device_process_flow.py)
extend the earlier timing-composer and seven permission groups. All native
code, phase/channel descriptors, dwell data and timer initialization match
stock in main, v2 and the exact captured image. This trace has not identified
an additional ignition code defect or changed a BIN.

`6938` services the injector devices at `8F08`, then the coil devices at
`9BCC`, before entering `11958`. Within `11958`, the native `2716C` mode
update precedes injector scheduling/logging, then **`2A214` updates the
auxiliary spark mask immediately before `29794` runs the ignition scheduler**.
Tests use this reviewed device-poll/scheduler ordering; they do not execute
all unrelated tasks in `11958` or model its dispatch deadlines.

| Stage | Process and ownership |
|---|---|
| Record initialization | `296F0` builds three **44-byte** records at `C204/C230/C25C`, using phase offsets `4C690` and channel/logical-mask pairs `4C69C`. Each has two 16-byte subrecords. `2A3D2` clears six lead offsets at `AD44..AD58`; `2A3CE` returns zero for this ROM. `29C00` requests scheduler reinitialization through `C28D`. |
| Mode and inhibit | `C0E1=1` selects initial-charge record mode 0, `C0E1=2` running mode 1. `2A262` returns `(C0E1 ? C0DC : FFFF) OR C290`. `C0DC` comes from native `27090`, using six stored cylinder-disable bits duplicated across the twelve logical slots. It is separate from injector inhibit `B744`. |
| Timing conversion | Running-mode `2A2BC` selects the relevant two final floats from `C0EC..C100`, writes `(timing-10)*65536` into record offsets `18/28`, and respects the alternate logical phase-half ordering. `29C62` later combines relative timing, current phase and its own offset; the intermediate subtraction alone is not final spark timing. |
| Phase update | `29794` tracks `C28C` modulo 24, uses three paired records and the mode descriptors at `4B6D8/4B6E8`. A phase increment other than one invokes `29AA8` to cancel pending requests and rebuild phase distances, mode, mask and timing. Mode changes go through `29D04`; changed masks go through `29E14`. |
| Queue callbacks | Initial-charge callback `2A018` uses `9952`. Running callback `2A0C0` converts through `29C62` and enqueues with `997A`, or updates an existing pending angle in `AD14+8*n`. Inhibited slots are skipped. Running release predicate `2A17A` includes dwell and `AC08` period before allowing restart. |
| Dwell | `9FEC` passes battery `ABB4` and RPM `AC00` to raw-u16 descriptor `60998`, writing `AD5C`. At the explicit 14 V fixture, 2500/2800/3000/3500 RPM produce 752/713/688/624 counts. `2A3C0` returns those counts times 16. Battery voltage was not logged during the cut. |
| Device snapshots | `9BCC` copies crank angle `AC18` to `AD64`, timer snapshot `AC1C >> 4` to `AD6C`, and `AC08/4` to `AD68`. It services six eight-byte states at `AD14..AD43`. Mode 1 uses `9C54`; mode 2 uses `9D3A`. |
| Prepare/program | `9F9C` initially places start/end comparisons away from the current counter and loads the down-counter through `D744`. `9D3A/9E58` use angle distance, dwell, period and snapshot to write the actual comparisons. Late start clamps to counter+3; the reviewed late-end branch retains at least half of requested dwell. |
| Cancellation | `99E0` distinguishes idle, pending-unarmed and armed states. `99B4` clears pending mode only before arming. An armed event remains until timer completion; a subsequent `9D3A` poll observes zero down-counter and clears its state. `29E14` checks both paired subrecords before permitting cancellation. |

The **six 24-byte hardware descriptors begin at `FADC`**. Each contains
the following pointers and mask; `FAE8` is the first descriptor's shared
counter pointer, not a descriptor base.

| Descriptor offset | Hardware channel `n=0..5` |
|---|---|
| `+00` | `DCNT8I..N`, `FFFFF650 + 2*n` |
| `+04` | Start comparison `OCR2A..F`, `FFFFF614 + 2*n` |
| `+08` | End comparison `GR2A..F`, `FFFFF604 + 2*n` |
| `+0C` | Shared `TCNT2B`, `FFFFF602` |
| `+10` | `DSTR`, `FFFFF666` |
| `+14:u16` | `0100 << n` |

Native `4E8C` sets **TCNR=`FFFF`, OTR=`7F00`, RLDENR=0**. `9AA4`
selects compare mode 1 for the six GR2 channels and disables their interrupt
enables while preserving unrelated bits. OCR2 compare starts the linked
down-counter; the enabled GR2 termination clears that down-counter and its
DSTR bit. These are the [Renesas manual's sections 11.2.12–13 and
11.2.18](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual)
contracts. The fixtures supply equal TCNT2A/B advances and between-call
termination matches. They do not simulate current, spark energy, oscillator
drift or interrupt timing.

There is a distinct cam-diagnostic dependency here. The final branch of
`63174`, at `647BA`, ORs **current protected** P0011/P0021/P0345/P0340
status (descriptor IDs `2D/2E/83/84`) into **`D270/80`**. `6521C -> 1A202`
publishes that result into `B52C/20` and `AC20`. With that flag set, `2A214`
clears `C290` to enable both logical phase halves. Otherwise phase zero
sets `C290=0FC0`, suppressing the six secondary slots. This permits one
command per hardware coil per 720 degrees normally, or two with the secondary
slots enabled. **It is not an all-coil cut.** Healthy current status restores
the normal auxiliary mask even while raw fault history remains set. This is
different from the raw-latched `D26F/10` AVCS permission dependency.

Tests verify all six final-value selections; start/end and nonzero timer
commands across 2500–4144 RPM and counter wrap; repeated phase cycles using
15/18.5/41.5-degree timing fixtures; every native six-cylinder cut mask and
release; pending versus armed cancellation; mode changes and phase jumps;
and the four cam diagnostic inputs, their native aggregate and recovery.
The observed range constrains the value fixtures, not the car's unlogged
per-cylinder state or battery. A nonzero logged injection pulse therefore
still cannot establish actual coil firing during the vehicle event.

### Cam performance reporting has a restrictive native RPM gate

The [four cam performance groups](../../tests/test_cam_performance_process_flow.py)
follow the actual P0011/P0021 producer, not just its stored flags.
`116A8 -> 7198C` copies `C8E8/C8EC` target-minus-actual error into
`DA2C/DA30`, runs `719A8` qualification, then `71D2C` healthy confirmation
and `71ADE` failure detection. The code and thresholds are unchanged in
stock, main, v2 and captured v2.

`719A8` requires the AVCS feature, diagnostic readiness `DB25=1`, groups
`41/42` eligible and coolant **strictly above 60 C**. Its two RPM paths are:

| Cam targets `C974/C978` | Additional qualification for `DA28/80` |
|---|---|
| Both within zero ±0.002746582 degrees | RPM at least **600** (`74F54`) |
| Both outside that zero band | RPM at least **12,800** (`74F58`) **and** controller permission `C948/01` |
| One zero, one nonzero | Fails qualification |

Consequently, an explicit 25-degree target/error at 2500–4144 RPM does
**not** report P0011/P0021 through this path, even after 200 invocations.
This is an executed counterexample to treating no cam-performance DTC as
proof that requested cam movement occurred. It is not evidence that the car
had that target/error, and this audit does not alter the native threshold.

With qualification present and both targets nonzero, absolute error at
least 10 degrees reaches reporting on the 48th consecutive call. With both
targets zero, reporting instead requires absolute error at least 40 degrees,
`C908/01`, an out-of-range learned offset (outside 0.5–59.5), and 157
qualifying calls. Losing qualification resets the four failure counters
`DA34/36/38/3A`; it does not itself clear the current DTC.

Healthy confirmation is a separate path. With the feature and `C948/01`
enabled, a bank target in **[5,30)**, absolute error **below 10**, and learned
offset in **[0.5,59.5]** reaches `5108C` on the 48th qualifying call through
`DA3C/DA3E`. It can clear current status at ordinary RPM, even though the
advanced-target failure gate is closed there. Raw history remains; the next
`63174` update clears the corresponding `D270/80` secondary-spark request.
Tests execute both publication and recovery, with a 12,800-RPM mathematical
positive control only. No vehicle test at that speed is requested or implied.

### Cam-sensor edges, qualification and fault-report queue

The P0340/P0345 producers use two distinct observations. Native capture
callbacks **E6B0/E6DA** set per-bank angle-pending **B0CC/B0CD** and
diagnostic edge latches **B0D0/B0D1**, copy **GR3A/GR3B at F4A2/F4A4**
into **B0C8/B0CA**, and saturating-increment **B0D2/B0D3** at 255.
The first callback is reached by the `5668` interrupt wrapper via `5714`.
These are timer 3 capture registers; they are separate from the repaired
timer 6 OCV PWM buffers. See the
[Renesas manual, sections 11.2.4, 11.2.6 and 11.2.20](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual).

**E468** also classifies the accumulated edge count against the bank's
configured **C6A8/C6A9** count at its **C6A6/C6A7** anchor. B0CE/B0CF
establish the first window; **B0D4/B0D5** enforce five subsequent anchor
holds. It publishes **B0B8/B0B9** as 0 for matching count, 1 for too few,
2 for too many; initialized 3 means no completed classification. It resets
the accumulated count when opening the next window. The native test feeds
the actual capture callbacks into this classification; expected crank
selectors and callback spacing are explicit, not measured waveforms.

Fast-task call **11CE4**, through **11E50**, enters
`69314 -> 69382 -> 69394`. With **D370/01** qualified, count states 1/2
advance **D375/D376**; **74D22=4 prior calls** sets **D371/D372 bit01**
on the fifth. State 0 clears the counter and bit01. State 3 resets the
counter while holding an existing bit01. Losing qualification also resets
the counter without deleting the acquired local bit.

Slow-task **115D4**, through **117A8**, enters **69318**. Its **69326**
qualifier requires basic **DB24**, AVCS feature `3BB26`, diagnostic group
**3D**, and battery **at least 8 V** (`74F10`). This differs from the
10.9-V DB25 gate used by OCV-current diagnostics. **6942C -> 69442** then
calls **E314**, which atomically reads and clears only B0D0/B0D1 under
`2088/2098` mask E0. It leaves pending angle captures and edge counts intact.

With no consumed edge and running **B51C/08** (`19CB8`), the separate
**D377/D378** counter uses **74D23=94 prior calls**, setting local bit02
on invocation 95. An edge clears bit02 and its counter immediately.
Loss of running/qualification resets the counter but holds the local bit.
These are two task-dependent qualification counts, not one RPM limit.

**694C2** reports either local bit through **50FF6**: ID **84/P0340**
uses current **8EB4/10**, ID **83/P0345** uses **8EB4/08**. Both enables
remain 1. Healthy reporting through **5108C** clears current status;
raw **DAE4** remains latched. Connected **63174** execution consequently
clears current-cam aggregate **D270/80** while raw AVCS fallback
**D26F/10** remains set. The prior ignition tests trace that current
aggregate into secondary-spark selection, separately from the raw fallback.

The full transition from healthy to acquired fault also executes
**53BD8**. Healthy reports have cleared request bytes **DBB1/DBB0**, so
the first acquired report creates **group 0/event 0**, queue **3**,
callback **53D10**, with payload `[DTC ID, 20, 0]`. This is the same
bounded queue used by the shutdown worker, not the cam-observation queue 2.
In the explicit full-queue control, no record is overwritten and current
fault publication still occurs. However, **53BD8 ignores enqueue failure
and marks the request 20 anyway**; freeing capacity alone does not retry
that already-marked request. This is a native conditional loss of queued
diagnostic work, not evidence that the vehicle's queue filled or an
explanation for the user's code scan.

[Six connected groups](../../tests/test_cam_sensor_process_flow.py) pass
on main, v2 and captured v2. Diagnostic mode transitions and class-0 queued
records are now covered separately below; physical scheduling remains open.
The first test setup used an oversized stack canary range that overwrote
DE08; it was corrected to the actual short message-frame area before the
recorded passing run. That fixture failure is not a firmware defect.

## Queued diagnostic history and snapshot records

[Eight additional groups](../../tests/test_diagnostic_record_process_flow.py)
execute the actual `C898 -> 6270 -> 53D10` queue-3/task-4 path through native
task completion. With a missing-edge cam fault acquired and then recovered
before delivery, current bank `8E58` is already clear. The queued worker
still promotes the retained raw fault into **`8F30`**, a third, separately
protected 54-byte status bank. This is another reason current control status,
raw fault history and a stored snapshot must be kept distinct.

`53D10` accepts request **20**; request 10 and other values return. Its
descriptor-class dispatch calls `53DA8`, `53E84`, `54464`, `54604` or
`54770`, followed by `54D60`, `5560C` and `556F6`. Class 0 covers the cam,
OCV, AVLS and IAT electrical codes reviewed here. `53DA8` uses descriptor
`5BDF0 + 20*ID`, raw byte `DAB6 + offset` and protected history
`8F30 + 2*offset`. A one-trip descriptor (`+6 == 1`) promotes a set raw bit.
Other trip types also need **`DC06 == 1`, shutdown `C778 == 0`, and the same
bit in prior bank `8EC4`**. Tests sweep every enabled class-0 descriptor
and all combinations of those gates for P0011/P0021. The current bank is
untouched; all writes preserve byte/complement packing and array bounds.

`54D60` selects a snapshot independently of control-fault aggregation:

- An existing ordinary record is retained for later ordinary fault reports.
- Existing priority DTCs are protected. Individual promoted P0301 history
  alone does not replace an existing cam record; the separate promoted
  aggregate at descriptor IDs **49/4A** selects `551F4`, which uses captured
  cylinder bitmap `D83D/D83B` and its own source buffer. That buffer and
  aggregate are explicit test inputs; their complete producers are still open.
- When DTC word **`8FE4` is zero**, the native routine scans all 153 class-0
  descriptors. It writes each matching promoted fault and **does not break
  after the first write**. Later matches overwrite earlier ones. ID 3C uses
  the zero-data writer `55400`; other matches use `55064`.

`55064` copies 19 byte sources **`DA4D..DA55`, `DA58..DA5A`, `DA5E..DA64`**
to protected words **`8FBC..8FE0`**. DTC code goes to **`8FE4`**; source
words **`DA56/DA5C`** go to **`8FE8/8FEC`**, each as a u16 and its inverse.
`24DC/24EC` provide the native encodings. The tests preserve record padding
`8FE2` and the following record at `8FF0`; these writers do not approach WB,
lean, cam-control or injector scratch. Source sampling times remain separate.

`55518` resets the snapshot, but does not clear raw or promoted history.
The next empty-record selection can immediately capture a remaining fault.
Tests demonstrate this with cam and OCV history and check the exact reset
encoding, instead of treating a snapshot clear as a complete fault reset.

The two age helpers also differ. In normal mode, `5560C` clears protected
counter **`8FB8`** on an eligible raw/promoted intersection, or on eligible
raw status while that counter is below 3. It excludes selected bits in
offsets 11/12/13/14/2C/2D/30 with masks **3F/3F/80/FC/BF/7F/9F**.
`556F6 -> 55722` clears **`8FBA`** on any raw/promoted intersection, without
those exclusions. FF/A5 modes hold both counters.

No memory collision or new cut request was found in these executed class-0
record paths. The complete common startup bank validator/reset is covered above. Complete class-1/2/3/4 producers, later reset parents,
transport, reset parents and physical task timing remain separate audit work.

## Actual cam selectors and periodic interface refresh

The former capture fixtures supplied phase identities and expected edge counts.
[Three more groups](../../tests/test_cam_selector_process_flow.py) execute
the real producer **`2FDDC`**, called both by startup thunk **`FEE4`** and
at the start of periodic **`10A28`**, through pointer **`10C74`**. These
values are refreshed periodically, rather than only initialized once.

Interleaved calibration bytes **`7B248..7B24D`** publish bank-0 identities
**`C6A0 = [0,8,16]`** and bank-1 identities **`C6A3 = [4,12,20]`**.
Byte **`7B260 = 0`** selects phase-modulo-four anchor 0 for **both** banks,
and **`7B25F = 3`** supplies expected counts **`C6A8/C6A9 = 3`**.
The earlier `[0,4,8]/[2,6,10]`, separate anchors and count 1 were explicit
controlled fixtures, not the installed calibration.

With actual calibration, the full 24-phase sequence queues six observations
per cycle, alternating banks. After the initial count window, three edges
per bank classify healthy. Two/four edges classify missing/extra and feed
the existing fast cam monitor; a healthy window releases the selected fault.
Both primary cam conversion and the independent diagnostic count window use
the installed selectors in these tests. Physical edge arrival remains an input.

The same routine refreshes adjacent ADC interface fields: floats
`7B2A4/7B2A8 -> C67C/C680`, bounds `7B270..7B276 -> C684..C68A`,
bytes `7B250..7B25B -> C68C..C697`, and words
`7B264..7B26A -> C698..C69E`. Native copier `4408` places two 12-byte
descriptors **`60938/60944 -> C6B4/C6C0`**, preserving `C6AC/C6B0`.
Every destination, copy width and adjacent canary is checked against the
actual source bytes on all three images. No new overlap was found here.

## Engine signal timeout and queued reset

[Five connected groups](../../tests/test_engine_timeout_process_flow.py)
extend the stopped-state producer back through native engine-signal startup
and periodic poll **`81C0`** (pointer `6A20`, caller `6836`). The poll holds
mask B0 around **`83B0 -> 8AD6`** and restores its caller's mask.

Startup **`813C`** calls `82E0`, configures timer/cam capture registers and
programs **`OCR10A/F6D4 = 72824 = 000FA000`**. It initializes selector
`AC20` and event qualifiers to zero, then `8AC0` starts all three timeout
latches **`AC0C/AC4E/AC4F` at 1** and counter `AC4C` at FFFF. A primary
event's **`8B2E`** clears `AC4E` and clears `AC0C` unless mode is 2.

`8AD6` sets the primary latch from **TSR10 `F6E8/01`, CMF10A**, the timer
10A compare event. The [Renesas manual, section 11.2.26](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual)
defines these flags as read-one/write-zero clear; writing one preserves a
flag. The tests model that behavior. Treating writes `0B/0E` as ordinary
RAM values would invent timer events. `83B0` clears compare-B bit 2 once
when arming; `8B2E` clears compare-A bit 0 while preserving other set bits.

The secondary latch uses **`AC4C >= u16(72820)`**, whose installed threshold
is zero. It is selected only for **`AC20 == 2`**. The identified normal
publishers do not select that state: startup writes 0, and current-cam-fault
publisher **`1A202 -> 80F8`** writes boolean **0 or 1**. Both modes use the
primary latch. A cam fault therefore does not by itself turn the zero
secondary threshold into an engine timeout; connected no-compare controls
retain internal 3,000 RPM and queue no reset in either mode.

A newly selected primary timeout sets **`AC0C`**, then **`8266`** resets
engine-signal synchronization and filter state. Internal **`AC00` becomes
0**, periods **`AC04/AC08` become 7FFFFFFF**, and phase state `AC15` becomes
36. **`CFD4 -> C700`**, group 1/event 4, appends callback **`69C4`** to
the same **30-record queue 2** that carries cam observations. The later
`1A16E` publication sets stopped bit `B52C/80` and clears `AC21`.

Explicit delivery of that actual queued callback runs
**`E3CA -> 11E80 (no-op) -> 8EDA -> 7E50`**. It resets cam observations,
cancels pending requests for all six injectors through **`920C`**, and resets
`ABFC/ABF0/ABF8`. An already-counting injector pulse remains active until
hardware completion; the pending-request cancel is not an immediate end
to an active electrical pulse. Those hardware start/completion events remain
explicit fixture inputs.

In the full-queue control, the immediate signal reset still happens, but
the callback cannot be enqueued. The sender ignores enqueue failure, and
`AC0C` being set prevents another publication. Freeing one slot does not retry
until primary-event recovery clears the latch and a new timeout occurs.
This is a conditional native queue dependency, **not evidence of a timer
timeout or full queue during the vehicle event**. Physical crank signal,
compare timing, scheduler response and the separate synchronization-transition
callback remain open.

## Synchronization transitions and adjacent work arrays

Native `8298` publishes group 1/event 5 through `FBD4 -> CFEC -> C700`.
Descriptor `FCB0` selects **queue 0, one payload word, callback `69DE`**.
Its ten 20-byte records occupy `9310..93D7`; head/tail/count are
`9304/9305/9306`, and its task is 1. Acquisition state 1 first calls
`8BCA`, clearing `AC60`, copying `AC38` to `AC10`, and setting
`AC14 = AC42 - 1` with byte wrap. Loss state 0 skips those seed changes.
A full queue rejects the record without overwriting storage; the publisher
contains no retry. Actual producer re-entry and delivery time are separate.

The complete queued callback is
`69DE -> 9B58 -> D914 -> DB2E -> A76C -> 11E84`. State 0 clears the
six pending coil-device flags through `9B58`. Both states clear the six
`B078..B07D` event bytes, refresh the `DB2E` state, and initialize adjacent
work through `A76C`. This last computed writer matters to our RAM allocation:
its three six-float arrays are `ADA4..ADBB`, `ADE0..ADF7` and
`AE0C..AE23`, with six calibration bytes copied from `C68C..C691`
to `AE45..AE4A`. Its scalar/flag stores also remain below WB `AE60`.
All eight WB publications and relocated lean slots `AE9C/AEA0` preserve
distinct canaries through both transitions; no alias was found on this path.

`11E84` then splits the transition:

| State | Native downstream effect |
|---|---|
| Acquisition 1 | `1D8AE` sets `B7D4=1`; `2A242` sets auxiliary spark mask `C290=0` for `B52C/20`, otherwise `0FC0`; `29C00` sets spark resync `C28D=1`; `26200` sets `BFB6=FF`; `26846` sets fuel resync `C0B5=1`. |
| Loss 0 | `29C08` cancels twelve logical spark requests using the actual hardware channel sequence `1,0,0,1,3,2,2,3,4,5,5,4`; `261EC` clears `BFB4..BFB7`; `2684E` cancels all six injector requests and zeros `C0A8/C0AC/C0B0`. Active hardware completion remains distinct from request cancellation. |

The timeout parent now also executes with `AC3C=1` and `AC16=1`.
Its native `8360 -> 87CE -> 8298(0)` publishes synchronization loss into
queue 0 before the separate `69C4` reset is placed in queue 2. Delivering
that actual loss record reaches both scheduler cancellations. These are
two queues; their eventual task ordering is not replaced by the producer's
publication order in the test.

[Five synchronization groups](../../tests/test_sync_transition_process_flow.py)
pass on main, v2 and exact captured v2. All native calls and bounded computed
writes execute, with explicit callback timing and hardware/synchronization
inputs. The finding establishes a native cut mechanism and its patch-RAM
boundaries; it does not establish a lost crank signal or queue overflow in
the vehicle. Crank-edge production and preemption remain separate work.

## Crank capture decoding and shared observation work

The primary IRQ wrapper at `3094` uses common native entry `340C` and
then enters `5DAE`. That handler reads `F6E8/TSR10`, clears its `04`
compare flag with the documented read-one/write-zero sequence, and calls
`8218 -> DB50 -> D92C`. Timer-10 event counter `TCNT10B` and compare
register `OCR10B` are **8-bit external-edge counters**, not elapsed-time
counters. `8764` resets both to zero. The timer-10 and timer-0 capture
registers used below are 32-bit. These meanings follow
[Renesas manual sections 11.2.18–19, 11.2.21 and 11.3.12](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual).
The primary wrapper bytes are retained; the common kernel, decoder and
post-edge workers have separate connected test boundaries.

`8218` skips capture processing when `AC22` is nonzero. Otherwise it clears
the primary timeout, advances the secondary countdown, and runs `8428`:
`F434 -> AC34`, old `AC2C -> AC30`, and `F6D0/ICR10A -> AC2C`.
Pattern decoder `84B2` advances `AC15` using 37 rows at `FA2C`; a prior
position greater than 36 resets before the table is indexed. Its `AC3D`
stages use interval ratios from `7B2AC ~= 2.18` and `7B2B0 ~= 0.68`.
The stage-2 gap search resets after five ordinary edges, bounding its
adjustment-table read to `FA76+1..5` when entered with the native count.

Qualified positions 0 and 12 run `8692(0/4)`. The phase flag in the second
byte of each transition row then permits `87F2`, except in mode 2. Secondary
entry `8248` separately clears its timeout, increments `AC44`, and reloads
`AC45` from `7B24E=5`. Primary processing decrements that countdown; mapped
phase events clear both bytes through `8776`. The installed `72828=00`
skips optional `8D06` ratio-extrema tracking.

[Six decoder groups](../../tests/test_crank_decoder_process_flow.py) run the
native entries on all three images. An explicit 36-position fixture omits
positions 7, 8, 10, 11, 31 and 32, and supplies secondary captures at
0/240/480 degrees of its 720-degree sequence. It acquires and holds all 24
phases in both normal mode 0 and cam-fault mode 1. Other cases exercise
invalid-position reset, gap-search limits, capture suppression and release.
This is a controlled waveform fixture, not a reconstruction of the car's
crank/cam signals. Phase activation is the separately tested kernel boundary.

### Capture-inhibit request and its low-RPM producer

Periodic parent `1081A` calls `193D0`, then `19EF0`, `1A16E` and `1A0BA`
in that order. `1A0BA` publishes `B52B = Boolean(B525/80 OR B542/80)`
and calls `8104`. A rising request stores `AC22=1`, then runs
`8286 -> 8360 -> 87CE -> 8298(0)` under interrupt mask `B0`. This resets
synchronization and queues its loss callback. Repeating the same request
does not reset/enqueue again; clearing both source bits releases processing.

`19EF0` is the low-RPM source of `B525/80`. At **RPM >= 1,000** it clears
that bit regardless of `B51E/08` or the retained hold counter. Tests include
the loaded 2,500–4,144-RPM range and preserve unrelated low bits. This closes
that source at the logged speeds, without inferring physical digital inputs.
The separate `B542/80` chain now has [four connected native
groups](../../tests/test_capture_inhibit_process_flow.py). Its only identified
setting writer, `1A428`, is called by `FEF4` at `FF68/FF6A` through pointer
`1018C`. It sets the high bit if `80D4/01=0`, byte `82A0=1`, or byte
`829C=0`; otherwise it clears that bit. Startup also sets the two-byte
`B540` counter to **25**, from `73806`. The unrelated seven bits survive.

Periodic `10A28` calls `1A368` through `10CBC`. This service **can release
the latch but cannot set it**. Fault getters `65366/653BA` return 2 for
`D273/04` or `D274/40` and immediately release it. Otherwise request `C2B4`
must be outside the native near-zero tolerance **0.0019073486328125**, and
all of these must hold: `ABD4/C2B4 >= 0.7999999523162842`, `80D4/01=1`,
`C618/01=0`, `D36C/80=0`, and byte `829C=1`. Every call decrements positive
`B540`, holding at zero. `193D0` uses that counter to suppress `B51C/08`
during the startup delay; the counter is separate from the capture latch.

The tests execute initialization, each release gate, ratio boundaries,
near-zero hold, 25-call countdown, propagation to the real loss message,
release and subsequent decoder acquisition. Changing the release inputs
after release does not rearm capture inhibit, including the supplied
2,500–4,144-RPM fixtures. This rules out a new RPM-dependent assertion by
this periodic service; it does not establish the vehicle's retained values.
The upstream `80D4` learning worker (`15AE8/15E24`) and paired retained
`829C/82A0` producers (`68BF6/68D74`) are identified separately. Reading
their branches is not represented as complete retained-memory execution.

### Interval observations share the cam queue

`D8EE` initializes `B07E=0`, `B07F=9`, channel `B058=0` and six flags
`B078..B07D`. For synchronized decoded positions, `D92C` stores six
capture timestamps at `B05C..B073`. Positions separated by nine table
steps complete a channel's interval; the second phase half adds 36 to the
position identity. Unsigned subtraction handles capture-counter wrap.
The resulting frequency value shifts the **eight-float history `B038..B057`**,
while `B074` records elapsed counts and `B058` identifies channel 0–5.
These computed writes remain below the WB mirror region even in the
historical image, and preserve all WB/lean publications in the tests.

The native send is `D01C -> C700`, group 1/event 9. Descriptor `FCD0`
selects **queue 2, zero payload words, callback `11ED2 -> 6A6AC`**.
Thus queue 2 carries interval observations as well as cam observations and
timeout reset. The diagnostic callback snapshots the **current shared**
channel/history when delivered. Three produced observations followed by
delivery of the first record consequently snapshot channel 2, not channel 0.
A full queue drops the callback while the global history still updates.
These conditional lag effects do not establish backlog in the vehicle.
At the supplied 3,000 RPM, the callback takes its existing early exit after
snapshotting, before the low-RPM monitor body.

`DB50` also sets edge latch `B08A`, increments saturating counter `B089`,
and checks a synchronized position-zero window. After its first qualified
window (`B088=1`), a just-updated count of 30 publishes `B080=1`; another
count publishes 2. It then clears the counter. These status bytes do not
alias WB mirrors or the restored OCV-current floats.

[Five observation groups](../../tests/test_crank_observation_process_flow.py)
cover all six channels, counter wrap, missing first samples, loss of sync,
actual queued callback, delayed/full queue and the 30-edge status window.
Their timestamps and delivery are explicit. Full low-RPM diagnostic work,
remaining status consumers, `B542` release and initial cranking-pulse work
remain separate process-flow edges.

## Retained inhibit sources before the injector publisher

[Eight source groups](../../tests/test_native_inhibit_sources_process_flow.py)
execute the complete native workers below and their `1C5D4` handoff on main,
v2 and captured v2. This extends the earlier tests that imposed final source
bits. All of these instructions and referenced limiter constants match stock.
The global branches write **`B744=FFFF`**; the speed-limiter pattern writes
six individual bits, reaching **`003F`**. Both inhibit all six injector
channels, but they are distinct native publications.

| Source | Producer and full decision | Release and patch relationship |
|---|---|---|
| `BF70/80` | `24C34 -> 19C18` counts two calls with `B51D/40` clear. The complete GPIO chain is `PFDR F74E/0001 -> 6BB4 -> AAE8/0001 -> 193D0 -> B51D/40`; `6B08` seeds its history. | Two equal samples update the debounced input; a healthy published bit clears the counter and cut immediately. WB's port-E writes do not alias port F in the connected fixture. PF0's external wiring is not inferred. |
| `BF74/80` | `24CB0` first maintains a low-speed plausibility latch `/10`, using speed `B538`, RPM `B544`, load `B438` and `B51C/80`. `24E0C` then qualifies coolant >=60 C, clear selected fault/mode gates and either speed <1 or `/10` plus its digital qualification. Four RPM histories qualify a retained timed-cut state. | The full pair clears `/10`, `/40`, `/20` and `/80` when supplied speed is >=1 and other tested inputs are clear, even with saturated old timers. The sampled loaded log values also clear this path. Load changes from SD do not bypass that speed reset in these cases. |
| `BF8C/01` and other cylinder bits | `2513C` has a speed threshold of 262 km/h, RPM >= 5,400 and a separate speed-fault alternative. It uses 16-call on/off history to move through partial/full cylinder patterns. | Healthy speed below 260 or RPM below 5,400 releases the qualified state. Tested loaded RPM values 2,500–4,144 do not start it, even with speed 262. Fault alternatives remain distinct inputs. |
| `CF24/80` | `4551C` sets RPM history `CF25/80` at 4,600; it requests cut only in `CD86=1` or when native `65208` reports the AVLS-fault fallback. | Clears below 4,400, including after a deliberately imposed 4,600-RPM activation. Current 1/3 lift-mode changes do not lower this limiter to 3,000. |
| `BF9C/02` | `25AC0` reads received request `B210` and a coolant/RPM lookup, but its native permission getter `35DEE` unconditionally returns0. It therefore takes `25F8E`, restoring pattern demand `BF94=12`; `25B58` publishes `BF9E=12`, then `25D42` clears the cut request. | The disabled producer also clears its enable, pattern flags and `BFB0/02`. This holds over supplied received values 0/40/510 and loaded RPM values; no received request can override the installed zero-return permission in this path. |
| `CE24/01` | `4162C` requires `B289/80` and either protected byte `8546=1` or `CE54/06`. Its three native getters and final publisher execute. | Removing the configuration permission clears the cut. The actual security-record/received-status producers are separate from this conditional test. |
| `CFA0/01` | `3C388` combines `CC71/08` and `/10` into `/20`; `472E4 -> 3C652` copies that result into the cut source and calls the publisher. | Either component clear releases it. The components come from received-message processing at `3BEE4`; their full acquisition/timeout path is tracked separately. |

The stationary timer's four bands are 5600/5500 RPM with 469 calls,
4000/3500 with 1094 calls, and two 2600/1900 bands with 4688 calls each.
Once a qualified timer expires, final cut starts at 1500 and releases below 1250
while its qualifying latch holds. These are **call counts**, not measured
wall-clock delays. One complete 1094-call positive control reaches the cut;
movement then clears it. The loaded 71–86 s and 130–132 s samples have nonzero
speed and clear the path even with an imposed stale cut latch. This does not
reconstruct every unlogged task invocation or prove a missing digital/CAN state.

The `CCB9` phase-pattern source and received-message latches are expanded
below. Other upstream fault/state producers and real asynchronous timing
remain separate work. No limiter calibration or cut protection was changed.

### Received CAN requests, phase patterns and duration-model aliases

[Eleven connected groups](../../tests/test_received_cut_process_flow.py)
execute receive copies, timeout/reset, the enabled-slot calculation, actual
integer lookup/rotation helpers, phase publication and slow release history.
All three pinned images retain the same native instructions and constants.
Mailbox payloads and arrival bits are explicit fixtures; the driving log
does not record the CAN traffic or these request latches. The later complete
mode-parent tests below establish that the normal-temperature gate blocks
the `CCB9` cut path. The earlier forced-permission pattern results must not
be read as evidence that it could activate at the logged coolant temperature.

| Path | Acquisition and dependency | Release and retained state |
|---|---|---|
| `14374 -> B250/B24C` | Descriptor `4AF5C`, CAN ID `501`: byte 3 times 1.6 supplies `B250`; byte 4 supplies `B24C`; byte 5 is sequence state. ID `512/513` share the native validation/timeout parent. | The tested accepted request followed by 63 missing-message calls invokes native `146A6`, clearing permission and restoring `B250=408`. It is not the SD airflow fallback. |
| `3CE0A -> CCAC -> 3CE58 -> CCB8` | `CCAC=min(100, B250*100/CA38)` when `CA38` passes the near-zero check; otherwise 100. With `B24C/01` set and `CA48/02` clear, descending ratio thresholds 75/50/25/2/1 select 10/8/6/4/2 enabled slots. Release hysteresis adds five ratio points. | Loss of permission restores all 12 slots and clears threshold history. The native minimum is two enabled slots, not a request to cut every slot. |
| `3D48C -> 3D050 -> CCB9 -> 1C5D4` | Periodic `10BB2` supplies a rising-request edge in `CCC4/01`. Crank-task call `1199A`, pointer `11AA4`, consumes phase `B528`, chooses a 12-bit pattern and rotates it. `B529!=0` skips the update. | Cylinder bits publish only at `CCC2` counts 0 and 6. With fixed zero rotation, a minimum request produces `B744=001F`; all 24 actual starting-phase alignment fixtures inhibit five cylinders while leaving one enabled. Permission release reaches zero within six eligible calls in the tested sequence. This is not a measured scheduling deadline. |
| `3D3A2 -> CCBB/04` | Slow call `10856`, pointer `109E4`, tracks the falling edge of `CCB9/01` using separate `CCC4` bits and `CCC0`. | This diagnostic/learning summary remains set through counts 1–250 and clears above 250, while the injector cut has already released. A held summary bit is not equivalent to continuing cylinder inhibition. |
| `3BEE4 -> CC71 -> CFA0 -> B744` | ID `514` byte 6 `/20` and ID `620` byte 0 `/01` independently qualify after two fresh frames, battery >=8 V and startup counter `CC7A>0`. `3C388` combines both latches; `472E4` publishes a global `FFFF` inhibit. | Startup `3C494` loads 44 into `CC7A`; `3C366` decrements it at battery >=8 V. Expiry prevents new qualification but does not clear existing latches. Missing frames and low-battery `3C4C6` reset also retain those bits. Fresh clear frames release them. These conditions were imposed in tests, not observed in the vehicle. |

The injector scalar has a downstream dependency beyond delivered pulse width:
`1E0C8` forms `B82C`, then `365C0` uses RPM and that duration in descriptor
`5E8F4` to publish model `CA38`. Its slot-scaled `CA3C` also feeds native CAN
message construction at `136D8`. Changing injector size therefore changes
the model even at identical calculated air mass. It is not a measured torque
channel, and correct physical torque calibration is not established here.

The native throttle branch separately forms
`C5F8=max(B250-CA38, -204.8)` at `2EE6C`. Pointer order `110C8..110E4`
runs received-request delta, delta latch, this error, PI correction, base
request, sum, publication and permission. A request decrease greater than
approximately 10.4 latches `C604`, resetting the proportional/integral
corrections; a rising request clears it. Changing load alone does not reset
that latch in the connected test. `36610` permits `CA49/01` from `B24C/01`
unless `CA48/01` inhibits it; `2ECCA` copies that permission to `C5E0/01`.
The resulting `C5DC` enters the already traced throttle selector `2AB06`.
The native `CA48` producers and their reason inputs are expanded below.

Across tested 2,500–4,144 RPM, loads 0.7/1.975/2.5 and requests
0/80/200/408, the installed smaller injector scalar lowers `CA38` compared
with an in-memory stock-scalar control. For the same request this raises
`CCAC`, reducing or retaining the calculated cut demand; it cannot manufacture
the received permission bit. This closes that numerical dependency without
attributing an unlogged CAN request to the loaded event. No calibration or
BIN changes were made for these findings.

### Native torque-mode parents rule out the warm received cylinder-cut path

[Six mode-parent groups](../../tests/test_torque_mode_process_flow.py)
execute `36054` initialization, `36190` common reasons, `36370` cylinder-cut
qualification, `36610` throttle permission and the complete three-stage
reentry timer. They expose a restriction that was absent from the earlier
tests with `CA48` supplied clear:

**At the logged 67 C coolant temperature, stock `36370` inhibits received
cylinder cutting.** The native upper coolant constants are `72D30=-38`
and `72D34=-37`; `2484` sets `CA48/08` at >=-37 C and clears it only below
-38 C. That flag forces `CA48/02`, so `3CE58` restores all 12 slots even
with `B24C/01` set and `B250=0`. The lower coolant gate sets a separate
inhibit below -40 C and releases at -39 C. The executable positive-control
window around -39 C is an explicit artificial fixture, not the captured
engine state. These constants and instructions match stock in both patches.

`36190` separately publishes reason bytes `CA45/CA46` and common inhibit
`CA48/01`. It consumes received availability `CC4C/80`, `B748/80`,
`C0E3/40`, external request `CA49/02`, digital `B51C/08` and its falling-edge
delay, battery >=8 V, current fault `D26F/08`, received status `B24D/80`,
coolant history and the `B90D/E` startup qualification. Isolated reason
fixtures assert the common inhibit and recover through the native parent.
Those raw status/digital producers are still explicit inputs; this is not
a reconstruction of their vehicle values.

The received **throttle** path can remain permitted while received cylinder
cutting is inhibited: `36610` uses common `/01`, while `3CE58` uses `/02`.
This distinction prevents incorrectly treating both as one torque mode.
Warm tests spanning 2,500–4,144 RPM, pressure 75–1,800 mmHg and signed
`BE48` values keep the cylinder request disabled despite supplied CAN
permission. Separate cold-window tests exercise the RPM gate (1,350/1,375),
ratio hysteresis (99.61/99.2) and coolant transitions.

The periodic order `3D2E4 -> 3D28E -> 3D322` maintains elapsed request count
`CCB6`, reentry holdoff `CCB4`, and previous-request bit `CCBB/02`.
A falling request loads 1,250 into `CCB4`; each following call decrements
it, and nonzero holdoff inhibits new cutting through `36370`. Saturated
`CCB6=65535` with an active request also reloads the holdoff. The connected
test runs the complete 1,250-call release and verifies counter saturation.
This delay prevents reentry; it does not keep injectors disabled.

This closes another possible source of the loaded cut without changing a
limiter or protection. It does not rule out the separate `CFA0` startup CAN
latch, other native cut sources or physical output faults. No new BIN was
needed for this finding.

## Injector duration to timer registers

The existing scheduler tests stopped at device helpers `900A`, `8F84`, and
`90F8`. The [new device-flow test](../../tests/test_injector_device_process_flow.py)
executes these native routines, pending promotion `938C`, width recalculation
`92DA`, register publisher `93D4`, and the actual `D744` word writer. This
extends the previous boundary; elapsed timers and current are not simulated.

`900A` stores requested effective pulse counts in `AC80+24*channel`. It adds
the additional count term `AD10` and common latency `AC7C`, divides by the
120-degree period `AC08`, and multiplies by 120 to form angular pulse width.
It subtracts that width from the requested end angle relative to `AC18`,
wraps the angle, and publishes pending mode 2. `8F84` instead publishes the
start-angle form, pending mode 1. A start distance below 35 degrees promotes
immediately; otherwise `8F08 -> 938C` subtracts 30 degrees on each native
phase call until promotion. `90F8 -> 92DA` recalculates pending end-angle
start distance if the pulse changes.

`93D4` uses the timer descriptor at `FA94+12*channel`. In the tested inactive-
timer branch, the width word is `(effective_count + AC7C) >> 4`; the start
compare derives from `AC1C/AC04` and the angular distance, with native bounds.
The actual word stores go through `D744`. Periodic and event inputs are
explicit fixtures; they are not reconstructed timing observations.

All eight groups pass on main, v2 and captured v2: immediate scheduling for
all six channels across 2,500/2,800/3,000/3,200/3,500/4,144 RPM and gross
widths 7.680–12.288 ms, natural pending promotion by `938C`, and a pending
duration increase advancing its start without dropping the request. The added
groups exercise active shortening/extension, deferred-pulse end callbacks,
counter wrap with bounded snapshot age, an excessively stale timestamp, and
the actual interrupt-priority initializer. The installed 14-V latency count
2,736 is an input. Ordinary scheduling fixtures reach nonzero corresponding
timer words; no RPM-specific truncation appears in those cases.

`90F8` adjusts an active down-counter by the duration difference and clamps
shortening to zero when the decrement consumes the remaining pulse. It holds
the update in record `+0C` while `+14=1` indicates a deferred request.
`93D4` sets that deferred state and enables the channel's `TIER8` bit when
the earlier pulse ends before the next requested start. Actual native end
handlers `5BD4/5BE2/5C30/5C3E/5C4C/5C5A -> 8F80 -> 961A` then publish
the updated duration and start compare, clear the interrupt-enable bit, and
clear `+12/+14` state. Tests supply the hardware-completion state explicitly.

The [Renesas manual, sections 11.2.11 and 11.2.16](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual)
identifies `F640..F64A` as down-counters, `F666` as `DSTR`, `F66A` as
`TSR8`, and `F66C` as `TIER8`. **A CPU zero does not clear a DSTR bit**;
the tests model that documented write behavior so starting one channel does
not incorrectly stop the other five. Actual elapsed counts, automatic flag
changes and interrupt delivery remain test inputs.

### Timestamp freshness is part of the native contract

`8428` samples input-capture `FFFFF434` into `AC34`. After the native
synchronization/phase gates, `87F2 -> 8BE6` copies it into `AC1C` and
publishes `AC18=30*phase-10`, wrapping a negative result by 720 degrees.
`93D4` uses `AC1C >> 4` as its timer snapshot. It also reads current
`TCNT1A` at `F440`; their difference matters when another pulse is active.

With an imposed snapshot of 1,000, current counter 4,000, an active channel
with 100 counts remaining, and a newly requested 2,500-count gross duration,
the native `954A..9556` path writes **65,036**, the 16-bit representation
of -500, to the down-counter. Its comparison negates a zero-extended
16-bit start/current difference; it does not saturate this late case to zero.
This is a reproducible arithmetic counterexample, not an observed vehicle
state. The gap represents 12 ms under the test's duration/count conversion.
Across 2,800–4,144 RPM fixtures with at most one supplied 30-degree interval
of age, including timer wrap, the same active branch retains nonzero bounded
widths. **Neither fixture establishes the actual maximum snapshot age.**

The native interrupt initializer `4DB2` writes `IPRI=99B0` and `IPRH=9999`.
VBR `7FC50` plus vector 178 selects `3094 -> 340C -> 5DAE -> 8218`;
the manual's table 7.3 identifies this as CMI10B with **priority 11**.
That handler reaches the timestamp producer above. Injector-end interrupts
have priority 9. The ordinary WB publication mask is 9, so it does not
directly mask this priority-11 crank path. SD adds no interrupt mask and the
cut wrappers use mask 1. Native priority-14 critical sections, higher-priority
interrupts, synchronization gates and task backlog still require timing
bounds. None has been shown to produce the imposed stale condition in the
loaded capture; changing the native branch is not yet a cut fix.

## Supplemental tip-in through the immediate device callback

Tip-in is separate from the signed normal-duration correction `B874`.
`23BAE` publishes effective supplemental microseconds at `BEFC`, total with
latency at `BF10`, then calls `C700(R4=0,R5=4,R6=&BEFC)`.
`FB88[0] -> FD04`, slot 4 at `FD24`, contains `FFFF,0001,00011EF4`:
one payload longword and **immediate invocation**, not a queued task message.
`C700` copies the value into its stack before invoking `11EF4`.

`11EF4 -> 2689C` calls `268E8` for all six channels. That gate checks
the current `B744` inhibit bit, converts microseconds to counts by dividing
by 0.25, applies the native channel map/enables, then calls `90BA -> 96FC`.
The inactive-channel branch adds latency and starts a pulse. An already
counting channel extends its down-counter by the supplemental effective
duration **without adding latency a second time**. Other branches account
for a scheduled/deferred main pulse; their hardware ordering is still bounded
by the explicit fixture assumptions.

All [three connected tip-in/device groups](../../tests/test_tip_in_device_process_flow.py)
pass: main/v2 pressure-gate differences, every one of 64 inhibit masks, and
active pulse extension followed by settled-throttle non-repetition. With a
supplied 20-degree delta, 3,000 RPM and 85 C, v2 requests 2,528 effective
microseconds at both 330 and 820 mmHg absolute. Main requests 1,548 at
330 mmHg and none at 820 mmHg with supplied barometric pressure 712 mmHg.
These are calibration/fixture results, not reconstruction of sub-sample
throttle movement in the road log. Table interpolation remains mathematical;
the callback, cut gating and device stores execute native opcodes.

This closes an earlier event-delivery test boundary. It also limits the
meaning of the road log: near-zero `B874` and ordinary P21 do not by themselves
rule out a supplemental pulse. A settled zero-delta fixture does not repeat
the previous request, so this trace alone does not explain the sustained bog.

## Deleted purge producers and retained consumers

`1BAF0` publishes exact zero to duty `B6D4`, modeled purge airflow `B6D8`
and mode `B720`, then tail-calls native `B182`. That writer scales the
fraction by 65,536 into `AE4C`; native signed fixed-point helper `2390`
multiplies it by period `AB60` and writes request `AB64`. The other direct
request writer is the native initializer at `B0D8`.

The retained compare handler `57DA` consumes the `AB60` record: `+2` on
time, `+4` requested on time, `+6` off time and `+8/+9/+A` phase/update
state. A zero request produces zero on time and a full-period off time.
It programs the `F4CB` control field and `F4C4` compare while preserving the
other `F4CB/8F` bits, with minimum compare distance computed from `F4C0`.
Its state record begins at `AB60`; the neighboring record at `AB54` and
fan output path are not written in these native fixtures. This establishes
the register command, not valve motion or installed wiring polarity.

`22FE8` seeds `BE7C`, filtered `BE70` and previous `BE80` from `B6D8`,
and initializes counters `BE68/BE69/BE6A` to 255. `2300A` then runs:

1. Native getters `1BFBC` (`B705/40`) and constant-zero `46FE8` publish
   `BE78/BE79`; current `B6D8` and ECT are copied to `BE7C/BE84`.
2. `23238` chooses filter coefficient `BE74` from load-change `B43C`,
   the sign of `BE70-BE7C` and its native counters.
3. `231D6 -> 2424` updates `BE70`, including native nonfinite-history
   handling and the near-zero snap threshold.
4. `230E8` qualifies and updates `BE6C`, normally bounded to 0..0.125
   using `BE70/B420`; its low-airflow branch avoids that division.
5. Both calls to patched `23054` publish zero to `BE60/BE64`, irrespective
   of any residual filter value, then `BE7C` is copied to `BE80`.

All [three native purge process groups](../../tests/test_purge_process_flow.py)
pass on main, v2 and captured v2. They exercise normal initialization and
load/ECT/airflow/qualifier transitions, a positive stale filtered flow decaying
to zero with both bank subtraction terms staying zero, and clearing a prior
nonzero PWM duty from both phase states. All helpers on these paths execute
ROM instructions; no table or output-writer substitute is used.

The zeroed outputs still have other consumers:

| Input | Retained consumers and dependency |
|---|---|
| `BE6C/BE70` | Their filter/ratio routines and the bypassed body of `23054`; no additional direct destination xrefs were found. Computed references still need independent review. |
| `BE60/BE64` | `1DD04` bank composition, `204AC` filtered feedback-side term, and learning eligibility. Zero final subtraction does not delete those routines. |
| `B6D4` | `62C0E/62CC4` circuit counters `D254/D256`, using `D258/01`, hardware `F726/0800` and separate duty thresholds. Only the matching P0458/P0459 report enables were disabled. |
| `B6D4` | `668FC -> 6693E` publishes near-zero-duty `D2CB`, persistence `D2C9` and qualification bit `10` in bank diagnostic states `D2B2/D2BE`. With zero duty it follows the no-purge qualification path; other fault/eligibility inputs remain. |
| `B6D4` | `6E5F4` compares current/previous near-zero states `D99D/D99E`, saves prior duty at `D984` and maintains stability counter `D995`. `6E338` consumes this counter and zero duty among many prerequisites; it can set `D94B/20` and decrement `D852`. These are retained monitor/learning dependencies, not proof of an injector cut. |

The diagnostic rows are static traces; their complete upstream and downstream
state transitions are not covered by the three purge tests. In particular,
`D94B` is shared with the configured cylinder-disable subsystem, so its
individual bit meanings must be preserved rather than treating the entire
byte as a single cut flag.

## Driver request, received limits and final throttle selection

The former map fixture explicitly copied `C3DC` into `C3D4`. The new
[seven-group execution suite](../../tests/test_dbw_arbitration_process_flow.py)
executes the intervening native arbitration and table helpers. In task
`10A28`, the relevant order is:

`2B35A -> 2B350 -> 2AF74 -> 2AF5C -> 2ADEC -> 2AD6C -> 2AC16 ->
2ADF6 -> 2ADCA -> 2AB06`, followed by the shutdown/stopped-override stages
listed below and final selector `2AAAC`.

`2B35A` maps pedal `B46C` and RPM through `607F0`, clamps to the native
`795CC` maximum and publishes `C3DC`. `2B350` copies it to **`C3D8`**,
not `C3D4`. `2AF74` owns that latter publication. It maintains:

- `C3E4`: a history of `C3D8` that follows falls immediately and rises with
  native alpha 0.1 (`795D4`).
- `C3E0/01`, `C3E8` and counters `C3F0..C3F5`: an opening-rate state
  selected using `CD48`, RPM, temperature, speed, processed throttle,
  pedal qualifiers and digital state. Clear latch selects a step of 408;
  the active latch selects the appropriate RPM-indexed table.
- `C3EC`: received limit `B214`, replaced with 510 if `651BA` returns 2
  (`D26F/08`). This is separate from the native injector-cut getters.

The final `C3D4` is the minimum of the filtered driver request, prior
`C3D4 + C3E8`, and `max(C3EC, 40)`. The driver-request filter's current
coefficient `795C4` is 1.0. Both rolling patches retain all these arbitration
instructions and constants. The V2 table changes remain upstream/downstream
of this retained state machine.

Normal supplied states at 2,500/2,800/3,000/3,200/3,500/4,144 RPM have no
RPM-window throttle cut. An explicit low-prior-throttle/digital-state fixture
does acquire the rate latch: V2 at 2,800 RPM initially ramps by about 4.8
torque units per call, later 6.4, and recovers to the requested value. Release
still goes to zero driver request. These are call counts and conditional
states, not measured throttle response times or reconstructed vehicle flags.

`CD48` is a native gear-classification code. `3F474` selects it using
speed divided by RPM/1000 against `73BC8..73BD8` or `73BDC..73BEC`, with
separate digital and speed-fault gates. It can publish code 6 or low-RPM
fallback code 5 independently of the physical gear. Its inputs are explicit
boundaries in the arbitration tests; a selected code alone does not establish
which gear the car was physically in.

### CAN publication and timeout behavior

`13FE0 -> C9AA` reads descriptors `4AFA4/4B01C/4AFEC` for IDs
`420/421/422`. Descriptor `4B01C` selects mailbox 10, receive mask `0004`,
data at `E500`, and eight destination bytes `B224..B22B`. `CC14` performs
the byte copy; `25BC` explicitly zero-extends the byte, so
**`B214 = 2 * unsigned(B224)`**, spanning 0–510. Values 128–255 do not
become negative. These published values now execute through `2AF74` and
the second throttle map in the tests.

`E40E` is HCAN0 `RXPR`; writing 1 clears the matching receive flag.
The test models this register's write behavior and supplies fixed mailbox
data, following the [Renesas manual, section 16.2.9](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual).
It does not simulate message arrivals, the CAN bus or simultaneous mailbox
overwrites.

`13E30` enables missing-message monitoring with `B1FC/02` after **1,000
calls above 10.9 V** (`ABB4`) and `C778 == 0`. Its separate HCAN health
inputs are `GSR` at `E401`, bits 1 and 0. In `13FE0`, any missing-message
counter `B244/B245/B246` reaching 63 invokes `142FA`, restoring `B214`
to **510**, and latches protected word `B208`. A newly received 421 frame
alone cannot defeat the other two expired counters; all expired message
streams must recover before their normal publication survives the routine.

The repeated message-counter condition has a distinct counter `B247` and
protected status `B20A`. It can latch while all three messages remain fresh,
and **does not itself call `142FA`**. Both status records can stay latched
after reception recovers. Native initializer `142E2` clears the records;
`142FA` alone resets published requests. The `B208` getter feeds retained
diagnostic/qualification routines `699E8` and `721F4`. No direct literal or
MCP xref was found for the `B20A` getter `1433C`; computed use is not ruled out.

Separate battery hysteresis `13E08` sets `B200` below 6.0 V and clears it
at 6.2 V. That state, `B51E/01`, or raw diagnostic mask `DAE4/01` causes
the immediate permissive reset. These gates do not use RPM. None of these
unlogged states is established as the loaded-cut cause.

### Computed histories and final overrides

`2AD6C` filters the mapped driver angle and applies a pedal-dependent cap.
`2AC16` then forms idle `C3F8 + driver C2C8`. Its computed history is
**51 floats, `C300..C3C8`**: 50 prior values are shifted, then the new first
entry is written. The selectable index is clamped to 0–50. Neighboring
byte `C3CC` and driver float `C3D0` are outside the array.

The connected final fixture retains these native stages in task order:
`2F684 -> 2F8C0 -> 2F914 -> 2EFB8 -> 2F03C -> 2F390 -> 2F500 ->
2F5E2 -> 2F968 -> 2AAAC`. Ignition-on and running-RPM conditions clear
deliberately stale shutdown/stop overrides before the final selection.
`2F500` shifts its separate six-float history `C620..C634`; this does not
overwrite following status byte `C638`.

Final `2AAAC` selects, in priority order, shutdown `C63C + learned 80F0`,
stopped override `C610`, fault request `C2D4 + 80F0` when `D274/40`, or
normal `C2B8 + 80F0`, then clamps to 0 and learned bound `80D8`. The
fault positive control still lowers the request; clearing it recovers the
normal result. Releasing the driver retains the supplied idle contribution.
Idle production, other learned bounds, raw digital/receive-state production
and physical actuator behavior remain distinct closure work. Tracking-monitor
production and retention are traced below. The tests do not replace these
boundaries with claims about the log.

### Tracking enable, position axes, latches and cut selection

**Correction to the earlier address audit:** descriptors `5EFE8/5EFDC`
are indexed by throttle position after subtracting learned `80F0`, not by
RPM. `654A6` produces `D284 = ABD4 - 80F0` (measured) and
`D288 = C2B4 - 80F0` (requested). `654F0` uses `D288` for tolerance
and `D284` for the excessive-opening delay, while comparing the absolute
difference between `C2B4` and `ABD4`.

| Native lookup | Axis and result |
|---|---|
| `209C`, descriptor `5EFE8` | Requested-position axis `75710`: 6.15, 9.65, 14.65, 26.65. Four u16 values at `75720`, scale `125/65536`, give about 3, 5, 12, 25 degrees of tolerance. Clamps outside the axis. |
| `2118`, descriptor `5EFDC` | Measured-position axis `756F8`: 5.5, 9, 13, 22. Four raw u16 values at `75708`: 125, 50, 38, 31 calls. Interpolation returns an integer into `D292`. |

Periodic task `10A28` calls `66244` immediately before `65424`, which
runs `65432 -> 654A6 -> 654F0`. `66244` publishes shared readiness
`D298/01` only when ignition `B51E/10`, readiness `C650/80` and local
voltage `ABB4 >= 6.0` qualify. Its other bits are distinct: `/02` retains
voltage qualification until a second low-voltage call; `/04` requires
ignition and received `C6F7/02`; `/08` retains that qualification after
ignition drops until the received bit clears. They must not be interpreted
as a single Boolean enable.

`65432` requires `D298/01`, received voltage `C6DC >= 6.0`, no existing
`8150/01`, stopped override `C618/01` clear and `D364/80` clear.
It also executes native prerequisite query `4711E(84) -> 56E64 -> 56F0C`.
With installed `75E02 = 0`, that query walks **19 callback pointers at
`579B0`**, including the terminal `5742C`; any tested local/received fault
returns zero. The resulting `D290 == 1` is required for `D280/01`.
The tests run this list, rather than imposing the monitor-enable bit.

With absolute tracking error at or above tolerance, the running branch
uses separate counters. Excess measured opening increments `D278` to the
angle-dependent `D292`; request shortfall increments `D27A` to the fixed
**125 calls** at `74DA6`. Changing error sign clears the opposite counter.
The local RPM hysteresis `D294` sets at **500 RPM**, clears below **300**,
and holds between. Its low-RPM branch uses `D27C` and **2,500 calls**
(`74DA8`). A good comparison clears the error counters and qualifies
`D280/04` after **250 calls** through `D27E` (`74DAA`). These are native
invocation counts, not measured milliseconds.

An acquired fault writes `8150 = (8150 & FC) | 01`. Subsequent enable
evaluation stops monitoring and zeros the counters, but **does not clear
that fault**. `653F8` resets the low pair to `02`; `653D4` does so only
when `312CA -> 4244` extracts the low bit of the top two bits of `825C`,
equivalent to `825C/40`. Reset preserves unrelated upper bits. The flag's
upstream packed-state transitions remain separate from physical ignition.

The connected native test sends that latch through `64874`, producing
`D271=02, D272=C0, D273=27` with other faults clear. Before cut selection,
`14CC6` computes **`B2C4 = max(ABD4 - 80F0 - 80A8, 0)`** and `14CE6`
selects `B2C8`, including its separate fault substitution. `253A8` then
chooses its response: the excessive-opening fixture with 40-degree measured
angle requests `B744=003F` at 2,800 RPM. The shortfall fixture with zero
measured angle instead requires the 3,000-RPM latch and holds it to 2,500.
This is why reducing the entire fault to `D273/02` misses dependencies.
Neither fixture establishes that tracking failed in the vehicle.

The second measured-angle offset `80A8` is a protected float record, not
patch scratch. `15238` initializes it to zero through `49530`; `152D4`
validates retained records through `4963A`. Under its timer/state gates,
`157D8` clamps `B344` and `B2C0`, subtracts them, then limits `80A8` to
**approximately -0.428..+0.428 degrees** (`73898/7389C`). The writer also
updates protected `8080/8088/80A0`, marks its acquisition state and holds
afterward. Native tests cover the 7/8-call gate, both offset bounds, an
interior value and repair of one damaged checksum copy. Production of the
learning samples and other learned offsets remains open.

Stored reporting is a separate path: `65724` requests record 121 (`P0638`,
enabled descriptor `5C764`) for `8150/01`, `C6F7/10` or `C6F8/01`.
Clear reporting requires all of `D280/04`, `C6F7/20` and `C6F8/40`.
`65F6A` also latches this local event into bit 80 of protected `8154`.
The raw fault selector does not wait for DTC storage. Full report-mode,
retention and transport behavior is not simulated by this tracking test.

All [nine tracking/learning test groups](../../tests/test_throttle_tracking_process_flow.py)
pass on main, v2 and exact captured v2. Native helpers, the selected measured
angle and fault aggregation execute with explicit write extents and ABI
checks. The monitor and its calibration are stock-identical; the changed
DBW request maps are upstream inputs, so stock identity alone does not close
the dependency. Actuator dynamics, unlogged states and task timing remain
outside these fixtures.

## Fuel-learning region, acquisition and open-loop application

The previous [fuel-learning explanation](AF_LEARNING_WOT_ISOLATION.md)
incorrectly claimed that v2's 500 g/s boundary prevented learned trim in
boost. Native `216EA` selects `BCD3` from **SD airflow `B420`**, while
its separate `BCFE` output only permits new learning at 2–52 g/s, upper
bound exclusive. At 100 g/s, v2 selects C and clears learning permission;
stock/main select D. Open-loop mode does not substitute a different region.

Slow-task dispatch at `11526` calls pair publisher `20B28`, whose order is
`216EA -> 20D80 -> 20D0E` (both banks) `-> 20F9C -> 20E5E` (both)
`-> 21024` (both) `-> 213CE -> 21350` (both), then summary/timer updates.
Bank descriptors `4B2EC/4B314` select four protected 8-byte records each at
`81C0..81DF` and `81E0..81FF`; these computed extents do not intersect
patch scratch. `21024` updates the selected record through `49530`.
Ghidra splits its entry/prologue at `21024` from a fall-through body at
`2104E`; both fragments have been annotated. The tested native entry is
`21024`, not the incomplete body fragment.

`20F9C` also requires **80 <= ECT < 94 C**, a small load-change input,
clear fault qualification and other counters. Losing eligibility clears
bank acquisition flags/counters. It does not delete a learned record.
`21350` applies the selected record through `BCB8/BCBC`, using coefficient
`76164 ~= .006` while the difference exceeds `76160 ~= .01`, then the
dynamic bounds `BCC0/BCC4`. The next fuel task's `1DD04` includes those
corrections even after `7EB20` has revoked closed-loop permission.

[Five native test groups](../../tests/test_fuel_learning_process_flow.py)
cover all three images, including the entire pair publisher and its helpers.
A supplied valid C trim of +12.5% changes the controlled v2 OL bank pulses
by +12.5% at 100 g/s; main selects the zero D record. A second test acquires
signed 0.1% steps through the native learning routine from zero records,
then retains/applies them after the airflow/OL transition. Crossing 500
selects D and filters the result; an already nonzero D record remains
nonzero. Readiness counters, feedback inputs and retained initial conditions
are explicit boundaries; no test attributes those values to the car.

The actual sustained bog's ECT of 66–67 C excludes new learning through
this gate during that window. Earlier stored corrections are not logged.
`B7DC` is an additive factor and excludes these bank corrections; its
reciprocal is not the complete commanded AFR. Existing pulse-residual
analysis also is not an independent measurement of trim or latency.
The documentation and source comment are corrected, with no changed
calibration or generated image. A causal cut fix is still unproven.

## Final timing feeds back into idle and monitoring

The [ten timing-feedback groups](../../tests/test_timing_feedback_process_flow.py)
follow another consumer of all six final angles: `28C38`, which maintains
retard `C1BC`. Its dynamic maximum is the native RPM result `C1B4` times
temperature factor `C1B8` times 0.01. Any cylinder angle at or below **-20**
sets the minimum-angle flag `C1C6/08`, preventing further growth in the
qualified branch. Tests cover all six slots, native reset/completion/rearm,
repeated updates and the actual final timing publication.

`279CC` subtracts `C1BC` once per cylinder. The saved main's default-OFF
wrapper and v2's direct call produce the same result in these fixtures;
calling them repeatedly does not compound the subtraction. At speed **44**
and 2,500–3,500 RPM, supplied positive `C1BC` decreases to zero across the
tested held-temperature values. The moving branch begins at speed **3** and
normally removes 0.5 degrees per call; earlier zero/hold gates remain native.
This path cannot explain a newly growing retard in those fixtures. Its
separate completion-latch hold at 6,000 RPM is outside the logged event range.

The temperature input here is **`B3B0`, not live `B3AC`**. Native `16B04`
captures `B3B0` on a rising `B51C/08` against history `B3B4`; ordinary calls
can update live coolant while leaving that sample unchanged. The connected
test raises live coolant from 50 to 90 C while the held value remains 50 C
until another capture edge. Fault `D26C/40` substitutes 70 C. Separate native
initialization also seeds this channel. The logged live coolant cannot be
substituted for this unlogged held value when explaining a particular call.

The idle-air consumer is a real dependency, with native order established
through MCP and tested from ROM instructions:

`2E8CC -> C5B8 -> 2B570 -> C2E8 -> 2B432 -> C408 -> 2B408 -> C3F8`

`2E8CC` uses retard table `60658` and held-temperature table `6066C`, plus
native multipliers, to publish target `C5BC`. Applied compensation `C5B8`
rises immediately and falls using alpha **0.5** or **0.9375**, selected by
`B6B8/80`. The three later calls are consecutive pointers at
`110EC/110F0/110F4`; the compensation call is earlier at `110A0`.

All audited images select `7952A=0`. In this mode, `2B570` includes `C5B8`
in base `C2E8`, and `2B432` uses that base. Its alternative mode would include
`C5B8` directly. Looking only at either routine would incorrectly suggest a
missing or duplicate term; the connected native path includes it **once**.
`2B408` maps the resulting air request through `6075C`, applies `C2F0` and
clamps it into idle throttle request `C3F8`. Continuing through the existing
native driver and final-throttle sequence shows the positive compensation
increases the request at both zero and 70% pedal. It does not suppress the
supplied driver request. Physical throttle tracking and intervening task
timing remain separate boundaries.

The other idle-timing consumer `28A82` clears its correction `C1A8` at
**2,000 RPM and above**, before reading `C1BC`. Below that gate it can select
between `5FCA4/5FCB8`, with further speed, coolant, target and digital-state
qualification. The loaded-RPM tests cover its unconditional clear. The idle
integral bounds in `2D1FC` also consume `C5B8`; the connected eligibility,
pressure-output and history checks below extend that dependency.

Monitor gain selector `6BB30` also reads `C1BC/C1C8`, then publishes
`D40C/D410/D414` for `6BBA2`. All six alternative descriptors use the same
16-point axis, format and **byte-identical gain data** in every audited image.
The timing-based selection is therefore numerically inert for these images.
Native tests follow both monitor mode branches through threshold publication
and preserve injector/spark-inhibit canaries. Later computed monitor consumers
are not replaced by that check or attributed to the actual cut.

### Idle feedback bounds and update-cycle release

The [four connected idle groups](../../tests/test_idle_feedback_process_flow.py)
extend the older [idle-air](../../tests/test_idle_air_execution.py) and
[handover](../../tests/test_idle_air_handover_execution.py) checks. Native
lookup helpers now execute as well, using all three pinned images and the
timing-air compensation producer. The actual periodic instruction/pointer
pairs establish this order:

`2C760 -> 2CE50 -> 2CF9C -> 2D0AC -> 2E8CC -> 2B570 -> 2B432 -> 2B408`.

These are connected calls with explicit intervening inputs, not a replay of
every routine in the complete periodic task. The pressure controller uses
`C4D6` as an **eight-call divider**, rather than an engine mode. Its output
update also requires `C4D9/08`. Outside that joint gate, `2D0AC` retains
`C45C`, filtered history `C4AC` and preliminary request `C4EC`.

`2D1FC` subtracts prior base `C2E8` and the listed air-compensation terms,
including `C5B8`, from lower/upper totals `C2E0/C2E4`. It publishes the
available bounds at `C4F0/C4F4` and limits `C45C`. In the explicit base-3,
upper-8 fixture, a request of 10 is limited to 5; after the native
0.362019 timing compensation has entered both the base and its separate
bound term, that limit is 4.275962. These are **headroom bounds**, separate
from the final request's sum. The instruction order matters: this controller
runs before the current cycle's timing compensation and base-air updates.

The actual `18B14` pedal qualifier feeds `2C760`. Starting with either
positive or negative old idle feedback, all eight divider positions at
2,500, 2,800, 3,250 and 3,500 RPM clear feedback and its filtered history
within eight supplied calls after 70% pedal. The connected final throttle
request stays above 40 in these controlled cases. A separate underspeed
fixture qualifies feedback after 40 release calls, develops positive air
correction through the native pressure path, and clears it again on pedal
opening. This excludes an indefinitely retained idle correction under the
tested normal inputs; it does not measure those calls' elapsed time or
reconstruct unlogged digital, pressure or actuator state.

## Knock feedback and learning handoff

The [nine feedback groups](../../tests/test_knock_feedback_process_flow.py)
execute the ordered native prefix at `11DA8..11DB4`:
`3E7DC -> 3E45C -> 3E760 -> 3E20E`. These are the actual native instructions
and table helpers from main, v2 and captured v2, with sampled inputs explicit.

`3E7DC` filters load `B438` into `CD18` using **0.0312** at `77FB8` and
publishes residual `CD1C=B438-CD18`. This is a separate knock-control history;
the airflow filter remains **0.06**. A controlled step from 2 to 1 or 3 g/rev
temporarily selects feedback correction, then releases after 73 native calls
when the residual enters `[-0.1,0.1)`. No knock event means no new retard in
these fixtures. Call counts do not establish elapsed vehicle time.

`3E45C` publishes learning inhibit `CD22/02`, with transition qualification
`/04`; `3E760` detects its rising edge in `/08` and keeps prior state in
`CD2D/10`. The gate checks coolant **70 C**, load stability, other transient
corrections, rough/fine range flags, AVCS eligibility, MAF/RPM/AVLS fault
queries, activity and lift histories. Thus the captured bog's 66–67 C lies
on the feedback side of this unchanged temperature gate. This does **not**
mean knock feedback is disabled below 70 C.

Final angle selection is explicit for all six `C0EC+4*n` slots using cylinder
`B52A=1..6`; invalid selectors use zero. Its `-20` degree comparison is gated
by a low-RPM hysteresis flag, set below 1,300 and cleared at/above 1,400 RPM.
Changing this angle does not affect the tested 2,800-RPM permission result.
These reads do not create a path into retired rotational-idle code.

When feedback is selected, `3E20E` sets `CD22/01` and publishes correction
`CD14`. A supplied knock event `B460/80` subtracts **1.05 degrees**, bounded
at **-7 degrees**. Native clean-event timer `3E80A` saturates at 65,535;
125 clean calls allow **+0.35 degrees** toward zero. Knock-sensor fault query
`650BA=2` instead selects the separate **-5 degree** calibration. Tests use
explicit faults/events; they do not assert that the logged car had them.
With stable loaded inputs and no knock event, neither the warm learning path
nor the cooler feedback path generates retard or writes the retained grid/IAM.

Returning to learned correction copies the old `CD14` into `CD00` through
`3E096`, then clears `CD14`. Fine-entry worker `3DC02` carries that value into
`CCFC`. Native `3DB90` runs before the entry handoff, so `CCF8` sees the carried
offset on its next publication. The test follows this one-publication delay;
it does not change the native order or claim atomic publication across tasks.

Separate periodic calls at `10DE4/10DE8/10DEC` maintain activity, clean-event
and transition timers. `3E83C` resets `CD28` on `CD86` changes `1 <-> 3`, then
requires **more than 125** stable calls before learning is allowed again.
`CD26` has the same delay for nondefault `CD2A` activity. Startup `3E1B0`
initializes both timers to 65,535, copies lift history and zeros `CD2A`.
The identified native writers only initialize/clear `CD2A`; its nonzero
test control is not presented as a reachable vehicle event. The fall-through
initializer at `3E1C8` resets load history and feedback only when `B52C/80`
requests it. Ghidra splits those two fragments; native execution begins at
the actual startup pointer's `3E1B0` entry.

This trace also corrects an outdated image distinction. **All three audited
images** bypass the airflow task's local MAF-fault pointer `173FC -> 27088`.
The shared `65168` getter remains native, and knock permission still reads
its `D26F/40` result. The address index and live Ghidra comment now distinguish
that local bypass from a global fault override. No production bytes or
calibration were changed by this follow-up.

### Knock-event source, neighboring RAM and hardware windows

The [nine native knock-event groups](../../tests/test_knock_event_process_flow.py)
extend the former explicit `B460/80` input back through its actual producer:
`AA50 -> AD94 -> 17914 -> B460/80 -> 17960 -> feedback/learning`.
`17914`, fast-task pointer `11D24`, publishes the event only when runtime
`B688 >= 250` and `AD94` equals **1**, preserving the other seven bits.
The separate `17942` worker at `10C88` clears it on `B52C/80`.
Connected samples produce zero or -1.05 degrees in native feedback without
inserting the event flag between those stages.

The two sampled channels are distinct from wideband **AN3 / AB06**:

| Producer | Native state and consumer |
|---|---|
| Normal ADC scan, AN30 | `AB3C -> A9A8 -> AE2E`. Only at `500 <= AC00 RPM < 2000`, a separate **0.003906** filter updates float reference `AE28` and its truncated u16 `AE2C`. At the loaded 2,800–3,500 RPM range, this reference holds. |
| Window completion, AN24 | `5CD8 -> A7EA -> 740C` performs a one-off ADC-module-2 conversion into u16 `AD98`. An active-window close can also call `A7EA`. The existing ADC handoff tests cover restoration of prior module-2 state; the connected callback preserves AN3 hardware/RAM values. |
| `AA50` calculation | `max(0, (AE2C - AD98) * 5/65536)` becomes `AE24`. Float table `60968` and the selected gain code produce nonnegative `ADA0`; adaptive histories produce threshold `AE04`, clamped **32..276**. `AD94` is set when strength is at least threshold. |

`A9A8` also derives window lead/width `AE32/AE30` and threshold multiplier
`AE08` from RPM. Its alternate gain-bank threshold is **12,799.8047 RPM**,
not an ordinary 3,000 RPM transition. The neighboring changed MAP diagnostic
threshold at `7B286` is outside these knock calibration fields. The knock
instructions, gain tables and reference-filter coefficient match stock in
all three images.

The cylinder-dependent arrays are close to the patch's WB allocation, so
their index producer matters. `A8F0` searches six phase entries at
`FB7A..FB7F` and `FB80..FB85`. A start match publishes `AE3B=0..5` and arms
the window. `AEEC` later copies that bounded index into `AE3C` after its
first-completion latch is set. The next cylinder wraps at six. The caller skips `AA50` for
the startup/reset sentinel `AE3C=FF`; unmatched phase bytes do not enter it.
All 256 phase-byte classifications, three six-cylinder laps and all six
array selections preserve the current WB and lean-state slots. This also
identifies the formerly vague `A76C` initializer as **knock-sample history**.
It clears the event and selected histories on synchronization reset, but
retains six accumulated offsets at `ADBC..ADD3`; startup DMA initializes
those separately.

`ADD8` and `AEEC` send command byte `AB50 | AB51` through native SCI0
`7748 -> 77AA`. The tested transfer preserves unrelated GPIO bits while
using PHDR `F72C/C000` and PGDR `F764/0001`. Its polling completion is an
explicit hardware event in the fixture. Window scheduling uses **OCR2G
`F620`, GR2G `F610`, DCNT8O `F65C`**, and bit `4000` in TSR8/TIER8.
Native future, late and wrap cases preserve all other tested injector,
ignition and WB timer words, including WB OCR2H `F622` and down-counter
channels G/H/P. TSR8 uses the manual's read-then-write-zero clearing rule;
writing `BFFF` clears only the window's status bit. The timer/port identities
follow [Renesas sections 11, 15 and 21](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual).

These results close the identified software source and adjacent allocation
dependency. They do not reconstruct physical knock, SCI/ADC latency, phase
delivery or window duration in the captured vehicle. No new ROM change is
justified by this trace.

### Remaining native readers of the repurposed MAF input

MCP references identify `AB06` readers in the old `7C30` converter, the
`7C52` electrical-range classifier, special-condition worker `7266C`, and
raw logger converter `317A2`. Both `7C30` callers are bypassed. `7C52`
returns a range classification without RAM writes; its callers
`61332/613AC` are reached through `61328`, whose task pointer `11804` is
replaced by `66C2`. Both `7266C` callers are also bypassed. These call
replacements are present in main, v2 and captured v2.

The old converted value `ABE4` feeds `17726`, whose task call at `107F8`
is bypassed. The already-executed complete airflow task uses the patch's
synthetic `B448/B458/B45C` publications and snapshots their previous values.
The identified remaining active raw-input uses are the external-wideband
calculation and raw logging. This conclusion combines reader references
with the actual callers; it does not treat a literal search alone as proof
against arbitrary computed or corrupted accesses.

## Dormant and retired patches

The [six dormant-patch groups](../../tests/test_dormant_patch_process_flow.py)
execute native `279CC` rather than replacing its timing calculation with a
stub. Main's `11E30 -> 7DB90` wrapper runs that calculation first, then returns
without modifying angles because `7DB40=00`. V2 and captured v2 call `279CC`
directly and contain only erased bytes at `7DB40..7DCFF`.

An enabled control exists only in test memory. It applies the configured
nonpositive offsets to `C0EC..C100` after each fresh native publication, so
repeated calls do not accumulate retard. The tests cover inclusive gate
boundaries, invalid inputs/calibration, maximum retard, minimum angle and
positive offsets. The floor cannot advance timing above the native value.
These checks do not measure interrupt latency or complete the downstream
timing/knock consumers listed in the coverage register.

The retired boost entries at `7D810` and `7E560` each execute only `RTS/NOP`;
tests observe no RAM reads, writes or calls, and unchanged registers. Changing
the old `7D80C` switch cannot reactivate them. The neighboring active pressure
enable/threshold at `7D80D/7D8C0` are excluded from the retired reservation.

The [six fan groups](../../tests/test_fan_retired_process_flow.py) execute the
unchanged five-call parent sequence:

`11768 -> 3F878 -> 3F9E4 -> 3F650 -> 3FC0A -> 3FD38`

Here `11768..11778` are the consecutive dispatcher pointers, not one native
call chain. `3F878` publishes coolant class `CD7F=0..2`, speed class
`CD80=0..3` and hysteresis thresholds. `3F9E4` maintains the timed override
`CD76`. Normal mode arbitration `3F650` indexes `4C778` with
`9*CD80+CD7F`, adding three for `B51D/80` and another three when `CA10/80`
also applies. All **36** bounded pointers address individual native mode bytes
`7BCC8..7BCEB`. `CD77=max(CD75,CD76)` selects the final mode. Native temperature
transitions exercise off, 70%, full duty and hysteresis back to off.

`3FC0A` publishes duty `CD54` from the selected mode, coolant and IAT. Its
unchanged tail pointer `3FD8C -> E8C4` writes fan PWM `F590`, using cached
period `AB84`. Native reload `E8B4` reads `72808=8000` into `F588/AB84`.
The tests check the actual Q16 quantization and preserve adjacent channel and
relocated lean-state canaries. Mode 4 retains the preceding request; it does
not enter an old boost function. `3FD38` counts a qualifying `B51D/80` and
duty-at-least-30% condition in `CD74`.

Poisoning retired descriptors, gains and switch data in memory leaves all
tested native fan modes unchanged across coolant/IAT fixtures. A separate
literal classification finds one external match, `4FC30 -> 7D790`; this is
the **exclusive** native checksum end, not a data read or call into the
reservation. The full checksum execution and computed fan-table traversal
supplement that literal search. They do not establish behavior under arbitrary
corrupted program counters or physical fan operation.

The preceding routine `3F5F0` is the already-traced ignition-switch-off
spark-inhibit producer `CD50/80`, not fan control. Its live Ghidra name was
already corrected; the repository naming script and old guard labels now
agree, preventing a later script run from reinstating the stale name.

## Evidence and next closure work

Reproduce the inventory with `python3 -B tools/analysis/inventory_patch_dependencies.py`.
It writes this review's generated assignment register and JSON only. Run the
consolidated tests with `python3 -B tools/analysis/verify_process_flow.py`.
The [saved 355-group report](evidence/process_flow_tests_20260912.json) passes with
the three image hashes recorded. Groups count test methods, including three
cylinder-disable image runs; they are not a percentage of ROM coverage.
Ghidra comments and corrected producer names are updated through MCP and read
back. Raw captures accompany the register in `evidence/`.

Next closure work follows the remaining edges in the table, particularly
all other writers of patched RAM, computed arrays, scheduler/interrupt order,
and calibration aliases into fault, load, torque and actuator state. The
[corrected FPU note](DENSO_SCALING_AND_FPU_MATH.md) removes incorrect addresses
and unmeasured timing claims from the evidence used for that work.
