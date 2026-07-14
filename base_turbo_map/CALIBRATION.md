# Calibration Changes

All addresses are D2WD610H flash offsets. The reference is the verified combined image with
SHA-256 `019e06e509afce2e798bfe29543e2536524c259d3ab6683c7dd3131ee069fb5e`.
The base-turbo image changes 1,043 bytes beyond that reference, confined to the tables listed here
plus the four-byte checksum value.

## Boost control: spring pressure only

| Calibration | Address | Combined default | Base-turbo value |
|---|---:|---:|---:|
| Boost Wastegate Duty | `0x7D7C4` | 0, 0, 21, 19, 18, 17, 15, 14% | all 0% |
| Boost Target | `0x7D7E0` | tapers from 5.0 to 3.93 psi | 5.0 psi from 2500 RPM onward |
| Boost Kp | `0x7D800` | 0.0005 ratio/mmHg | 0 |
| Boost Max Duty Ratio | `0x7D804` | 0.33 | 0 |
| Soft duty shutdown | `0x7D808` | 6.0 psi | 5.5 psi |
| Hard MAP fuel cut | `0x7D8C0` | 7.0 psi | 6.5 psi |
| Boost patch enable | `0x7D80C` | on | on |

The RPM axis and 30.0 native throttle gate remain unchanged. The low-RPM target ramp is retained,
then the target remains 5 psi instead of tapering at high RPM. With the maximum ratio at zero,
neither the feed-forward table nor proportional correction can command solenoid duty. The patch
remains enabled so its separate hard MAP fuel-cut wrapper remains active.

Both pressure limits are stored as absolute native pressure but displayed relative to 760 mmHg.
There is still no atmospheric-pressure compensation or hard-cut hysteresis. Validate the MAP
reading first and expect weather/altitude offset in the displayed gauge value.

## STI top-feed pink injectors

The pinned factory reference is `A4TE002B`, a 2003 JDM STI ROM. It contains raw flow `4900` under
the 16-bit `2707090/x` conversion, or **552.4673 cc/min estimated**, plus this factory deadtime
curve:

| Battery voltage (V) | A4TE002B deadtime (ms) | D2WD610H uint16 count |
|---:|---:|---:|
| 6.5 | 2.788 | 11152 |
| 9.0 | 1.488 | 5952 |
| 11.5 | 0.980 | 3920 |
| 14.0 | 0.684 | 2736 |
| 16.5 | 0.380 | 1520 |

