# D2WD610H 5 psi / 98 RON Base Turbo Map

This directory contains a conservative **starting calibration**, built from the verified combined
boost + single-front-A/F/rear-O2-delete image for D2WD610H.

Generated ROM:

- `D2WD610H_5psi_98RON_base_turbo.bin`
- SHA-256: `fd9a9354c7a9f2d82813253d41b17adb058b68ceb3f426a0c197a6322fbf2c0f`
- CALID: `D2WD610H`
- Size: 512 KiB
- Subaru additive checksum: valid (`0x4BD6335B`)
- Matching definition: `../defs/D2WD610H_AVLS_boost_single_front_af_patch.xml`

## Important status

**This is not a finished tune and is not flash-ready merely because its checksum is valid.** It
provides conservative targets and limits, but it cannot determine whether the installed fuel and
air-metering hardware will achieve them.

Do not apply boost until all of these are known and entered or validated:

- confirmation that all six injectors are genuine, matched STI top-feed pinks, plus their part
  numbers, condition/cleaning report, base fuel pressure, and individual flow spread;
- fuel-pump flow at the required rail pressure and stable injector differential pressure under
  boost;
- MAF sensor and housing dimensions with a calibrated MAF curve that does not saturate;
- the physical MAP sensor matching the installed `{-414.0, 514.199951}` conversion;
- post-turbo wideband lambda logging, fault/status logging, and timestamp alignment;
- intercooler, intake-temperature behavior, compression/leak-down health, plugs, and ignition
  system condition.

The injector starting point is now translated from the factory 2003 JDM STI `A4TE002B` ROM pinned
at `../base_roms/A4TE002B-2003-JDM-Subaru-Impreza-STi.hex`. That ROM encodes an estimated
**552.47 cc/min** scalar and deadtimes of **2.788, 1.488, 0.980, 0.684, and 0.380 ms** at 6.5,
9.0, 11.5, 14.0, and 16.5 V. D2WD610H's different raw units are handled by the builder. The
displayed flow is an ECU-model estimate rather than a bench-flow claim; six used or counterfeit
injectors can still differ enough to make this unsafe without inspection and fuel-trim validation.

The donor ROM is pinned from
[bludgod/RomRaider commit 639f3c7](https://github.com/bludgod/RomRaider/blob/639f3c73c1bd8efee48347bd71bb064211b95242/JDM/Impreza/A4TE002B-2003-JDM-Subaru-Impreza-STi.hex),
with table locations and conversions from
[Merp/SubaruDefs commit 9b2992e](https://github.com/Merp/SubaruDefs/blob/9b2992eba8133fe5338b89aa77b22c1bb14d6507/ECUFlash/subaru%20metric/Impreza%20STi/A4TE002B.xml).

## What this map does

- Rebuilds the combined patch from the pinned stock ROM; it never stacks changes onto a generated
  image.
- Keeps both runtime patch switches on.
- Uses the 5 psi wastegate spring as the sole boost controller:
  - all base wastegate duty cells = `0%`;
  - proportional gain = `0`;
  - maximum final duty ratio = `0`.
- Holds the nominal target at 5 psi from 2500 RPM through the top of the table; the target cannot
  command duty in this spring-only image.
- Lowers the soft threshold to 5.5 psi and the hard MAP fuel cut to 6.5 psi, both referenced to
  760 mmHg by the current patch.
- Richens and matches both high-load Primary Open Loop tables, reaching lambda 0.78 and lambda
  0.77 at 6000 RPM and above.
- Expands both fuel-load axes and all base-timing/KCA load axes from 2.0 to 3.0 g/rev so expected
  boosted operation has tuning resolution instead of immediately holding the last stock column.
- Clears the atmospheric CL-to-OL delay so the enriched Primary Open Loop map controls the
  transition without the stock high-load delay.
- Caps all six base-timing maps, including both early-AVLS paths, with extra retard around torque
  onset; positive Knock Correction Advance is zero at 1.22 g/rev and above.
- Adds stronger high-IAT timing retard from 80 to 110 degrees C.
- Moves load-based AVLS eligibility to 2500 RPM and the forced high-cam crossover to 3200 RPM,
  with a 3000 RPM release point and stock hysteresis.
- Sets the requested maximum to 6800 RPM cut / 6770 RPM resume. The 5 psi target does not taper
  before that limit, and the hard limiter is deliberately retained.
- Installs the factory STI-pink scalar/deadtime curve and ratio-scales all four cranking-IPW maps,
  both tip-in maps, and the tip-in activation threshold as first-start values.
- Recalculates and verifies the ROM checksum.

See [CALIBRATION.md](CALIBRATION.md) for the exact policies and addresses and
[COMMISSIONING.md](COMMISSIONING.md) for the required test order.

## Build and verify

From the repository root:

```sh
python3 base_turbo_map/build_base_turbo_map.py
python3 base_turbo_map/verify_base_turbo_map.py
```

The builder verifies all of the following before writing the output:

1. root stock ROM SHA-256;
2. byte identity of the root stock, `base_roms` stock BIN, and original SRF `MEMD` payload;
3. reconstruction of the combined image directly from stock;
4. byte identity and SHA-256 of that stage against the canonical combined artifact;
5. size, CALID, SHA-256, flow bytes, and latency bytes of the pinned A4TE002B injector donor;
6. guarded calibration ownership and a valid final checksum;
7. no change to any protected stock, donor, or combined source.

Any RomRaider edit after this build changes the hash and requires another checksum-correct save.
Run the verifier again only against an unedited generated baseline; keep separately named working
revisions for real tuning.

## Hardware assumption for the boost valve

Zero commanded EBCS duty must physically produce minimum boost. For the first pressure test,
leave the wastegate reference connected directly to the compressor/manifold source and keep the
solenoid out of the control path. A controller cannot reduce boost below a spring or correct boost
creep caused by the manifold, turbine housing, gate priority, or dump routing.

The supplied turbo description is treated as a Garrett 35-frame Gen II unit with a separate 45 mm
wastegate. Exact turbine housing A/R, manifold layout, and compressor part number remain hardware
inputs; they affect spool and creep but do not justify adding electronic duty to a 5 psi spring
baseline. Garrett's current GTX3582R Gen II catalog page is
<https://www.garrettmotion.com/racing-and-performance/performance-catalog/turbo/gtx3582r-gen-ii/>.
