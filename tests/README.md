# Offline tests and verifiers

Run commands from the repository root. These tools operate on saved ROMs;
they do not connect to an ECU.

```sh
python3 -B tests/verify_master_patch.py
python3 -B master_patch_v2/verify_master_patch.py
```

The first command rebuilds the rolling master in memory, checks its saved
artifact, and runs the retained routine, hook, FPU, scheduler, calibration,
definition, logger and provenance checks. The v2 verifier checks checksum,
layout, definition, rotational-idle removal and five lean-cut hysteresis
execution tests, including the installed positive reset threshold. These
cover latch/release boundaries, invalid hysteresis and preservation of the
stock rev and overboost cuts. Coverage is still narrower than the master suite.
Both verifiers also execute five AVLS oil-gate test groups: stationary versus
moving selection, the erroneous 110 C calibration as a negative control,
independent pedal/oil inputs, both threshold branches, cold/fault behavior and
RPM hysteresis. Upstream selector state and unlogged qualifiers are fixtures;
the tests do not model hydraulic lift or physical engine response.
V2 additionally includes the eight primary-fueling and thirteen injector-scheduler
test groups, plus seven native diagnostic-cut groups: no-fault behavior,
3000/2500 RPM hysteresis, fault release, two-frame received-fault qualification
and independence from the test-mode connector, plus the direct received
RPM/pedal pattern and combined faults that keep cutting below 2500 RPM.
Six native pump-demand groups now cover the paired injector/consumption
scalars, pulse conversion, former-MAF independence, discrete modes, pump-off
override and filter weighting. This makes ten top-level v2
verifier groups. Forced diagnostic inputs are fixtures, not vehicle findings.
The scheduler suite also executes the standard P21 getter, confirming it
retains latency alone after a sustained all-six cut has reached the records.
The separate ignition-permission suite runs seven groups on either image:
spark/injector mask separation, global spark inhibition, warm startup release,
ignition-switch shutdown, configured status qualification, effective mask
composition and stock dwell counts. These use imposed inputs and a modeled
dwell-table lookup; they do not measure vehicle spark or run the full coil
scheduler. This focused suite is not included in the ten v2 verifier groups.
The separate load-fallback script executes the actual status call/store and
retained conditioning body, including a negative control for the old failure.

For a focused check, run its script directly, for example:

```sh
python3 -B tests/test_map_boundary_execution.py
python3 -B tests/test_v2_load_fallback_execution.py
python3 -B tests/test_lean_cut_hysteresis_execution.py
python3 -B tests/test_avls_oil_gate_execution.py
python3 -B tests/test_native_fault_cut_execution.py
python3 -B tests/test_ignition_permission_execution.py
python3 -B tests/test_fuel_pump_demand_execution.py
python3 -B tests/test_ssm_receive_execution.py
python3 -B tests/test_hook_execution.py master_patch/D2WD610H_master_patch.bin
python3 -B tests/verify_romraider_toggles.py
```

`_test_paths.py` supplies the shared component, fixture and
[analysis-module](../tools/analysis/README.md) import paths. Default
ROM inputs still refer to their build/artifact directories. Tests for historical
standalone components may require their corresponding standalone ROM or an
explicit input filename; do not substitute a different build merely because
it shares the same factory CALID.

`master_patch/verify_master_patch.py` is retained as a compatibility entry point
for existing workflows and links from the unchanged K-line adapter documentation.
The adapter's own tests remain in its folder.

The September 12 [process-flow audit](../docs/reference/PATCH_PROCESS_FLOW.md)
has a separate consolidated runner:

```sh
python3 -B tools/analysis/verify_process_flow.py
```

