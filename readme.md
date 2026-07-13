# D2WD610H — ADM/JDM EZ30R Denso ECU Reverse Engineering

## About this ECU

- **Processor:** Renesas SH7055 (SH-2E core, big-endian)
- **Flash Size:** 512 KB (0x00000000–0x0007FFFF)
- **Vehicle:** 2005 ADM Subaru Liberty 3.0R (EZ30R) MT (BLE Sedan)

## Goals

None of the public ECU definitions for the 3.0 H6 have AVLS mapped out. Denso made quite a capable ECU, so I don't believe an aftermarket one is required to get a good feature set when doing a turbo conversion. The post-facelift ECU can handle flex fuel by utilizing the available extra space. There is 9 KB of free space in this ECU, which I believe can be used.

| # | Goal Description | Status |
| :-: | :--- | :--- |
| 1 | Find AVLS settings and tables, and create definitions. | **DONE** - See: [avls_def_fragment.xml](defs/avls_def_fragment.xml) pending testing in RomRaider|
| 2 | Replace dual o2 sensor trim logic with a single aftermarket wideband O2 sensor input. | *In Progress* |
| 3 | Repurpose the three other O2 sensor circuits for other hardware. | Planned |
| 4 | Reuse the EVAP solenoid as an EBCS solenoid and implement boost control strategies similar to the 32-bit WRX ECUs. | Planned |
| 5 | Potentially change MAF logic to Speed Density | TBD | 

For current engineering notes, see [D2WD610H_RE_notes.md](D2WD610H_RE_notes.md).
