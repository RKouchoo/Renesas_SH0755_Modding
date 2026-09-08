# D2WD610H — ADM/JDM EZ30R Denso ECU Reverse Engineering

> Archived investigation, retained for evidence and historical reproduction.
> Use the [central reference](../reference/README.md) and [audited corrections](../reference/FINDINGS.md) for current conclusions.
> Build identities, commands and recommendations below describe their original stage.

Start with the [central reference](../reference/README.md) for the patch's
history, signal flow, reviewed addresses and remaining uncertainties. It is
backed by saved-image checks, execution fixtures and Ghidra MCP evidence.
Older documents remain available pending review; see the
[audit status](../reference/AUDIT_STATUS.md) and
[document retirement register](../reference/DOCUMENT_REGISTER.md).

## Repository layout

| Location | Purpose |
|---|---|
| [patches/](../../patches/README.md) | Shared firmware components and low-level build tools. |
| [tests/](../../tests/README.md) | Offline execution tests, verifiers and interpreter helpers. |
| [master_patch/](master_patch/README.md) | Rolling master builder, calibration, ROM, definitions, profiles and historical investigations. |
| `master_patch_v2/` | Separate v2 build; shared component references follow the new layout. |
| [docs/reference/](../reference/README.md) | Central reference, evidence and explicit review status. |
| [logs/](../../logs/README.md) | Preserved captures and analysis results. |
| `base_roms/`, `defs/` | Stock/donor inputs and source definitions. |
| `pico_kline_adapter/` | Independent adapter project, unchanged by this cleanup. |

## Rolling master

The single current output is
[master_patch/D2WD610H_master_patch.bin](../../master_patch/D2WD610H_master_patch.bin).
Fixes go into the rolling master sources and normal build; Git retains previous
versions for regression analysis. Independent user experiments stay out unless
explicitly requested.

Current SHA-256: `154760a5f2fdadbf6d9221480595f58dc77c6a4eccc492f50899c815aca79e4d`.
Subaru checksum: `0x16F63B0D`. The [MAP boundary repair](master_patch/MAP_BOUNDARY_REPAIR.md)
and earlier ten-cell idle-VE correction are integrated. **The user's dashpot
experiment is excluded; DBW/dashpot calibration is stock.** The complete master
verifier passes. The cause of the logged near-stall remains unresolved.

```sh
python3 master_patch/build_master_patch.py
python3 tests/verify_master_patch.py
```

Earlier firmware repair history:

> **September 8 corrective build:** stock radiator-fan control is restored and
> the misidentified electronic boost actuator is retired. The actual canister
> purge command, modeled purge airflow and both banks' purge-fuel subtraction
> are now disabled for the removed/capped purge plumbing. Previous images with
> the fan-output hook remain quarantined, including EBCS-OFF builds. The new
> image is statically checked, not vehicle-validated or a proved idle lean-out
> cure. See [the master audit](master_patch/GHIDRA_AUDIT.md).

The 10:30 image used for the 12:36 capture had SHA-256:
`48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0`
(Subaru checksum `0x1923EC61`). The retained-sensor audit adds a 20-byte repair
to `fbc1a8...`: unity factory lambda atmospheric compensation, neutralized
fuel adders and target corrections dependent on removed O2 voltages, and
checksum. VE, injector and timing calibrations are unchanged; the second idle-VE trial
remains unvalidated. See [the retained-routine audit](master_patch/RETAINED_ROUTINE_AUDIT.md).
The subsequent [guard execution audit](master_patch/GUARD_EXECUTION_AUDIT.md)
adds a 17-byte correction from `5a1b3e...`: zero/negative logger lambda can no
longer reset lean confirmation with stale valid readiness. Twelve new execution
test groups pass, with no added flash/RAM or calibration changes.
The later [primary-fueling execution audit](master_patch/PRIMARY_FUEL_EXECUTION_AUDIT.md)
corrects test-interpreter rounding and executes the retained primary target,
transition and bank/cylinder fuel composer. Further tracing found that added
cuts could leave the injector inhibit word stale. Both cut paths now publish
that word as well as the status flag; the `aea793...` stage contains that repair.
See [the injector-cut audit](master_patch/INJECTOR_CUT_EXECUTION_AUDIT.md).
The current [scheduler repair](master_patch/INJECTOR_SCHEDULER_EXECUTION_AUDIT.md)
also protects the complete cut update with the native scheduler lock. It fixes
a temporary release visible to the higher-priority injector task. Twelve added
execution groups cover queued pulses, release, resync, masks and negative controls.
Its IRQ/context follow-up adds eight groups executing native interrupt returns,
task dispatch and register restoration, including nested interrupts and damaged
gate/restore controls. The full verifier passes with no further ROM changes;
controlled bench/idle validation and a known VE baseline remain the next step.

