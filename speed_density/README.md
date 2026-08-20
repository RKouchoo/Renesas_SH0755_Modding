# D2WD610H MAFless speed-density component

This folder contains the standalone, always-on MAFless speed-density firmware component for the
2005 ADM Liberty 3.0R BLE manual ROM `D2WD610H`.

The builder never edits the canonical root ROM. It verifies the SHA-256 of
`2005 BLE MT.bin`, copies it in memory, and writes a separate output.

## What it changes

The live stock Ghidra project confirms that periodic task pointer `0x11D20` invokes
`maf_airflow_temperature_compensation_update` at `0x172A4`. This component deliberately retains
that task because its downstream half derives and filters the engine-load channels
`0xFFFFB428..0xFFFFB440`.

The stock task normally calls helper `0x24B0` through literal `0x1743C` immediately before storing
final airflow to `0xFFFFB420`. The component redirects that one helper pointer to
`speed_density_airflow_calculate` at `0x7E18C`. The returned SD value is therefore stored before
the retained load/state calculations run.

The retained stock normalization is Ghidra-verified: `0xFFFFB428 = 0xFFFFB420 [g/s] * 60 /
0xFFFFB544 [RPM]`, followed by the stock conditioning path to `0xFFFFB438` in g/rev. AVCS,
ignition, fueling, and knock maps continue to consume that conditioned g/rev value. The separate
AVLS lift-switch state machine does not use it: its RPM curves compare conditioned vehicle speed
in km/h and are selected by engine-oil temperature.

It also:

- replaces both raw-MAF conversion calls, at `0x639C` and `0x66D8`, with `nop`;
- replaces the only scheduled `maf_airflow_limit_update` call at `0x107F8` with `nop`;
- redirects the high/low MAF-input diagnostic task at pointer `0x11804` to the stock no-op return
  stub at `0x66C2`;
- redirects both scheduled calls to the MAF-dependent temperature-plausibility condition
  (`0x1062C` and `0x1185C`) to that same no-op stub;
- clears D2WD610H diagnostic switches P0102 and P0103 at `0x5BD57..0x5BD58`; and
- removes the MAF limit, scaling, compensation, P0102, and P0103 entries from this component's
  generated RomRaider definition.

The replacement helper validates native absolute MAP, RPM, IAT, and its calibration values, looks
up a 13×17 VE surface, applies displacement and IAT-density corrections, caps normal output, and
writes modeled mass airflow to the existing final channel at `0xFFFFB420`. Existing load,
fueling, trim, timing, diagnostic, and logging consumers therefore receive speed-density airflow
without being individually patched. It also mirrors the synthetic result to the former raw-MAF
state channels `B448/B458/B45C`; this keeps the retained task's next-cycle internal state coherent
without sampling the physical MAF.

There is deliberately no stock-MAF fallback or runtime OFF switch. Exact zero RPM writes zero
airflow. Any other invalid input, calibration, table result, or arithmetic state writes a fixed
500 g/s value, selecting rich/high-load behavior rather than retaining stale or missing MAF data.
That is an emergency indication, not a drivable limp mode.

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

The current deterministic standalone ROM SHA-256 is
`548fc5353338248c683098507aed79a6c5f377bb2462b65a091a2f02b0899467`.
It is not included in the main combined patch or base turbo map.

## Calibration model

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

The downstream stock load calculation therefore simplifies to:

```text
calculated_load_g_rev =
    min(
        VE × MAP_abs_mmHg × displacement_L × 1.3203052e-5 × 60
        × IAT_density_multiplier × global_multiplier,
        4.0 g/rev
    )
```

At VE 1.0, 20 °C, and 2.999 L, this is approximately 1.81 g/rev at 760 mmHg absolute and
2.42 g/rev at about 5 psi gauge. This confirms the scaling and dimensional path; it does not
validate the supplied VE values for the real engine.

The supplied VE surface is only a conservative mathematical starting point. It is not a measured
EZ30R VE map and must be calibrated from synchronized lambda, MAP, RPM, IAT, fuel-pressure, and
load data on a load-controlled dyno.

## Required hardware

- The MAF may be physically removed; it is no longer an airflow input.
- The original MAF assembly also carries IAT on common configurations. A standalone, fast-response
  IAT sensor must therefore retain the ECU's IAT circuit and be located after the intercooler in
  representative charge air. Confirm the actual vehicle harness and wiring diagram before wiring;
  this patch does not assume a pinout.
- MAP must be correctly scaled and valid throughout vacuum and the intended positive-pressure
  range. This component does not alter MAP scaling. The existing boost component supplies its own
  donor-derived scaling and requires the matching sensor plus a pressure-reference check.
- Stock MAP and direct IAT diagnostics remain active. The MAF high/low monitor and its P0102/P0103
  switches are disabled; one mixed temperature-plausibility condition is also bypassed because
  its decision requires the removed MAF signal.
- The shared ADC scan and raw MAF logger channel remain in stock code, but no patched airflow or
  diagnostic decision consumes that value. A raw-MAF log from this image has no tuning meaning.

## Status

Static implementation, Ghidra tracing, deterministic rebuilding, opcode checks, definition checks,
and multi-component overlap checks pass. Vehicle validation does not. Follow
[COMMISSIONING.md](COMMISSIONING.md) before any boosted operation.
