# D2WD610H master turbo patch

This directory contains the single current integration target for the 2005 ADM
Liberty 3.0R manual ECU (`D2WD610H`). It combines the previously separate
firmware work into one deterministic stock-to-output build:

- always-on MAFless speed density with committed-state low/high-lift AVLS VE
  tables and retained post-intercooler IAT input;
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
  calibration; and
- a focused, self-contained D2WD610H RomRaider definition and logger fragment.

The generated baseline is `D2WD610H_master_patch.bin`, SHA-256
`3e5a18d495e567e121f6692f0f8939b8a4dc8bf22f479186c56f66b82cf993a2`.
It is 512 KiB, contains CALID `D2WD610H`, and has a valid Subaru additive
checksum (`0xB0B76582`). It is a development artifact, not a vehicle-tested tune.

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

## Build and verify

Run from the repository root:

```sh
python3 master_patch/build_master_patch.py
python3 master_patch/build_definition.py
python3 master_patch/verify_master_patch.py
```

The builder reads only the immutable root `2005 BLE MT.bin`, verifies its
SHA-256, checks the byte-identical `base_roms` copy and de-encapsulated original
SRF payload, applies each component to an in-memory copy, then writes the
separate output. Generated ROMs are never accepted as build inputs.

`verify_master_patch.py` independently reconstructs the image, audits changed
regions, disassembles new firmware, tests sensor boundary policy, checks every
hook and diagnostic switch, runs the independent master-calibration policy
checks, validates the RomRaider definition and logger fragment, and verifies
provenance and checksum.

## Files

| File | Purpose |
|---|---|
| `build_master_patch.py` | Deterministic stock-to-master builder. |
| `master_calibration.py` | Fuel, timing, STI-pink injector, spring-only boost, rev-limit, and Subaru-checksum implementation. |
| `verify_master_calibration.py` | Independent fuel, timing, injector, boost, limiter, and checksum policy checks used by the master verifier. |
| `../speed_density/patch_speed_density.py` | Single MAFless SD component containing committed-state dual VE and predictable 3200/3000 RPM AVLS calibration. |
| `wideband_component.py` | Permanent four-stock-O2 delete and former-MAF external-wideband input firmware. |
| `../fueling_safety/fueling_safety_component.py` | Pressure-forced-open-loop and latched lean-cut component. |
| `../patch/patch_rotational_idle.py` | Reusable bounded rotational-idle component, integrated default OFF. |
| `verify_master_patch.py` | Independent binary, opcode, calibration, XML, logger, and provenance audit. |
| `MEMORY_LAYOUT.md` | Exact injected-flash boundaries and collision policy. |
| `build_definition.py` | Generates the focused D2WD610H RomRaider definition. |
| `D2WD610H_master_patch.xml` | Matching self-contained metric RomRaider definition. |
| `D2WD610H_master_logger_ecuparams.xml` | Seven D2WD610H-only RomRaider logger parameters, including AFR, AVLS state, and lean-cut state/counter. |
| `install_master_logger.py` | Adds those parameters to a copy of a normal SSM logger definition. |
| `ghidra_scripts/ApplyMasterNames.java` | Reproducibly reapplies the names/comments confirmed in live Ghidra. |

## Hard limitations

- The base VE table is mathematical, not measured on this engine.
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
