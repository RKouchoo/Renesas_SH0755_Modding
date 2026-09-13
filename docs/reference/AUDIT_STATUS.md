# Audit scope, results and limits

[Reference home](README.md) · [Findings](FINDINGS.md) · [Address index](ADDRESS_INDEX.md)

The later [full process-flow review](PATCH_PROCESS_FLOW.md) is **in progress**.
It expands the scope to every patch touchpoint and its transitive native
dependencies. Completion of the historical address inventory below does not
mean that broader state-machine review is complete.

Its latest [consolidated native results](evidence/process_flow_tests_20260912.json)
passes 354 groups with the captured loaded-drive image explicitly pinned.
The new [flow document](PATCH_PROCESS_FLOW.md) separates those bounded results
from open fault/arbitration edges and unmeasured scheduling limits. The [OCV repair](AVCS_OCV_REPAIR_20260913.md) now changes both rolling BINs: the
former rear-O2 bypass removed native AVCS feedback/output. Earlier conclusions
endorsing that deletion and its RAM reclamation are retracted. Vehicle
resolution remains unproven.

Started September 8, 2026 from commit `2d95301`; this report was finalized
September 9 in Australia/Sydney. The audit used the connected Ghidra MCP
server, saved images, source builders and offline instruction fixtures.

This page records the completed audit and its original image identities.
The subsequent [v2 bypass repair](V2_LOAD_FALLBACK_FIX.md) has its own bounded
regression evidence; it does not retroactively change the audit snapshot.

## Repository organization and preservation

Shared components are grouped under `patches/`. Thirty-seven existing Python
test/verifier/helper files moved into `tests/`, alongside one new import-path
helper. `master_patch/` retains its builder, calibration, normal artifacts and
profiles. Its former verifier path remains a small
compatibility entry point for existing workflows.

V2 has only five Python files with component/path reference changes. Its
runtime source behavior, calibration, BIN and XML are unchanged. The K-line
adapter, raw logs, stock inputs, generated main artifacts and the user's
independent dashpot BIN are unchanged. Comparing the 2,884-file protection
manifest found no unexpected differences; permitted differences were those
five v2 source files and Ghidra project database files.

The completed audit was committed as `46bfc52`. After the user requested
cleanup, 27 historical documents moved into `docs/archive/`, two specialist
sources into `docs/hardware/`, and the rotational-idle guide alongside its
component. Seventeen analysis/helper scripts moved from `master_patch/` into
`tools/analysis/`. Concise project/build guides replace the two archived
overviews. The [disposition register](DOCUMENT_REGISTER.md) covers all 44
original documents; unique investigation evidence was retained.

The source inventory now reads the exact audited document text from `46bfc52`,
plus superseded claims from `2d95301`, while separately recording current
locations and hashes. The same 1,187 candidates and 3,000 claims are retained.
This makes the completed audit reproducible after moves and later edits.
See [cleanup verification](REPOSITORY_CLEANUP.md) for the subsequent checks;
the audit results below retain their original scope and counts.

## Address review coverage

The inventory contains **44 documents, 1,187 address
candidates and 3,000 source occurrences**.
These include addresses, range endpoints, numeric constants, opcodes and
historical claims; they are not 1,187 independently verified variables.

- All **245 on-chip-RAM candidates** have an explicit scoped review outcome,
  including corrected identities, prototype-only locations and boundaries.
  Some conclusions establish only width, producer or a limited dependency.
- All **24 peripheral/boundary candidates** have an explicit outcome,
  including the two false fan-address claims.
- All **392 inventoried Ghidra routine entries** have captured disassembly and
  authored reviews of their documented contracts. The original 390 entries
  and two entries introduced by corrections are covered. Broader physical or
  algorithmic meanings remain limited where only a dependency was established.
- All **1,187 candidates** have a scoped authored outcome; **zero remain
  unreviewed**. The index distinguishes 557 static reviews, 249 bounded
  execution reviews, 80 dependency reviews, 137 build contracts, 123 corrected
  claims, 31 numeric literals, 6 prototype locations, 2 hardware bounds and
  2 incorrect address claims. These outcomes do not certify every possible
  input, physical identity or existing label.
