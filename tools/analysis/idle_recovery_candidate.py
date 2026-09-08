#!/usr/bin/env python3
"""Reconstruct the historical idle-recovery calibration for log replay.

The September 8 14:13 capture shows improved settled fueling but unresolved
near-stall recovery. See logs/20260908_recovery_review.md before further use.

The captured 10:30 master is read from pinned Git history, then ten low-lift VE
cells are changed. The current rolling build lives in build_master_patch.py.
Nothing is written to the master BIN or stock files. No transient
fueling code, calibration or cut behavior is disabled.
"""

import _analysis_paths  # Shared repository, artifact and interpreter paths.
import hashlib
import json
from pathlib import Path
import struct

import build_master_patch as master
from historical_roms import master_1030

HERE = _analysis_paths.MASTER
BASELINE_SHA256 = '48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0'
CANDIDATE_SHA256 = '6af0d130b585abf9c9b275840ddb0b237485d84f8f8adf7b15df8462adc72433'
OUTPUT = HERE / 'candidates/D2WD610H_idle_recovery_candidate.bin'
ROWS_RPM = (500, 800)
# Hold the measured idle region, then join back to stock at 760 mmHg by
# interpolating modeled air mass (pressure * VE). Blending VE itself to zero
# correction too quickly can make rising pressure reduce modeled air mass.
PLATEAU_MAP = (250, 350)
TRANSITION_MAP = (450, 550, 650)
EXIT_MAP = 760


def revise_image(baseline):
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA256:
        raise ValueError('Idle recovery candidate requires the pinned 10:30 baseline')
    sd = master.speed_density
    image = bytearray(baseline)
    columns = len(sd.MAP_AXIS)
    donor_row = sd.LOW_RPM_AXIS.index(1200)
    def value_at(row, pressure):
        column = sd.MAP_AXIS.index(pressure)
        return struct.unpack_from('>f', baseline, sd.LOW_VE_DATA_ADDR + 4 * (row * columns + column))[0]
    cells = []
    for rpm in ROWS_RPM:
        row = sd.LOW_RPM_AXIS.index(rpm)
        anchor = PLATEAU_MAP[-1]
        anchor_mass = anchor * value_at(donor_row, anchor)
        exit_mass = EXIT_MAP * value_at(row, EXIT_MAP)
        if exit_mass <= anchor_mass:
            raise ValueError('No increasing-air-mass transition to the unchanged MAP boundary')
        for pressure in PLATEAU_MAP + TRANSITION_MAP:
            column = sd.MAP_AXIS.index(pressure)
            address = sd.LOW_VE_DATA_ADDR + 4 * (row * columns + column)
            old = struct.unpack_from('>f', baseline, address)[0]
            if pressure in PLATEAU_MAP:
                target = value_at(donor_row, pressure)
            else:
                target = (anchor_mass + (exit_mass-anchor_mass) * (pressure-anchor) / (EXIT_MAP-anchor)) / pressure
            if not 0 < old < target < 1.5:
                raise ValueError(f'Unexpected baseline VE at {address:#x}')
            struct.pack_into('>f', image, address, target)
            cells.append(dict(rpm=rpm, map_mmhg=pressure, address=f'0x{address:05X}',
                              old_ve=old, new_ve=struct.unpack_from('>f', image, address)[0]))
    checksum_address = master.calibration.CHECKSUM_TABLE_ADDR + 8
    _, checksum, _ = master.calibration.checksum_value(image)
    struct.pack_into('>I', image, checksum_address, checksum)
    allowed = set(range(checksum_address, checksum_address + 4))
    for cell in cells:
        address = int(cell['address'], 16)
        allowed.update(range(address, address + 4))
    changed = {i for i, (a, b) in enumerate(zip(baseline, image)) if a != b}
    assert changed <= allowed
    assert master.calibration.checksum_value(image)[:2] == (checksum, checksum)
    assert hashlib.sha256(image).hexdigest() == CANDIDATE_SHA256
    return bytes(image), dict(
        status='RESEARCH CANDIDATE; 14:13 capture improves settled fueling but rev recovery remains unresolved',
        baseline_sha256=BASELINE_SHA256,
        candidate_sha256=hashlib.sha256(image).hexdigest(),
        subaru_checksum=f'0x{checksum:08X}', changed_bytes=len(changed), cells=cells,
        changed_ranges=[f'0x{a:05X}..0x{b:05X}' for a,b in master.merge_ranges(changed)],
        method='Hold existing 1200-RPM VE at 500/800 RPM and 250/350 mmHg; join pressure*VE to unchanged 760-mmHg values through 450/550/650-mmHg cells.',
        limitations='The recorded inputs are not an engine simulation. Cranking interpolation, timing/load lookups and actual fueling need validation. No stock transient correction is removed.')


def build_candidate():
    baseline = master_1030()
    image, manifest = revise_image(baseline)
    return baseline, image, manifest


if __name__ == '__main__':
    baseline, image, manifest = build_candidate()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(image)
    OUTPUT.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(OUTPUT)
    print(json.dumps(manifest, indent=2))
