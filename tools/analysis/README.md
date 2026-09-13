# Offline analysis and historical replay

These modules were moved out of `master_patch/` after the documentation audit.
They still use the same saved captures, pinned historical ROMs and instruction
fixtures. `_analysis_paths.py` locates those files and the shared test helpers
independently of the current working directory.

| Modules | Purpose |
|---|---|
| `analyze_20260913_patch_workload.py` | Paired stock/v2 native airflow and wideband instruction/mask counts; isolates SD call substitutions in memory without creating a ROM. No elapsed-time or deadline claim. |
| `analyze_20260913_cylinder_fuel_followup.py` | Individual-cylinder fuel modifiers through the native composer, running refresh and pending/active injector updates; explicit state fixtures and native division controls. |
| `analyze_20260913_crank_refresh_followup.py` | Connects the native cranking-flag producer to six injector duration-refresh requests at the logged RPM/ECT pairs; distinguishes ignition mode from fuel scheduler state. |
| `analyze_20260913_ignition_followup.py` | Native dwell lookup at logged voltages, bounded late-start device cases, P10 visibility and per-cylinder correction clearing; no ECU writes or physical-output claim. |
| `analyze_20260913_cut_trace.py` | Repeated loaded cuts with spark/sync/task counters, exact profile matching, rich-at-onset event sequence and bounded mode-only VE replay; optional comparison figure. |
| `analyze_20260913_avcs_repair.py` | First repaired-v2 vehicle capture, full flash CRC identity, explicit Right/Left bank mapping and sampled cut/knock/AFR evidence; preserves the unresolved-cut finding. |
| `analyze_20260912_adjusted_drive.py` | Matched post-adjustment drive, low-lift bog, native fuel arithmetic and held-input cut checks; no physical-cause claim. |
| `analyze_20260912_pump_demand.py`, `_captured_images.py` | Native pump-demand comparison with explicit missing-input fixtures; exact capture-image recovery across the later pump-scaling correction. |
| `analyze_20260912_avls_neutral.py`, `analyze_20260912_fueling_adjustment.py` | Exact neutral capture identities and the measured idle/high-lift vacuum VE adjustment, with historical-image reconstruction. |
| `analyze_20260908_idle.py`, `analyze_20260908_recovery.py`, `analyze_20260908_dashpot.py` | Capture analysis tied to the original image and log hashes. |
| `analyze_sd_fallback.py`, `analyze_transient_components.py`, `compare_transient_remedies.py` | Historical airflow/fuel hypotheses and bounded comparisons. |
| `replay_20260908_transient.py`, `replay_20260908_load_recovery.py` | Retained transient/load instruction replay. |
| `audit_fpu_usage.py`, `audit_map_intercept.py`, `audit_map_sources.py` | Arithmetic census and native/processed MAP source investigations. |
| `prototype_sd_fpu_reuse.py`, `prototype_sd_fault_repair.py`, `audit_sd_fault_repair_prototype.py` | Unintegrated, memory-only experiments and their analysis. |
| `historical_roms.py`, `idle_recovery_candidate.py` | Pinned historical image recovery and reproduction of the old idle-VE candidate. |

Run from the repository root, for example:

```sh
python3 -B tools/analysis/audit_fpu_usage.py --help
python3 -B tools/analysis/audit_map_sources.py --help
python3 -B tests/test_map_boundary_execution.py
```

Analysis scripts can write requested JSON/plot reports. Running
`idle_recovery_candidate.py` directly reproduces its historical candidate and
metadata at the existing paths; it is not the current master builder. Some
capture analyses require the original local FastECU flash log to establish
image provenance. The [archive](../../docs/archive/README.md) preserves the
corresponding investigations, while the [central reference](../../docs/reference/README.md)
records corrected conclusions. No prototype is included in either saved
master ROM by this cleanup.
