# `patch/` — reusable D2WD610H components

This directory contains the audited component builders used by the focused
[`master_patch`](../master_patch/README.md). The master is the only generated flash target kept in
the repository. Standalone component ROMs can still be generated locally for binary testing, but
they are ignored and must never be stacked or treated as current tuning images.

Every builder reads the immutable root [`2005 BLE MT.bin`](../2005%20BLE%20MT.bin), verifies its
SHA-256 (`ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`), patches an
in-memory copy, and refuses to overwrite a protected stock source. `extract_srf.py` also proves
that the original [`base_roms/2005 BLE MT.srf`](../base_roms/2005%20BLE%20MT.srf) contains the
same 512-KiB ROM payload.

## Current composition

`master_patch/build_master_patch.py` composes these components from fresh stock:

| Component | Source | Master behavior |
|---|---|---|
| EVAP-output boost control and hard overboost cut | `patch_boost.py` | EBCS defaults OFF; hard cut defaults ON. Spring-only boost remains the baseline. |
| Rotational idle | `patch_rotational_idle.py` | Installed, bounded retard-only, defaults OFF. |
| MAFless speed density | `../speed_density/patch_speed_density.py` | Always on; committed-AVLS-state dual VE. |
| Former-MAF wideband and four-stock-O2 removal | `../master_patch/wideband_component.py` | Installed as part of the master architecture. |
| Pressure-forced open loop and lean cut | `../fueling_safety/patch_fueling_safety.py` | Independent guards default ON. |

The historical `patch_single_front_af.py` and `patch_combined.py` sources remain for audit and
regression purposes. They implement the superseded one-factory-front-sensor architecture and are
not part of the current master.

Build and verify the current target from the repository root:

```sh
python3 master_patch/build_master_patch.py
python3 master_patch/build_definition.py
python3 master_patch/verify_master_patch.py
python3 patch/verify_romraider_toggles.py
```

To exercise the rotational component in isolation, use a temporary or ignored local output:

```sh
python3 patch/patch_rotational_idle.py /tmp/D2WD610H_rotational_idle_test.bin
python3 patch/verify_rotational_idle.py /tmp/D2WD610H_rotational_idle_test.bin
```

## Rotational-idle component

The master redirects periodic task pointer `0x11E30` from
`ign_final_timing_per_cylinder_update` at `0x279CC` to a wrapper at `0x7DB90`. The wrapper always
runs the stock final-angle task first. Only exact enable `01`, ECT 80–105 °C, RPM 600–1050,
throttle at or below about 2%, vehicle speed at or below 1 km/h, and MAP 150–550 mmHg absolute
permit the default offsets `{-6, 0, -6, 0, -6, 0}` degrees.

The wrapper cannot add advance. Retard is capped at 8 degrees, final timing has a 5-degree-BTDC
floor, and the original stock angle remains the final ceiling. Invalid gate data exits to stock.
The component occupies `0x7DB40..0x7DCEB`; the master verifier proves it does not collide with the
boost, speed-density, wideband, fueling-safety, calibration, hook, or RAM allocations. Full policy
and commissioning notes are in [rotational_idle_patch.md](../docs/rotational_idle_patch.md).

## Definitions and generated artifacts

Use [`master_patch/D2WD610H_master_patch.xml`](../master_patch/D2WD610H_master_patch.xml) with the
master ROM. It exposes the independent EBCS, hard-overboost, pressure-open-loop, lean-cut, and
rotational-idle controls plus their calibrations. `verify_romraider_toggles.py` checks the
one-byte EBCS, hard-cut, and rotational switches against the committed master image.

`defs/D2WD610H_AVLS_boost_patch.xml` and
`speed_density/D2WD610H_AVLS_speed_density_patch.xml` are retained only as definition-generator
inputs. Old standalone/combined XML files and generated component BINs were removed so there is
one unambiguous flash/tuning target.

## Key source files

| File | Purpose |
|---|---|
| `patch_boost.py` | EVAP-output proportional/feed-forward controller and independent hard MAP cut. |
| `patch_rotational_idle.py` | Guarded retard-only component with reusable `apply_to_rom()` API. |
| `verify_rotational_idle.py` | Opcode, policy, ownership, and component-layout audit. |
| `patch_single_front_af.py` | Superseded one-front-A/F/rear-delete research component retained for provenance. |
| `patch_combined.py` | Superseded two-component composition retained for regression. |
| `sh2_asm.py` / `sh2_disasm.py` | Minimal SH-2E assembly/disassembly used by patch verification. |
| `verify_regions.py` | Free-flash and scratch-RAM assumption audit. |
| `verify_boost_donor.py` | Pinned donor-table and boost-default audit. |
| `verify_romraider_toggles.py` | Current master switch/definition audit. |

No static or binary verification makes the master vehicle-proven. Keep EBCS and rotational idle
OFF for first commissioning, run directly from the 5 psi wastegate spring, verify MAP/wideband
signals against independent references, and prove all fuel/boost protections before enabling any
optional behavior.
