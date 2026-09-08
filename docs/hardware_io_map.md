# D2WD610H hardware and memory map

The [central memory/I/O reference](reference/MEMORY_AND_IO.md) now owns the
reviewed layouts, register identities and evidence. This page remains as a
compatibility entry point pending review of the
[document retirement register](reference/DOCUMENT_REGISTER.md).

## Corrected address spaces

| Region | Inclusive range | Meaning |
|---|---|---|
| Saved flash | `0x00000000–0x0007FFFF` | 512 KiB; file offset equals ROM address. |
| Physical SH7055SF RAM | `0xFFFF6000–0xFFFFDFFF` | 32 KiB; initial stack pointer `0xFFFFDFA0`. |
| Ghidra I/O mapping | `0xFFFFE400–0xFFFFFFFF` | Broad analysis block, including reserved holes. |

The old `0xFFFF0000–0xFFFFBFFF` RAM block is wrong. The repository setup
helper is corrected; changing the open project's blocks is unavailable through
the current MCP server. See [Ghidra status](reference/GHIDRA.md).

Reset PC is `0x000009E0`. Internal ID is at `0x00002000`, packed ECU ID at
`0x0007BDA8`, and CALID at `0x0007BDDD`. The stock erased patch window starts
at `0x0007D790`; that is not a claim that the current image has 9 KiB free.
Main's contiguous unallocated tail is `0x0007EE00–0x0007FAF7` (3,320 bytes).
The native rolling checksum stops before `0x0007D790`, but the separate
additive checksum covers `0x00002000–0x0007FAF7` inclusive, including patches.

## Timer descriptors and output identities

| Object | Correct identity |
|---|---|
| `0x0000FA94` | Table A: six 12-byte records; down-counter pointer, general-register pointer, u16 mask, padding. |
| `0x0000FADC` | Table B: six 24-byte records; three channel pointers, shared counter pointer, start-register pointer, u16 mask, padding. |
| `0x000096FC` | Injector timer duration driver using table A, reached through `0x000268E8 → 0x000090BA`. |
| `0xFFFFF602` | `TCNT2B`, a counter. It is not a channel-enable word. |
| `0xFFFFF666` | `DSTR`, down-count start register. |
| `0xFFFFF640` / `0xFFFFF444` | Table A series start: `DCNT8A` / `GR1A`. |
| `0xFFFFF650` / `0xFFFFF614` / `0xFFFFF604` | Table B series start: `DCNT8I` / `OCR2A` / `GR2A`. |
| `0xFFFFF590` / `0xFFFFF598` | `BFR7A` / `DTR7A`; traced fan PWM path. |
| `0xFFFFF592` | `BFR7B`; separate traced fuel-pump PWM path. |

The former descriptor bases `0xFA90` and `0xFAE8` were incorrect. Table B's
physical output assignment is still unresolved. The old cam-solenoid labels
must not be used to select an output.

Fan duty is float percent at `0xFFFFCD54`; the native route is
`0x3FD8C → 0xE8C4 → 0xFFFFF590`. Period state is `0xFFFFAB84`.
Fan mode uses RAM bytes `0xFFFFCD7F` and `0xFFFFCD80`: ROM literal locations
`0x3F97C` and `0x3FA80` contain those pointers. The old `0xFFFFF97C` and
`0xFFFFFA80` hardware-address claims were false.

Actual CPC purge duty is `0xFFFFB6D4`, modeled flow `0xFFFFB6D8`.
Writer `0xB182` publishes a scaled request at `0xFFFFAB64`, through a pointer
to `0xFFFFAB60`; this alone does not identify the final pin or polarity.
Main deletes CPC command/flow and bank purge subtraction while preserving fan
control. The former fan-as-purge repurpose instructions are retracted.

## Sensor and RAM references

MAP raw ADC is u16 `0xFFFFAB04`, filtered ADC is u16 `0xFFFFABC8`, and the
converted pressure is float mmHg absolute at `0xFFFFABC4`. Routine `0x7A14`
performs the conversion. The current external wideband uses former-MAF ADC
`0xFFFFAB06`; the older single-front-A/F design used different channels.

Use [signals](reference/SIGNALS.md) for types, units and producers,
[logger contracts](reference/LOGGER.md) for exported sources, and
[methods](reference/METHODS.md) for sign-extended literals and computed access.
Hardware names are checked against the
[Renesas SH7055S manual](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual).
Physical harness assignments require separate evidence.
