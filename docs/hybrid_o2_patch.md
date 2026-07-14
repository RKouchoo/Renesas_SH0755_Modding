# D2WD610H Hybrid Factory-A/F + AEM Logging Patch

## Status and scope

This is a separate development patch for the exact project ROM:

- CALID `D2WD610H`
- ECU ID `3C5A387116`
- 2005 ADM Liberty 3.0R BLE MT project image
- SH7055, 512 KiB

It retains one factory front A/F sensor pre-turbo for low-load closed-loop fueling and adds an
AEM X-Series Inline 30-0310 post-turbo as a logging-only sensor. The AEM does **not** command
fuel, force enrichment, or provide overboost protection. The current patch retains the LH rear
narrowband sensor and its diagnostics.

The binary is statically verified, but the analog interface and exact vehicle harness are not yet
vehicle-verified. Do not flash or splice the harness until the continuity and bench checks below
pass.

## Implemented architecture

| Role | Physical channel | ECU path | Result |
|---|---|---|---|
| Closed-loop feedback | Stock RH/Bank-1 front A/F sensor at `E47`, pre-turbo | Stock processing to `0xFFFFAE60`, then the patch mirrors Bank 1 into Bank 2 | Both banks retain stock conditioning/fuel control; RomRaider E91/E109 remain factory-sensor lambda |
| Removed front sensor | LH/Bank-2 front A/F sensor at `E24` | Bank-2 lambda/current/readiness and inhibit state follow Bank 1 | P0051, P0052, P0151, P0152, and P0154 switches are disabled |
| Post-turbo reference | AEM 30-0310 through a protected 0.2 V/V conditioner into RH rear input `E61-3`/`E61-4` | Raw `0xFFFFAB20` → calibrated AEM volts → lambda → `0xFFFFB098` | RomRaider E500 logs lambda; `0.0` means reconstructed voltage is outside the configured window |
| Remaining rear sensor | Stock LH rear sensor | Stock `0xFFFFAB0C` → `0xFFFFB09C` | Stock processing and P0057/P0058/P0157/P0158 switches remain enabled |

The front-sensor hook runs the complete stock `front_af_sensor_pair_signal_process` body before
copying `AE60→AE64`, `AE68→AE6C`, and `AE70→AE74`. The stock pump-current diagnostic task also
runs before its wrapper refreshes `AE70→AE74`. The Bank-2 inhibit helper tail-jumps to the
unchanged Bank-1 helper. This preserves Bank-1 sensor diagnostics instead of globally bypassing
the factory A/F subsystem.

Ghidra's direct-reference audit of the reused `0xFFFFB098` rear result found only the stock
rear-sensor diagnostic getter and the SSM/log conversion stubs; no direct fuel-control consumer
was found. The AEM value is therefore kept out of the traced fueling path, although untested
rear/catalyst diagnostic behavior remains a commissioning item.

## Correct connector identity

The project ROM identifies itself as ADM D2WD610H/`3C5A387116`. The matching-generation Subaru
H6 diagnostics manual identifies these engine/ECM circuits:

| Circuit | Engine connector | ECM terminal(s) |
|---|---|---|
| Front A/F RH, retained | `E47`, black 4-pole | signal+ `B134-33`, signal− `B134-26`, shield `B134-25`; heater control `B134-3`/`B134-2`, heater ground `B134-7` |
| Front A/F LH, removed | `E24`, black 4-pole | signal+ `B134-34`, signal− `B134-27`, shared shield `B134-25`; heater control `B134-1`/`B135-7`, heater ground `B134-5` |
| Rear O2 RH, repurposed | `E61`, dark-gray 4-pole | `E61-3` ↔ signal `B137-24`; `E61-4` ↔ sensor ground `B136-35` |
| Rear O2 LH, retained | `E25` | signal `B137-25`; sensor ground `B136-35` |

These assignments come from the Subaru H6 diagnostic I/O table and the circuit-specific
continuity procedure, not a generic turbo/USDM pin list. The firmware independently agrees:
`adc_module_1_scan_results_copy` supplies raw `0xFFFFAB20`, and
`rear_o2_sensor_pair_voltage_process` converts it into RH output `0xFFFFB098`.

Critical exclusion: **do not use `B135-15`**. On this H6 generation it is ignition control #4,
not a spare analog input.

Primary references:

- [Subaru 2004 Legacy H6 engine diagnostics, part 1](https://subaruport.ru/leg4/leg4_sec3_11-1.pdf)
- [Subaru 2004 Legacy H6 engine diagnostics, part 2](https://subaruport.ru/leg4/leg4_sec3_11-2.pdf)
- [Subaru 2004 Legacy wiring system](https://subaruport.ru/leg4/leg4_wir_3.pdf)

Those manuals cover the matching RHD H6 generation, but they are not a VIN-specific ADM-MT
harness guarantee. Subaru published differing diagrams. The following on-car checks are the
final authority for this vehicle:

1. Key off; disconnect the ECM and `E61` before continuity testing.
2. Prove `E61-3` reaches `B137-24` and no adjacent terminal.
3. Prove `E61-4` reaches `B136-35` and no adjacent terminal.
4. Reconnect the ECM but leave the stock RH rear sensor disconnected. With a high-impedance
   meter, key-on voltage at `E61-3` should be in the manual's `0.2–0.5 V` diagnostic bias range.
5. Stop if connector colour, cavity numbering, continuity, or bias differs. Do not adapt a
   different diagram by guesswork.

## AEM wiring boundary

Use AEM 30-0310 with its Bosch LSU4.9 sensor:

- AEM red: switched 12 V through the specified 5 A fuse.
- AEM black: controller power ground.
- AEM white: analog positive into the conditioner differential input.
- AEM brown: analog negative/reference into the conditioner differential input.
- Conditioner output positive: `E61-3`.
- Conditioner output reference: `E61-4`.
- Insulate the unused stock RH rear-sensor heater conductors individually.

The [official AEM manual](https://documents.aemelectronics.com/techlibrary_30-0310_x-series_inline_wideband_uego_sensor_controller.pdf)
defines white/brown as a differential analog pair and gives:

```text
lambda = 0.1621 × AEM_volts + 0.4990
valid output = 0.5–4.5 V
below 0.5 V = not ready
above 4.5 V = sensor error
```

Do **not** connect the AEM 0.5–4.5 V output directly to `E61-3`. Subaru specifies this rear input
as roughly 0–0.9 V and the disconnected input is biased. Use a high-impedance,
buffered/protected conditioner that maps 0.5–4.5 V to 0.1–0.9 V (nominal gain `0.2 V/V`) while
preserving the AEM brown reference. The earlier 40 kΩ/10 kΩ passive-divider idea is not an
approved final circuit because input bias, loading, fault current, and transient protection have
not been measured.

The conditioner is external hardware and is not supplied by the ROM patch. Its final design must
be differential at the AEM white/brown side, present little load to the AEM output, tolerate the
measured `E61-3` bias, limit fault current into the ECM, and provide automotive transient/input
protection. If ECU-wire disconnect detection is required, make its output fail below 0.1 V (or
provide an independently logged fault signal) when the controller/interface loses power or
continuity. The stock open-input bias of 0.2–0.5 V can reconstruct as a plausible AEM voltage, so
the ROM voltage-window check alone cannot prove that the ECU-side signal wire is connected.

Install the AEM sensor at least 45 cm/18 in downstream of the turbo, upstream of the catalyst,
in a leak-free section, with the sensing end more than 10° above horizontal for condensation
drainage. Avoid a completely vertical orientation, per AEM's placement guidance.

## RomRaider logging

RomRaider metric logger definition v370 already maps this ECU's factory channels as follows:

- E91 A/F Sensor #1 (4-byte): `0xFFFFB4E8`
- E109 A/F Sensor #2 (4-byte): `0xFFFFB4EC`

The patch intentionally leaves both as the mirrored factory sensor. A separate D2-only logger
fragment adds:

- E500 `AEM Post-Turbo Lambda (D2WD610H)*`: float `0xFFFFB098`
- E501 `AEM Input Raw ADC (D2WD610H)*`: unsigned 16-bit `0xFFFFAB20`

Install the fragment into a normal RomRaider logger definition without altering the source file:

```sh
python3 patch/install_aem_logger.py /path/to/logger_METRIC_EN_v370.xml
```

Then select the generated `_D2WD610H_AEM.xml` file under **Logger → Settings → Logger
Definition Location**. The installer verifies that the source supports ECU ID `3C5A387116`,
refuses parameter-ID collisions, writes a new file, and parses the result before finishing. See
the [RomRaider logger-definition update thread](https://www.romraider.com/forum/viewtopic.php?f=8&t=1642)
and [RomRaider logger DTD](https://github.com/RomRaider/RomRaider/blob/master/definitions/logger.dtd)
for the upstream format.

The standard `Rear O2 Sensor` parameter may display a numerically related value with the wrong
unit/format; use E500 for this patch.

## Analog calibration and commissioning

The default ROM model is:

```text
AEM_volts = 0.0001274108854 × raw_AB20 − 0.175
lambda    = 0.1621 × AEM_volts + 0.4990
```

The first line is only a nominal model of the stock rear-input scaling plus a 0.2 V/V
conditioner. Calibrate it on the actual ECU and harness:

1. Keep the engine off and the AEM sensor/controller out of fuel control (it is logging-only in
   this patch).
2. Feed the conditioner a current-limited 0.5 V, 2.5 V, and 4.5 V referenced exactly as the AEM
   white/brown pair will be referenced.
3. Record E501 raw counts at all three points. Confirm monotonic response and no clipping.
4. Fit `AEM_volts = scale × raw + offset`; enter the fitted pair in `AEM Logger Input Raw Scale`
   and `AEM Logger Input Voltage Offset` in
   `defs/D2WD610H_AVLS_wideband_patch.xml`.
5. Repeat the sweep. E500 should read approximately lambda `0.58005`, `0.90425`, and `1.22845`.
6. Confirm the AEM's below-0.5 V warm-up output and above-4.5 V error output propagate through
   the conditioner and produce E500 `0.0`.
7. Disconnect the ECU-side conditioner output and record E501/E500. Do not accept a plausible
   value as proof of continuity; the stock rear-input bias can place an open circuit inside the
   software's valid window. Add a hardware fail-low mechanism if this fault must be detectable.
8. Only then compare the post-turbo AEM against the retained factory sensor at steady
   stoichiometric operation. Expect transient disagreement from exhaust transport delay and
   sensor location.

## Known limitations before vehicle use

- One pre-turbo sensor cannot identify a bank-specific fueling or exhaust fault; both fuel banks
  see the retained RH sensor's feedback.
- The post-turbo AEM is a reference only. A lean reading does not currently trigger enrichment,
  boost shutdown, or fuel cut.
- The patch retains stock CL/OL transition logic. The later merged boost/O2 patch must be
  reviewed as one system before boost testing.
- RH rear catalyst-monitor behavior beyond the explicitly disabled P0037/P0038/P0137/P0138
  switches has not been vehicle-tested.
- The software validity window does not reliably detect an open `E61-3` circuit because the stock
  rear-input bias may look like a valid conditioned AEM voltage.
- The ROM still needs the correct `subarudbw` checksum before flashing.
- Exhaust placement, ground offset, input protection, conditioner accuracy, and logging rate all
  require physical validation.