D2WD610H's flow table uses `1804727/x`, so the equivalent stored float is `3266.667236` after
float32 quantization at `0x76014`. The five latency values at `0x7B318` are exactly representable
at 0.00025 ms/count. This intentionally follows the factory calibration rather than entering a
literal 565 in RomRaider: the displayed cc/min value is an estimated conversion of the ECU pulse
constant, not a bench-flow measurement. EcuTek likewise cautions that the ECU flow number does not
necessarily equal physical injector size: [Flash2002 guide, pages 7–8](https://ecutek.zendesk.com/hc/en-gb/article_attachments/204333175).

The old/new raw pulse-scale ratio is `0.4893883551`. The builder applies it, rounding toward a
longer pulse, to all four 16-cell cranking-IPW tables at `0x76B76..0x76BF5` and both five-cell
tip-in tables at `0x7739C`/`0x773BC`; it also scales the raw tip-in activation threshold at
`0x763E0` from 380.0 to about 185.97 counts (1.520 to 0.744 ms displayed). COBB documents the
factory/new injector-size ratio as a universal starting multiplier for cranking and tip-in tables,
but these values still require cold/hot starts, voltage sweeps, trims, and transient-lambda tests:
[COBB Subaru Accesstuner tuning guide](https://cobbtuning.atlassian.net/wiki/pages/viewpage.action?pageId=2551382020).

## Primary Open Loop fueling

Tables A and B at `0x7777C` and `0x77868` remain 14-load by 10-RPM. Their separate load axes at
`0x7771C` and `0x77808` retain every breakpoint through 1.22 g/rev, then become 1.40, 1.60, 1.85,
2.15, 2.50, and 3.00 g/rev instead of ending at 2.00. At each high-load cell, the builder uses the
richer original bank value or the cap below, whichever is richer, then writes the same value to
both banks. No data cell is made leaner than the combined image.

| Load (g/rev) | Maximum lambda below 6000 RPM | Gasoline AFR equivalent at 14.7 stoich | Maximum lambda at 6000+ RPM |
|---:|---:|---:|---:|
| 0.96 | 0.93 | 13.67 | 0.93 |
| 1.09 | 0.88 | 12.94 | 0.88 |
| 1.22 | 0.83 | 12.20 | 0.82 |
| 1.40 | 0.80 | 11.76 | 0.79 |
| 1.60 and above | 0.78 | 11.47 | 0.77 |

The uint8 table encoding rounds toward richer, so the stored result can be slightly richer than
the displayed cap. Actual lambda depends on correct MAF, injector, fuel-pressure, and transient
calibration; this table is a command, not a measurement.

The two `CL to OL Delay (Atm. Pressure)` counters at `0x772DC` change from `{6, 625}` to `{0, 0}`.
In this ECU's documented logic, zero selects the Primary Open Loop enrichment result rather than
waiting on the stock throttle/base-pulse-width delay path. Confirm the logged open-loop state
before positive manifold pressure.

## Base ignition timing

All six maps are covered so AVLS state, map-selection flags, and advance-multiplier blending do
not expose an unmodified high-load path:

| Map | Address | RPM rows |
|---|---:|---:|
| Base Timing A | `0x78AA0` | 14 |
| Base Timing B | `0x78BAC` | 14 |
| Base Timing C | `0x78CD0` | 20 |
| Base Timing D | `0x78E34` | 14 |
| Base Timing E | `0x78F40` | 14 |
| Base Timing F | `0x79064` | 20 |

The shared base-timing axis at `0x780BC` and both KCA axes at `0x791D8`/`0x79320` now end at
3.00 g/rev using the same expanded high-load breakpoints as documented above (with the timing
axis's existing 0.45 g/rev column retained). At 1.60 g/rev and above, the table below is the
maximum base timing. Existing cells below the ceiling remain unchanged; the builder never advances
a cell. The 1.40, 1.22, and 1.09 g/rev columns use the same curve plus 2, 4, and 8 degrees
respectively. Cells below 1.09 g/rev or below
2000 RPM remain unchanged.

| RPM | Full-boost base-timing ceiling (degrees BTDC) |
|---:|---:|
| 2000 | -2 |
| 2400 | 0 |
| 2800 | 2 |
| 3200 | 4 |
| 3600 | 5 |
| 4000 | 6 |
| 4400 | 7 |
| 4800 | 8 |
| 5200 | 9 |
| 5600 | 10 |
| 6000 | 11 |
| 6400 | 12 |
| 6800 | 13 |

The values are conservative placeholders for a stock-compression EZ30R on 98 RON, not MBT or a
knock-limit claim. Maps C and F receive the same caps, so moving AVLS earlier does not expose a
stock high-load/high-cam timing path. Excessively retarded timing also raises exhaust temperature;
tune from logged combustion evidence on a load-controlled dyno rather than assuming less timing is
always safer.

## Knock Correction Advance

`Knock Correction Advance Max A` at `0x7924C` and B at `0x793AC` are capped from 2000 RPM up:

- 1.09 g/rev: maximum 2 degrees positive KCA (encoded at or below the cap);
- 1.22 g/rev and above: 0 degrees positive KCA;
- lower load and lower RPM: unchanged.

This keeps the high-load timing ceiling from receiving a large IAM-based positive addition.
Feedback and fine knock retard mechanisms remain present; their ability to detect every damaging
combustion event is not assumed.

## IAT timing compensation

The stock 50–110 degrees C axis and 0.60 g/rev activation threshold remain unchanged. Data at
`0x7834C` becomes:

| IAT (degrees C) | Timing correction (degrees) |
|---:|---:|
| 50 | 0.00 |
| 60 | -1.05 |
| 70 | -2.11 |
| 80 | -4.22 |
| 90 | -6.33 |
| 100 | -8.09 |
| 110 | -10.20 |

## Rev limit

Rev Limit A at `0x7644C` is **6800 cut / 6770 resume**, preserving the stock 30 RPM hysteresis at
the requested lower maximum. Rev Limit B remains stock. The hard limiter itself is retained as
engine protection.

## Earlier AVLS

The stock 10.0 load-unit hysteresis at `0x7D480`/`0x7D484` remains unchanged. The calibrated
switching values are:

| Calibration | Address | Stock | Base-turbo value |
|---|---:|---:|---:|
| OSV actuation minimum | `0x7D4AC` | 3000 RPM | 2500 RPM |
| Forced high-cam release | `0x7D4B8` | 3800 RPM | 3000 RPM |
| Forced high-cam engage | `0x7D4BC` | 4000 RPM | 3200 RPM |
| Threshold 1 data | `0x7D67C` | 100,100,30,28,25,15,5 | 100,100,25,20,15,10,5 |
| Threshold 2 data | `0x7D6B4` | 100,100,90,50,30,10,0 | 100,100,60,35,20,10,0 |

The RPM axes remain stock. This permits a load-requested high-cam transition from 2500 RPM and
forces high cam at 3200 RPM; it does not force high cam at light load below that point. The load
signal's physical unit has not been proven, so confirm the commanded/actual AVLS transition,
oil-pressure behavior, lambda, torque, and knock on the engine. Engage remains above release, and
all six ignition maps are covered by the conservative timing policy.

## Deliberately unchanged

- MAF voltage axis and 44-point scaling curve (currently tops out at about 297.69 g/s);
- MAF Limit data at `0x73C68`, already `0xFFFF,0xFFFF` (about 300 g/s and the largest representable
  value in this table format);
- Engine Load Limit at 4.0 g/rev, above the new 3.0 g/rev tune axes;
- donor MAP conversion `{-414.0, 514.199951}` installed by the boost patch;
- boost RPM axis and throttle gate;
- AVCS calibrations;
- requested-torque and DBW tables;
- front A/F and rear-O2 patch code and switches;
- P0458/P0459 purge circuit diagnostics.

The only intentional high-RPM restriction added here is the requested 6800/6770 RPM limiter: the
boost target holds 5 psi to that point and fuel/timing resolution extends to 3.0 g/rev. Values above
3.0 g/rev hold the final calibrated columns; calculated load itself remains capped only at the
stock 4.0 g/rev limit. The MAF maximum is already at its uint16 ceiling and cannot be raised through
RomRaider. If logs approach 300 g/s, do not extrapolate blindly—rescale a proven MAF/housing or
implement and validate a different airflow strategy before further load.
