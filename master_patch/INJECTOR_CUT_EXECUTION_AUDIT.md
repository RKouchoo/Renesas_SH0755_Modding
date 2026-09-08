# Added fuel cuts and the native injector inhibit word

2026-09-08. A further downstream trace found and repaired a real integration
defect after the primary-calculation tests passed. No ECU traffic, flashing,
or engine operation was performed.

This records the publication-repair stage. The subsequent
[scheduler repair](INJECTOR_SCHEDULER_EXECUTION_AUDIT.md) produces current
`48d63c...`, protecting the temporary clear during each update. Hash, checksum
and wrapper sizes below describe the preceding stage.

Publication-repair master SHA-256:
`aea793053fd3df4cab1efc3f15fbcee81024e6e90c0e8ba13025cb602b253b6b`.
Subaru checksum: `0x11787AA2`.

## Defect and reproduction

The added overboost and lean paths set `BF6C bit 0x80` after calling the stock
rev limiter `24B24`. Stock `24B24` first updates BF6C for its own RPM decision,
then tail-calls `1C5D4`, which builds the injector inhibit word at `B744`.
Consequently, an added cut could leave the scheduler's word stale when the
composed wrapper returned.

Executing actual `1C5D4`, including its six D94C status getters, reproduced
these results in the prior `5fff8b...` image at 1300 RPM:

| Scenario | Final BF6C cut flag | Final B744 |
|---|---:|---:|
| Normal vacuum, no other faults | Clear | `0000` |
| Hard overboost, MAP 1150 mmHg | Set | **`0000`** |
| Latched lean cut, MAP 820 mmHg | Set | **`0000`** |

The stock `23FC0` aggregator can set BF1C correctly while this inconsistency
persists. Another stock call to `1C5D4` could subsequently rebuild B744; this
audit does not assign a duration to that delay or claim the cut never occurs.
Relying on another producer was not a complete integration of the cut.

The earlier guard tests modeled the `1C5D4` tail and checked only flag and
aggregator behavior, so they could not catch this defect. Their boundary has
now been removed. This is not evidence that the defect caused the September 7
cold-idle lean-out: these added cuts require their respective pressure/state
conditions, which the idle logs do not establish.

## Downstream evidence and corrected identification

`1C5D4` publishes `FFFF` for a native global cut, otherwise six per-channel
fault bits. Its writer is `1C90A`; the destination literal is `1C91C = B744`.
`26DFC` reads that word. Its consumers include:

- Phase scheduler `263EE`: snapshots B744 into `C0B2`, calls `26AEC` when the
  inhibit state changes, and suppresses normal channel scheduling through the
  per-channel byte at structure offset `+1`.
- `26AEC`: updates inhibit transitions for six `0x28`-byte records beginning
  at `BFB8`, using masks at `4B64C` and native output cancellation handling.
- Channel output gate `268E8`: reads B744 through `26DFC`, tests the channel's
  mask, and returns before output handoffs when inhibited.
- Pulse logger `26F8C`: uses those same six records and publishes zero for a
  record with its inhibit byte set, otherwise its scheduled count times 0.25.

Thus the earlier generic “solenoid”/“cam bank” identification of this
crank-phase subsystem was misleading. The five relevant function names were
corrected in live Ghidra and in `ApplyMasterNames.java`; source comments and
canonical RAM/RE notes now identify the injector path. The later scheduler
suite covers queue/phase transitions; physical output remains unvalidated.

## Bounded repair

Both added-cut sites now set BF6C and then publish `0xFFFF` to B744, matching
the stock global-cut branch. They share `patch_boost.emit_added_fuel_cut`.
The hard-cut component is corrected on its own as well as in the integrated
master. On the next invocation, the retained limiter still rebuilds B744 from
native global/per-cylinder faults before the wrappers decide whether to add a
cut. No new persistent state or separate clear policy is introduced.

The builder pins the native all-cut constant, word writer and downstream
reader before any ROM mutation. If those contracts differ, it refuses rather
than applying the new direct word store to another layout.

| Region | New extent | Actual differing bytes from `5fff8b...` |
|---|---|---:|
| Hard-overboost wrapper | `7D8C4..7D90B`, 72 bytes, previously 64 | 37 |
| Composed lean wrapper | `7EC00..7EDF3`, 500 bytes, previously 488 | 128 |
| Subaru checksum | `7FB88..7FB8B` | 4 |
| Total | | **169** |

The wider byte difference includes relocated PC-relative literals and branch
displacements. No stock instructions, tuning values, hook addresses or
calibration addresses change in this repair. VE, injector calibration, timing,
AVLS, thresholds and delay counts are unchanged. B744 is existing stock RAM.
Contiguous free flash is now **3,332 bytes at `7EDF4..7FAF7`**; the hard-cut
growth fits before the unchanged architecture signature at `7D91C`.

## Execution tests and release limits

Six new groups in `test_injector_cut_execution.py` run within the master
verifier:

- 1,536 native per-channel fault-byte cases across six input fields, plus all
  six native global-cut inputs, execute `1C5D4` and its actual getters.
- All 64 six-channel masks are tested against all six channels through actual
  `26DFC` and `268E8` instructions: 384 gate cases.
- Both added cuts block all six output handoffs; releasing them restores a
  nonzero native per-cylinder fault mask instead of blindly clearing it.
- Independently replacing each new word store with NOP reproduces the old
  flag-set/word-zero mismatch and allows the channel handoff.
- Six deliberately damaged native contracts are refused before mutation.

The existing 216 composed cut/state/switch/RPM/pressure cases now assert B744
as well as BF6C and BF1C. All previous guard, retained-sensor and SD tests pass
with the corrected SH-2E arithmetic model. The earlier primary-fueling pass
also added eight target/transition/composer groups and five FPU groups.

```
python3 master_patch/verify_master_patch.py
python3 speed_density/test_hook_execution.py master_patch/D2WD610H_master_patch.bin
```

Both pass. The master verifier confirms a deterministic rebuild, valid checksum,
stock provenance, ownership and definitions. `90BA` remains a recorded device
boundary. The later scheduler suite removes the old `26958` substitute: that
tail simply sets activity byte C0B0. It also executes queued-state/phase handling;
interrupt timing and actual injector delivery remain unvalidated. These tests do not establish 100% flash/engine certainty,
validate the second-VE trial or clear the image for load/boost operation.
