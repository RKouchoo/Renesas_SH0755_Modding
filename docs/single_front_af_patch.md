# D2WD610H Single-Front-A/F Patch

## Status and scope

This is a separate development patch for the exact project ROM:

- CALID `D2WD610H`
- ECU ID `3C5A387116`
- 2005 ADM Liberty 3.0R BLE MT project image
- SH7055, 512 KiB

It retains the factory RH/Bank-1 front A/F sensor pre-turbo as the only closed-loop feedback
sensor and mirrors its processed results into the Bank-2 paths after the complete stock Bank-1
processing runs. The LH/Bank-2 front A/F sensor can then be removed.

Both factory rear narrowband sensors and their processing remain stock. A post-turbo aftermarket
wideband is external instrumentation only: it is not wired to an ECU input, does not occupy an
ECU RAM parameter, and is not part of this ROM image.

The binary is statically verified but not vehicle-verified. Do not flash it until the sensor
identity, connector variant, checksum, and logged both-bank behavior have been checked on the
actual car.

## Implemented architecture

| Role | Physical channel | ECU behavior |
|---|---|---|
| Closed-loop feedback | Stock RH/Bank-1 front A/F sensor at `E47`, pre-turbo | Complete stock processing remains active; processed lambda/current/readiness are copied from Bank 1 to Bank 2 |
| Removed sensor | LH/Bank-2 front A/F sensor at `E24` | Bank-2 results and inhibit decision follow Bank 1; P0051, P0052, P0151, P0152, and P0154 switches are disabled |
| Rear catalyst sensors | Stock RH and LH rear narrowband sensors | Both ADC channels, processed results, heaters, diagnostics, and catalyst-monitor inputs remain stock |
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

## RomRaider runtime switch

Use
[D2WD610H_AVLS_single_front_af_patch.xml](../defs/D2WD610H_AVLS_single_front_af_patch.xml) for
this generated image. `Single Front A/F Patch Enable` writes `01` (on) or `00` (off) at
`0x7D91C`; the generated image defaults to on. Only exact `01` enables mirroring; erased `FF`
and every other value select the disabled/stock-logic paths.

This is a flash-image switch, not a live RomRaider logger control. Save the edited image with a
valid checksum and reflash it before the selected state can take effect.

- `ON`: run the complete stock front process, then mirror Bank-1 lambda/current/readiness into
  Bank 2; mirror diagnostic readiness; use Bank-1 inhibit status for both banks.
- `OFF`: run stock dual-front processing and diagnostics without mirroring, and use the original
  Bank-2 inhibit semantics.

The switch controls injected runtime logic, not the five noncontiguous DTC bytes written by the
patch builder. To restore fully stock diagnostic configuration, also turn on P0051, P0052,
P0151, P0152, and P0154 before saving/flashing. Do not use `OFF` as a normal operating mode after
the Bank-2 sensor is physically removed: stock logic will again depend on that absent sensor.

## Deliberately unchanged

The patch does not:

- hook `rear_o2_sensor_pair_voltage_process` at `0xE0D0`;
- repurpose raw rear ADC channels `0xFFFFAB20` or `0xFFFFAB0C`;
- overwrite rear results `0xFFFFB098` or `0xFFFFB09C`;
- disable RH- or LH-rear sensor/heater diagnostics;
- convert an aftermarket controller voltage to lambda;
- add aftermarket-wideband calibration tables or RomRaider ECU parameters; or
- use an external lambda value for fueling, enrichment, boost shutdown, or fuel cut.

This boundary avoids the uncertain analog conditioning, ground-offset, input-bias, and
vehicle-variant wiring issues associated with feeding a controller into a stock rear-O2 input.

## Patch layout

| Item | Address |
|---|---:|
| Front process hook | `0xB690` |
| Front diagnostic task pointer | `0x6A6C` |
| Bank-2 inhibit hook | `0x6500C` |
| Runtime enable byte | `0x7D91C` |
| Front mirror wrapper | `0x7D920` |
| Stock-prologue trampoline | `0x7D9A0` |
| Front diagnostic mirror wrapper | `0x7D9E0` |
| Bank-2 inhibit runtime selector | `0x7DA20` |

The standalone boost patch occupies `0x7D790..0x7D903`; this patch's injected blocks do not
overlap it. A future merged image must still be produced from the root stock ROM and audited as a
new combined system—never by stacking generated binaries.

## Harness boundary

Matching-generation RHD H6 service material identifies:

| Circuit | Engine connector | ECM terminal(s) |
|---|---|---|
| Front A/F RH, retained | `E47`, black 4-pole | signal+ `B134-33`, signal- `B134-26`, shield `B134-25`; heater control `B134-3`/`B134-2`, heater ground `B134-7` |
| Front A/F LH, removed | `E24`, black 4-pole | signal+ `B134-34`, signal- `B134-27`, shared shield `B134-25`; heater control `B134-1`/`B135-7`, heater ground `B134-5` |

Subaru diagrams vary by market and transmission. Before changing the harness, verify connector
colour, cavity numbering, and continuity on the actual vehicle. Do not infer the car's wiring
from a generic turbo or USDM pin list. Leave both rear sensor circuits wired exactly as stock.

## Logging

The standard RomRaider channels remain the ECU-side view:

- E91 A/F Sensor #1 (4-byte): `0xFFFFB4E8`
- E109 A/F Sensor #2 (4-byte): `0xFFFFB4EC`

After patching, both should track the retained factory sensor. That confirms the mirror reaches
the later stock logger paths; it does not prove that every per-bank transient or diagnostic
consumer behaves correctly.

Record the post-turbo wideband independently through its serial or CAN logger. For later analysis,
merge it with the RomRaider file using monotonic timestamps and retain explicit lambda-valid and
sensor-fault fields when the external protocol provides them. The external sensor's transport
delay must be considered when comparing lambda with RPM, throttle, load, or boost events.

## Known limitations and commissioning

- One pre-turbo sensor cannot identify a bank-specific fueling or exhaust fault; both fuel banks
  receive the retained RH sensor's feedback.
- Removing the LH sensor also removes independent Bank-2 sensor plausibility information. The
  five disabled DTC switches must be reviewed against the exact vehicle's regulatory use.
- Stock closed/open-loop transition logic remains unchanged.
- Both rear sensors remain required unless a separately designed and verified change removes
  them later.
- The ROM still needs a correct `subarudbw` checksum before flashing.

Commission in this order:

1. Confirm the exact ROM, retained RH sensor, and actual connector variant.
2. Build only from the canonical root stock ROM and run `verify_single_front_af.py`.
3. Open the image with the matching single-front-A/F RomRaider definition; confirm the enable
   switch reads on and verify that an off/on edit changes only `0x7D91C` before checksum handling.
4. Correct and verify the ROM checksum.
5. First run without boost and log E91/E109, closed-loop state, both fuel corrections, and all
   front/rear sensor DTCs.
6. Prove both displayed front channels track through idle, steady cruise, throttle transitions,
   forced open loop, warm-up, and a controlled retained-sensor fault.
7. Confirm both stock rear sensors and catalyst diagnostics still behave as they did on stock.
8. Validate the independently logged post-turbo lambda stream and timestamp alignment before it
   is used for tuning decisions.
