# Injector scheduler, queued pulses and cut-update locking

2026-09-08. This pass found and repaired a second cut-integration defect after
the earlier B744 publication fix. No ECU connection, flash or engine operation
was performed. Calibration bytes are unchanged.
The subsequent IRQ/context follow-up below executes native dispatch and return
paths on this same image; it requires no further ROM changes.

Current master SHA-256:
`48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0`.
Subaru checksum: `0x1923EC61`.

## Defect: a continuing added cut briefly looked released

The prior `aea793...` image published B744 correctly before returning, but
retained `24B24 -> 1C5D4` first rebuilt it for the stock RPM/fault decision.
During a continuing added cut, BF6C and B744 could temporarily become zero
before the wrapper reasserted them. Checking only the return state missed this.

The native task trace makes this a scheduling concern:

- Task 5 descriptor `49EC` has priority **4**, entry `6938`. Its call at
  `6962 -> 11958`, then `119B8 -> 263EE`, reaches the injector scheduler.
- Task 6 descriptor `49FC` has priority **2**, entry `696C`. It calls `11AD0`,
  whose `11B18` slot contains the composed cut wrapper.
- `CF58` activates task 5; `CF7E` activates task 6 through `3A28`.
  `3BCA..3BD8` treats a larger priority as higher. `3A6C..3A9A` permits a
  dispatch when the saved interrupt mask and kernel dispatch restrictions
  allow it. Both task descriptors have their non-dispatchable byte clear.

Instruction-produced publication states at 1300 RPM were:

| Continuing cut | Prior image: intermediate B744 / IMASK | Corrected: intermediate B744 / IMASK | Final B744 |
|---|---|---|---|
| Standalone hard overboost, MAP 1150 mmHg | `0000 / 0` | `0000 / 1` | `FFFF` |
| Composed latched lean cut, MAP 820 mmHg | `0000 / 0` | `0000 / 1` | `FFFF` |

Replaying the exposed zero word into actual `263EE/26AEC` instructions, with
a previously inhibited record inside its native release window, releases the
record and reaches the native enqueue callback for all six channels. This is
a state-replay reproduction plus a static priority trace. The later IRQ tests
below also reproduce it with explicitly injected interrupts and native task
dispatch. Neither establishes the actual IRQ arrival time or that this defect
caused the September 7 cold-idle event.

## Repair: retain the native lock through the complete decision

Both wrappers now use the existing `3AF4` / `3B08` critical-section pair.
`3AF4(0x10)` raises IMASK to at least 1 and returns the incoming mask. It never
lowers a higher incoming mask. `3B08` restores that mask and reaches the native
pending-task dispatcher when unlocking to zero. The stock injector enqueue
routine `900A` uses this same pair.

The outer lean wrapper protects the entire nested stock/overboost/lean update,
including disabled, disarm, invalid-input and release exits. The standalone
overboost wrapper also protects its own update. Its nested unlock restores
IMASK 1, leaving the outer update protected. Hardware interrupts above the
mask remain enabled; their timing and peripheral events are not simulated.

The incoming mask is saved in the existing prior-call delay slot. A common
tail restores it and the original caller PR before entering `3B08`. Each
wrapper adds one four-byte stack slot, so the composed path adds eight bytes
relative to `aea793...`. No static RAM or new native code hook is needed.
The builder checks the exact `3AF4..3B27` native contract before any mutation.

| Region | Corrected extent | Actual differing bytes from `aea793...` |
|---|---|---:|
| Hard-overboost wrapper | `7D8C4..7D91B`, 88 bytes, previously 72 | 75 |
| Composed lean wrapper | `7EC00..7EDFF`, 512 bytes, previously 500 | 464 |
| Subaru checksum | `7FB88..7FB8B` | 4 |
| Total | | **543** |

The many differing bytes reflect moved branches and literal pools. Every
difference is inside those three regions. The hard-cut wrapper ends immediately
before the unchanged architecture signature at `7D91C`. Free contiguous flash
is **3,320 bytes at `7EE00..7FAF7`**. Stock instructions, calibration values,
hook addresses, VE, injector settings, timing, AVLS and delay counts are unchanged.

