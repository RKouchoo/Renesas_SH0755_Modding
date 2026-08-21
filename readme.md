# D2WD610H — ADM/JDM EZ30R Denso ECU Reverse Engineering

## About this ECU

- **Processor:** Renesas SH7055 (SH-2E core, big-endian)
- **Flash Size:** 512 KB (0x00000000–0x0007FFFF)
- **Vehicle:** 2005 ADM Subaru Liberty 3.0R (EZ30R) MT (BLE Sedan)
- **CALID:** D2WD610H · **ECU ID:** 3C5A387116 · **~9 KB free space** @ 0x7D790

## Goals

None of the public ECU definitions for the 3.0 H6 have AVLS mapped out. Denso made quite a capable ECU, so I don't believe an aftermarket one is required to get a good feature set when doing a turbo conversion. The post-facelift ECU can handle flex fuel by utilizing the available extra space. There is 9 KB of free space in this ECU, which I believe can be used.

| # | Goal Description | Status |
| :-: | :--- | :--- |
| 1 | Find AVLS settings and tables, and create definitions. | **DONE** — switchover thresholds + hysteresis + RPM overrides mapped; defs in [defs/D2WD610H_AVLS.xml](defs/D2WD610H_AVLS.xml). See notes §5. Pending RomRaider bench test. |
| 2 | Replace all four stock oxygen sensors with one post-turbo wideband feedback source. | *Integrated development patch built* — the supplied seller-labelled 50-4110/30-4110-style P0/P1 signal enters through the former MAF ADC, feeds both stock bank lambda/readiness paths, and is directly loggable. Both front A/F and both rear O2 conversion/monitor paths plus 18 mapped DTC switches are removed. The controller is single-ended and its fault voltages remain a commissioning blocker. The older one-factory-front-sensor patch remains only as a standalone historical alternative. Heater drivers are not electrically forced off. See [master_patch/README.md](master_patch/README.md). |
| 3 | Repurpose removed sensor inputs for other hardware. | **Architecture decided** — the former MAF signal input is the external-wideband channel. Its original signal-ground terminal is not used by the four-wire controller; controller black must use a clean power ground. Original oxygen-sensor circuits are deliberately not repurposed; all four connectors must be disconnected and insulated. |
| 4 | Reuse the EVAP solenoid as an EBCS solenoid + WRX-style boost control. | *Integrated development patch built* — the master keeps the verified proportional + feed-forward controller, throttle gate, external-wideband voltage gate, MAP/RPM/IAT validity gates, minimum-control-RPM and SD-fault gates, 5.5 psi soft duty shutdown, and 6.5 psi hard fuel cut. Independent RomRaider switches default electronic boost control OFF and the hard cut ON for direct 5 psi wastegate-spring operation. It uses the exact Omni MAP-SUP-3BR transfer and also commands zero base duty, zero Kp, and zero maximum duty. Output is ATU-II `0xFFFFF590`; feedback is native MAP at `0xFFFFABC4`. Static/binary verified, not vehicle verified. |
| 5 | Replace MAF logic with MAFless Speed Density. | *Integrated development patch built* — one speed-density component supplies committed-AVLS-state low/high-lift VE tables over their real 0..3200 and 3000..7500 RPM ranges, retained post-intercooler IAT correction, and no MAF fallback. Raw MAF conversion/filter/diagnostic paths and P0102/P0103 are bypassed; the ADC remains live for the external-wideband input. Invalid running data selects a fixed 500 g/s high-load fail-safe; exact zero RPM writes zero. See [speed_density/README.md](speed_density/README.md) and [master_patch/README.md](master_patch/README.md). |
| 6 | Add a conservative rotational/lumpy idle mode. | *Standalone development patch built* — the complete stock final-timing task runs first, then an exact-`01`, warm/stationary/closed-throttle gate applies six bounded retard-only offsets. The image and RomRaider switch default OFF. It has its own guarded component API and non-overlapping allocation for a later merge, but is deliberately absent from the legacy combined patch, base turbo map, and current master. Binary-verified, not vehicle-verified. See [rotational_idle_patch.md](docs/rotational_idle_patch.md). |
| 7 | Produce one focused turbo-conversion master image and definition. | **Development baseline complete** — `master_patch` deterministically composes SD with committed-state dual VE, exact 3-bar MAP scaling, boost safeties, external-wideband input/four-stock-O2 delete, live-pressure forced open loop, a delayed/confirmed/latched lean fuel cut, STI-pink donor scaling/deadtime, conservative fuel/timing with a corrected 1000--6800 RPM Primary OL grid, fixed 3200/3000 RPM AVLS, and a 6800 RPM limit from immutable stock. Output, definition, logger fragment, and Ghidra audit pass static verification; physical commissioning remains. |

Also solved along the way: the central **table-interpolation** system (descriptor-based) and the
full **ignition-timing** blend/selection logic. See the notes.

## Documentation

