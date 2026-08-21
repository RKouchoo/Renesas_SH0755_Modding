# D2WD610H committed-state dual-VE patch

This standalone component converts the existing MAFless speed-density image
from one full-range VE surface to two surfaces selected by the ECU's committed
AVLS lift state:

- **Low lift:** 13 MAP columns x 9 RPM rows, 0..3200 RPM.
- **High lift:** 13 MAP columns x 11 RPM rows, 3000..7500 RPM.

Committed AVLS mode byte `0xFFFFCD86 == 3` selects high lift; every other value
selects low lift. The 3000..3200 RPM overlap is intentional hysteresis coverage,
not duplicated unreachable range. Both seed surfaces are resampled from the
same conservative original VE map, so installing the patch does not deliberately
introduce a lambda step at the switch.

The AVLS calibration is made predictable at the same time. High lift engages at
3200 RPM and releases at 3000 RPM. All stock vehicle-speed request paths are set
above the verified 100 km/h conditioned-speed cap, so lift selection no longer
changes with vehicle speed or oil-temperature curve selection. The existing
stock request/commit delay, status gates, and output actuation remain intact.

This is binary selection, not a time blend. It compensates the large VE change
caused by switched valve lift while leaving continuous intake-AVCS effects to be
tuned within each surface.

## Build and verify

Run from the repository root:

```sh
python3 avls_ve/patch_avls_ve.py
python3 avls_ve/build_definition.py
python3 avls_ve/verify_avls_ve.py
```

The generated image is `D2WD610H_avls_dual_ve.bin`, SHA-256
`9cfcf45d075818c1a8320e540eb855979289ce25a6e03b8879a0c4767db49d16`,
with valid Subaru additive checksum `0x051694B7`. It is layered from the
immutable root stock image through the standalone speed-density component.

Load only `D2WD610H_AVLS_dual_ve_patch.xml` for this standalone image. The XML
removes the obsolete full-range VE table and variable vehicle-speed/oil-band
AVLS controls. The old single-VE bytes remain inert in ROM because erasing them
adds risk without changing execution; the patched wrapper cannot reference its
descriptor.

See [COMMISSIONING.md](COMMISSIONING.md) before engine use and
[GHIDRA_AUDIT.md](GHIDRA_AUDIT.md) for the stock-code evidence.

## Limitations

- The VE values are mathematical starting values, not measured engine data.
- The high-lift selector follows committed state, so logs should use the same
  state rather than RPM alone when assigning samples to a table.
- Continuous AVCS position still changes cylinder filling inside each lift
  state. This patch does not add a third VE dimension for cam angle.
- Static verification does not prove the AVLS hardware, airflow model, fueling,
  or transition behavior on a running engine.
