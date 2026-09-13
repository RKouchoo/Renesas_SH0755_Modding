# Document disposition register

[Reference home](README.md) · [Archive](../archive/README.md)

The user requested post-audit cleanup on September 9, 2026. This register covers all 44 original Markdown documents outside the excluded adapter: **27 archived, 17 retained as operational, component, hardware or capture references.** Unique investigation evidence was preserved. The two old project overviews are archived and have been replaced with concise current guides.

The central pages hold current conclusions. Archived pages describe historical stages and may contain superseded claims or commands. Their banners link back to the audited corrections. The adapter and v2 trees remain unchanged by this cleanup; a compatibility page preserves the adapter's original logger-audit link.

Audited source text is pinned to `46bfc52` with superseded claims from `2d95301`. [document_locations.json](document_locations.json) maps the later moves; the inventory retains the original source hashes/line numbers separately from the current file hashes.

September 12–13 additions are outside those frozen counts. No new document is
removed by the ongoing process-flow review.

| Later document | Central destination | Disposition after this review |
|---|---|---|
| [AVCS_OCV_REPAIR_20260913.md](AVCS_OCV_REPAIR_20260913.md) | [AVCS coverage](PATCH_PROCESS_FLOW.md#coverage-register), [signals](SIGNALS.md), [logger](LOGGER.md) and [memory](../../master_patch/MEMORY_LAYOUT.md) | Retain as the evidence-backed correction. Earlier archived claims that `E0D0/33xxx/34BE4/69568` are rear-O2 work, or that `B098/B09C/C85C/C860` are safely reclaimed, are explicitly withdrawn. Preserve historical files for review. |
| [AF_LEARNING_WOT_ISOLATION.md](AF_LEARNING_WOT_ISOLATION.md) | [Fuel-learning process](PATCH_PROCESS_FLOW.md#fuel-learning-region-acquisition-and-open-loop-application) | Incorrect zero-trim guarantee retracted and replaced with native evidence. Retain for user review; may later be archived once the central account is accepted. |
| [PATCH_TOUCHPOINT_REGISTER.md](PATCH_TOUCHPOINT_REGISTER.md) | [Coverage register](PATCH_PROCESS_FLOW.md#coverage-register) | Retain as generated assignment inventory; it is not a complete flow proof. |
| [PATCH_PROCESS_FLOW.md](PATCH_PROCESS_FLOW.md) | This is the new central process account. | Retain and continue; outstanding edges remain explicit. |

| Original document | Present location | Central destination | Disposition |
|---|---|---|---|
| `audit.md` | [docs/archive/audit.md](../../docs/archive/audit.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `docs/D2WD610H_RE_notes.md` | [docs/archive/research/D2WD610H_RE_notes.md](../../docs/archive/research/D2WD610H_RE_notes.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `docs/boost_donor_A2WC510N.md` | [docs/hardware/boost_donor_A2WC510N.md](../../docs/hardware/boost_donor_A2WC510N.md) | [MEMORY_AND_IO.md](MEMORY_AND_IO.md) | Retained: specialist source; physical limits apply |
| `docs/boost_repurpose_notes.md` | [docs/archive/research/boost_repurpose_notes.md](../../docs/archive/research/boost_repurpose_notes.md) | [MEMORY_AND_IO.md](MEMORY_AND_IO.md) | Archived; historical evidence retained |
| `docs/direct_attach_aud_interface.md` | [docs/hardware/direct_attach_aud_interface.md](../../docs/hardware/direct_attach_aud_interface.md) | [MEMORY_AND_IO.md](MEMORY_AND_IO.md) | Retained: specialist source; physical limits apply |
| `docs/hardware_io_map.md` | [docs/archive/research/hardware_io_map.md](../../docs/archive/research/hardware_io_map.md) | [MEMORY_AND_IO.md](MEMORY_AND_IO.md) | Archived; historical evidence retained |
| `docs/patch_build_guide.md` | [docs/archive/research/patch_build_guide.md](../../docs/archive/research/patch_build_guide.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `docs/ram_map.md` | [docs/archive/research/ram_map.md](../../docs/archive/research/ram_map.md) | [MEMORY_AND_IO.md](MEMORY_AND_IO.md) | Archived; historical evidence retained |
| `docs/rotational_idle_patch.md` | [patches/core/ROTATIONAL_IDLE.md](../../patches/core/ROTATIONAL_IDLE.md) | [PATCH_STORY.md](PATCH_STORY.md) | Retained: component guide |
| `docs/single_front_af_patch.md` | [docs/archive/research/single_front_af_patch.md](../../docs/archive/research/single_front_af_patch.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `docs/solenoid_subsystem.md` | [docs/archive/research/solenoid_subsystem.md](../../docs/archive/research/solenoid_subsystem.md) | [MEMORY_AND_IO.md](MEMORY_AND_IO.md) | Archived; historical evidence retained |
| `fueling_safety/README.md` | [patches/fueling_safety/README.md](../../patches/fueling_safety/README.md) | [IMAGES.md](IMAGES.md) | Retained: component contract |
| `logs/20260908_dashpot_review.md` | [logs/20260908_dashpot_review.md](../../logs/archive/20260908_dashpot_review.md) | [LOGGER.md](LOGGER.md) | Retained: capture provenance unchanged |
| `logs/20260908_idle_review.md` | [logs/20260908_idle_review.md](../../logs/archive/20260908_idle_review.md) | [LOGGER.md](LOGGER.md) | Retained: capture provenance unchanged |
| `logs/20260908_recovery_review.md` | [logs/20260908_recovery_review.md](../../logs/archive/20260908_recovery_review.md) | [LOGGER.md](LOGGER.md) | Retained: capture provenance unchanged |
| `logs/README.md` | [logs/README.md](../../logs/README.md) | [LOGGER.md](LOGGER.md) | Retained: capture provenance unchanged |
| `master_patch/CALIBRATION.md` | [master_patch/CALIBRATION.md](../../master_patch/CALIBRATION.md) | [IMAGES.md](IMAGES.md) | Retained: detailed current build contract |
| `master_patch/COMMISSIONING.md` | [master_patch/COMMISSIONING.md](../../master_patch/COMMISSIONING.md) | [README.md](README.md) | Retained: operational entry point |
| `master_patch/FPU_USAGE_AUDIT.md` | [docs/archive/master_patch/FPU_USAGE_AUDIT.md](../../docs/archive/master_patch/FPU_USAGE_AUDIT.md) | [METHODS.md](METHODS.md) | Archived; historical evidence retained |
| `master_patch/GHIDRA_AUDIT.md` | [docs/archive/master_patch/GHIDRA_AUDIT.md](../../docs/archive/master_patch/GHIDRA_AUDIT.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `master_patch/GUARD_EXECUTION_AUDIT.md` | [docs/archive/master_patch/GUARD_EXECUTION_AUDIT.md](../../docs/archive/master_patch/GUARD_EXECUTION_AUDIT.md) | [METHODS.md](METHODS.md) | Archived; historical evidence retained |
| `master_patch/IDLE_AIR_RECOVERY_AUDIT.md` | [docs/archive/master_patch/IDLE_AIR_RECOVERY_AUDIT.md](../../docs/archive/master_patch/IDLE_AIR_RECOVERY_AUDIT.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `master_patch/IDLE_RECOVERY_AUDIT.md` | [docs/archive/master_patch/IDLE_RECOVERY_AUDIT.md](../../docs/archive/master_patch/IDLE_RECOVERY_AUDIT.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `master_patch/INJECTOR_CUT_EXECUTION_AUDIT.md` | [docs/archive/master_patch/INJECTOR_CUT_EXECUTION_AUDIT.md](../../docs/archive/master_patch/INJECTOR_CUT_EXECUTION_AUDIT.md) | [METHODS.md](METHODS.md) | Archived; historical evidence retained |
| `master_patch/INJECTOR_SCHEDULER_EXECUTION_AUDIT.md` | [docs/archive/master_patch/INJECTOR_SCHEDULER_EXECUTION_AUDIT.md](../../docs/archive/master_patch/INJECTOR_SCHEDULER_EXECUTION_AUDIT.md) | [METHODS.md](METHODS.md) | Archived; historical evidence retained |
| `master_patch/LOGGER_CONNECTION_AUDIT.md` | [docs/archive/master_patch/LOGGER_CONNECTION_AUDIT.md](../../docs/archive/master_patch/LOGGER_CONNECTION_AUDIT.md) | [LOGGER.md](LOGGER.md) | Archived; historical evidence retained |
| `master_patch/MAP_BOUNDARY_REPAIR.md` | [docs/archive/master_patch/MAP_BOUNDARY_REPAIR.md](../../docs/archive/master_patch/MAP_BOUNDARY_REPAIR.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `master_patch/MAP_SOURCE_AUDIT.md` | [docs/archive/master_patch/MAP_SOURCE_AUDIT.md](../../docs/archive/master_patch/MAP_SOURCE_AUDIT.md) | [LOGGER.md](LOGGER.md) | Archived; historical evidence retained |
| `master_patch/MEMORY_LAYOUT.md` | [master_patch/MEMORY_LAYOUT.md](../../master_patch/MEMORY_LAYOUT.md) | [IMAGES.md](IMAGES.md) | Retained: detailed current build contract |
| `master_patch/PRIMARY_FUEL_EXECUTION_AUDIT.md` | [docs/archive/master_patch/PRIMARY_FUEL_EXECUTION_AUDIT.md](../../docs/archive/master_patch/PRIMARY_FUEL_EXECUTION_AUDIT.md) | [METHODS.md](METHODS.md) | Archived; historical evidence retained |
| `master_patch/README.md` | [docs/archive/master_patch/README.md](../../docs/archive/master_patch/README.md) | [README.md](README.md) | Archived; historical evidence retained |
| `master_patch/RETAINED_ROUTINE_AUDIT.md` | [docs/archive/master_patch/RETAINED_ROUTINE_AUDIT.md](../../docs/archive/master_patch/RETAINED_ROUTINE_AUDIT.md) | [METHODS.md](METHODS.md) | Archived; historical evidence retained |
| `master_patch/SD_FALLBACK_AUDIT.md` | [docs/archive/master_patch/SD_FALLBACK_AUDIT.md](../../docs/archive/master_patch/SD_FALLBACK_AUDIT.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `master_patch/SD_FAULT_REPAIR_PROTOTYPE.md` | [docs/archive/master_patch/SD_FAULT_REPAIR_PROTOTYPE.md](../../docs/archive/master_patch/SD_FAULT_REPAIR_PROTOTYPE.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `master_patch/THROTTLE_LINK_AUDIT.md` | [docs/archive/master_patch/THROTTLE_LINK_AUDIT.md](../../docs/archive/master_patch/THROTTLE_LINK_AUDIT.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `master_patch/TRANSIENT_COMPONENT_AUDIT.md` | [docs/archive/master_patch/TRANSIENT_COMPONENT_AUDIT.md](../../docs/archive/master_patch/TRANSIENT_COMPONENT_AUDIT.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `master_patch/WIRING.md` | [master_patch/WIRING.md](../../master_patch/WIRING.md) | [MEMORY_AND_IO.md](MEMORY_AND_IO.md) | Retained: specialist source; physical limits apply |
| `master_patch/candidates/README.md` | [master_patch/candidates/README.md](../../master_patch/candidates/README.md) | [PATCH_STORY.md](PATCH_STORY.md) | Retained: historical image provenance |
| `master_patch/romraider_query_fix/README.md` | [master_patch/romraider_query_fix/README.md](../../master_patch/romraider_query_fix/README.md) | [LOGGER.md](LOGGER.md) | Retained: implementation/reproduction guide |
| `patch/README.md` | [patches/core/README.md](../../patches/core/README.md) | [IMAGES.md](IMAGES.md) | Retained: component contract |
| `readme.md` | [docs/archive/project_overview.md](../../docs/archive/project_overview.md) | [README.md](README.md) | Archived; historical evidence retained |
| `speed_density/COMMISSIONING.md` | [patches/speed_density/COMMISSIONING.md](../../patches/speed_density/COMMISSIONING.md) | [README.md](README.md) | Retained: operational entry point |
| `speed_density/GHIDRA_AUDIT.md` | [docs/archive/speed_density/GHIDRA_AUDIT.md](../../docs/archive/speed_density/GHIDRA_AUDIT.md) | [PATCH_STORY.md](PATCH_STORY.md) | Archived; historical evidence retained |
| `speed_density/README.md` | [patches/speed_density/README.md](../../patches/speed_density/README.md) | [IMAGES.md](IMAGES.md) | Retained: component contract |

The machine-readable inventory preserves each document's content hash and every extracted claim. Historical errors are retained as history with retractions; central pages supply the corrected current interpretation. Preservation does not mean those old claims remain valid.
