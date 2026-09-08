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
- `romraiderlog_idle_diagnostic2_20260908_141335.csv` contains 2,510 samples
  and 19 channels on the `6af0d1...` candidate, verified against recorded flash
  CRCs. Settled fueling improves, but blips nearly stall the engine. The user
  confirms intentional key-off at the end. Its AVLS units label contains an
  unquoted comma; the [analysis](20260908_recovery_review.md) normalizes that
  exact header in memory without changing the source CSV.

`20260908_recovery_review.json` contains summaries and explicitly conditional
timing-table comparisons; the associated PNG plots recorded channels. These
are derived review artifacts, not another ECU capture.

`20260908_load_recovery_replay.json` contains native load-filter/B874 replay
and in-memory alpha sensitivity on the fixed 14:13 engine trajectory. It is
not a new log or an engine prediction. The [follow-up audit](../master_patch/IDLE_AIR_RECOVERY_AUDIT.md)
documents its limits and the new idle-air request profile for the same BIN.

`20260908_transient_replay.json` contains **offline model outputs**, not new
ECU measurements. It replays the complete capture through the retained B874
correction and fuel composer; assumptions and the separate VE candidate are
documented in [the recovery audit](../master_patch/IDLE_RECOVERY_AUDIT.md).

The installed seller-labelled 50-4110-style controller is suspected to be a
clone. Agreement between its display and ECU analogue input does not validate
the measured AFR, so these files are evidence for diagnosis only.
