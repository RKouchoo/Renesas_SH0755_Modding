# Idle-recovery calibration candidate

`D2WD610H_idle_recovery_candidate.bin` is a separate research candidate for the
September 8 near-stall/lean-recovery investigation. It holds the existing
1200-RPM VE in the lower idle rows at the measured vacuum pressures. Ten
VE cells and the Subaru checksum differ from the 10:30 image; stock transient
fueling and all firmware instructions are retained.

SHA-256: `6af0d130b585abf9c9b275840ddb0b237485d84f8f8adf7b15df8462adc72433`.
Checksum: `0x16CB75E9`. The adjacent JSON records every changed cell.

The plateau covers 250/350 mmHg in the 500/800-RPM rows. The 450/550/650-mmHg
cells bridge modeled air mass back to each row's unchanged 760-mmHg value.
Checks include the slope between pressure knots, so rising pressure cannot
reduce modeled air mass through this transition. There are 34 changed bytes.

The [September 8 14:13 capture](../../logs/20260908_recovery_review.md) now
matches this candidate's flash CRCs. Settled fueling improves, but rev blips
still cause near-stalls down to 558 RPM. The user confirms it stayed running
and the final shutdown was intentional. This is not a finished calibration;
no new BIN was produced from that review. The change remains substantial
below 800 RPM. Original build evidence and limits are in
[IDLE_RECOVERY_AUDIT.md](../IDLE_RECOVERY_AUDIT.md).

Build from canonical stock with `python3 master_patch/idle_recovery_candidate.py`.
The script preserves the main 10:30 `D2WD610H_master_patch.bin` as the logged
baseline and refuses other baseline hashes.
