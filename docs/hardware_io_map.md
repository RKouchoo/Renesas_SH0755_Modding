# D2WD610H Hardware / Memory / I-O Map (SH7055)

Reference for the SH7055 memory layout and the on-chip peripheral registers identified so far.
Peripheral register *names* are inferred from behaviour (no datasheet loaded); addresses are
confirmed from code. See also [ram_map.md](ram_map.md), [solenoid_subsystem.md](solenoid_subsystem.md).

## Memory map
| Region | Range | Notes |
|---|---|---|
| Flash (ROM) | 0x00000000 – 0x0007FFFF | 512 KB; flash base = file offset in the .bin |
| RAM | 0xFFFF0000 – 0xFFFFBFFF | on-chip RAM (setup script block); actuator state extends into 0xFFFFCxxx |
| I/O (peripherals) | 0xFFFFE400 – 0xFFFFFFFF | marked volatile in Ghidra |

## ROM landmarks
| Address | Meaning |
|---|---|
| 0x000009E0 | Reset PC (`reset_entry`) |
| 0xFFFFDFA0 | Initial SP |
| 0x00002000 | Internal ID string "D2WD610H" |
| 0x0007BDA8 | ECU ID `3C5A387116` |
| 0x0007BDDD | CALID `D2WD610H` |
| **0x0007D790** | **~9 KB free space** (patch code + new tables land here). Also the ROM checksum's END boundary (`rom_checksum_accumulate` @0x4FB8C sums up to, not into, this address) — so free-space writes are outside the internal sum; only in-range edits need the flasher's checksum recalc. |
| 0x0007FFFF | end of flash |

## Denso literal trick (how RAM/I-O addresses appear in code)
Addresses ≥ 0xFFFF8000 are stored as **sign-extended 16-bit `mov.w` literals** (2-byte pool
entry, e.g. `0xC17C` → `0xFFFFC17C`). 32-bit `mov.l` literals are used for flash pointers and
some full I/O addresses. When scanning the ROM, a 2-byte pool word `0x8000–0xFFFF` may be an
`0xFFFF8000–0xFFFFFFFF` address.

## Identified peripheral registers
### ATU-II — cam/valve-timing solenoid bank (AVCS/AVLS)  (crank-angle synced)
6 output channels; see [solenoid_subsystem.md](solenoid_subsystem.md).
| Register | Role |
|---|---|
| 0xFFFFF602 | shared channel-enable control word (bit `0x0100<<n` = channel n) |
| 0xFFFFF666 | shared control register |
| 0xFFFFF652 + 2·n | per-channel output-compare / duty register (ch0..5) |
| 0xFFFFF640 + 2·n | per-channel counter/reload (bank A descriptor @0xFA90) |
| 0xFFFFF444 + 2·n | per-channel ATU config (bank A) |
| 0xFFFFF606 + 2·n, 0xFFFFF616 + 2·n | per-channel aux compare regs |

### ATU-II — EVAP purge PWM (the boost-patch output)
| Register | Role |
|---|---|
| **0xFFFFF590** | **purge solenoid output-compare register** (written = period − scaled duty) |
| 0xFFFFF598 | paired/complement register (adjacent) |
| period source | RAM 0xFFFFAB84 (see ram_map.md) |
Output stage `evap_purge_pwm_output_write` @0xE8C4; setup fn ~0xE884. **This is the pin to
reuse for the boost (wastegate) solenoid.**

### A/D — sensors
| Register/var | Role |
|---|---|
| MAP raw ADC → RAM 0xFFFFAB04 | manifold pressure sensor; processed by `map_sensor_voltage_to_pressure_process` @0x7A14 into native mmHg absolute at 0xFFFFABC4 |
| **0xFFFFAB18** | **RH/Bank-1 front A/F raw channel**; retained factory pre-turbo sensor (`E47`, signal `B134-33/B134-26`) |
| 0xFFFFAB00 | LH/Bank-2 front A/F raw channel; physical sensor removed by the single-front-A/F patch, whose processed Bank-2 paths mirror Bank 1 |
| **0xFFFFAB20** | **Stock RH rear-O2 raw ADC**; module-1 channel 4, deliberately unmodified by the single-front-A/F patch |
| 0xFFFFAB0C | Stock LH rear-O2 raw ADC; deliberately unmodified by the single-front-A/F patch |

See [single_front_af_patch.md](single_front_af_patch.md) for the exact firmware boundary and the
matching-generation front-sensor connector assignments. An aftermarket post-turbo wideband is
logged externally and is not connected to any ECU ADC channel.

## Notable ROM data-structure locations
| Address | Meaning |
|---|---|
| 0x0000FA90 | ATU cam-bank descriptor A (6 × 0x0C) |
| 0x0000FAE8 | ATU cam-bank descriptor B (6 × 0x18: ctrl/mask/compare regs) |
| 0x000116E8 | slow-task dispatch table (~50 fn ptrs; `slow_task_dispatcher` @0x114B0) |
| 0x0004B1CC | SSM datalogger RAM-address table (154 entries) |
| 0x000609C4 / 0x000609D8 | purge temp→duty map descriptors |
| 0x0007BD6C.. | purge calibration block (maps) |
