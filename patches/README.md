# Shared patch components

The shared firmware implementations live here. The integrated builders and
their ROM/definition artifacts remain in `master_patch/` and `master_patch_v2/`.

| Directory | Contents |
|---|---|
| [core](core/README.md) | SH-2 assembler/disassembler, SRF reader, boost protection, rotational idle and historical standalone builders. |
| [speed_density](speed_density/README.md) | MAFless airflow wrapper, dual VE tables and the component definition source. |
| [wideband_o2](wideband_o2/wideband_component.py) | External wideband conversion and the stock oxygen-sensor integration repairs. |
| [fueling_safety](fueling_safety/README.md) | Pressure-based open-loop permission and delayed, latched lean fuel cut. |
| [purge_delete](purge_delete/purge_delete_component.py) | Actual CPC purge output, modeled airflow and bank fuel-subtraction removal. |

Offline verification and execution fixtures are in [tests](../tests/README.md).
The developing [central reference](../docs/reference/README.md) records the
architecture, verified addresses, historical corrections and remaining questions.

This directory move changes file organization only. It does not change the
machine code or calibration of either saved master ROM.
