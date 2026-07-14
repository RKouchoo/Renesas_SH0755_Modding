# D2WD610H Single-Front-A/F + Rear-O2-Delete Patch

## Status and scope

This is a development patch for the exact project ROM:

- CALID `D2WD610H`
- ECU ID `3C5A387116`
- 2005 ADM Liberty 3.0R BLE MT project image
- SH7055, 512 KiB

It retains the factory RH/Bank-1 front A/F sensor pre-turbo as the only closed-loop feedback
sensor and mirrors its processed results into the Bank-2 paths after the complete stock Bank-1
processing runs. The LH/Bank-2 front A/F sensor can then be removed.

The same runtime enable now logically removes both factory rear narrowband sensors. While enabled,
the patch bypasses their ADC conversion and the complete traced rear monitoring pipeline, and it
disables the eight rear sensor/heater DTC switches mapped for D2WD610H. A post-turbo aftermarket
wideband remains external instrumentation only: it is not wired to an ECU input, does not occupy
an ECU RAM parameter, and is not part of this ROM image.

The binaries are statically verified but not vehicle-verified. Do not flash them until the sensor
identity, connector variant, checksum, and logged both-bank behavior have been checked on the car.
Rear-O2 deletion may also affect emissions compliance and readiness requirements.

## Implemented architecture

| Role | Physical channel | ECU behavior while enabled |
|---|---|---|
| Closed-loop feedback | Stock RH/Bank-1 front A/F sensor at `E47`, pre-turbo | Complete stock processing remains active; processed lambda/current/readiness are copied from Bank 1 to Bank 2 |
| Removed front sensor | LH/Bank-2 front A/F sensor at `E24` | Bank-2 results and inhibit decision follow Bank 1; P0051, P0052, P0151, P0152, and P0154 are disabled |
| Removed rear sensors | RH and LH rear narrowbands | Rear ADC conversion, threshold/filter/delta updates, response integration, and low/high-voltage diagnostic dispatch are bypassed; P0037, P0038, P0057, P0058, P0137, P0138, P0157, and P0158 are disabled |
| Post-turbo reference | External wideband and logger | No electrical or firmware connection to the ECU; synchronize its timestamped log with the ECU log off-board |

The front entry hook runs the complete stock `front_af_sensor_pair_signal_process` body through a
prologue trampoline, then copies:

```text
0xFFFFAE60 -> 0xFFFFAE64   processed lambda-like result
0xFFFFAE68 -> 0xFFFFAE6C   pump-current-like result
0xFFFFAE70 -> 0xFFFFAE74   readiness/diagnostic metric
```

The stock front pump-current diagnostic task still runs. Its wrapper refreshes only the final
Bank-2 readiness copy while enabled. A runtime selector makes the Bank-2 inhibit hook use the
unchanged Bank-1 helper while enabled and reconstructs the complete stock Bank-2 helper behavior
while disabled.

Ghidra tracing found that processed rear values `0xFFFFB098/0xFFFFB09C` feed a bank-select getter,
the rear monitor chain, and two logging conversion stubs; no fuel-control consumer was found. The
enabled patch therefore:

1. hooks `rear_o2_sensor_pair_adc_convert` at `0xE0D0` and returns before either rear ADC channel is
   converted;
2. redirects task pointers `0x11488`, `0x1148C`, `0x11490`, and `0x11494` through exact-`01`
   selectors that bypass threshold, filter/delta, response-integrator, and response-ratio updates;
   and
3. redirects task pointer `0x114A0` through a selector that bypasses the paired low/high rear-O2
   voltage diagnostics.

The stock rear heater-output routines are not rewritten or electrically tri-stated. With the
sensors physically disconnected those ECU outputs can still be commanded into an open circuit,
but their mapped circuit DTCs are disabled and their signals are not consumed by the traced rear
monitor pipeline. Keep disconnected harness terminals insulated.

## RomRaider runtime switch

Use
[D2WD610H_AVLS_single_front_af_patch.xml](../defs/D2WD610H_AVLS_single_front_af_patch.xml) for
the standalone image. `Single Front A/F Patch Enable` writes `01` (on) or `00` (off) at
`0x7D91C`; the generated image defaults to on. Only exact `01` enables the substitutions. Erased
`FF` and every other value select the disabled/stock-logic paths.

This is a flash-image switch, not a live RomRaider logger control. Save the edited image with a
valid checksum and reflash it before the selected state can take effect.

- `ON`: mirror the retained front sensor into Bank 2, use Bank-1 inhibit status for both banks,
  and bypass both rear narrowband processing/monitor paths.
- `OFF`: run stock dual-front and rear-O2 runtime logic.

The switch does not restore the 13 noncontiguous DTC bytes written by the patch builder. For fully
stock diagnostics, turn on P0051, P0052, P0151, P0152, P0154, P0037, P0038, P0057, P0058,
P0137, P0138, P0157, and P0158 before saving/flashing. Do not use `OFF` after any of those physical
sensors has been removed: stock logic will again depend on absent channels.

