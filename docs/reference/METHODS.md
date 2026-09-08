# Reverse-engineering and verification methods

[Reference home](README.md) · [Evidence index](ADDRESS_INDEX.md)

## What counts as evidence

Unprefixed ROM/RAM addresses and masks are hexadecimal. Table dimensions,
byte lengths and call counts are decimal; physical values carry their units.

The address index separates structural checks from semantic verification.
Saved bytes establish a literal, table value or installed hook. MCP disassembly
and xrefs establish the analyzed instruction/caller relationships. Bounded
instruction fixtures establish behavior for their supplied inputs and modeled
callees. None alone measures the engine or proves a hardware output assignment.

`verified_dependency` certifies only the stated direct read, such as a generic
`engine_load_dependent_*` label. `verified_build_contract` certifies an exact
current image range or mutation, not every historical owner of that address.
An unresolved meaning can have valid byte, xref and fixture evidence while its
full algorithmic identity remains unproved.

The stock SHA in the evidence pins the local file. The MCP program is named
`2005 BLE MT.bin`; its literal values and code are cross-checked against that
file. The MCP interface does not expose a complete program-memory hash.
Generated main/v2 code is checked against their builders and saved bytes, not
mistakenly looked up as injected code in the stock-only Ghidra program.

## Literal decoding and computed addresses

For a SH instruction at PC:

| Instruction | Pool location | Interpretation |
|---|---|---|
| `MOV.W @(disp,PC),Rn` | `PC + 4 + 2*disp` | Sign-extended 16-bit word. `C17C` becomes `FFFFC17C`; `1234` stays `00001234`. |
| `MOV.L @(disp,PC),Rn` | `(PC & ~3) + 4 + 4*disp` | Big-endian 32-bit value. It may be a pointer, integer or float bits. |
| `MOVA` | Same aligned longword formula | Produces the pool address, not its contents. |

Do not extend a ROM pool address into the I/O range. The corrected
`3F97C -> FFFFCD7F` fan example shows why. Likewise `FAE8` is a descriptor
field address, not necessarily the descriptor base. A byte pattern matching
an address can also be an opcode or a constant; scans retain that uncertainty.

Xrefs do not enumerate all indexed accesses. Injector records at
`BFB8 + n*28`, cylinder arrays, descriptors and stack traffic need interval
ownership. The relocated `verify_regions.py` now reports literal-match gaps
as gaps, not proven scratch RAM, and uses the corrected physical RAM bounds.

MCP function boundaries can split a shared tail. For example, `3D95A` sets
CCE1/CCE2 to FF and falls through into separately defined `3D964`, which
conditionally reaches the six-float clear at `3D980`. A short listing without
an RTS is not evidence of a broken return path; follow fall-through and branch
destinations before assigning the complete routine behavior.

## Native lookup ABI and data layout

| Entry | Input | Result / role |
|---|---|---|
| `209C` | R4 descriptor, FR4 x | Single-axis float result in FR0. |
| `2150` | R4 descriptor, FR4 x, FR5 y | Two-axis float result in FR0. |
| `20E0/2118` | Single-axis descriptor and float x | Raw u8/u16 interpolated result converted to integer. |
| `2194/21B0` | Two-axis descriptor and float axes | Raw u8/u16 interpolated result converted to integer. |
| `26E0` | Float axis search inputs | Interval index plus interpolation fraction; clamps outside endpoints. |
| `27D0` | Two axis-search inputs | Performs both searches. |

A one-axis descriptor has u16 length at `+0`, type byte at `+2`, axis pointer
at `+4`, data pointer at `+8`, and, for integer data, float scale/offset at
`+C/+10`. Float-only descriptors can occupy 12 bytes. A two-axis descriptor
has u16 x/y lengths at `+0/+2`, axis pointers at `+4/+8`, data at `+C`,
type byte at `+10`, and scale/offset at `+14/+18` when applicable.

Type bytes index the handler tables: `00` float32, `04` u8, `08` u16,
`0C` s8, `10` s16. Data rows use `row * x_count + column`. A data-pointer
xref must be traced back by the appropriate field offset before querying
descriptor users. Base Timing A is a concrete example: data `78AA0`, pointer
slot `60114`, descriptor `60108`, consumer `28418`.

Those type/scale fields apply to the **typed dispatchers**. The raw entry
points select their own element width and do not read a scale/offset pair.
For example, `608D8`, `5F8FC` and `5FFF8` are 12-byte records consumed by
the raw-u16 entry `2118`; `5F21C` uses raw-u8 entry `20E0`. Interpreting the
following record as scale/offset, or inferring float data from a zero type
byte, gives the wrong schema. The generic index recognizer deliberately
reports only candidates. [Reviewed table decodes](evidence/documented_data.json)
select the schema from the caller/callee and retain all three images' axes
and data. [Scalar decodes](evidence/documented_scalars.json) retain reviewed
access widths and exact values separately.

