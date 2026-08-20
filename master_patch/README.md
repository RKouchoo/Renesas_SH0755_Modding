# D2WD610H master turbo patch

This directory contains the single current integration target for the 2005 ADM
Liberty 3.0R manual ECU (`D2WD610H`). It combines the previously separate
firmware work into one deterministic stock-to-output build:

- always-on MAFless speed density with a 13x17 MAP/RPM VE table and retained
  post-intercooler IAT input;
- Omni Power `MAP-SUP-3BR` 3-bar MAP scaling;
- EVAP-output boost control with throttle, wideband, speed-density-input/result,
  soft-overboost, and hard fuel-cut gates;
- the former MAF ADC repurposed for an AEM X-Series `30-0300` 0-5 V lambda
  signal;
- both stock front A/F paths and both rear O2 paths removed from feedback and
  diagnostics;
- a factory-ROM-derived STI pink injector scalar/deadtime starting point;
- a conservative 5 psi / 98 RON fuel, ignition, AVLS, and 6800 RPM starting
  calibration; and
- a focused, self-contained D2WD610H RomRaider definition and logger fragment.

The generated baseline is `D2WD610H_master_patch.bin`, SHA-256
`6557eda87eebaef51892b6607175cbd19b909565c3de6d9f90fe5e597aec0fac`.
It is 512 KiB, contains CALID `D2WD610H`, and has a valid Subaru additive
checksum (`0xB87F6478`). It is a development artifact, not a vehicle-tested tune.

Only `Boost Control Patch Enable` remains a RomRaider firmware toggle. MAFless
airflow and the AEM/four-stock-O2 replacement are intentionally permanent in
this image because its physical architecture has no MAF or stock O2 fallback.

## Exact hardware assumptions

The MAP transfer comes from the supplied
[Omni Power MAP-SUP-3BR product data](https://www.prospeedracing.com.au/products/omni-power-3-bar-map-sensor-subaru-wrx-sti-97-00-wrx-08-14-lgt-04-09-toyota-supra-93-02-map-sup-3br):
0.60 V at 30 kPa absolute and 4.75 V at 300 kPa absolute. The advertised
Subaru fitment does not specifically name the EZ30R application, so connector
keying and terminal continuity still require physical confirmation.

The only supported wideband transfer in this baseline is the
[AEM X-Series 30-0300](https://documents.aemelectronics.com/techlibrary_30-0300.pdf):
`lambda = 0.1621 * volts + 0.4990`. The firmware accepts 0.50 through 4.50 V
inclusive. A different controller must not be connected until its transfer and
fault voltages have been entered and the image rebuilt or edited with the
matching definition.

See [WIRING.md](WIRING.md) before altering the harness,
[CALIBRATION.md](CALIBRATION.md) for exact defaults, [COMMISSIONING.md](COMMISSIONING.md)
for the required test sequence, and [GHIDRA_AUDIT.md](GHIDRA_AUDIT.md) for the
stock-ROM evidence and remaining uncertainties.

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
hook and diagnostic switch, reuses the complete base-turbo calibration audit,
validates the RomRaider definition and logger fragment, and verifies provenance
and checksum.

## Files

| File | Purpose |
|---|---|
| `build_master_patch.py` | Deterministic stock-to-master builder. |
| `wideband_component.py` | Permanent four-stock-O2 delete and former-MAF AEM input firmware. |
| `verify_master_patch.py` | Independent binary, opcode, calibration, XML, logger, and provenance audit. |
| `build_definition.py` | Generates the focused D2WD610H RomRaider definition. |
| `D2WD610H_master_patch.xml` | Matching self-contained metric RomRaider definition. |
| `D2WD610H_master_logger_ecuparams.xml` | Three D2WD610H-only RomRaider logger parameters. |
| `install_master_logger.py` | Adds those parameters to a copy of a normal SSM logger definition. |
| `ghidra_scripts/ApplyMasterNames.java` | Reproducibly reapplies the names/comments confirmed in live Ghidra. |

## Hard limitations

- The base VE table is mathematical, not measured on this engine.
- One post-turbo sensor now represents both banks; it cannot detect a bank-only
  mixture fault and has more transport delay than either original pre-cat sensor.
- The stock oxygen-sensor heater outputs are not electrically disabled. Removed
  sensor connectors must be unplugged, sealed, and prevented from shorting.
- A valid checksum and passing static audit do not prove ADC voltage tolerance,
  harness pinout, MAP accuracy, PWM polarity/frequency, wastegate plumbing, fuel
  delivery, or combustion safety.
- The 5 psi target cannot limit boost caused by wastegate spring error or boost
  creep. Use an independent mechanical pressure test and a load-controlled dyno.
