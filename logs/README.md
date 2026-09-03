# Captured commissioning logs

These CSVs are preserved outside `master_patch` as diagnostic inputs. They are
not generated patch artifacts and must not be treated as calibration approval.

- `romraiderlog_20260903_022932.csv` is the engine-off/invalid capture used to
  establish that the earlier file did not contain the reported start.
- `romraiderlog_20260903_023334.csv` contains the cold-start lean-out event
  analysed in `../master_patch/GHIDRA_AUDIT.md` and `../audit.md`.

The installed seller-labelled 50-4110-style controller is suspected to be a
clone. Agreement between its display and ECU analogue input does not validate
the measured AFR, so these files are evidence for diagnosis only.