| Doc | Contents |
|---|---|
| [D2WD610H_RE_notes.md](docs/D2WD610H_RE_notes.md) | **Canonical engineering notes** — ROM identity, memory map, interpolation core, ignition timing, AVLS, RAM anchors, open targets, Ghidra rename log, methods. Read this first. |
| [boost_repurpose_notes.md](docs/boost_repurpose_notes.md) | EVAP-purge control chain + WRX-style boost-control design + patch plan + files/decisions. |
| [boost_donor_A2WC510N.md](docs/boost_donor_A2WC510N.md) | Pinned A2WC510N turbo-EJ25 donor, extracted table addresses, MAP calibration, and 5 psi reduction. |
| [patch_build_guide.md](docs/patch_build_guide.md) | How the single boost patch gets built, calibrated, verified, and flashed. |
| [single_front_af_patch.md](docs/single_front_af_patch.md) | One-factory-A/F architecture, rear-narrowband logical deletion, external logging boundary, and commissioning limits. |
| [rotational_idle_patch.md](docs/rotational_idle_patch.md) | Separate default-OFF per-cylinder retard patch, operating gates, allocation, verifier, and commissioning limits. |
| [speed_density/README.md](speed_density/README.md) | Single always-on MAFless MAP/RPM/IAT component with committed-state low/high-lift VE, Ghidra trace, verifier, and commissioning boundary. |
| [base_turbo_map/README.md](base_turbo_map/README.md) | Reproducible combined-image derivative with conservative 5 psi / 98 RON fuel, ignition, spring-only boost, checksum, and commissioning documentation. |
| [master_patch/README.md](master_patch/README.md) | **Current integrated target** — architecture, exact hardware assumptions, deterministic builder, artifact, definition, logger, and limitations. |
| [master_patch/GHIDRA_AUDIT.md](master_patch/GHIDRA_AUDIT.md) | Stock-ROM function evidence, injected layout, verified decisions, and unresolved physical risks for the master. |
| [solenoid_subsystem.md](docs/solenoid_subsystem.md) | The two PWM output subsystems: crank-synced AVCS/AVLS cam bank vs. the purge PWM (boost target). |
| [ram_map.md](docs/ram_map.md) | Consolidated confirmed RAM variables (RPM, MAP, ECT, ignition, AVLS, purge, CL/OL, oxygen sensors, solenoids). |
| [hardware_io_map.md](docs/hardware_io_map.md) | SH7055 memory map, ROM landmarks, identified peripheral registers, sensor channels, and key ROM data structures. |

### Definitions
| File | Use |
|---|---|
| [defs/D2WD610H.xml](defs/D2WD610H.xml) | Base metric EcuFlash definition retained as the D2WD610H source definition. |
| [defs/D2WD610H_AVLS.xml](defs/D2WD610H_AVLS.xml) | Self-contained metric RomRaider definition: D2WD610H standard tables + AVLS only. |
| [defs/D2WD610H_AVLS_boost_patch.xml](defs/D2WD610H_AVLS_boost_patch.xml) | Self-contained metric RomRaider definition: D2WD610H standard tables + AVLS + boost calibration + independent EBCS and hard-overboost switches. |
| [defs/D2WD610H_AVLS_single_front_af_patch.xml](defs/D2WD610H_AVLS_single_front_af_patch.xml) | Self-contained metric RomRaider definition: D2WD610H standard tables + AVLS + the front-mirror/rear-delete runtime switch. |
| [defs/D2WD610H_AVLS_rotational_idle_patch.xml](defs/D2WD610H_AVLS_rotational_idle_patch.xml) | Self-contained metric RomRaider definition: D2WD610H standard tables + AVLS + standalone rotational-idle gates, offsets, and default-OFF switch. |
| [defs/D2WD610H_AVLS_boost_single_front_af_patch.xml](defs/D2WD610H_AVLS_boost_single_front_af_patch.xml) | Self-contained metric RomRaider definition for the combined image: D2WD610H standard tables + AVLS + boost calibration + boost and front-mirror/rear-delete switches. |
| [speed_density/D2WD610H_AVLS_speed_density_patch.xml](speed_density/D2WD610H_AVLS_speed_density_patch.xml) | Generated self-contained metric definition for the single MAFless SD component: committed-state low/high-lift VE, predictable 3200/3000 RPM AVLS, and inherited MAF tables/DTCs removed. |
| [master_patch/D2WD610H_master_patch.xml](master_patch/D2WD610H_master_patch.xml) | Focused self-contained metric master definition: active timing/KCA identities, fuel/injectors, AVLS, SD/VE, exact Omni MAP, boost, external-wideband transfer/range, pressure-open-loop, and lean-cut controls; obsolete MAF/O2/diagnostic and dormant timing entries removed. |
| [defs/romraider_ecu_defs.xml](defs/romraider_ecu_defs.xml) | Clean upstream RomRaider metric definition set from SubaruDefs Stable; no project AVLS/boost modifications. |

> Load exactly **one** of the seven custom RomRaider definitions at a time—the AVLS-only,
> boost, single-front-A/F, rotational-idle, speed-density, legacy combined, or current master
> variant matching the ROM being edited. The focused master definition further removes stock
> MAF/O2/diagnostic material and dormant timing B/E that no longer belongs to its architecture.

## Reverse-engineering setup

The ROM is analysed in Ghidra (imported as `SuperH4:BE:32:default`, base 0x0) driven live over
GhidraMCP. `ghidra_sh7055_setup.py` creates the RAM/IO memory blocks and labels the reset entry,
CALID/ECU-ID, and free-space markers before auto-analysis. Working ROM image: `2005 BLE MT.bin`
(flash base = file offset 0). `patch/extract_srf.py` parses the original
`base_roms/2005 BLE MT.srf` and verifies that its 512-KiB `MEMD` payload is byte-identical to this
canonical stock image.