- The evidence includes **764 MCP capture records** covering 408 distinct
  routine bodies (23 additional routine queries had no defined body), exact
  stock/main/v2 bytes, 39 explicitly typed lookup records,
  76 scalar/array records, and XML address declarations at **67** candidates.
  XML matches are address declarations, not independent proof of runtime use.

The address/routine review and central consolidation are complete for this
inventory. Missing physical evidence and MCP capabilities are documented
audit results, not items silently counted as verified.

The candidate extractor handles explicit hex, selected inline abbreviations
and RAM-qualified continuations. It cannot guarantee discovery of every
implicit address in prose. Structural classifications and semantic outcomes
remain separate in [address_audit.json](evidence/address_audit.json).
The [findings register](FINDINGS.md) explains the 34 corrections and the
remaining physical/software questions.

## Verification results

| Check | Result and boundary |
|---|---|
| Full rolling-main verifier, before and after moves | PASS: deterministic in-memory rebuild, hashes/checksum, ownership, calibration, definitions, logger and execution groups. Final integration run also passed. |
| Existing v2 verifier, before and after moves | PASS: its three checksum/layout/definition checks. This is narrower than the main suite. |
| Image-specific audit contracts | PASS: three exact image pins, both timer descriptor tables, fan literals and eight main/v2 load-fallback cases. |
| Existing fixture trace | PASS: 4,155 access groups across image variants; main has 12,875 visited PC addresses. Intercepted/simulated callees and negative controls are explicitly identified. |
| Standalone boost donor and combined verifiers | PASS against temporary component builds after correcting stale pre-lock wrapper instruction checks. Runtime code unchanged. |
| Standalone speed-density verifier | PASS against its own temporary standalone build, not a substituted main/v2 image. |
| Moved MAP-boundary and SSM scripts | PASS as direct CLI entry points: six and three test groups respectively. |
| RomRaider toggle/layout checks | PASS; existing BIN/XML bytes preserved. |
| Reviewed native data schemas | PASS: 39 lookup and 76 scalar/array decodes against exact stock/main/v2 hashes; raw and typed ABIs are kept separate. |
| Python syntax and import checks | PASS: 86 Python files parse; analysis imports and relocated shared test helpers resolve. |
| Documentation links and diff whitespace | PASS: 1,663 local links resolve; `git diff --check` is clean. |
| Region-inspection utility | Runs with corrected physical RAM bounds; literal-reference gaps are no longer described as proven spare RAM. |
| Protected-file comparison | PASS; no unexpected protected-file changes. |

Main SHA-256 at audit completion:
`154760a5f2fdadbf6d9221480595f58dc77c6a4eccc492f50899c815aca79e4d`.
V2 SHA-256 at audit completion, before the later bypass repair:
`2fe5f9cc7f960bff1efd784bb29e6c984ccbc025f1d8029c920fd52a3ce25ac9`.
The standalone images used for verification live only in ignored
`tmp/documentation_audit/`; they are not new release or flashing candidates.

Reproduce the core checks with the commands in [Methods](METHODS.md) and
[tests/README.md](../../tests/README.md). Machine-readable captures are retained
under [evidence/](evidence/). Test success does not establish vehicle behavior,
physical output mapping, deadline margin or the cause of the near-stall.

## Ghidra outcome and remaining limits

MCP readback confirms **38 routine names, 10 data labels, 67 instruction
comments and 4 decompiler comments**. Two descriptor comments returned success without independent
comment readback. Eight undefined/unmapped data-label attempts were no-ops,
with the conclusions recorded at mapped producers/readers instead.

The connected MCP server cannot modify memory blocks or explicitly save the
program. The live RAM block is still the incorrect `FFFF0000–FFFFBFFF`;
physical RAM is `FFFF6000–FFFFDFFF`. The repository setup helper is corrected
and rejects that overlap without destroying analysis. An explicit disk
save/reopen cycle and block migration remain unverified. Old PLATE comments
can coexist with corrected PRE comments because the MCP endpoint writes only
the latter. See the
[Ghidra ledger and limitation](GHIDRA.md).

The audit does not resolve the vehicle near-stall or certify every historical
routine interpretation. Conditional v2 MAF-fault load substitution is proven
in saved-image fixtures; activation in a capture is not. No arbitrary MAP
intercept, transient gain, load-filter or dashpot change was made here.
