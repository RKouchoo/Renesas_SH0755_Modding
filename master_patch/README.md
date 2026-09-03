# D2WD610H master turbo patch

This directory contains the single current integration target for the 2005 ADM
Liberty 3.0R manual ECU (`D2WD610H`). It combines the previously separate
firmware work into one deterministic stock-to-output build:

- always-on MAFless speed density with committed-state low/high-lift AVLS VE
  tables and a provisional Haltech HT-010206 post-intercooler IAT calibration
  converted for an assumed 2.49 kOhm ECU pull-up;
- Omni Power `MAP-SUP-3BR` 3-bar MAP scaling;
- EVAP-output boost control with throttle, wideband, speed-density-input/result,
  soft-overboost, and hard fuel-cut gates;
- the former MAF ADC repurposed for the supplied seller-labelled `AEM 50-4110`
  / 30-4110-style P0/P1 0-5 V lambda signal;
- both stock front A/F paths and both rear O2 paths removed from feedback and
  diagnostics;
- the bounded per-cylinder rotational-idle timing post-processor, installed but
  default OFF;
- a live-barometric pressure failsafe that requests open loop before boost and
  a delayed, confirmed, pressure-release-latched 13.0-AFR fuel cut;
- a factory-ROM-derived STI pink injector scalar/deadtime starting point;
- a conservative 5 psi / 98 RON fuel, ignition, AVLS, and 6800 RPM starting
  calibration with every active engine-load axis extended to 4.0 g/rev; and
- focused, self-contained D2WD610H RomRaider ECU and logger definitions.

The generated baseline is `D2WD610H_master_patch.bin`, SHA-256
`f3efa36f8e3bef4e1eaa68544d0c1bc0578c6dbc53e7a13f87e08f8dcba01e6d`.
It is 512 KiB, contains CALID `D2WD610H`, and has a valid Subaru additive
checksum (`0xC96A0526`). It is a development artifact, not a vehicle-tested tune.
The complete generated logger definition has SHA-256
`9e16c1d8c39152d06af9e5a97070d2b97f581d4ab244e5d60539a71436626d2e`.

Two independent boost switches remain in RomRaider. `Electronic Boost Control
Enable` defaults OFF and forces zero actuator duty for direct wastegate-spring
control. `Overboost Fuel Cut Enable` defaults ON and independently retains the
6.5 psi hard MAP cut. MAFless airflow and the external-wideband/four-stock-O2
replacement are intentionally permanent because this architecture has no MAF
or stock-O2 fallback.

Two independent fueling-safety switches also default ON. The pressure guard
calls the original Primary Open Loop target routine and then revokes closed-loop
permission at live barometric pressure minus 0.5 psi. The lean guard arms above
0.5 psi gauge, waits 50 periodic task calls for the post-turbo sensor, confirms
eight consecutive invalid or leaner-than-13.0-AFR samples, and latches the stock
fuel-cut path until pressure falls below -0.5 psi gauge. The call-count defaults
are not time-calibrated and require controlled validation from logs.

`Rotational Idle Enable` defaults OFF. When enabled inside its warm,
stationary, closed-throttle, high-vacuum window, the wrapper runs the complete
stock timing calculation first and then applies the bounded cylinder pattern
`{-6, 0, -6, 0, -6, 0}` degrees. It cannot add advance, exceeds neither an
8-degree retard limit nor the original stock angle, and retains a 5-degree-BTDC
floor unless stock timing is already lower.

## Exact hardware assumptions

