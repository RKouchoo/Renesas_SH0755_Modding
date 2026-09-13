# Logger for the persisting loaded cut

[Profile and use](../../logger/README.md#loaded-cut-trace) · [Last capture](AVCS_REPAIR_CAPTURE_20260913.md) · [Native protocol tests](../../tests/test_ssm_command_process_flow.py) · [Evidence](evidence/cut_trace_logger_20260913.json)

**Capture received:** the [14:36 vehicle review](CUT_TRACE_CAPTURE_20260913.md)
records repeated cuts with normal sampled spark/synchronization state and
zero missed-task counts. The preparation and validation below remain the
historical record; no further profile was created for that review.

The next capture reads the native spark gate and scheduler state that the
AVCS profile omitted. It uses the existing repaired v2 image. No ROM code,
calibration, RAM allocation or ECU state was changed to prepare this profile.
The eight prior profile selections and all existing parameter meanings remain
unchanged. Regenerated profiles add inactive entries to clear the new selection
when loading another profile.

Load the updated **complete** logger definition before
`D2WD610H_cut_trace_profile.xml`. The profile retains IAM, both knock
corrections, wideband, MAP, driver/engine context, injector/lean-cut state and
committed AVLS mode. Its 24 channels use exactly **43 requested byte addresses**,
a **136-byte request** and **49-byte continuous responses**.

| ID | Address and storage | Native meaning and interpretation |
|---|---|---|
| E530 | `FFFFC0DC`, u16 | Spark inhibit from `27090`; independent of injector word B744. Configured cylinder bits are duplicated across twelve logical slots; CD50/80 or CE28/01 forces FFFF. |
| E531 | `FFFFC0E1`, u8 | Ignition mode from `2716C` and timeout reset `27330`. Zero makes effective mask FFFF; one selects initial charge and two running mode. |
| E532 | `FFFFC290`, u16 | Auxiliary mask from `2A214/2A242`. Normal `0FC0` (decimal4032) suppresses secondary phase slots and does not mean all coils are cut. |
| E533 | `FFFFAC16`, u8 | Native synchronization state from `87F2/87CE`; stable synchronized operation uses1. This is not a physical sensor-health measurement. |
| E534 | `FFFFB52C`, u8 | Bit128 is the delayed runtime stopped/timeout publication from AC0C, cleared by engine-event `19F9C`. Bit32 requests secondary spark slots for current cam diagnostics; bit64 has a separate warmup meaning. |
| E535 | `FFFFB00C`, u8 | Missed task5 activations. `CF58 -> 3A28` failure calls `D156(5)`, increments `B007+5` and skips phase enqueue. |
| E536 | `FFFFB00D`, u8 | Missed task6 activations. `CF7E -> 3A28` failure calls `D156(6)` instead of enqueueing the mapped phase. Task6 contains the SD/cut path. |
| E537 | `FFFFAC0C`, u8 | Selected engine-signal timeout latch from `8AD6`, initialized by `8AC0` and cleared by qualifying input events. A new timeout resets engine-signal state and queues cancellation/reset work. |

`2A262` uses `C290 | (C0E1 != 0 ? C0DC : FFFF)` as its effective spark
mask. The u16 channels preserve native byte order. Multi-byte reads and
separate channels are not an atomic snapshot. Interpret the time sequence,
not an isolated row assembled across an update.

The two missed-activation counters are native computed writes. Their empty
direct Ghidra destination-xref lists do not make them unused RAM. MCP
disassembly of `D156`, `CF58` and `87F2` corroborates the previously executed
phase/capacity tests. The counters saturate at255, remain observable after an
event, and are cleared by startup RAM initialization. Reading them does not
reset them. An increase establishes a lost activation request, not its cause
or the physical result of that loss.

The original AVCSREPAIR1 log did not contain these channels. No values for
them can be recovered from that CSV. Native timeout/synchronization, ignition
and phase tests establish possible mechanisms; they do not establish that
those mechanisms occurred on the vehicle.

## Verification

The seven-group SSM suite passed in **18.035 seconds**, now exchanging all
nine generated profiles on main, repaired v2 and reconstructed captured v2.
The new selection uses independent nonzero sentinels for both bytes of each
mask and distinct adjacent loss-counter values. Both complete responses
return the expected bytes, preserve those source values and the protected
bank, and never reach the reset handlers. The protocol write guard remains
restricted to native transport workspace. This is offline instruction
execution with supplied receive/echo/completion events, not a live ECU test.

The fragment, complete definition, selected units, CSV-safe labels and request
budgets pass the existing logger verifiers. All prior parameter semantics and
all eight earlier selected channel sets were compared against the saved
pre-change files. No complete firmware rebuild or full audit-suite rerun was
needed; the cumulative test-group count remains355.

The updated complete definition SHA-256 is
`ee8b217571b0b2a65ba4d0ccf0aec7e16f3d8eddd077e4596434e17c5344bc9d`.
The earlier `855b0a...` definition remains the historical AVCS-profile revision.
Both ROM hashes remain those pinned in the [resume checkpoint](AUDIT_RESUME_20260913.md).

MCP accepted the updated `D156` counter/logger comment, and a subsequent
disassembly returned it. The comment is also in the reapplication script.
Raw queries, readback, test output and artifact hashes accompany this note.

The counters help expose missed work between samples, but all other states
can change between reads. If these sampled states remain normal, that alone
does not prove healthy physical spark/injection or exclude brief ECU
interruptions. The cut remains unresolved until an event is tied to a cause.
