# Project tools

[Analysis and replay tools](analysis/README.md) hold the historical capture
analyses and unintegrated experiments formerly mixed into `master_patch/`.
The scripts below reproduce the completed documentation audit.

These scripts inspect saved files and run existing offline fixtures. They do
not connect to an ECU. Run from the repository root:

```sh
python3 -B tools/documentation_inventory.py
python3 -B tools/audit_image_contracts.py
python3 -B tools/audit_documented_data.py
python3 -B tools/trace_audit_fixtures.py
python3 -B tools/build_reference_index.py
```

| Tool | Purpose |
|---|---|
| `documentation_inventory.py` | Reproduce the original `2d95301` document set using source text at audited commit `46bfc52`; retain superseded claims and map files to their current locations. |
| `audit_image_contracts.py` | Verify the original stock/main/v2 images at `2d95301`, descriptor records and fan pointers; replay the pre-fix MAF-fault load difference. |
| `audit_documented_data.py` | Decode 39 lookup records using explicitly reviewed native schemas and 76 scalar/array records; retain exact stock/main/v2 bytes and values. |
| `trace_audit_fixtures.py` | Observe the existing full master verifier, separating immutable image variants and recording bounded RAM/I/O accesses and visited PCs. |
| `build_reference_index.py` | Join the inventory, retained MCP captures, reviewed meanings, fixture observations and XML declarations into the central index and completed document disposition register. |
| `inspect_routine_evidence.py` | Print retained routine claims and SH-2E instructions with literal values from pinned stock bytes; an inspection aid, not an automatic semantic reviewer. |

For example, `python3 -B tools/inspect_routine_evidence.py 217B8` shows the
legacy O₂ dispatcher. Add `--brief` to show only claims and pool-bearing
instructions. MOVA targets may be jump tables or data, so a displayed float
interpretation alone does not establish their type.

Outputs live in [reference evidence](../docs/reference/evidence/). The toolchain
does not replace the reviewed-meaning ledger with guesses from Ghidra labels.
The source-text inventory is frozen to its reviewed Git revision; later edits
are not silently counted as audited. Current document moves are recorded in
[document_locations.json](../docs/reference/document_locations.json).
`_audit_images.py` retrieves the original audit images and definitions from
Git and checks image hashes, allowing the saved master artifacts to keep
rolling. This preserves the old v2 omission as evidence. Use the
[v2 verifier](../master_patch_v2/verify_master_patch.py) for the current repair.
MCP captures and annotation readbacks were collected through the connected
server; these scripts consume those saved records rather than pretending to
refresh the open program. See [methods and limitations](../docs/reference/METHODS.md).