Eight diagnostic-record groups extend queue delivery into protected fault
history and snapshot storage, including all enabled class-0 descriptors,
trip/shutdown gates, bounded source copies, retained records and reset,
misfire aggregate selection and the stock-disabled P0111 report/status mask.
The separate misfire source buffer remains an explicit fixture.
Nine knock-event groups execute the sample/reference calculation, all phase
byte classifications, six-cylinder histories, gain selection, SCI0 commands,
AN24 completion callback, timer isolation and event-to-feedback publication.
ADC/serial completion and phase timing are explicit hardware inputs.
Four idle-feedback groups connect native pressure/output limits, timing-air
compensation, all eight update phases and actual pedal qualification to the
final throttle request. Earlier mathematical-table fixtures remain separate.
Three cam-selector groups execute the actual periodic calibration refresh
and 24-phase capture/count sequence. Five timeout groups connect native
startup and poll to immediate state reset, shared-queue success/full behavior
and the actual injector-reset callback. Five synchronization groups execute
the loss/acquisition message, complete callback, both schedulers, computed
arrays beside WB RAM, full queue and the timeout-driven loss producer.
Hardware events and task delivery remain explicit. Five phase-activation groups
then connect the producer to the native kernel, finite task capacity, FIFO
consumption and missed-event recovery. Three preemption groups interrupt
each reached instruction address in selected SD/WB paths and check exact
resumption through that kernel. Full task execution time remains unmeasured.
Five crank-observation groups connect all six capture intervals and shared
queue delivery to the native diagnostic snapshot. Six decoder groups run
primary/secondary entry, a supplied missing-tooth pattern, acquisition/loss,
bounded table search and the capture-inhibit request/low-RPM producer.
Four startup-inhibit groups connect retained input fixtures to the native
startup latch, throttle-ratio release, countdown, loss callback and decoder
reacquisition. The periodic release worker has no rearming path.
Eight native-inhibit groups execute digital debounce/loss, stationary timers,
sampled loaded-log gates, speed and low-lift limiters, disabled received-torque
pattern publication, and conditional security/combined-message sources through
the actual injector-inhibit builder. Unlogged upstream states remain explicit.

Eighteen knock extensions execute retained-record validation, IAM initialization,
fault recovery, changed load-window resets, rough/fine learning, event histories
and mode reentry. Computed writes stay within the 64-cell grid; published
correction changes follow the native task order. Sensor events, upstream feedback
permission and retained vehicle history remain explicit boundaries.

Nine further feedback groups connect the native load-stability filter,
learning permission, final-cylinder selection, correction and transition
histories. They verify bounded feedback, clean recovery, initialization and
the carry into fine correction, including its native publication delay.

Ten timing-feedback groups connect six-angle minimum gating, bounded C1BC
retard/release, native final spark, held coolant sampling, the three-stage
idle-air sum and final DBW request, and equivalent monitor gain branches.
They distinguish the held temperature from live coolant and preserve the
native task-order dependencies without assuming physical actuator response.

Twelve dormant/retired extensions execute the actual final-timing wrapper,
enabled controls confined to test memory, return-only retired entries, all
36 computed fan mode entries, all eight duty branches and native period/output
writes. Retired-data poisoning preserves the fan results; the sole external
retired-address literal is the checksum's exclusive end.

Seven startup groups execute the RAM pattern test, temporary stack relocation,
explicit DMA completion, all 18 retained validators and all 58 cold initializers.
They verify preservation, duplicate-checksum repair, whole-bank reset after an
unrecoverable record and the separate outgoing invalid-bank flag. Ordinary
task startup, power retention and physical handshakes remain explicit limits.

Five retained-reset groups connect the actual serial input, all request/rearm
gates, native shutdown callbacks, one-shot invalidation and the next startup
reset. The switch suite now also verifies the corrected serial/AVLS mapping.
Seven SSM command groups execute all eight saved profiles through two complete
continuous responses, distinguish read/getter and write/setter dispatch,
and exercise explicit reset writes and rejected requests entirely offline.

