# Wideband and fuel-guard execution audit

> Archived investigation, retained for evidence and historical reproduction.
> Use the [central reference](../../reference/README.md) and [audited corrections](../../reference/FINDINGS.md) for current conclusions.
> Build identities, commands and recommendations below describe their original stage.

The later [injector-cut audit](INJECTOR_CUT_EXECUTION_AUDIT.md) supersedes this
stage's image with `aea793...`, fixing a separate stale B744 inhibit word.
The subsequent [scheduler repair](INJECTOR_SCHEDULER_EXECUTION_AUDIT.md)
produces current `48d63c...`. The `5fff8b...` image and 488-byte layout below identify this earlier
fault-sentinel repair stage, not the latest build.

2026-09-08. Continued review after the retained-sensor repairs. No ECU traffic,
flash, or engine operation was performed. The user reports the ECU still has
the September 7 image; the exact saved readback remains unavailable.

## Result

Executing the generated guard instructions found a real validation gap:
with readiness above 35, a zero or negative logger lambda reset the lean
confirmation counter as though the mixture were rich. The old code rejected
NaN but did not require lambda to be positive. Zero is the wideband logger's
intentional invalid-input sentinel, not a usable mixture measurement.

The corrected guard requires `lambda > 0` before a sample may clear the
counter. NaN and negative infinity fail that comparison; positive infinity
fails the later rich-mixture comparison. Invalid samples count toward the
existing eight-sample trip after the existing pressure and transport gates.
This is not a new unconditional idle cut or a change to the AFR threshold.

The change moves the existing `fldi0 fr4` ahead of the lambda validation and
replaces its self-equality test with a positive comparison. The threshold
validation reuses the same zero. The wrapper remains 488 bytes at
`0x7EC00..0x7EDE7`, with unchanged literal addresses, branch destinations after
the edited sequence, RAM allocation, and 3,344 bytes of remaining free flash.

Fault-sentinel repair stage SHA-256:
`5fff8b3776af0b56b720c360e940b193f49893b35eb64e15b3578b203b97046c`.
Stored/calculated checksum: `0x75E22B4F`.

Exactly 17 bytes differ from `5a1b3e...`: 13 instruction bytes within
`0x7ECA4..0x7ECB1` and four checksum bytes at `0x7FB88..0x7FB8B`.
There are no calibration changes, including VE, injector, timing, after-start,
pump, lean threshold, or delay/confirmation counts. The unvalidated second-VE
trial remains in the master.

## Why a ready/zero pair matters

The external-wideband producer at `0x7E440`, reached through stock entry
`0xB690`, publishes several separate RAM words. On rejected ADC input, it
writes zero to logger B098 before clearing readiness AE70. A transition from a
valid sample therefore has an intermediate state containing ready=50 and
logger lambda=0. A reader can also take its readiness and lambda reads on
opposite sides of an update if scheduling permits that interleaving.

The new test executes the actual invalid producer and captures its RAM after
the zero logger store, while readiness is still 50. It supplies this captured
state to the actual guard chain in monitoring state with seven prior bad
samples. Old behavior is `(state=2, counter=0, cut=false)`; corrected behavior
is `(state=3, counter=0, cut=true)`. Negative and negative-infinite lambda are
additional adversarial cases, not values the normal ADC transfer publishes.

This establishes the intermediate data and the guard's response. It does not
establish real task preemption, the frequency of this observation, or that it
occurred in the September 7 log. The logged cold lean-out remains unresolved.

## Executed code and modeled boundaries

`test_wideband_fuel_guard_execution.py` decodes machine words independently of
the assembler/disassembler and existing Python policy models. It reads the
integrated BIN, follows actual entry hooks and task-pointer targets, and fails
on an unknown instruction or unexpected helper.

| Path | Coverage |
|---|---|
| B690 hook → 7E440 wideband producer | 2,121 unsigned ADC values across both signed halves, exact acceptance boundaries, all eight output words, valid/fault transitions, bad transfer constants |
| 64FD0 and 6500C inhibit hooks | Both follow the emitted helper; ready=50 returns 0, invalid/threshold/NaN readiness inhibits with 2 |
| 7EB20 pressure-OL wrapper | All 256 incoming state bytes across six pressure/baro scenarios, boundary floats, disabled states; only permission bit 0x80 may change |
| 7EBA0 initializer | Exactly two reclaimed four-byte words are cleared; neighboring words remain untouched |
| 7EC00 → 7D8C4 → 24B24 | Actual lean, hard-overboost and retained rev-limiter instructions execute together in 216 state/switch/RPM/pressure combinations |
| Lean state machine | Exact 50-call delay and eight-sample confirmation, rich resets, invalid samples, latch persistence, release/rearm, pressure/AFR boundary floats |
| Retained 24FC and 23FC0 | Actual comparison helper and fuel-cut aggregator, all ten other cut sources, preservation of unrelated flag bits |
| Retained 24BC6 and 1A256 | All 256 flag values: no cut-flag clearing when B52C bit 7 is clear; the stock stopped/cranking reset remains effective when set |
| Retained 22AC2, running path | Cannot re-enable the cleared CL-permission bit when B52C bit 7 is clear |

