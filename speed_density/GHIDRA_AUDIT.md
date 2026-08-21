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
| `0x40168` | `avls_cam_mode_state_machine` | Forms requested lift mode from RPM and conditioned vehicle speed. |
| `0x405B2` | `avls_mode_commit_copy` | Copies requested byte `0xFFFFCD87` to committed byte `0xFFFFCD86`. |
| `0x405CC` | `avls_osv_actuation_gate` | Applies retained stock timing/status gates to lift-solenoid actuation. |

The airflow wrapper selects high-lift VE only when committed mode
`0xFFFFCD86 == 3`; all other values select low lift. This prevents fueling from
switching on the earlier requested state. Both RPM-indexed AVLS speed tables and
the two fixed/fallback speed thresholds are calibrated to 110 km/h, above the
verified 100-km/h conditioned-speed cap. The retained RPM policy engages at
3200 and releases at 3000 RPM, with a 3000-RPM actuation minimum.

The wrapper, dual descriptors/axes/data, MAF removal, fail-safe behavior, AVLS
calibration, checksum, definitions, and stock provenance are checked together
by `verify_speed_density.py`. Static verification does not prove physical lift
actuation, VE accuracy, or engine safety.
