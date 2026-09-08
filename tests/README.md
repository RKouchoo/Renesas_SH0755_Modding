# Offline tests and verifiers

Run commands from the repository root. These tools operate on saved ROMs;
they do not connect to an ECU.

```sh
python3 -B tests/verify_master_patch.py
python3 -B master_patch_v2/verify_master_patch.py
```

The first command rebuilds the rolling master in memory, checks its saved
artifact, and runs the retained routine, hook, FPU, scheduler, calibration,
definition, logger and provenance checks. The v2 verifier remains its existing
checksum/layout/definition check; it is not equivalent to the master suite.

For a focused check, run its script directly, for example:

```sh
python3 -B tests/test_map_boundary_execution.py
python3 -B tests/test_ssm_receive_execution.py
python3 -B tests/test_hook_execution.py master_patch/D2WD610H_master_patch.bin
python3 -B tests/verify_romraider_toggles.py
```

`_test_paths.py` supplies the shared component and fixture import paths. Default
ROM inputs still refer to their build/artifact directories. Tests for historical
standalone components may require their corresponding standalone ROM or an
explicit input filename; do not substitute a different build merely because
it shares the same factory CALID.

`master_patch/verify_master_patch.py` is retained as a compatibility entry point
for existing workflows and links from the unchanged K-line adapter documentation.
The adapter's own tests remain in its folder.