## About this ECU

- **Processor:** Renesas SH7055 (SH-2E core, big-endian)
- **Flash Size:** 512 KB (0x00000000–0x0007FFFF)
- **Vehicle:** 2005 ADM Subaru Liberty 3.0R (EZ30R) MT (BLE Sedan)
- **CALID:** D2WD610H · **ECU ID:** 3C5A387116
- **Master free flash remaining:** 3,320 contiguous bytes at `0x7EE00..0x7FAF7`

## Goals

None of the public ECU definitions for the 3.0 H6 have AVLS mapped out. Denso made quite a capable ECU, so I don't believe an aftermarket one is required to get a good feature set when doing a turbo conversion. The post-facelift ECU can handle flex fuel by utilizing the available extra space. There is 9 KB of free space in this ECU, which I believe can be used.

| # | Goal Description | Status |
| :-: | :--- | :--- |
| 1 | Find AVLS settings and tables, and create definitions. | **DONE** — switchover thresholds + hysteresis + RPM overrides mapped; defs in [defs/D2WD610H_AVLS.xml](../../defs/D2WD610H_AVLS.xml). See notes §5. Pending RomRaider bench test. |
| 2 | Replace all four stock oxygen sensors with one post-turbo wideband feedback source. | *Integrated development patch built* — the supplied seller-labelled 50-4110/30-4110-style P0/P1 signal enters through the former MAF ADC, feeds both stock bank lambda/readiness paths, and is directly loggable. Both front A/F and both rear O2 conversion/monitor paths plus 18 mapped DTC switches are removed. The controller is single-ended and its fault voltages remain a commissioning blocker. The older one-factory-front-sensor patch remains only as a standalone historical alternative. Heater drivers are not electrically forced off. See [master_patch/README.md](master_patch/README.md). |
| 3 | Repurpose removed sensor inputs for other hardware. | **Architecture decided** — the former MAF signal input is the external-wideband channel. Its original signal-ground terminal is not used by the four-wire controller; controller black must use a clean power ground. Original oxygen-sensor circuits are deliberately not repurposed; all four connectors must be disconnected and insulated. |
| 4 | Retain boost protection for direct wastegate-spring operation. | **Electronic actuator retired** — the previous supposed EVAP output was radiator-fan PWM. The master now retains stock `0x3FD8C → 0xE8C4` fan control, removes electronic-boost tuning controls, and keeps the independently enabled 6.5 psi hard MAP fuel cut. Actual CPC purge and its fuel compensation are deleted separately. Direct 5 psi spring operation is the baseline; no electronic boost output is implemented. |
| 5 | Replace MAF logic with MAFless Speed Density. | *Integrated development patch built* — one speed-density component supplies committed-AVLS-state low/high-lift VE tables over their real 0..3200 and 3000..7500 RPM ranges, a provisional Haltech HT-010206 IAT curve for an assumed 1.00 kOhm ECU pull-up, and no MAF fallback. Raw MAF conversion/filter/diagnostic paths and P0102/P0103 are bypassed; the ADC remains live for the external-wideband input. Invalid running data selects a fixed 500 g/s high-load fail-safe; exact zero RPM writes zero. See [patches/speed_density/README.md](../../patches/speed_density/README.md) and [master_patch/README.md](master_patch/README.md). |
| 6 | Add a conservative rotational/lumpy idle mode. | *Integrated into master, default OFF* — the complete stock final-timing task runs first, then an exact-`01`, warm/stationary/closed-throttle/high-vacuum gate applies six bounded retard-only offsets. The master verifier checks its hook, opcodes, calibration, policy model, and collision-free ownership. Binary-verified, not vehicle-verified. See [rotational_idle_patch.md](../../patches/core/ROTATIONAL_IDLE.md). |
| 7 | Produce one focused turbo-conversion master image and definition. | **Corrective development baseline built** — `master_patch` deterministically composes SD with committed-state dual VE, exact 3-bar MAP scaling, spring-pressure boost safeties, actual purge deletion, external-wideband input/four-stock-O2 delete, live-pressure forced open loop, a delayed/confirmed/latched lean fuel cut, `16611AA510`/A4TE002B injector scaling and dead-time, conservative fuel/timing with a corrected 1000--6800 RPM Primary OL grid, the existing unvalidated second idle-VE trial, fixed 3200/3000 RPM AVLS, and a 6800 RPM limit from immutable stock. Static verification does not resolve the observed lean-out or replace physical commissioning. |

