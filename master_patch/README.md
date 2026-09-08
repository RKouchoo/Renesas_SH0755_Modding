# D2WD610H master patch — v1

This directory contains the rolling v1 builder, calibration and saved artifacts.
Use the [central reference](../docs/reference/README.md) for architecture and
verified address meanings, and the [image comparison](../docs/reference/IMAGES.md)
for differences from v2.

The saved [D2WD610H_master_patch.bin](D2WD610H_master_patch.bin) matches the
current builder byte for byte. SHA-256:
`154760a5f2fdadbf6d9221480595f58dc77c6a4eccc492f50899c815aca79e4d`;
Subaru checksum `16F63B0D`.

V1 contains the local MAF-fault load bypass, repaired SD pressure boundary and
ten-cell idle-VE correction. V2 contains additional timing and MAP-pressure
tip-in corrections and now includes the same bypass through the
[September 9 repair](../docs/reference/V2_LOAD_FALLBACK_FIX.md). This v1 image
is unchanged. The near-stall's cause remains unresolved.

## Build and verify

From the repository root:

```sh
python3 -B master_patch/build_master_patch.py
python3 -B master_patch/build_definition.py
python3 -B tests/verify_master_patch.py
```

The build commands write the normal v1 outputs. The verifier independently
rebuilds in memory and checks the saved BIN, changed regions, firmware hooks,
calibration, definitions, logger, instruction fixtures and checksum. The
builder accepts pinned stock inputs; generated ROMs are not build inputs.

The former `master_patch/verify_master_patch.py` command remains a compatibility
entry point. Shared firmware is under [patches/](../patches/README.md), and
offline analysis/replay modules are under [tools/analysis/](../tools/analysis/README.md).
Fixes belong in the rolling source; historical candidate files are retained
for their matching captures.

## Definitions and logging

Use [D2WD610H_master_patch.xml](D2WD610H_master_patch.xml) as the ECU definition
for this v1 image. Stock, component and v2 definitions share the factory CALID,
so CALID alone does not identify the correct definition.

The shared definitions and capture profiles are in [logger/](../logger/README.md).
[D2WD610H_master_logger.xml](../logger/D2WD610H_master_logger.xml) is the complete
logger definition. The smaller `D2WD610H_master_logger_ecuparams.xml` is its
generator input. The [logger reference](../docs/reference/LOGGER.md) explains
the five diagnostic profiles, parameter identities and request limits.

To regenerate the complete logger from the pinned upstream v370 source:

```sh
python3 -B master_patch/install_master_logger.py \
  /path/to/logger_METRIC_EN_v370.xml \
  logger/D2WD610H_master_logger.xml
```

## Build contracts and hardware

| Guide | Purpose |
|---|---|
| [Calibration](CALIBRATION.md) | Exact v1 defaults, sensor transfers, injector data and tune assumptions. |
| [Memory layout](MEMORY_LAYOUT.md) | Injected code/data ownership and collision checks. |
| [Wiring](WIRING.md) | Harness connections and installed-hardware assumptions. |
| [Commissioning](COMMISSIONING.md) | Physical checks and validation boundaries. |
| [Image comparison](../docs/reference/IMAGES.md) | Main/v2 differences, exact hashes and the v2 bypass repair. |
| [Historical investigations](../docs/archive/README.md) | Original traces, earlier fixes and capture-specific conclusions. |

The calibration assumes the Omni MAP-SUP-3BR transfer, Haltech HT-010206 IAT
with a provisional 1.00-kohm pull-up, Subaru 16611AA510 injectors and the
configured P0/P1 wideband analog transfer. See the guides for the physical
evidence still required. Main retains stock DBW/dashpot calibration and excludes
the user's independent dashpot experiment. Rotational idle defaults off.
