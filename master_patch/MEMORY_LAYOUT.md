# Master-patch memory ownership

The master verifier treats injected flash, stock hook sites, and calibration writes
as distinct ownership classes. A
build fails on any overlap except the explicit replacement of boost component
seed data by the final boost calibration.

Current corrected master SHA-256 is
`5a1b3e389bdb1a6099b6ed39c3f59d53dfc1808b2d16e56f05148c127c4f48b5`
(checksum `0xCAACD6C4`). The fan/purge repair adds no RAM or free-flash
allocation; the contiguous unallocated tail remains 3,344 bytes.

## Injected flash

| Range | Owner |
|---:|---|
| `0x7D790..0x7D80F` | Legacy actuator descriptors/data and independent hard-cut enable; actuator data is inert. |
| `0x7D810..0x7D8BB` | Retired actuator reservation: `RTS; NOP`, then erased bytes (172 bytes). |
| `0x7D8BC..0x7D8C3` | Inert former throttle gate and active hard-overboost limit. |
| `0x7D8C4..0x7D903` | Independent rev-limiter/hard-overboost fuel-cut wrapper. |
| `0x7D91C` | Master wideband/O2 architecture signature. |
| `0x7DB40..0x7DCEB` | Integrated default-OFF rotational-idle calibration and wrapper. |
| `0x7DD00..0x7E18B` | Speed-density calibration, descriptors and original seed data. |
| `0x7E18C..0x7E3A3` | Hardened dual-VE speed-density wrapper (536 bytes including literals). |
| `0x7E3A4..0x7E3FF` | Unused speed-density reservation (92 bytes). |
| `0x7E400..0x7E41B` | Wideband constants. |
| `0x7E440..0x7E51B` | Wideband update routine. |
| `0x7E520..0x7E53B` | Shared closed-loop inhibit helper. |
| `0x7E560..0x7E63F` | Retired actuator-guard reservation: `RTS; NOP`, then erased bytes (224 bytes). |
| `0x7E640..0x7E667` | Low/high dual-VE descriptors. |
| `0x7E668..0x7E6B7` | Low/high dual-VE RPM axes. |
| `0x7E6B8..0x7EAC7` | Low/high dual-VE data. |
| `0x7EAC8..0x7EAEB` | Pressure-open-loop and lean-cut switches/calibration. |
| `0x7EB20..0x7EB9B` | Stock-target-first pressure/open-loop wrapper. |
| `0x7EBA0..0x7EBB7` | Explicit lean-state zero initializer. |
| `0x7EC00..0x7EDE7` | Composed rev-limit/overboost/latched-lean-cut wrapper. |
| `0x7EDE8..0x7FAF7` | Unallocated contiguous verified free flash remaining in the checksum range (3,344 bytes). |

The critical boundary is exact: the wideband component ends at `0x7E63F` and
the speed-density component's dual-VE data segment starts at `0x7E640`. Component builders also require every destination
byte of a free-flash blob to remain `0xFF` before writing. In-place stock
replacements instead require their exact pinned original bytes.

## Intentional composition

- `0x7D80C` remains `00` as an inert legacy byte, with no live actuator code or
  tuning definition. `0x7D80D` is the independent exact-`01` hard-overboost-cut
  enable and defaults `01`.
- `0x3FD8C` is the stock **radiator-fan** output literal, not a purge hook.
  It remains `0x0000E8C4` in the corrected build. No custom controller or guard
  is in the fan path. Older builds incorrectly composed this pointer through
  the two now-retired reservations; those images must not be run.
- Final calibration deliberately replaces only boost target data, base duty,
  Kp, maximum duty ratio, soft overboost, and hard overboost seed data. The
  verifier requires this exact intersection and rejects any other calibration
  contact with injected flash.
- Dual-VE selection is built directly into the one speed-density wrapper. There
  is no second patch stage or shared wrapper ownership.
- Stock literal `0x173FC` is locally redirected from `0x65168` to existing
  constant-zero helper `0x27088`. This bypasses the obsolete MAF-fault load
  substitution only in the retained airflow task; neither shared helper bytes
  nor other diagnostic users are modified.

## In-place actual CPC purge delete

| Range | Replacement |
|---:|---|
| `0x1BAF0..0x1BB17` | 40-byte stackless dispatcher replacement: clears CPC duty `B6D4`, modeled flow `B6D8` and mode `B720`, then tail-calls stock `0xB182` with zero duty. |
| `0x23054..0x2305B` | 8-byte leaf: stores exact positive zero to the stock bank destination in R4 and returns. Both callers still select `BE60` / `BE64`. |
| `0x5BD85..0x5BD86` | Verified P0458/P0459 circuit switches set to zero. |

These 50 bytes have explicit stock-hook ownership, not free-flash ownership.
The component checks all expected bytes before any mutation, preserves the
actual CPC output writer and zero-request initializer, and does not claim
physical output polarity. Both replacement leaves preserve PR and callee-saved
registers and add no stack frame. Residual filter state cannot produce either
bank subtraction because the final publisher stores zero independently of it.

## RAM

The retained-sensor correction additionally owns 24 in-place bytes:
`0x73E08..0x73E0F` (four Q15 unity atmospheric coefficients),
`0x76384..0x7638B` (two zero auxiliary O2-dependent fuel adders),
`0x760F0..0x760F3` (zero legacy-voltage bank target offset), and the instruction
words at `0x202CC/0x202D0` (`fldi0 fr4` excludes legacy voltage trim from each
lambda target). The wideband component guards the surrounding code, literals,
bank/lookup descriptors and existing data before writing. Only exact installed
instruction replacements are normalized when checking consumer hashes.
It adds no RAM or free-flash allocation.

The fueling-safety component reserves `0xFFFFC85C` as a 16-bit task-call counter
and `0xFFFFC860` as an 8-bit state (`0` idle, `1` sensor delay, `2` monitoring,
`3` cut latched). These were rear-O2 response-integrator locations. The component
refuses to install unless all five traced rear-O2 runtime tasks have already been
bypassed. It repoints the stock float-1.0 initializer at task pointer `0x1055C`
to an explicit zero initializer at `0x7EBA0`. Other injected code uses only the
SH stack and already-mapped stock signals.
The purge delete writes only its existing stock duty, modeled-flow, mode and
bank-subtraction locations. It claims no new RAM and does not repurpose any
fan or cam state.
The hardened SD wrapper adds no static RAM: its maximum own frame is 16 bytes
(saved FR12/FR13/PR plus a temporary product). Including the selected stock
lookup helpers gives a statically traced 28-byte additional depth at this call
site, excluding interrupt frames and the caller's pre-existing frame. Total
runtime stack headroom remains unmeasured. The wrapper is 16 bytes smaller than
before; the contiguous 3,344-byte free tail is unchanged.

`python3 master_patch/verify_master_patch.py` checks all declared blob ranges,
stock hook ranges, calibration ranges, the rotational-idle component,
undeclared changed bytes, fresh-rebuild equality, checksum, and pinned output
hash.
