#!/usr/bin/env python3
"""Verify the A2WC510N donor extraction and the generated 5 psi patch defaults.

Usage: python3 patch/verify_boost_donor.py [donor.hex] [patched.bin]
"""

import hashlib
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "patch"))
import patch_boost as patch
from sh2_disasm import dis_one

DONOR = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "base_roms/A2WC510N-2005-USDM-Subaru-Legacy-GT-MT.hex"
)
PATCHED = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "patch/D2WD610H_boost.bin"
if len(sys.argv) > 3:
    raise SystemExit("usage: python3 patch/verify_boost_donor.py [donor.hex] [patched.bin]")

DONOR_SHA256 = "db8827673a2383ce0ee3182d2c33f81be39fd63c3545e77b3e6bf8476488008d"
ATM_NATIVE = 760.0
NATIVE_PER_PSI = 51.71493257
PATCH_RPM = [1500.0, 2000.0, 2500.0, 3000.0, 3500.0, 4000.0, 5000.0, 6000.0]


def floats(data, address, count):
    return list(struct.unpack_from(">%df" % count, data, address))


def uint16s(data, address, count):
    return list(struct.unpack_from(">%dH" % count, data, address))


def column(data, address, rows, columns, index):
    values = uint16s(data, address, rows * columns)
    return [values[row * columns + index] for row in range(rows)]


