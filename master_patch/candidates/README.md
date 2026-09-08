# Historical investigation images

The current output is [D2WD610H_master_patch.bin](../D2WD610H_master_patch.bin).
The MAP repair and earlier idle-VE correction are integrated in its ordinary
builder. The user's `D2WD610H_slight_dashpot_candidate.bin` is an independent
experiment and is excluded from the rolling master. These saved images remain
only for historical log analysis; see [the current repair](../../docs/archive/master_patch/MAP_BOUNDARY_REPAIR.md).

## Earlier idle-recovery calibration

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
[IDLE_RECOVERY_AUDIT.md](../../docs/archive/master_patch/IDLE_RECOVERY_AUDIT.md).

The historical `idle_recovery_candidate.py` recipe reads the captured 10:30
baseline from pinned Git history and verifies the reconstructed image's hash.
Current builds use `python3 master_patch/build_master_patch.py`.