It currently runs 355 groups covering checksums, diagnostic masks, configured
cylinder disable, WB monitoring, cam/IAM correction, knock cells, barometric
learning, AVLS phase/output, injector timers, immediate tip-in delivery, purge
filters/PWM, IAT conversion/substitution, connected CAN/driver/final-throttle
arbitration, tracking-fault qualification/cut and protected angle-offset
learning, plus airflow-region selection, acquisition and retained trim in
open-loop fuel, external-WB/native-feedback readiness and phase clearing,
retained heater qualification, activation and PWM buffer publication, and
native ADC scan/front-sensor handoff, missing completion and assigned timers,
plus the other WB-status callers through fault summaries and port output,
cruise cancellation, pedal selection, native overrun delays and the separate
cruise/AVLS speed gate. Readiness-history copies, heater activity diagnostics
and rear-monitor qualification include reset/hold boundary checks. Shared purge/
WB monitor flags, native RPM/MAP cell selection and all 234 computed monitor
history cells are also covered. The complete airflow task, startup/stopped
resets, cranking/event-state publishers and the two retained legacy-O2 workers
are included, with protected-offset retention and exclusion from final fuel.
The AVCS suites reproduce the removed OCV output in the captured image, then
verify the repaired initializer, current feedback, PWM buffers and temporary
override recovery. They also execute all 21 consecutive cam-controller stages,
rest learning, bank capture conversion/queue callbacks, and OCV diagnostic
qualification through current status, raw fault latches and native reset
helpers. A forced full cam-event queue records another conditional failure;
actual occupancy and deadlines are not inferred from that fixture.
The IAT electrical suite follows unsigned filtered-ADC thresholds through
P0112/P0113 reporting, the native fallback aggregate, 20 C substitution and
healthy recovery. P0111 is stock-disabled; the record suite verifies its reporter early return and native retained-status masking.
The ignition device suite adds native record initialization, all six timing
selections, timer routing, coil start/end publication, paired queue transitions,
cut/release, phase resynchronization and the current-cam-fault secondary-spark
mask. Crank periods, counter progress and hardware termination are explicit
fixtures; actual coil current and scheduling deadlines are not modeled.
Four cam performance groups execute the P0011/P0021 report and recovery
parent, including its unchanged 12,800-RPM nonzero-target qualification gate.
Fourteen additional groups cover AVLS native timer output and its shared
AVCS channels, electrical/switch reporting and healthy recovery, the
current-fault low-lift override, and complete GPIO debounce/switch
publication. WB status output on the same GPIO port preserves the two AVLS
input bits. The unrelated serial peripheral and physical pin observations
remain explicit inputs.
Seven shutdown groups connect AVLS diagnostic-message gates, callback
accounting, ignition-off qualification, queue bounds and the native queued
protected-counter worker. Six readiness groups execute the complete six-gate
publisher, reset helpers, acquired-fault retention and IAT-dependent minimum
temperature history. Six cam-sensor groups connect capture callbacks and
edge-count/absence qualification to current/raw faults, healthy recovery and
diagnostic queue success/full behavior. Physical interrupt delivery and the
queued snapshot's later storage worker remain explicit boundaries.
Seven diagnostic-mode groups add native startup, connector/mode latching,
stopped rearm, complete mode dispatch, descriptor reset rules and the shared
inhibit timer. Mode outputs are also passed to native fault aggregation and
cut selection with the other endpoint faults explicitly clear.
The cylinder-disable suite runs
separately on main, v2 and captured v2; other modules define their image sets
internally. Captured-image helpers verify the exact loaded-drive hash and fail
instead of silently calling an unrelated future build the captured image.

Eleven received-request groups connect CAN copies and timeout, startup-only
cut acquisition, held-message behavior, all 24 initial phase alignments,
delayed release summaries, and the injector-scalar alias into the native
torque/throttle model. Native integer lookup/division and rotation execute;
the input CAN traffic and mode state remain explicit fixtures.

Six mode-parent groups extend that boundary: the native warm coolant gate
blocks received cylinder cutting, separately from received throttle control.
They also execute reason-byte recovery, cold-window hysteresis, the complete
1,250-call reentry delay and elapsed-counter saturation.

The [saved run](../docs/reference/evidence/process_flow_tests_20260912.json)
records image hashes and individual test output. Passing these fixtures does
not close all state-machine edges or establish real interrupt deadlines. One
test deliberately reproduces a native down-counter wrap with an excessively
stale timestamp; its passing result records that counterexample, not safe
behavior or proof that it caused the vehicle cut.