def interpolate(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for left in range(len(xs) - 1):
        if xs[left] <= x <= xs[left + 1]:
            fraction = (x - xs[left]) / (xs[left + 1] - xs[left])
            return ys[left] + fraction * (ys[left + 1] - ys[left])
    raise AssertionError("unreachable interpolation input")


def close(actual, expected, tolerance=1e-4):
    assert len(actual) == len(expected)
    for index, (got, want) in enumerate(zip(actual, expected)):
        assert abs(got - want) <= tolerance, (index, got, want)


def expect(image, address, data, label):
    actual = image[address:address + len(data)]
    assert actual == data, (label, hex(address), actual.hex(), data.hex())


def decode_span(image, start, end):
    decoded = []
    for address in range(start, end, 2):
        text, _ = dis_one(image, address)
        assert not text.startswith(".word"), (hex(address), text)
        decoded.append((address, text))
    return decoded


def main():
    donor = DONOR.read_bytes()
    patched = PATCHED.read_bytes()
    stock = Path(patch.STOCK).read_bytes()
    assert len(donor) == 0x100000
    assert len(patched) == 0x80000
    assert len(stock) == 0x80000
    assert hashlib.sha256(stock).hexdigest() == patch.STOCK_SHA256
    assert hashlib.sha256(donor).hexdigest() == DONOR_SHA256
    assert donor[0x2000:0x2008] == b"A2WC510N"

    target_throttle = floats(donor, 0xC1178, 8)
    target_rpm = floats(donor, 0xC1198, 12)
    assert target_throttle == [0.0, 10.0, 20.0, 25.0, 30.0, 35.0, 45.0, 80.0]
    target_a = uint16s(donor, 0xC11C8, 12 * 8)
    target_b = uint16s(donor, 0xC12D8, 12 * 8)
    assert target_a == target_b
    target_full = [target_a[row * 8 + 7] for row in range(12)]
    assert target_full == [810, 1080, 1460, 1460, 1460, 1430, 1380, 1360,
                           1340, 1310, 1290, 1200]

    iwgdc_throttle = floats(donor, 0xC0B68, 8)
    iwgdc_rpm = floats(donor, 0xC0B88, 11)
    assert iwgdc_throttle == [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 80.0]
    iwgdc_a = uint16s(donor, 0xC0BB4, 11 * 8)
    iwgdc_b = uint16s(donor, 0xC0CB0, 11 * 8)
    assert iwgdc_a == iwgdc_b
    iwgdc_full = [value * 0.00390625 for value in column(donor, 0xC0BB4, 11, 8, 7)]

    max_wgdc_full = [value * 0.00390625 for value in column(donor, 0xC0EA8, 11, 8, 7)]
    assert floats(donor, 0xC0E5C, 8) == iwgdc_throttle
    assert floats(donor, 0xC0E7C, 11) == iwgdc_rpm
    assert max_wgdc_full == [90.0, 63.80078125, 58.80078125, 56.0, 56.0, 54.0,
                             51.0, 48.0, 49.0, 40.0, 40.0]

    td_error = floats(donor, 0xC07A0, 9)
    td_correction = [value * 0.00390625 - 50.0 for value in uint16s(donor, 0xC07C4, 9)]
    assert td_error == [-150.0, -50.0, -20.0, -10.0, 0.0, 10.0, 20.0, 50.0, 150.0]
    assert td_correction == [-5.0, -3.0, -1.0, -0.5, 0.0, 0.5, 1.0, 3.0, 9.0]
    assert floats(donor, 0xC8144, 6) == [440.0, 504.0, 568.0, 632.0, 696.0, 760.0]
    assert uint16s(donor, 0xC815C, 6) == [1207, 1301, 1394, 1488, 1581, 1660]
    assert floats(donor, 0xC00C0, 2) == [-414.0, 514.199951171875]

    donor_peak_psi = (max(target_full) - ATM_NATIVE) / NATIVE_PER_PSI
    reduction = 5.0 / donor_peak_psi
    expected_target_psi = [
        (interpolate(target_rpm, target_full, rpm) - ATM_NATIVE) / NATIVE_PER_PSI * reduction
        for rpm in PATCH_RPM
    ]
    expected_base = [
        0 if rpm < 2500.0 else round(interpolate(iwgdc_rpm, iwgdc_full, rpm) * reduction)
        for rpm in PATCH_RPM
    ]
    assert expected_base == [0, 0, 21, 19, 18, 17, 15, 14]
    assert round(max(max_wgdc_full) * reduction / 100.0, 2) == 0.33
    assert (0.005 / 10.0) == 0.0005

    assert list(patched[patch.BASE_DATA:patch.BASE_DATA + 8]) == expected_base
    stored_target = floats(patched, patch.TARGET_DATA, 8)
    expected_target = [ATM_NATIVE + psi * NATIVE_PER_PSI for psi in expected_target_psi]
    close(stored_target, expected_target)
    close(floats(patched, patch.KP_ADDR, 3), [0.0005, 0.33, ATM_NATIVE + 6 * NATIVE_PER_PSI])
    close(floats(patched, patch.THROTTLE_GATE_ADDR, 1), [30.0])
    close(floats(patched, patch.OVERB_FC_ADDR, 1), [ATM_NATIVE + 7 * NATIVE_PER_PSI])
    assert floats(patched, patch.MAP_SCALING_ADDR, 2) == floats(donor, 0xC00C0, 2)

    blobs = [
        (patch.BASE_DESC, patch.desc_1axis(0x04, patch.RPM_AXIS, patch.BASE_DATA,
                                          patch.DUTY_SCALE, 0.0), "base descriptor"),
        (patch.RPM_AXIS, b"".join(patch.f32(value) for value in patch.RPM_BREAKS), "RPM axis"),
        (patch.BASE_DATA, bytes(patch.BASE_DUTY), "base duty"),
        (patch.TARGET_DESC, patch.desc_1axis(0x00, patch.RPM_AXIS, patch.TARGET_DATA,
                                            1.0, 0.0), "target descriptor"),
        (patch.TARGET_DATA, b"".join(patch.f32(value) for value in patch.TARGET_MAP), "target data"),
        (patch.KP_ADDR, patch.f32(patch.KP) + patch.f32(patch.MAXRATIO) +
                        patch.f32(patch.OVERBOOST), "gain/soft-cut constants"),
        (patch.BOOST_ENABLE_ADDR, b"\x01", "runtime enable"),
        (patch.STUB_ADDR, patch.build_stub(), "boost controller"),
        (patch.THROTTLE_GATE_ADDR, patch.f32(patch.MIN_THROTTLE), "throttle gate"),
        (patch.OVERB_FC_ADDR, patch.f32(patch.OVERBOOST_FUELCUT), "hard cut"),
        (patch.REVWRAP_ADDR, patch.build_fuelcut_wrapper(), "fuel-cut wrapper"),
    ]
    for address, data, label in blobs:
        expect(patched, address, data, label)
    expect(patched, patch.HIJACK_LITERAL, patch.be32(patch.STUB_ADDR), "output hook")
    expect(patched, patch.REVLIM_FNPTR, patch.be32(patch.REVWRAP_ADDR), "rev-limit hook")
    # Independently pin the critical enable branches rather than relying only on
    # regeneration from the same builders. Disabled controller path: require exact 01,
    # load FR4=0.0, and jump to the stock output. Wrapper: test bit 0 and branch
    # over the added MAP cut for every other value.
    expect(patched, patch.STUB_ADDR,
           bytes.fromhex("d11e601088018903f48dd21d422b0009"),
           "zero-duty disabled path")
    expect(patched, patch.REVWRAP_ADDR + 8,
           bytes.fromhex("d109601088018b09"),
           "added-fuel-cut disabled branch")
    decoded = (decode_span(patched, patch.STUB_ADDR, 0x7D88C) +
               decode_span(patched, patch.REVWRAP_ADDR, 0x7D8F0))

    allowed = set(range(patch.MAP_SCALING_ADDR, patch.MAP_SCALING_ADDR + 8))
    allowed.update(range(patch.HIJACK_LITERAL, patch.HIJACK_LITERAL + 4))
    allowed.update(range(patch.REVLIM_FNPTR, patch.REVLIM_FNPTR + 4))
    for address, data, _ in blobs:
        allowed.update(range(address, address + len(data)))
    changed = [index for index, (old, new) in enumerate(zip(stock, patched)) if old != new]
    unexpected = [index for index in changed if index not in allowed]
    assert not unexpected, [hex(value) for value in unexpected[:32]]

    print("A2WC510N donor and generated defaults verified")
    print("  donor peak : %.6f psi relative to 760 mmHg" % donor_peak_psi)
    print("  target psi : %s" % [round(value, 3) for value in expected_target_psi])
    print("  base WGDC  : %s" % expected_base)
    print("  MAP scale  : %s" % floats(patched, 0x72810, 2))
    print("  switch     : 0x%05X=01; 00 forces zero EBCS duty and bypasses added hard cut" %
          patch.BOOST_ENABLE_ADDR)
    print("  OFF caveat : MAP-sensor scaling remains patched")
    print("  changed    : %d bytes, all inside guarded hooks/calibration/free-space allocations" %
          len(changed))
    print("  code       : %d decoded instructions; enable branches independently pinned" %
          len(decoded))


if __name__ == "__main__":
    main()
