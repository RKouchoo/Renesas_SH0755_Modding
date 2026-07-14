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
| 2 | Replace dual O2 sensor trim logic with a single aftermarket wideband O2 input. | *In progress* — closed/open-loop state flag found (0xFFFFBE38); tracing per-bank enable. |
| 3 | Repurpose the three other O2 sensor circuits for other hardware. | Planned |
| 4 | Reuse the EVAP solenoid as an EBCS solenoid + WRX-style boost control. | *In progress* — **purge control chain fully reverse-engineered**; physical output = ATU-II reg 0xFFFFF590; MAP feedback = 0xFFFFABC4; boost-patch def created. See [boost_repurpose_notes.md](boost_repurpose_notes.md) + [patch_build_guide.md](patch_build_guide.md). |
| 5 | Potentially change MAF logic to Speed Density. | TBD |

Also solved along the way: the central **table-interpolation** system (descriptor-based) and the
full **ignition-timing** blend/selection logic. See the notes.

## Documentation

| Doc | Contents |
|---|---|
| [D2WD610H_RE_notes.md](D2WD610H_RE_notes.md) | **Canonical engineering notes** — ROM identity, memory map, interpolation core, ignition timing, AVLS, RAM anchors, open targets, Ghidra rename log, methods. Read this first. |
| [boost_repurpose_notes.md](boost_repurpose_notes.md) | EVAP-purge control chain + WRX-style boost-control design + patch plan + files/decisions. |
| [patch_build_guide.md](patch_build_guide.md) | How the boost patch gets built and flashed (patcher, free-space layout, phases, checksum). |
| [solenoid_subsystem.md](solenoid_subsystem.md) | The two PWM output subsystems: crank-synced AVCS/AVLS cam bank vs. the purge PWM (boost target). |
| [ram_map.md](ram_map.md) | Consolidated confirmed RAM variables (RPM, MAP, ECT, ignition, AVLS, purge, CL/OL, solenoids). |
| [hardware_io_map.md](hardware_io_map.md) | SH7055 memory map, ROM landmarks, identified peripheral registers, key ROM data structures. |

### Definitions (RomRaider)
| File | Use |
|---|---|
| [defs/D2WD610H_AVLS.xml](defs/D2WD610H_AVLS.xml) | Self-contained def: all standard D2WD610H tables + AVLS. |
| [defs/D2WD610H_boost_patch.xml](defs/D2WD610H_boost_patch.xml) | Working boost-patch def (xmlid D2WD610H_BOOST) — iterate here as the patch is built. |
| [defs/romraider_ecu_defs.xml](defs/romraider_ecu_defs.xml) | Full multi-ECU distribution (32BITBASE = WRX STi base; D2WD610H has AVLS merged). |

> Load exactly **one** D2WD610H definition at a time (they share ROM identity).

## Reverse-engineering setup

The ROM is analysed in Ghidra (imported as `SuperH4:BE:32:default`, base 0x0) driven live over
GhidraMCP. `ghidra_sh7055_setup.py` creates the RAM/IO memory blocks and labels the reset entry,
CALID/ECU-ID, and free-space markers before auto-analysis. Working ROM image: `2005 BLE MT.bin`
(flash base = file offset 0).