In this suite, stock primary-target update 22454 is a stand-in that writes its
resulting flag byte and poisons caller-saved registers. The subsequent
[primary-fueling execution audit](PRIMARY_FUEL_EXECUTION_AUDIT.md) executes
actual 22454, 22756 and final composer 1DD04 in a separate suite, and corrects
the shared interpreter to SH-2E round-to-zero arithmetic. The subsequent
injector-cut audit removes the 1C5D4 stand-in and verifies its actual word
publication and downstream channel gate. The
actual limiter, helper, aggregator and reset code/literal ranges are checked
against canonical stock. Tests check stack/PR, saved registers, and allowed
RAM writes. The cut-chain tests retain state between invocations.

Single-instruction negative controls recover the original zero-lambda defect,
lose an intended cut with an incorrect bit operation, and reject valid upper-half
ADC samples when unsigned conversion is removed. These detect behavioral errors
that presence/count checks alone would miss.

## Further stock interaction tracing

**Cut order and alternate flag writer.** The master periodic dispatcher calls
the composed wrapper at 11B18 through 11D3C. It subsequently calls the stock
aggregator at 11B4E through 11D60. BF6C bit 0x80 remains one of the aggregator's
inputs. The other mapped stock BF6C writer, 24BC6, clears it only when helper
1A256 reports B52C bit 7 set. It is called from diagnostic dispatch at 112A4.
Its normal-running path and reset path are now instruction-tested. This is a
static call-order trace, not an interrupt or worst-case latency measurement.

**CL permission writers.** 22756 updates bits 0x40/0x20 and reads permission
bit 0x80; 22948 updates bit 0x10. Their mapped writes do not restore bit 0x80.
22AAE sets it from the startup call at 1008A/1024C. 22AC2 can also restore it,
but only with B52C bit 7 set; its running path is covered above. Primary-target
22454 remains followed by the pressure guard at the patched 11D78 task slot.
No additional runtime permission rewrite was justified by this trace.

**Legacy voltage diagnostic state.** 17040's B404 readiness bits still feed
17210/1722C, then both the 217B8 voltage loop and 45350 diagnostic snapshot.
45350 snapshots raw voltages to CF10/CF14 and creates bank flags CF09/CF0A
through 453F2; their union CF08 can gate B91A at 1F3AC. Thus these states are
not categorically irrelevant to fuel-control eligibility.

However, setting those diagnostic bank flags through 453F2 requires
CEFC/CF00 >= `0x76374` (about 0.09). With the repaired B900/B904 offsets zero,
the current B8FC table at descriptor 5FB0C has finite interpolated values
bounded by -0.014007568359375 and +0.0019989013671875 (uint16 values at
779B0, scale 2^-16, offset -0.5). Its startup alternative 760FC is zero and
75E1A is disabled. The corresponding largest reciprocal correction is about
0.014207, below that diagnostic threshold. This bounds this *new-setting*
path under normal finite table output; it does not clear old latched flags,
prove initialization/interruption behavior, or cover corrupt state. No extra
diagnostic bypass was added.

**Stored voltage history.** 8200/8208 also feed initialization snapshots
BDD4/BDD8 via 220C8, the 22286 learning structures, reset/integrity routines
220E4/220FE and logging/export paths. Removing the direct BD04/BD08 target
contribution does not remove that subsystem. The earlier consumer fix remains
scoped; ordinary BCB8/BCBC learned fuel corrections remain separate.

## Verification and readiness

Run:

```
python3 tests/test_wideband_fuel_guard_execution.py master_patch/D2WD610H_master_patch.bin
python3 tests/verify_master_patch.py
python3 tests/test_hook_execution.py master_patch/D2WD610H_master_patch.bin
```

All 12 new execution test groups run inside the master verifier. This closes
the previously identified generated-wideband/guard execution-test gap. It does
not emulate hardware FP exception delivery, complete injector scheduling,
ADC/controller timing, ISR interleaving, or the whole ECU.

The remaining release work includes selecting a defensible VE baseline and
validating actual inputs/controller fault output and post-turbo feedback
dynamics. This audit does not clear the image for driving or boost testing,
and does not establish a cure for the September 7 lean-out. See
[COMMISSIONING.md](../../../master_patch/COMMISSIONING.md) and
[RETAINED_ROUTINE_AUDIT.md](RETAINED_ROUTINE_AUDIT.md).