For finite, ordered axes, out-of-axis lookup inputs clamp at endpoints.
That is separate from the SD wrapper's own validity checks. A valid low MAP
must not be rejected solely because it lies below the first VE knot. A
malformed descriptor, NaN input or electrical fault is a different condition.

Important math helpers include `2424` (first-order filter with snap), `2458`
(guarded division), `24C0` (clamp), `24FC` (difference/tolerance check),
`257C` (u16 affine float conversion) and `25CC` (integer filter with Q8
coefficient). `257C` is generic: its call-site scale determines whether the
result is volts or another unit. `25CC`'s literal `25F4` is exactly 1/256.

`49530` publishes a protected eight-byte RAM record: float value at `+0` and
two copies of the complemented sum of its halfwords at `+4/+6`. It rejects
NaN and locks the publication with `3AF4(10)/3B08`. `B536` merely calls it
with zero for records `803C/8044`; the old FP-register-support label was wrong.
`16CA4` similarly initializes protected coolant records. The conditioned
coolant publisher is `16B04`, not `16CA4`.

## SH-2E floating point and ABI

The Ghidra SuperH4 language is an analysis approximation. SH-2E uses its own
single-precision behavior; do not accept a double-precision-looking decompile
or host rounding as proof. The independent interpreter models truncation,
denormal handling, finite overflow and multiply-then-add behavior. FPSCR
exception delivery, status flags and NaN payload propagation remain excluded.
See [arithmetic implementation](../../tests/sh2e_test_fpu.py) and its tests.

The [Renesas SH-2E software manual](https://www.renesas.com/en/document/mah/sh-2e-software-manual)
describes interlocks and the 13-cycle FDIV E1 stage. Those waits preserve
dependencies. An immediately consumed result is not evidence of a persistent
software freeze. The emitted SD wrapper contains no FDIV; stock axis helpers
can divide for interpolation. The existing FPU census is an instruction count,
not measured utilization or a deadline guarantee. The 40-MHz clock remains an
assumption until measured on the target.

Hooks must preserve caller state, PR, callee-saved integer/float registers and
stack balance, including delay slots. The SD wrapper uses the caller's saved
FR15 RPM and one MAP/IAT snapshot each. Its own maximum frame is 16 bytes;
the traced lookup chain gives 28 bytes of additional depth, excluding existing
caller and interrupt frames. That does not establish total stack headroom.

## Scheduler and injector boundaries

The native phase task can outrank the calculation task. Added cuts protect the
whole native decision plus added inhibition with `3AF4(10)/3B08`, preserving
the prior mask and dispatch behavior. Publishing a status bit after releasing
the native lock leaves a race. Tests execute the scheduler/context paths and
include altered-lock negative controls.

`26AEC` can defer record inhibition once a pulse has been handed to the timer.
The record catches up at its phase boundary. `26F8C` exports scheduled pulse
width from record state; it is not a physical on-time measurement. Device
queues, intercepted helper calls and interrupt injection have explicit fixture
boundaries in the [scheduler audit](../archive/master_patch/INJECTOR_SCHEDULER_EXECUTION_AUDIT.md).

## Editor and logger methods

The earlier reported float-axis byte-order error was a false positive. In the
installed RomRaider legacy reader/writer, an unspecified memory-model byte
order leaves big-endian ByteBuffer behavior; the existing `little` float label
does not make these axis bytes swap. The checked implementation is
`RomAttributeParser.java` in the local RomRaider source, lines 252–285. No
firmware or XML byte-order correction was applied. A future parser/version
change needs its own check; XML spelling alone is insufficient evidence.

SSM RAM addresses omit the leading byte (`FFABC4` corresponds to
`FFFFABC4`). Length and storage type still matter. Multi-byte values are
sequential reads and are not guaranteed coherent across an ECU update.
RomRaider highlights using formatted logger values, so an axis must use the
matching logger source and display units; there is no automatic pressure-source
or unit conversion. See [logger reference](LOGGER.md).

## Reproducing the audit

```sh
python3 -B tools/documentation_inventory.py
python3 -B tools/audit_image_contracts.py
python3 -B tools/trace_audit_fixtures.py
python3 -B tools/build_reference_index.py
```

The inventory retains original claims and source locations. MCP evidence was
captured through the connected server and stored separately. The fixture trace
observes the existing verifier, separates immutable image variants by hash and
includes negative controls. A visited PC can be intercepted by a fixture; it
must not be described as measured instruction retirement. The generated index
keeps these structural/fixture observations separate from reviewed meanings.
The document set is pinned to commit `2d95301`. Working-tree source locations
are hashed, and claims removed or rewritten during this audit are retained
from the baseline with their original revision and line number. This also
preserves corrections to the evidence, instead of erasing the earlier claim.
