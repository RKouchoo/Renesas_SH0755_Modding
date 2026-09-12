# Memory and hardware addresses

[Reference home](README.md) · [Methods](METHODS.md) · [Ghidra map limitation](GHIDRA.md)

## Address spaces and image identity

| Region | Range | Interpretation |
|---|---|---|
| D2WD610H saved flash | `00000000–0007FFFF` | 512 KiB; file offset equals address. |
| SH7055SF on-chip RAM | `FFFF6000–FFFFDFFF` | 32 KiB. Previous `FFFF0000–FFFFBFFF` setup was wrong. |
| Current Ghidra I/O block | `FFFFE400–FFFFFFFF` | Broad mapping; individual registers and holes need their own identities. |
| Reset vectors | `00000000`, `00000004` | PC `000009E0`, initial SP `FFFFDFA0`; repeated at offsets 8 and C. |
| Identity | `00002000`, `0007BDDD`, `0007BDA8` | Internal ID, CALID `D2WD610H`, packed ECU ID `3C5A387116`. |

RAM and register identities are checked against the
[Renesas SH7055S hardware manual](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual),
section 23 and tables 11.3/A.1. Wiring and physical output assignment need
separate evidence; a register name alone does not identify a harness pin.

The old Ghidra block omitted `C000–DFFF`, including injector, ignition/AVLS
state and stack. This was an analysis-project error; physical ECU memory did
not change. The setup helper now uses the correct range and rejects an
overlapping legacy block instead of accepting it or deleting existing analysis.

## Corrected timer descriptors

Saved stock bytes and MCP callers establish these record boundaries:

| Table | Extent | Record fields |
|---|---|---|
| A | `FA94–FADB`, 6 × 12 bytes | `+0` u32 down-counter address; `+4` u32 general-register address; `+8` u16 channel mask; `+A` padding. |
| B | `FADC–FB6B`, 6 × 24 bytes | `+0` down-counter; `+4` output compare; `+8` general register; `+C` shared counter; `+10` start register; `+14` u16 mask; `+16` padding. |

All pointers are big-endian u32. A uses `F640+2*n`, `F444+2*n` and mask
`1<<n`. B uses `F650+2*n`, `F614+2*n`, `F604+2*n`, shared `F602`, shared
`F666`, and mask `0100<<n`, for `n=0..5`.

Old A base `FA90` was four bytes early. Old B base `FAE8` is record 0's
`+C` counter-pointer slot. Starting there shifts every field and makes record
6 run into unrelated data. `96FC` uses **table A** through literal `983C`;
the injector route is `268E8 -> 90BA -> 96FC`. The B-table physical output
assignment is not established by this audit.

| Full register address | Hardware identity | Correct interpretation |
|---|---|---|
| `FFFFF444` | `GR1A` | A-table general register. |
| `FFFFF590` | `BFR7A` | Fan PWM buffer. |
| `FFFFF592` | `BFR7B` | Separate buffer in traced fuel-pump path. |
| `FFFFF598` | `DTR7A` | Duty register. |
| `FFFFF602` | `TCNT2B` | Counter, not channel-enable word. |
| `FFFFF604/606` | `GR2A/GR2B` | B-table series starts at 604. |
| `FFFFF614/616` | `OCR2A/OCR2B` | B-table series starts at 614. |
| `FFFFF640` | `DCNT8A` | A-table down-counter series. |
| `FFFFF650/652` | `DCNT8I/DCNT8J` | B-table series starts at 650. |
| `FFFFF666` | `DSTR` | Down-count start register. |
| `FFFFEC26` | `RAMER` | Flash/RAM emulation control. |
| `FFFFF718/71C` | `CMCSR1/CMCOR1` | CMT1 control/status and compare. |
| `FFFFF804` | `ADDR2` | MAP ADC word copied to `AB04` at `7060`. |

Native drivers also handle timing, status, counters and interrupt constraints.
The register table is not a replacement for those drivers.

## Fan, purge, fuel pump and injector state

Fan request is float percent at `CD54`, exported by SSM P92. The fan caller
literal is `3FD8C -> E8C4`. The writer converts duty fraction, uses period
state `AB84`, caches count `B0F0`, and writes BFR7A. The mode selector uses
RAM bytes **`CD7F/CD80`**: literals `3F97C/3FA80` contain those pointers.
Old claims of hardware bytes `FFFFF97C/FFFFFA80` confused literal locations
with their contents.

Actual CPC duty is float ratio `B6D4` (P38), with modeled flow `B6D8` and
mode `B720`. Writer `B182` caches a scaled count at `AE4C` and publishes a
request at `AB64`, through a pointer to `AB60`. Its electrical polarity is
not inferred from that RAM store. Main replaces the dispatcher with zero
publication and independently zeros bank purge subtractions `BE60/BE64` at
`23054`. Fan and CPC calibration maps must not be interchanged.

Fuel-pump request percent is `C298` (P47), produced through `2A53A` and its
state selector. `DEAA` is its traced PWM writer, separate from fan and CPC.
Native demand `2A910` consumes B1C4, produced from effective injector pulse
C0B8 by `13CA8` through a separate injector-dependent coefficient at `72D54`.
The [September 12 correction](FUEL_PUMP_SCALING_20260912.md) pairs that coefficient
with the resized injector calibration; it leaves the discrete commands and
pump-off gates intact.

The injector scheduler owns six records at `BFB8 + n*0x28`, through `C0A7`
inclusive. `BFF0` and `BFF8` are inside those records even without direct
xrefs. `B744` is a u16 inhibit word, `BF21` a circuit-fault byte and `D94C`
channel-status bits. The old cam-solenoid identity is retracted.

## Protected records and feedback arrays

`49530` writes an eight-byte protected float record: four float bytes followed
by two copies of a complemented halfword-sum checksum. `4963A` accepts either
matching checksum copy, repairs both copies and returns zero. It returns one
when neither matches. It does not determine whether a correction is active.
For example, `3D916` applies this validation to six records at `82EC + 8*n`.

| Native array | Bank 1 | Bank 2 | Allocation and update |
|---|---|---|---|
| Lambda response coefficients | `B9D0–BA27` | `BA28–BA7F` | 22 floats per bank; `1FB16` writes indices 1–21. |
| Lambda feedback histories | `BA90–BAE3` | `BAE4–BB37` | 21 floats per bank; `1FCD4` weights and shifts the history. |

Conditional initializer `1F1DC` zeros both complete allocations. These sizes
are distinct; counting generated coefficients is insufficient to infer the
allocation size or identify unused RAM.

## Flash ownership and the two checksum mechanisms

The original erased patch window begins at `7D790`. Current main's contiguous
unallocated tail is **`7EE00–7FAF7`, 3,320 bytes**. Retired reservations are
not automatically available. The [ownership table](../../master_patch/MEMORY_LAYOUT.md)
records injected ranges, hooks, intentional overlaps and reclaimed RAM. The
main verifier checks exact original bytes, ownership and undeclared changes.

`4FB8C` is a native rolling diagnostic accumulator; its upper-bound literal
`4FC30` contains `7D790`. The separate Subaru additive checksum descriptor
covers **`2000–7FAF7` inclusive**, including injected code. Writes above
`7D790` still require additive checksum repair. The old statement that
free-flash writes need no flasher checksum was incomplete.

No absent xref, erased-byte scan or configured block proves spare RAM.
Computed arrays, initialization, interrupts and stack depth also matter.
Total hardware stack headroom has not been measured.