The MAP transfer comes from the supplied
[Omni Power MAP-SUP-3BR product data](https://www.prospeedracing.com.au/products/omni-power-3-bar-map-sensor-subaru-wrx-sti-97-00-wrx-08-14-lgt-04-09-toyota-supra-93-02-map-sup-3br):
0.60 V at 30 kPa absolute and 4.75 V at 300 kPa absolute. The advertised
Subaru fitment does not specifically name the EZ30R application, so connector
keying and terminal continuity still require physical confirmation.

The IAT transfer uses the published Haltech HT-010206 voltage/temperature
points, which Haltech documents for a 1 kOhm pull-up to 5 V. The builder
converts those points back to thermistor resistance and then to voltage for an
assumed 2.49 kOhm D2WD610H pull-up. That ECU resistance has not been confirmed
from a D2WD610H primary source or an installed-circuit measurement. The cold
tail below -10 C is extrapolated. It is therefore a useful starting reference,
not a verified sensor calibration; see [CALIBRATION.md](CALIBRATION.md) and
[COMMISSIONING.md](COMMISSIONING.md).

The only supported wideband transfer in this baseline is the P0/P1 table in the
instruction sheet supplied with the seller-labelled `AEM 50-4110` unit:
`gasoline AFR = 2*volts + 10` and
`lambda = (2*volts + 10)/14.64`. P0 displays AFR and P1 displays lambda while
producing the same analog output; P2/P3 are incompatible. Firmware retains a
conservative 0.50-4.50 V operating-plausibility window (11-19 gasoline AFR).
That window is not proof of sensor/controller health, because a fault may still
produce a midscale voltage. A different controller or calibration mode must not
be connected until its transfer has been entered and the image rebuilt.

See [WIRING.md](WIRING.md) before altering the harness,
[CALIBRATION.md](CALIBRATION.md) for exact defaults, [COMMISSIONING.md](COMMISSIONING.md)
for the required test sequence, [MEMORY_LAYOUT.md](MEMORY_LAYOUT.md) for exact
flash/RAM ownership, and [GHIDRA_AUDIT.md](GHIDRA_AUDIT.md) for the stock-ROM
evidence and remaining uncertainties.

## RomRaider definition selection

Load **only** `master_patch/D2WD610H_master_patch.xml` as the ECU definition for
this image. The stock, standalone speed-density, and older component XML files
share the unchanged factory CALID `D2WD610H`; if one of those files is selected,
RomRaider can open the master binary with legacy names such as `Base Timing A`
through `F` and without the complete master tables. The master definition shows
the four reachable surfaces as normal/high cam and intake-AVCS-tracking-ratio
1.0/0.0, and omits the two unreachable surfaces. It also replaces the ambiguous
AVCS A/B labels with functional AVLS-low-cam and AVLS-high-cam target names.
Restart RomRaider after changing the definition file so no old parsed definition
remains in memory.

The matching logger artifact is `D2WD610H_master_logger.xml`. It is a complete
metric SSM logger definition, not an XML fragment. It deliberately reduces the
upstream global catalogue to 63 H6-MT standard parameters, 46 relevant switches,
35 useful stock extended parameters for ECU ID `3C5A387116`, and master
parameters E500--E506. TCU/DCCD, diesel/common-rail/DPF, removed stock-O2/MAF,
and unrelated-model dashboard entries are omitted. The smaller
`*_ecuparams.xml` file is builder input only and must not be selected as a
complete logger definition.

The master definition uses numbered workflow categories so related stock and
patched calibrations stay together in RomRaider: air model, fueling, wideband,
ignition, cam control, boost, protection, throttle, idle, sensors/cooling, then
the checksum entry. The numbering controls RomRaider's otherwise alphabetical
flat category list; it does not affect ROM addresses or calibration data.
`02.8 - Fueling - Fuel Pump Control` exposes the Ghidra-verified stock 33.3 and
66.7-percent FPCU command literals. Their generated values remain stock; they
are present so a copied BIN can run the documented stationary full-speed mode
diagnostic while P47 is logged. The shared 100-percent high-mode/PWM
normalization constant is deliberately fixed and omitted from the editor.

## Build and verify

Run from the repository root:

```sh
python3 master_patch/build_master_patch.py
python3 master_patch/build_definition.py
python3 master_patch/verify_master_patch.py
```

The checked-in complete logger was generated from the metric-English file in
the [RomRaider logger v370 package](https://www.romraider.com/forum/viewtopic.php?start=1&t=1642),
`logger_METRIC_EN_v370.xml` (source SHA-256
`e5fa42e381eae904437f87319bd891cc497340d1c4758dde6f652f8eeeccc68f`):

```sh
python3 master_patch/install_master_logger.py \
  /path/to/logger_METRIC_EN_v370.xml \
  master_patch/D2WD610H_master_logger.xml
```

The builder reads only the immutable root `2005 BLE MT.bin`, verifies its
SHA-256, checks the byte-identical `base_roms` copy and de-encapsulated original
SRF payload, applies each component to an in-memory copy, then writes the
separate output. Generated ROMs are never accepted as build inputs.

`verify_master_patch.py` independently reconstructs the image, audits changed
regions, disassembles new firmware, tests sensor boundary policy, checks every
hook and diagnostic switch, runs the independent master-calibration policy
checks, validates both complete RomRaider definitions and the logger fragment,
and verifies provenance and checksum.

## Files

| File | Purpose |
|---|---|
| `build_master_patch.py` | Deterministic stock-to-master builder. |
| `master_calibration.py` | IAT, fuel, timing, KCA, AVCS, STI-pink injector, spring-only boost, rev-limit, and Subaru-checksum implementation. |
| `verify_master_calibration.py` | Independent IAT, fuel, timing, KCA, AVCS, injector, boost, limiter, and checksum policy checks used by the master verifier. |
| `../speed_density/patch_speed_density.py` | Single MAFless SD component containing committed-state dual VE and predictable 3200/3000 RPM AVLS calibration. |
| `wideband_component.py` | Permanent four-stock-O2 delete and former-MAF external-wideband input firmware. |
| `../fueling_safety/fueling_safety_component.py` | Pressure-forced-open-loop and latched lean-cut component. |
| `../patch/patch_rotational_idle.py` | Reusable bounded rotational-idle component, integrated default OFF. |
| `verify_master_patch.py` | Independent binary, opcode, calibration, XML, logger, and provenance audit. |
| `MEMORY_LAYOUT.md` | Exact injected-flash boundaries and collision policy. |
| `build_definition.py` | Generates the focused D2WD610H RomRaider definition. |
| `D2WD610H_master_patch.xml` | Matching self-contained metric RomRaider definition. |
| `D2WD610H_master_logger.xml` | Complete metric, SSM-only logger definition for ECU ID `3C5A387116`; ready artifact generated from logger v370. |
| `D2WD610H_master_logger_ecuparams.xml` | Internal seven-parameter fragment used to generate the complete logger definition. |
| `D2WD610H_idle_diagnostic_profile.xml` | RomRaider profile selecting the cold-idle diagnostic channels in Data and all E500--E506 custom channels on Dashboard. |
| `install_master_logger.py` | Generates a complete D2WD610H-only logger from a normal complete logger XML, retaining its DTD and applicable stock channels. |
| `ghidra_scripts/ApplyMasterNames.java` | Reproducibly reapplies the names/comments confirmed in live Ghidra. |

## Hard limitations

- The base VE table is mathematical, not measured on this engine.
- The HT-010206 IAT curve assumes a 2.49 kOhm ECU pull-up. A wrong pull-up,
  sensor-ground offset, or cold-tail extrapolation directly biases
  speed-density airflow and all load-indexed tuning.
- The two AVLS VE tables are seeded from that same mathematical surface and
  still require separate log calibration. Continuous AVCS position remains an
  unmodeled influence within each lift state.
- One post-turbo sensor now represents both banks; it cannot detect a bank-only
  mixture fault and has more transport delay than either original pre-cat sensor.
- The supplied four-wire controller has a single-ended analog output and no
  separate analog ground. Ground offset and in-range fault output must be
  physically characterized; the firmware validity window cannot prove health.
- The stock oxygen-sensor heater outputs are not electrically disabled. Removed
  sensor connectors must be unplugged, sealed, and prevented from shorting.
- A valid checksum and passing static audit do not prove ADC voltage tolerance,
  harness pinout, MAP accuracy, PWM polarity/frequency, wastegate plumbing, fuel
  delivery, or combustion safety.
- The 5 psi target cannot limit boost caused by wastegate spring error or boost
  creep. Use an independent mechanical pressure test and a load-controlled dyno.