## Deliberately unchanged

The patch does not:

- feed an aftermarket controller into a stock rear-O2 or other ECU analog input;
- convert an aftermarket-controller voltage to lambda;
- add aftermarket-wideband calibration tables, RAM publication, or RomRaider ECU parameters;
- use an external lambda value for fueling, enrichment, boost shutdown, or fuel cut;
- alter the retained RH/Bank-1 front sensor diagnostics; or
- repurpose any removed O2 wiring for other hardware.

This boundary avoids uncertain analog conditioning, ground-offset, input-bias, and
vehicle-variant wiring issues. The post-turbo wideband must be logged independently.

## Patch layout

| Item | Address |
|---|---:|
| Front process hook | `0xB690` |
| Front diagnostic task pointer | `0x6A6C` |
| Bank-2 inhibit hook | `0x6500C` |
| Rear ADC conversion hook | `0xE0D0` |
| Rear monitor task pointers | `0x11488`, `0x1148C`, `0x11490`, `0x11494`, `0x114A0` |
| Runtime enable byte | `0x7D91C` |
| Front mirror wrapper | `0x7D920` |
| Front stock-prologue trampoline | `0x7D9A0` |
| Front diagnostic mirror wrapper | `0x7D9E0` |
| Bank-2 inhibit runtime selector | `0x7DA20` |
| Rear ADC selector / relocated prologue | `0x7DA60` / `0x7DA80` |
| Rear monitor selectors | `0x7DAA0`, `0x7DAC0`, `0x7DAE0`, `0x7DB00`, `0x7DB20` |

The standalone boost patch occupies `0x7D790..0x7D903`; these blocks do not overlap it.
`patch/patch_combined.py` applies both guarded change sets to one fresh root-stock copy and audits
the result as a new combined system. It never stacks generated binaries.

## Harness boundary

Matching-generation RHD H6 service material identifies:

| Circuit | Engine connector | ECM terminal(s) |
|---|---|---|
| Front A/F RH, retained | `E47`, black 4-pole | signal+ `B134-33`, signal- `B134-26`, shield `B134-25`; heater control `B134-3`/`B134-2`, heater ground `B134-7` |
| Front A/F LH, removed | `E24`, black 4-pole | signal+ `B134-34`, signal- `B134-27`, shared shield `B134-25`; heater control `B134-1`/`B135-7`, heater ground `B134-5` |

Subaru diagrams vary by market and transmission. Before changing the harness, verify connector
colour, cavity numbering, and continuity on the actual vehicle. Do not infer the car's wiring from
a generic turbo or USDM pin list. Disconnect rear sensors at their verified sensor connectors;
do not cut, ground, or repurpose unknown ECU terminals.

## Logging

The standard RomRaider front channels remain the ECU-side view:

- E91 A/F Sensor #1 (4-byte): `0xFFFFB4E8`
- E109 A/F Sensor #2 (4-byte): `0xFFFFB4EC`

After patching, both should track the retained factory sensor. That confirms the mirror reaches
the later stock logger paths; it does not prove every transient or diagnostic consumer behaves
correctly. Rear-O2 logger values are stale/undefined while the delete is enabled and must not be
used for tuning or validation.

Record the post-turbo wideband independently through its serial or CAN logger. Merge it with the
RomRaider file using monotonic timestamps and retain explicit lambda-valid and sensor-fault fields.
Account for post-turbo transport delay when comparing lambda with RPM, throttle, load, or boost.

## Known limitations and commissioning

- One pre-turbo sensor cannot identify a bank-specific fueling or exhaust fault; both fuel banks
  receive the retained RH sensor's feedback.
- Removing three factory sensors removes their independent plausibility information.
- Stock closed/open-loop transition logic remains unchanged.
- Ghidra found no direct rear-voltage fuel-control consumer, but this remains static analysis and
  must be proven on the vehicle.
- Rear heater output drivers are not forced off; only their mapped DTCs and downstream monitoring
  are disabled.
- The ROM still needs a correct `subarudbw` checksum before flashing.

Commission in this order:

1. Confirm the exact ROM, retained RH sensor, and actual connector variant.
2. Build only from the canonical root stock ROM and run `verify_single_front_af.py`.
3. Open the image with the matching definition; confirm the enable reads on and verify an off/on
   edit changes only `0x7D91C` before checksum handling.
4. Correct and verify the ROM checksum.
5. First run without boost. Log E91/E109, closed-loop state, both fuel corrections, and every
   front/rear sensor DTC.
6. Prove both displayed front channels track through idle, cruise, throttle transitions, forced
   open loop, warm-up, and a controlled retained-sensor fault.
7. With the rear connectors safely isolated, confirm all eight mapped rear DTCs remain inactive,
   rear logger channels are ignored, and closed-loop fuel corrections do not change unexpectedly.
8. Validate the independent post-turbo lambda stream and timestamp alignment before using it for
   tuning decisions.
