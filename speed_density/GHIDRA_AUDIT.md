# MAFless speed-density and AVLS VE Ghidra audit

Speed density and committed-state AVLS VE selection are one firmware component.
The canonical stock ROM was checked in the existing Ghidra project; the merged
`ghidra_scripts/ApplyMaflessNames.java` reproduces every relevant name/comment.

| Address | Name | Relevant result |
|---:|---|---|
| `0x24B0` | `float_minimum_select` | Returns the lower float; identified while following AVLS threshold conditioning. |
| `0x172A4` | `maf_airflow_temperature_compensation_update` | Retained stock airflow/load task containing the replaced final-airflow helper. |
| `0x353B0` | `intake_avcs_target_by_avls_mode_update` | Committed mode 1 selects low-lift AVCS target A; mode 3 selects high-lift target B. |
| `0x3FDBC` | `avls_control_sequence_update` | Runs request selection/state machine, commit copy, then OSV actuation. |
| `0x40168` | `avls_cam_mode_state_machine` | Forms requested lift mode from RPM and conditioned accelerator pedal. |
| `0x405B2` | `avls_mode_commit_copy` | Copies requested byte `0xFFFFCD87` to committed byte `0xFFFFCD86`. |
| `0x405CC` | `avls_osv_actuation_gate` | Applies retained stock timing/status gates to lift-solenoid actuation. |

The airflow wrapper selects high-lift VE only when committed mode
`0xFFFFCD86 == 3`; all other values select low lift. This prevents fueling from
switching on the earlier requested state. Both RPM-indexed AVLS pedal tables and
the two fixed/fallback pedal thresholds are calibrated to 110 percent, above the
verified 100-percent conditioned-pedal cap. The previous vehicle-speed label
was wrong; native P30 dispatch/getter proof is in [the idle-air audit](../master_patch/IDLE_AIR_RECOVERY_AUDIT.md).
No numerical calibration or ROM byte changes with that correction. The retained RPM policy engages at
3200 and releases at 3000 RPM, with a 3000-RPM actuation minimum.

The wrapper, dual descriptors/axes/data, MAF removal, fail-safe behavior, AVLS
calibration, checksum, definitions, and stock provenance are checked together
by `verify_speed_density.py`. Static verification does not prove physical lift
actuation, VE accuracy, or engine safety.

## September 8 hook hardening

The wrapper keeps the proven final-airflow hook but now uses caller FR15 RPM
through validation, VE lookup and multiplication, matching the retained load
divisor. MAP/IAT are each captured once in saved FR12/FR13. This prevents
within-call rereads, not unequal physical sensor acquisition times. Every
exit restores the saved registers; no interrupt masking/static RAM is added.

Only local literal `0x173FC` is redirected from diagnostic getter `0x65168`
to verified `constant_zero_return @ 0x27088`, removing this task's obsolete
MAF-fault load substitution. Other diagnostic users and cranking/timeout
initialization remain. The 6% load filter remains and is explicitly defined.

Both binary verifiers run the new eight-group wrapper-opcode regression test;
the stock lookup callees are descriptor-based models, not instruction-emulated.
The rebuilt wrapper is 536 bytes at `0x7E18C..0x7E3A3`; no memory collision is
introduced. The complete stock-address trace, changed-byte audit, hashes and
remaining limitations are in the implementation section of
[the master audit](../master_patch/GHIDRA_AUDIT.md). This is not a confirmed
lean-out repair, and no VE/injector/timing calibration changed in this work.
