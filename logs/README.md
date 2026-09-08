# Captured commissioning logs

These CSVs are preserved outside `master_patch` as diagnostic inputs. They are
not generated patch artifacts and must not be treated as calibration approval.

- `romraiderlog_20260903_022932.csv` is the engine-off/invalid capture used to
  establish that the earlier file did not contain the reported start.
- `romraiderlog_20260903_023334.csv` contains the cold-start lean-out event
  analysed in `../master_patch/GHIDRA_AUDIT.md` and `../audit.md`.
- `romraiderlog_20260908_120702.csv` and
  `romraiderlog_firstidlelog1_20260908_121839.csv` contain headings only;
  they are logger-failure evidence, not engine traces.
- `romraiderlog_idle_diagnostic_20260908_123651.csv` contains 1,786 complete
  samples on the user-confirmed 10:30 BIN. It captures improved steady idle
  followed by near-stall RPM and lean recovery after throttle blips. The user
  reports the physical gauge followed RomRaider. See
  [the numerical review and chart](20260908_idle_review.md).

The installed seller-labelled 50-4110-style controller is suspected to be a
clone. Agreement between its display and ECU analogue input does not validate
the measured AFR, so these files are evidence for diagnosis only.