## Native queued-pulse behavior

Actual `26AEC` distinguishes cancellation from waiting for a native phase
boundary. Each of six records at BFB8 has an inhibit byte at `+1`, stage at
`+2`, and a subrecord at `+0x10`. Its hardware channel has a software-pending
byte at `AC80 + channel*24 + 0x13`.

| Record state when cut changes | Native transition |
|---|---|
| Stage 0 | Set inhibit byte |
| Stage 1, cancellable substate | Call `920C`, return record to stage 0, set inhibit |
| Stage 1, substate 1 with software-pending byte zero | Defer the transition for the pulse already handed to the timer |
| Stage 1, substate 2, or stage 2 | Defer to the native phase boundary |

For substate 1, nonzero software-pending values are cancellable. `920C` clears
that pending byte without timer-register writes. Its other branches modify
the native timer registers; the tests execute those writes against inert
register fixtures, without claiming their physical effects.

`263EE` caches the new word even when some record transitions are deferred.
At each record's cycle boundary it resets the substate/stage and copies the
cached inhibit bit. Actual `26990` returns **720 degrees on equality**, not
zero, which makes the boundary test work. Tests follow the records through
the cycle, resynchronization and startup mode changes. Releasing a cut obeys
the native phase windows and retains unrelated cylinder-fault bits.

The pulse logger `26F8C` reads each record's inhibit byte, not B744. Consequently
some nonzero logged pulse widths can remain after the global word is FFFF for
already handed-off pulses. They disappear when the record reaches its native
boundary in the tested sequence. This does not measure actual injector on-time.
`26958`, previously treated as a hardware boundary by the channel-gate test,
is now executed: it simply writes the activity byte `C0B0 = 1`.

## Execution coverage and boundaries

Twelve new groups in `test_injector_scheduler_execution.py` run in the master
verifier:

- 1,728 cut-transition fixtures, covering 10,368 record decisions across all
  64 channel masks, three stages, three substates and three pending values.
- Both added cuts through repeated crank-phase cycles and release to native
  fault mask `0x12`; six already-queued scenarios through the next boundary.
- Both native release modes/windows, phase equality/wrap, 60 startup/resync/
  mode-change fixtures and their following 24 phase updates.
- 72 native cancellation/register fixtures and all 64 logger inhibit masks.
- 768 wrapper/mask/pressure/state/enable fixtures: all 16 incoming IMASK
  values restored, no unmasked intermediate publication, and only the outer
  unlock reaches the pending-task dispatcher when entering with IMASK zero.
- Independently removing the outer lean lock or standalone overboost lock
  exposes the temporary release while the final return value remains correct.
  Three removed native gates/cache stores also expose output. Eight damaged
  scheduler-lock contracts are refused before mutation.

The native scheduler, resynchronizer, mode/transition callbacks, phase helpers,
parameter conversion, cancellation routine, interrupt-mask helpers and logger
execute their ROM instructions. Device enqueue/update calls `900A/8F84/90F8`
are recorded boundaries. `21CC` fixed-point division and `4280` integer division
are mathematical boundaries on bounded positive inputs; upstream cranking
angle/pulse producers `1C958/26250/1D450` are fixture inputs. `3F84` is a recorded
ABI boundary in this original suite. The separate follow-up below replaces
that boundary with native execution. Timer registers do not advance on their own.

## IRQ/context follow-up: native return paths pass

The kernel explicitly respects the interrupted task's saved mask. IRQ exit
`3454` loads the saved SR at `3482`, extracts IMASK at `3486`, combines it with
the remaining nesting/dispatch restrictions, and branches at `3492` to the
ordinary `RTE` path when any restriction remains. Raising IMASK to 1 therefore
allows higher-level IRQ bodies to run and queue task 5 while preventing those
IRQs from dispatching it during the protected cut update. This conclusion now
has instruction-execution coverage, rather than relying only on the activation
path or final publication state.