Also solved along the way: the central **table-interpolation** system (descriptor-based) and the
full **ignition-timing** blend/selection logic. See the notes.

## Documentation

| Doc | Contents |
|---|---|
| [D2WD610H_RE_notes.md](research/D2WD610H_RE_notes.md) | **Canonical engineering notes** — ROM identity, memory map, interpolation core, ignition timing, AVLS, RAM anchors, open targets, Ghidra rename log, methods. Read this first. |
| [boost_repurpose_notes.md](research/boost_repurpose_notes.md) | Current fan restoration/purge deletion and the explicitly retracted historical boost-output identification. |
| [boost_donor_A2WC510N.md](../hardware/boost_donor_A2WC510N.md) | Pinned A2WC510N turbo-EJ25 donor, extracted table addresses, MAP calibration, and 5 psi reduction. |
| [patch_build_guide.md](research/patch_build_guide.md) | Historical boost-build reference; its output-hook advice is superseded by the September 8 correction. Use the master README for the current build. |
| [single_front_af_patch.md](research/single_front_af_patch.md) | One-factory-A/F architecture, rear-narrowband logical deletion, external logging boundary, and commissioning limits. |
| [rotational_idle_patch.md](../../patches/core/ROTATIONAL_IDLE.md) | Integrated default-OFF per-cylinder retard component, operating gates, allocation, verifier, and commissioning limits. |
| [patches/speed_density/README.md](../../patches/speed_density/README.md) | Single always-on MAFless MAP/RPM/IAT component with committed-state low/high-lift VE, Ghidra trace, verifier, and commissioning boundary. |
| [master_patch/README.md](master_patch/README.md) | **Current integrated target** — architecture, exact hardware assumptions, deterministic builder, artifact, definition, logger, and limitations. |
| [master_patch/GHIDRA_AUDIT.md](master_patch/GHIDRA_AUDIT.md) | Stock-ROM function evidence, injected layout, verified decisions, and unresolved physical risks for the master. |
| [master_patch/RETAINED_ROUTINE_AUDIT.md](master_patch/RETAINED_ROUTINE_AUDIT.md) | Retained factory sensor assumptions: atmospheric lambda, O2-voltage fuel adders and feedback-target repairs, execution tests and unresolved cold-idle paths. |
| [master_patch/GUARD_EXECUTION_AUDIT.md](master_patch/GUARD_EXECUTION_AUDIT.md) | Wideband/guard instruction execution, lean fault-sentinel fix and remaining stock-state tracing. |
| [solenoid_subsystem.md](research/solenoid_subsystem.md) | Historical PWM subsystem research; its former purge-output identification is superseded by the master audit. |
| [ram_map.md](research/ram_map.md) | Consolidated confirmed RAM variables (RPM, MAP, ECT, ignition, AVLS, purge, CL/OL, oxygen sensors, solenoids). |
| [hardware_io_map.md](research/hardware_io_map.md) | SH7055 memory map, ROM landmarks, identified peripheral registers, sensor channels, and key ROM data structures. |
| [direct_attach_aud_interface.md](../hardware/direct_attach_aud_interface.md) | Verified SH7055 AUD direct-logging architecture, CPU pins, 5 V interface, wire protocol, bandwidth, hardware choices, and safe live-calibration boundary. |

