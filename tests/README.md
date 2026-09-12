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
