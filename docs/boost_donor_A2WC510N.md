# A2WC510N EJ255 Boost-Control Donor

This note records the exact stock turbo ROM used to seed the D2WD610H boost-patch defaults and
the reduction from Subaru's 3D controller tables to this patch's RPM-only controller.

## Donor identity and provenance

| Field | Value |
|---|---|
| CALID | `A2WC510N` (also present at file offset `0x2000`) |
| Vehicle | 2005 USDM Subaru Legacy GT, manual transmission, turbo EJ255 |
| ECU | 32-bit Denso, Renesas SH7058 |
| Image size | 1,048,576 bytes |
| Local reference | `base_roms/A2WC510N-2005-USDM-Subaru-Legacy-GT-MT.hex` |
| SHA-256 | `db8827673a2383ce0ee3182d2c33f81be39fd63c3545e77b3e6bf8476488008d` |

The image comes from the public
[RomRaider stock-ROM archive](https://github.com/bludgod/RomRaider/blob/639f3c73c1bd8efee48347bd71bb064211b95242/USDM/Legacy/A2WC510N-2005-USDM-Subaru-Legacy-GT-MT.hex).
Addresses and formats come from the matching
[SubaruDefs A2WC510N definition](https://github.com/Merp/SubaruDefs/blob/9b2992eba8133fe5338b89aa77b22c1bb14d6507/ECUFlash/subaru%20metric/Legacy%20GT/A2WC510N.xml)
and its `32BITBASE` include.

The donor ROM is reference material only. It is never used as the patch input and must never
replace the root `2005 BLE MT.bin` Ghidra image.

## Extracted donor tables

| Donor table | Data address | Axes | Use in patch |
|---|---:|---|---|
| Target Boost A / B | `0xC11C8` / `0xC12D8` | throttle × RPM | A and B are identical; full-demand column supplies target shape. |
| Initial Wastegate Duty A / B | `0xC0BB4` / `0xC0CB0` | throttle × RPM | A and B are identical; full-demand column supplies feed-forward shape. |
| Max Wastegate Duty | `0xC0EA8` | throttle × RPM | Used to choose the conservative scalar cap. |
| Turbo Dynamics Proportional | `0xC07C4` | boost error | Near-zero slope supplies the patch's scalar Kp. |
| Boost Limit (Fuel Cut) | `0xC815C` | atmospheric pressure | Used as strategy reference; thresholds are lowered around the 5 psi target. |
| Manifold Pressure Sensor Scaling | `0xC00C0` | offset, multiplier | Copied exactly to D2WD610H `0x72810`. |

The extracted full-demand columns used by the reduction are:

```text
Target RPM:       800, 2000, 2400, 2800, 3600, 4000, 4800, 5200, 5600, 6000, 6400, 6800
Target native:    810, 1080, 1460, 1460, 1460, 1430, 1380, 1360, 1340, 1310, 1290, 1200

WGDC RPM:         2250, 2400, 2800, 3200, 3600, 4000, 4400, 5200, 5600, 6400, 6800
Initial WGDC %:   90, 56.8008, 51.8008, 49, 49, 47, 44, 41, 42, 33, 33
Maximum WGDC %:   90, 63.8008, 58.8008, 56, 56, 54, 51, 48, 49, 40, 40

TD error native: -150, -50, -20, -10, 0, 10, 20, 50, 150
TD correction %: -5, -3, -1, -0.5, 0, 0.5, 1, 3, 9
```

At full demand, donor Target Boost peaks at native absolute pressure `1460`, or
`(1460 - 760) / 51.71493257 = 13.536 psi` relative to 760 mmHg. Its high-demand target tapers
with RPM.

The donor MAP calibration contains these big-endian floats:

```text
offset     = -414.0
multiplier =  514.199951171875
```

Ghidra revalidation of D2WD610H renamed `0x7A14` to
`map_sensor_voltage_to_pressure_process` and confirmed that it performs:

```text
MAP_native = sensor_voltage * calibration[1] + calibration[0]
```

`MAP_native` at `0xFFFFABC4` is therefore in the Subaru native pressure convention used by the
donor: mmHg absolute. The prior notes that treated it as kPa were incorrect. The patch and its
RomRaider definition now store mmHg absolute and display psi relative to the 760 mmHg reference.

## Five-psi reduction

The donor full-demand target curve is interpolated onto the patch RPM axis. Pressure above the
760 mmHg reference is then multiplied by `5 / 13.5357422936`; the reference remains `760` native
units.

The donor Initial WGDC full-demand column is interpolated and multiplied by the same ratio,
then rounded to whole percentage points. Values below 2,500 RPM are deliberately zeroed. This
preserves the donor shape, but it is only a starting estimate—wastegate duty does not physically
scale linearly with target pressure.

| RPM | Donor target, psi relative 760 mmHg | Patch target, psi relative 760 mmHg | Patch base WGDC |
|---:|---:|---:|---:|
| 1,500 | 4.01 | 1.48 | 0% |
| 2,000 | 6.19 | 2.29 | 0% |
| 2,500 | 13.54 | 5.00 | 21% |
| 3,000 | 13.54 | 5.00 | 19% |
| 3,500 | 13.54 | 5.00 | 18% |
| 4,000 | 12.96 | 4.79 | 17% |
| 5,000 | 11.80 | 4.36 | 15% |
| 6,000 | 10.64 | 3.93 | 14% |

Other defaults:

- Kp `0.0005 ratio/mmHg`, equivalent to 2.59 WGDC percentage points per psi error. This matches
  the local slope of the donor proportional table around zero error.
- Maximum duty ratio `0.33`.
- Minimum processed-throttle value `30.0` (approximately 35.7% using the donor `x/.84` display
  convention), chosen at the donor target table's transition into its higher-demand columns.
- Soft duty shutdown `6.0 psi` relative to 760 mmHg.
- Hard fuel cut `7.0 psi` relative to 760 mmHg.

## Limitations

The donor controller is load/throttle × RPM and includes compensations plus integral Turbo
Dynamics. The current D2WD610H patch is RPM-only with a demand gate and proportional correction;
copying all donor tables byte-for-byte would not reproduce donor behavior. Only compatible
shapes and calibration slopes are reduced above.

The patch uses `760 mmHg` as its sea-level pressure reference and does not yet implement the
donor's atmospheric-pressure target compensation. The displayed 5 psi target and 6/7 psi limits
therefore mean pressure relative to 760 mmHg, not a constant 5/6/7 psi above local atmosphere at
altitude.

Run `python3 patch/verify_boost_donor.py` to re-extract the pinned donor bytes, check the A/B
pairs, and compare the generated patch tables and MAP floats with this reduction.

Use the MAP sensor matching this donor calibration and validate logged pressure against a
reference gauge. Confirm that zero duty gives minimum boost, scope PWM frequency/polarity, and
prove both overboost responses before connecting the solenoid to boost control.
