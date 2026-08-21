# AVLS dual-VE Ghidra audit

The canonical stock image was checked in the existing Ghidra project. Every
function opened in this pass has a project-convention name, reproduced by
`ghidra_scripts/ApplyAvlsVeNames.java`.

| Address | Name | Relevant result |
|---:|---|---|
| `0x24B0` | `float_minimum_select` | Returns the lower float; identified while following AVLS threshold conditioning. |
| `0x172A4` | `maf_airflow_temperature_compensation_update` | Existing speed-density hook replaced by the dual-VE wrapper. |
| `0x353B0` | `intake_avcs_target_by_avls_mode_update` | Confirms committed mode 1 selects low-lift AVCS target A and mode 3 selects high-lift target B. |
| `0x3FDBC` | `avls_control_sequence_update` | Runs request selection/state machine, commit copy, then OSV actuation. |
| `0x40168` | `avls_cam_mode_state_machine` | Uses RPM and conditioned vehicle speed to form the requested lift mode. |
| `0x405B2` | `avls_mode_commit_copy` | Copies requested byte `0xFFFFCD87` to committed byte `0xFFFFCD86`. |
| `0x405CC` | `avls_osv_actuation_gate` | Applies the retained status/timing gates to physical actuation. |

The patched airflow wrapper reads `0xFFFFCD86` only. A value of 3 selects the
high-lift descriptor; all other values select low lift. This avoids assigning
fueling from a requested state before the stock commit path has advanced.

The stock state machine's conditioned vehicle-speed source is capped at
100 km/h. Both RPM-indexed speed tables and the two fixed/fallback speed
threshold literals are calibrated to 110 km/h, making the speed-request route
unreachable. The retained RPM hysteresis engages at 3200 and releases at 3000
RPM; the actuation minimum is 3000 RPM.

Injected layout:

| Address | Use |
|---:|---|
| `0x7E18C..0x7E3B3` | Replacement speed-density/dual-VE airflow wrapper. |
| `0x7E640..0x7E667` | Low- and high-lift 3D descriptors. |
| `0x7E668..0x7E68B` | Low-lift RPM axis, 0..3200 RPM. |
| `0x7E68C..0x7E6B7` | High-lift RPM axis, 3000..7500 RPM. |
| `0x7E6B8..0x7E88B` | Low-lift 13x9 VE data. |
| `0x7E88C..0x7EAC7` | High-lift 13x11 VE data. |

The verifier checks the wrapper opcodes and literal pool, descriptor contents,
axis ranges, seeded table continuity, AVLS calibration, definition freshness,
checksum, stock hash, and fresh-rebuild equivalence. It does not constitute
bench or engine validation.
