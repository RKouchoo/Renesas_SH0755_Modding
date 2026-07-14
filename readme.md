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
| 2 | Replace dual front-sensor feedback with one retained factory A/F sensor and add a post-turbo aftermarket wideband. | *Development patch built* — RH/Bank-1 factory A/F remains pre-turbo and is mirrored into both fuel-bank paths; an AEM 30-0310 is converted on the repurposed RH rear input and published as a dedicated logging-only RAM value. Binary-verified, not vehicle-verified. See [hybrid_o2_patch.md](docs/hybrid_o2_patch.md). |
| 3 | Repurpose the other O2 sensor circuits for other hardware. | *In progress* — RH rear input is assigned to the conditioned AEM logger path; LH rear remains stock and the unused LH front circuit is not yet reassigned. |
| 4 | Reuse the EVAP solenoid as an EBCS solenoid + WRX-style boost control. | *In progress* — purge chain fully RE'd; **one proportional + feed-forward patch with throttle gating and two-tier overboost protection is built** ([patch/](patch/)), binary-verified vs Ghidra, and region-audited. Output = ATU-II reg 0xFFFFF590 (sole owner); MAP feedback = 0xFFFFABC4. Defaults are reduced from turbo-EJ25 ROM A2WC510N to a 5 psi peak target, including its MAP scaling. Needs the matching sensor and bench validation before boost. See [boost_donor_A2WC510N.md](docs/boost_donor_A2WC510N.md), [boost_repurpose_notes.md](docs/boost_repurpose_notes.md), and [patch_build_guide.md](docs/patch_build_guide.md). |
| 5 | Potentially change MAF logic to Speed Density. | TBD |

Also solved along the way: the central **table-interpolation** system (descriptor-based) and the
full **ignition-timing** blend/selection logic. See the notes.

## Documentation

| Doc | Contents |
|---|---|
| [D2WD610H_RE_notes.md](docs/D2WD610H_RE_notes.md) | **Canonical engineering notes** — ROM identity, memory map, interpolation core, ignition timing, AVLS, RAM anchors, open targets, Ghidra rename log, methods. Read this first. |
| [boost_repurpose_notes.md](docs/boost_repurpose_notes.md) | EVAP-purge control chain + WRX-style boost-control design + patch plan + files/decisions. |
| [boost_donor_A2WC510N.md](docs/boost_donor_A2WC510N.md) | Pinned A2WC510N turbo-EJ25 donor, extracted table addresses, MAP calibration, and 5 psi reduction. |
| [patch_build_guide.md](docs/patch_build_guide.md) | How the single boost patch gets built, calibrated, verified, and flashed. |
| [hybrid_o2_patch.md](docs/hybrid_o2_patch.md) | One-factory-A/F + post-turbo AEM architecture, exact H6 connector checks, external analog-interface requirements, logger installation, and commissioning limits. |
| [solenoid_subsystem.md](docs/solenoid_subsystem.md) | The two PWM output subsystems: crank-synced AVCS/AVLS cam bank vs. the purge PWM (boost target). |
| [ram_map.md](docs/ram_map.md) | Consolidated confirmed RAM variables (RPM, MAP, ECT, ignition, AVLS, purge, CL/OL, oxygen sensors, solenoids). |
| [hardware_io_map.md](docs/hardware_io_map.md) | SH7055 memory map, ROM landmarks, identified peripheral registers, sensor channels, and key ROM data structures. |

### Definitions
| File | Use |
|---|---|
| [defs/D2WD610H.xml](defs/D2WD610H.xml) | Base metric EcuFlash definition retained as the D2WD610H source definition. |
| [defs/D2WD610H_AVLS.xml](defs/D2WD610H_AVLS.xml) | Self-contained metric RomRaider definition: D2WD610H standard tables + AVLS only. |
| [defs/D2WD610H_AVLS_boost_patch.xml](defs/D2WD610H_AVLS_boost_patch.xml) | Self-contained metric RomRaider definition: D2WD610H standard tables + AVLS + canonical boost-patch calibration. |
| [defs/D2WD610H_AVLS_wideband_patch.xml](defs/D2WD610H_AVLS_wideband_patch.xml) | Self-contained metric RomRaider definition: D2WD610H standard tables + AVLS + standalone hybrid-O2 logger calibration. |
| [defs/D2WD610H_AEM_logger_ecuparam.xml](defs/D2WD610H_AEM_logger_ecuparam.xml) | D2-only RomRaider logger fragment for E500 AEM lambda and E501 raw ADC; install with `patch/install_aem_logger.py`. |
| [defs/romraider_ecu_defs.xml](defs/romraider_ecu_defs.xml) | Clean upstream RomRaider metric definition set from SubaruDefs Stable; no project AVLS/boost modifications. |

> Load exactly **one** of the three custom ROM definitions at a time. Each embeds a metric
> `32BITBASE` pruned to the 206 templates actually referenced by D2WD610H. The AEM ecuparam file
> is a logger fragment, not a ROM definition; use the installer rather than loading it as an ECU
> definition.

## Reverse-engineering setup

The ROM is analysed in Ghidra (imported as `SuperH4:BE:32:default`, base 0x0) driven live over
GhidraMCP. `ghidra_sh7055_setup.py` creates the RAM/IO memory blocks and labels the reset entry,
CALID/ECU-ID, and free-space markers before auto-analysis. Working ROM image: `2005 BLE MT.bin`
(flash base = file offset 0).
