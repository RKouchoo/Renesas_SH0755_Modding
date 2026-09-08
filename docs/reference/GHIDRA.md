# Ghidra project and MCP audit trail

[Reference home](README.md) · [Exact mutation ledger](evidence/ghidra_changes.json)

The audit used the connected **Ghidra MCP server**, operating on the stock
`2005 BLE MT.bin` program in `Renesas_SH0755_modding`. Stock-program annotations
describe patched behavior only when explicitly scoped to main or v2. The
stock binary on disk was not patched.

## Verified live updates

Readback confirms **38 routine names, 10 existing data labels, 67 instruction
comments and 4 decompiler comments** across **129 mutation attempts**. Two
additional descriptor comments returned success but the MCP
data listing does not expose their comment text for independent readback.

The routine updates cover the injector timer path, protected-record integrity,
coolant and paired-pedal processing, purge state and fuel compensation,
legacy-O₂ consumers, throttle requests, idle target and corrected FPU-stop
handling. Data labels cover the timer and feedback descriptor bases,
MAP raw/pressure channels, pedal, injector inhibit word and defined fan registers.

Comments record the verified ADC-word type, descriptor fields, fan/purge
distinction, corrected fan RAM literals, image-specific load fallback,
transient correction identity, barometric source, checksums, cut locking,
logger size limit and ignition arrays. Producers/readers are annotated where
the affected RAM object cannot currently be defined through MCP.

## Server limitations that matter

This server's `rename_data` implementation only renames an already-defined
Data item. It returns “Rename data attempted” even for a no-op. Eight attempts
could not be verified: ABC8, CD7F, CD80, F602, F640, F650, F652 and F444.
They remain explicit no-ops in the ledger rather than claimed successes.

The server has no exposed endpoint to create Data, create/split/join memory
blocks, create missing functions, execute a script or explicitly save a
program. A successful annotation transaction and readback establishes live
project state; it does not establish an explicit save/reopen cycle. Project
recovery snapshots are not described as a verified final save.

`set_decompiler_comment` writes a PRE comment, not a function PLATE comment.
Consequently, a decompile can still show an old plate interpretation above
the verified correction inside the body. The old vehicle-speed plate at
`17984` is an example. The repository naming scripts contain corrected plate
text for later reapplication; this audit does not claim MCP removed every
old plate comment. The new comments and names are independently read back.

## Memory-map correction prepared in the repository

Current MCP block listing:

| Block | Current range | Assessment |
|---|---|---|
| `ram` | `00000000–0007FFFF` | Saved flash. |
| `RAM` | `FFFF0000–FFFFBFFF` | Incorrect physical range. |
| `IO` | `FFFFE400–FFFFFFFF` | Broad peripheral analysis mapping. |

The corrected physical RAM range is **`FFFF6000–FFFFDFFF`**. The
[setup helper](../../ghidra_sh7055_setup.py) now uses it. For a fresh import,
it creates that range. For an existing overlapping block, it stops with a
specific error rather than silently keeping the wrong geometry or deleting
analysis. It does not pretend to migrate the open project.

A later block migration must preserve existing RAM labels/comments while
removing the falsely mapped prefix and adding `C000–DFFF`. It should be
followed by checking key Cxxx/Dxxx state and the `FFFFDFA0` stack label,
then an explicit save/reopen check. This remains a tooling limitation under
the requested MCP-only workflow; no UI workaround was used after that request.

## Evidence files

| File | Purpose |
|---|---|
| [ghidra_snapshot.json](evidence/ghidra_snapshot.json) | Final September 9 MCP inventory: 2,764 functions, 304 scoped data labels from 30,572 listed items, and observed segments. |
| [ghidra_evidence.json](evidence/ghidra_evidence.json) | Captured disassembly and address xrefs, including corrected producer comments. |
| [ghidra_changes.json](evidence/ghidra_changes.json) | Every mutation, response, readback and no-op. |
| [fixture_accesses.json](evidence/fixture_accesses.json) | Existing verifier's bounded access observations, separated by image variant. |
| [local_instruction_supplement.json](evidence/local_instruction_supplement.json) | Explicit local SH-2E byte windows where MCP had no defined function; not mislabeled as MCP disassembly or execution. |

The evidence is retained in the repository so a new chat can inspect the
reasoning without relying on unsaved conversation history or existing names.
