# Post-audit repository cleanup

[Reference home](README.md) · [Document register](DOCUMENT_REGISTER.md)

Requested September 9, 2026, after audit commit `46bfc52`. This change organizes
the repository and preserves the completed audit's source provenance.

- 27 historical documents moved to [docs/archive](../archive/README.md), with
  banners identifying their historical scope and links to corrected conclusions.
- Two specialist hardware sources moved to [docs/hardware](../hardware/README.md).
  The rotational-idle guide now sits with its [component](../../patches/core/ROTATIONAL_IDLE.md).
- 17 analysis/helper scripts moved to [tools/analysis](../../tools/analysis/README.md).
  Artifact paths still resolve to the same saved ROMs and logs.
- The root and master READMEs now describe current build differences and the
  outstanding combined v1/v2 fix set. Their original versions are archived.
- Documentation links and analysis/test imports follow the new layout. A small
  logger-audit compatibility page preserves the unchanged adapter's link.
- The source inventory reproduces text from the reviewed Git commit and the
  original baseline. Source hashes/line numbers and current file locations are
  recorded separately. All 44 original documents and 1,187 reviewed address
  candidates remain represented.

No firmware implementation, calibration, BIN, definition XML, raw capture,
Ghidra project or protected v2/adapter file is changed. Historical candidate
ROMs and memory-only prototypes retain their original purpose; no combined
or replacement ROM is produced by cleanup.

## Verification

The full main verifier, v2's three existing checks, eight image-specific
load-fallback cases and all 16 prototype tests passed. All 17 moved modules
import from outside the repository; all 12 argument-based entry points display
their help successfully. Syntax checks passed for 86 Python files, and all
1,814 local documentation links resolve. Comparison against the starting
commit found no changes in 196 protected tracked files. Regenerating the four
documentation index/register outputs produces identical bytes.

The final checks are recorded in
[cleanup_verification.json](evidence/cleanup_verification.json). The main
verification includes its in-memory rebuild and existing instruction suite;
v2's three existing checks remain narrower. Regeneration of the documentation
inventory must preserve the audited candidate/claim set and authored meanings.