### Definitions
| File | Use |
|---|---|
| [defs/D2WD610H.xml](../../defs/D2WD610H.xml) | Base metric EcuFlash definition retained as the D2WD610H source definition. |
| [defs/D2WD610H_AVLS.xml](../../defs/D2WD610H_AVLS.xml) | Self-contained metric RomRaider definition: D2WD610H standard tables + AVLS only. |
| [defs/D2WD610H_AVLS_boost_patch.xml](../../defs/D2WD610H_AVLS_boost_patch.xml) | Internal boost-definition source used by the master generator; not the current flash target. |
| [patches/speed_density/D2WD610H_AVLS_speed_density_patch.xml](../../patches/speed_density/D2WD610H_AVLS_speed_density_patch.xml) | Internal speed-density-definition source used by the master generator; not the current flash target. |
| [master_patch/D2WD610H_master_patch.xml](../../master_patch/D2WD610H_master_patch.xml) | Current focused metric definition: active timing/KCA identities, fuel/injectors, AVLS, SD/VE, exact Omni MAP, hard-overboost protection, wideband, pressure/lean safety, and default-OFF rotational idle. Retired EBCS controls are absent. |
| [master_patch/D2WD610H_master_logger.xml](../../master_patch/D2WD610H_master_logger.xml) | Complete metric SSM K-line ECU logger; the lean-out diagnostic set and D2WD610H project parameters E500--E516 are always visible. |
| [master_patch/D2WD610H_idle_diagnostic_profile.xml](../../master_patch/D2WD610H_idle_diagnostic_profile.xml) | Core idle capture, live-verified at 12:36; within the stock receiver's 43-address limit. |
| [master_patch/D2WD610H_afterstart_diagnostic_profile.xml](../../master_patch/D2WD610H_afterstart_diagnostic_profile.xml) | Separate 43-address after-start/fuel-factor capture; the two profiles are not simultaneous. |
| [logs/20260908_recovery_review.md](../../logs/20260908_recovery_review.md) | Latest candidate capture: settled fueling improves, blips still nearly stall; timing drop closely follows base-map demand during opening. |
| [master_patch/IDLE_RECOVERY_AUDIT.md](master_patch/IDLE_RECOVERY_AUDIT.md) | Signed transient correction trace and ten-cell VE candidate build; retained as a diagnostic calibration. |
| [master_patch/D2WD610H_idle_recovery_profile.xml](../../master_patch/D2WD610H_idle_recovery_profile.xml) | 19-channel recovery capture with transient correction, base factor and committed lift state; 43 addresses. |
| [master_patch/IDLE_AIR_RECOVERY_AUDIT.md](master_patch/IDLE_AIR_RECOVERY_AUDIT.md) | Native load/transient and idle-air investigation; repeat rev test withdrawn, car off. |
| [master_patch/D2WD610H_idle_air_diagnostic_profile.xml](../../master_patch/D2WD610H_idle_air_diagnostic_profile.xml) | Prepared 19-channel profile; live test deferred. Idle RPM target, combined throttle request, pedal/idle flags and fueling; 43 addresses. |
| [defs/romraider_ecu_defs.xml](../../defs/romraider_ecu_defs.xml) | Clean upstream RomRaider metric definition set from SubaruDefs Stable; no project AVLS/boost modifications. |

> Load the AVLS-only definition for the stock/AVLS-only ROM, or the focused master definition
> for the current turbo ROM. Legacy component XML files retained as generator inputs are not
> flash targets. The master definition removes obsolete MAF/O2/diagnostic material and dormant
> timing B/E that no longer belongs to its architecture.

## Reverse-engineering setup

The ROM is analysed in Ghidra (imported as `SuperH4:BE:32:default`, base 0x0) driven live over
GhidraMCP. `ghidra_sh7055_setup.py` creates the RAM/IO memory blocks and labels the reset entry,
CALID/ECU-ID, and free-space markers before auto-analysis. Working ROM image: `2005 BLE MT.bin`
(flash base = file offset 0). `patches/core/extract_srf.py` parses the original
`base_roms/2005 BLE MT.srf` and verifies that its 512-KiB `MEMD` payload is byte-identical to this
canonical stock image.
