# D2WD610H EZ30R ECU project

Firmware patches and reverse engineering for the 2005 Subaru Liberty 3.0R
manual ECU: Denso D2WD610H, ECU ID `3C5A387116`, Renesas SH7055 / SH-2E,
big-endian, 512 KiB flash.

Start with the [central reference](docs/reference/README.md). It explains the
patch, the reviewed RAM and routines, the saved-image evidence and the
remaining issues. The [document register](docs/reference/DOCUMENT_REGISTER.md)
records where the older notes now live.

## Current builds

| Build | State |
|---|---|
| [V1 / rolling main](master_patch/README.md) | Contains the local MAF-fault load bypass and SD low-pressure boundary repair. Its saved ROM matches its builder. |
| [V2](docs/reference/IMAGES.md) | Includes timing and MAP-pressure tip-in corrections absent from v1, plus other separate calibration changes. It still lacks main's local load-fallback bypass. |

**A ROM combining those fixes has not been built.** The September audit and
the subsequent cleanup changed no firmware or calibration. The logged
near-stall remains unresolved; offline verification establishes the tested
software behavior. See [image identities and differences](docs/reference/IMAGES.md)
before choosing a build or interpreting a capture.

The integration supplies MAFless speed density with separate low/high-lift VE,
an external wideband through the former MAF input, removal of the four stock
O2 processing paths and CPC purge contributions, and pressure/lean fuel cuts.
Stock fan control is retained. Boost uses the mechanical wastegate spring;
the optional rotational-idle component is installed with its switch off.

## Repository layout

| Location | Contents |
|---|---|
| [master_patch/](master_patch/README.md) | V1 integration, calibration, saved ROM, ECU/logger definitions and profiles. |
| `master_patch_v2/` | Separate v2 builder, calibration, ROM and definition. |
| [patches/](patches/README.md) | Shared firmware components and low-level build utilities. |
| [tests/](tests/README.md) | Offline instruction fixtures and verifiers. |
| [tools/](tools/README.md) | Documentation audit tools and [historical analysis/replay tools](tools/analysis/README.md). |
| [docs/reference/](docs/reference/README.md) | Current documentation, reviewed address index and retained MCP evidence. |
| [docs/hardware/](docs/hardware/README.md) | Specialist donor and direct-attach interface research. |
| [docs/archive/](docs/archive/README.md) | Superseded investigations and former project overviews. |
| [logs/](logs/README.md) | Original captures and their analysis results. |
| `base_roms/`, `defs/` | Pinned factory/donor inputs and source definitions. |
| `pico_kline_adapter/` | Independent K-line adapter project. |

## Verification and development

Run from the repository root:

```sh
python3 -B tests/verify_master_patch.py
python3 -B master_patch_v2/verify_master_patch.py
python3 -B tools/audit_image_contracts.py
```

The main verifier rebuilds in memory and checks the saved image, calibration,
ownership, definitions, logger and instruction fixtures. V2's existing three
checks cover checksum/layout/definition and are narrower. The image audit
also exercises both builds' conditional MAF-fault load paths.

Make fixes in the relevant rolling sources and use Git for regression history.
Build commands and hardware assumptions are in the [master guide](master_patch/README.md).
Existing candidate ROMs are retained only to reproduce their historical logs.
The user's independent dashpot experiment has not been merged into main.

The stock Ghidra project remains at the repository root. Its annotations were
updated through MCP; [Ghidra status](docs/reference/GHIDRA.md) records the RAM
block and save/reopen limitations. Audit source text is pinned to its reviewed
Git revision so reorganizing notes cannot silently change what was audited.
