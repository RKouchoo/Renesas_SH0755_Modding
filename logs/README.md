# Captured commissioning logs

These CSVs are preserved outside `master_patch` as diagnostic inputs. They are
not generated patch artifacts and must not be treated as calibration approval.

The [14:42 adjusted-VE drive](../docs/reference/V2_AVLS_MISFIRE_20260912.md#1442-adjusted-ve-drive-loaded-fault-persists)
reproduces the loaded bog on the verified `fd795813…` image. Its
[derived evidence](20260912_adjusted_drive_review.json) records the low-lift
loaded event, fuel arithmetic and conditional cut replay. No new road
capture is requested, and no cure has been established.

The [14:13 warm fueling review](../docs/reference/V2_AVLS_NEUTRAL_20260912.md#1413-warm-fueling-sustained-enrichment-follows-calculated-load)
records lean idle and sustained rich high-lift holds with reported OL status.
The resulting [VE adjustment evidence](20260912_fueling_adjustment_review.json)
contains the ten edited cells, original words for capture reconstruction,
and conditional replay estimates. Those estimates are not a new engine log.

The [13:37 neutral follow-up](../docs/reference/V2_AVLS_NEUTRAL_20260912.md#1337-follow-up-changeover-now-occurs)
verifies the corrected v2 flash and two stationary high-lift entries with both
solenoids responding and no pedal-applied fuel cut. The driver reports it felt
fine. Its [JSON](20260912_avls_neutral_followup_review.json) also records the
repeatable richening and an explicitly conditional airflow/table replay.

The [13:16 neutral AVLS review](../docs/reference/V2_AVLS_NEUTRAL_20260912.md#1316-baseline-capture-and-firmware-identity)
checks the complete AVLS/cut capture and its flashed image. It stayed in low
lift and exposed the stationary oil-gate calibration error now corrected in
both rolling builds. Its JSON contains derived summaries and flash evidence.

The [September 12 rotational-delete review](../docs/reference/V2_AVLS_MISFIRE_20260912.md)
matches the flashed image and compares three loaded AVLS transitions. Its
[chart](20260912_rotationaldelete_review.png) and JSON are derived artifacts.
The review separates the high-lift-associated disturbance from the confirmed
lean-cut reset defect corrected after this capture.

The [September 11 v2 driving-bog review](20260911_drive2_review.md) examines
the new drive2 capture, matches the flashed image, and separates the sustained
rich bog from a confirmed mistake in the newest warning-light hook.

The [September 8 evening review](archive/20260908_dashpot_review.md) covers the
18:01, 18:11 and 18:15 dashpot captures, with matched recorded flash CRCs,
timing execution and a tip-in pressure multiplier that can suppress added fuel.
The report distinguishes both versions of the user's reused BIN filename.
Its JSON and PNG are derived review artifacts, not new measurements.

- `romraiderlog_20260903_022932.csv` is the engine-off/invalid capture used to
  establish that the earlier file did not contain the reported start.
- `romraiderlog_20260903_023334.csv` contains the cold-start lean-out event
  analysed in the [master investigation](../docs/archive/master_patch/GHIDRA_AUDIT.md)
  and [historical audit log](../docs/archive/audit.md).
- `romraiderlog_20260908_120702.csv` and
  `romraiderlog_firstidlelog1_20260908_121839.csv` contain headings only;
  they are logger-failure evidence, not engine traces.
- `romraiderlog_idle_diagnostic_20260908_123651.csv` contains 1,786 complete
  samples on the user-confirmed 10:30 BIN. It captures improved steady idle
  followed by near-stall RPM and lean recovery after throttle blips. The user
  reports the physical gauge followed RomRaider. See
  [the numerical review and chart](archive/20260908_idle_review.md).
- `romraiderlog_idle_diagnostic2_20260908_141335.csv` contains 2,510 samples
  and 19 channels on the `6af0d1...` candidate, verified against recorded flash
  CRCs. Settled fueling improves, but blips nearly stall the engine. The user
  confirms intentional key-off at the end. Its AVLS units label contains an
  unquoted comma; the [analysis](archive/20260908_recovery_review.md) normalizes that
  exact header in memory without changing the source CSV.

`20260908_recovery_review.json` contains summaries and explicitly conditional
timing-table comparisons; the associated PNG plots recorded channels. These
are derived review artifacts, not another ECU capture.

`20260908_load_recovery_replay.json` contains native load-filter/B874 replay
and in-memory alpha sensitivity on the fixed 14:13 engine trajectory. It is
not a new log or an engine prediction. The [follow-up audit](../docs/archive/master_patch/IDLE_AIR_RECOVERY_AUDIT.md)
documents its limits and the new idle-air request profile for the same BIN.

`20260908_transient_replay.json` contains **offline model outputs**, not new
ECU measurements. It replays the complete capture through the retained B874
correction and fuel composer; assumptions and the separate VE candidate are
documented in [the recovery audit](../docs/archive/master_patch/IDLE_RECOVERY_AUDIT.md).

The installed seller-labelled 50-4110-style controller is suspected to be a
clone. Agreement between its display and ECU analogue input does not validate
the measured AFR, so these files are evidence for diagnosis only.
