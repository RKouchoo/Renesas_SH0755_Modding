# D2WD610H speed-density component

This folder contains a standalone, default-OFF firmware component for the 2005 ADM
Liberty 3.0R BLE manual ROM `D2WD610H`.

It does not replace the stock ROM in the repository root. The builder always hashes and copies
that stock image into a separate output.

## What it changes

The Ghidra-verified periodic task pointer at `0x11D20` normally calls
`maf_airflow_temperature_compensation_update` at `0x172A4`. The component repoints that one
slot to `speed_density_airflow_wrapper` at `0x7E18C`.

The wrapper:

1. runs the complete stock airflow task;
2. returns with the stock result unless the enable byte is exactly `01`;
3. rejects NaN/out-of-window MAP, RPM, and IAT values and invalid calibrations;
4. looks up VE from native absolute MAP and RPM;
5. applies displacement, ideal-gas conversion, IAT density correction, and a global multiplier;
6. caps the result at the configurable maximum; and
7. writes modeled mass airflow to the stock post-compensation channel at `0xFFFFB420`.

All existing consumers—including fuel-trim range selection and the MAF-derived load/fueling
pipeline—continue to use the same RAM signal. The wrapper is after the stock MAF compensation
and limit logic, so the enabled result is not silently constrained by the stock MAF table format.

## Build and verify

From the repository root:

```sh
python3 speed_density/patch_speed_density.py
python3 speed_density/build_definition.py
python3 speed_density/verify_speed_density.py
```

Outputs:

- `speed_density/D2WD610H_speed_density.bin`
- `speed_density/D2WD610H_AVLS_speed_density_patch.xml`

The ROM defaults OFF at `0x7DD00`. Loading the XML does not enable the component by itself; set
`Speed Density Patch Enable` to `on`, save a new working ROM, correct its Subaru checksum, and
verify the changed file before use.

## Calibration model

The runtime equation is:

```text
airflow_g_s =
    VE(MAP_abs_mmHg, RPM)
    × MAP_abs_mmHg
    × RPM
    × displacement_L
    × 1.3203052e-5
    × IAT_density_multiplier
    × global_multiplier
```

The fixed constant is the ideal-gas/four-stroke conversion per litre at 20 °C. The default IAT
curve is `293.15 / (IAT_C + 273.15)`.

The supplied VE table is a conservative mathematical starting surface, not measured EZ30R
volumetric efficiency. Around high load it intentionally estimates on the rich/high-load side.
It must be calibrated against synchronized MAP, RPM, IAT, ECU lambda, external post-turbo
wideband lambda, fuel pressure, and the retained MAF before the MAF is treated as non-authoritative.

## Hardware assumptions

- The MAP signal must remain valid across vacuum and the intended positive-pressure range.
- IAT must be measured after the intercooler in representative charge air. A MAF-integrated,
  pre-compressor IAT invalidates the density correction under boost.
- Keep the MAF electrically connected during initial commissioning. The wrapper deliberately
  retains the full stock result on invalid speed-density input; it does not disable MAF DTCs.
- The component does not change MAP scaling. A ROM combined with the existing boost component
  uses that component's `-414.0 / 514.199951` native-mmHg scaling and therefore requires the
  matching sensor and a pressure-calibration check.

## Status

Static implementation and binary verification are complete. Vehicle validation is not. Do not
enable it for a boosted pull until the commissioning gates in [COMMISSIONING.md](COMMISSIONING.md)
have passed on a load-controlled dyno.