`test_cut_interrupt_execution.py` uses the unchanged task-5/task-6 descriptors,
priority queues and native kernel instructions:

| Path | Executed ROM code |
|---|---|
| IRQ entry and exit | `33F4` vector wrapper, `340C` entry, `3454` exit |
| Request task 5 | `3A28` activation, `3B8E` ready-queue insertion |
| Unlock to a pending task | `3B08 -> 3F84 -> 3DC8` synchronous context save |
| Preempt an unmasked task at IRQ exit | `34C8` full context save |
| Select/start/resume task | `3930`, `3A1C` new-task bootstrap, `3998/399C` restores |
| Finish task 5 and resume task 6 | `3F2C`, `3BFC` dequeue, `3E54` priority selection |
| Injector task payload | Actual `263EE`, with the scheduler/device boundaries above |

Eight groups, comprising 82 fixtures including negative controls, run in the
full master verifier:

- Thirty IRQ-return fixtures cover incoming IMASK 0 through 14, with and
  without a newly pending task. Every GPR, FR, PR, SP, PC, SR/T, FPUL, FPSCR,
  MACH, MACL and GBR is compared after returning to the interrupted context.
- Nested level-3 IRQs inside a level-2 IRQ queue both activations without
  dispatching at the nested return. An unmasked outer return runs both; an
  outer return to IMASK 1 keeps them pending.
- Both continuing cuts are interrupted immediately after the stock B744
  clear. Task 5 runs only after the complete outer unlock and sees
  `B744=FFFF / BF6C=80`; no injector enqueue is requested.
- Thirty-two additional fixtures inject a single or nested IRQ at wrapper
  entry, lock/callee boundaries, flag and word stores, and native unlock/
  dispatcher entry. Both wrappers preserve the continuing cut and caller ABI.
- Eight fixtures enter the wrappers with IMASK 1, 2, 7 or 14. The pending task
  remains queued when the wrapper restores that mask, then runs correctly
  when the caller later unlocks to zero.
- Independently removing either wrapper's lock reproduces the temporary
  release through native task dispatch, reaching all six enqueue boundaries.
  Removing the saved-mask extraction at `3486` produces the same release
  despite both wrapper locks remaining present. All four defective fixtures
  still end with B744=FFFF, showing why final-state-only checking was inadequate.
- Four deliberately misdirected FPUL, FR15 or R14 restores are detected as
  corrupted contexts. These are test-only copies, never flash artifacts.

The test model seeds bounded stack RAM with nonzero old values: native `3DCC`
reserves an unwritten R0 slot for synchronous context saves, and `39E6` reloads
it into that caller-scratch register. Native context calls can resume via `RTE`
with a different PR, so they execute directly rather than through a simulated
ordinary subroutine return. Nested IRQ completion is identified by its actual
returned frame, not merely by revisiting the handler address.

Exception arbitration/initial PC+SR frame creation and the IRQ body are
scripted. The body requests task 5 through actual `3A28`; it is not the full
physical crank/timer ISR at `60F4`. Task 5 executes the injector scheduler and
then a scripted register-clobbering payload before native completion, not its
entire engine task. Debug callback `37A0` is an ABI stand-in. The modeled
`RTE` restores the frame after the actual NOP delay slot. This is deterministic
interleaving coverage, not a cycle-accurate ECU or timer simulation.

The full master verifier and SD execution checks pass, including deterministic
rebuild, byte ownership, native contracts, checksum, stock provenance, prior
guard/primary-fueling/retained-sensor tests and single-front-A/F isolation.
This closes the reproduced scheduling-state gap and validates the tested native
IRQ/context returns. It does not establish worst-case execution time, real stack
headroom, physical injector delivery, controller health, or the validity of the
second-VE trial. The IRQ follow-up changes only tests and documentation; master
SHA-256 and checksum above are unchanged. Controlled bench/idle commissioning
with an explicitly chosen calibration baseline is the next source of evidence;
these passes do not provide a 100% flash/engine sign-off.
