# patch/ — D2WD610H boost-control patch

Scripts + build artifacts for repurposing the EVAP purge PWM output as an open-loop
boost/wastegate solenoid driver. Background: [../docs/boost_repurpose_notes.md](../docs/boost_repurpose_notes.md),
[../docs/patch_build_guide.md](../docs/patch_build_guide.md).

## Files
| File | What |
|---|---|
| `patch_boost.py` | Phase 1 patcher — stock `.bin` → patched `.bin`. |
| `sh2_disasm.py` | Minimal SH-2E disassembler used to build/verify the patch. |
| `D2WD610H_boost_p1.bin` | Build output (generated; not the stock image). |

## Usage
```
python3 patch_boost.py [stock.bin] [out.bin]
# defaults: ../2005 BLE MT.bin  ->  D2WD610H_boost_p1.bin
```
Then open the output in **EcuFlash/RomRaider and save** (recomputes the `subarudbw`
checksum) before flashing. Load [../defs/D2WD610H_boost_patch.xml](../defs/D2WD610H_boost_patch.xml)
to tune the **Boost Wastegate Duty (RPM)** table.

## What Phase 1 does (verified at binary level)
1. Writes into free space @0x7D790: a 1-axis table descriptor, RPM axis (float[8]),
   duty data (u8[8]), and an SH-2E stub.
2. Repoints one 4-byte literal @**0x3FD8C** (in `evap_purge_duty_compute`) from the stock
   output stage `0x0000E8C4` to the stub `0x0007D7CC`.
3. The stub reads RPM (0xFFFFB544), looks up boost duty via the ROM interpolator (0x209C),
   and tail-calls the real output stage — so the (former purge) solenoid is driven by the map.

The patcher refuses to run if the free-space target isn't 0xFF or the hijack literal isn't the
stock value (guards against double-patching / wrong image).

## Layout constants (keep in sync with the def)
| Item | Addr |
|---|---|
| descriptor | 0x7D790 |
| RPM axis (float[8]) | 0x7D7A4 |
| duty data (u8[8]) | 0x7D7C4 |
| stub | 0x7D7CC |
| hijack literal | 0x3FD8C |

## Status / not yet done
- **Binary-verified only** — stub disassembles correctly, hijack + tables confirmed. NOT yet
  run on hardware. Bench/scope the solenoid output before driving boost.
- No overboost fuel cut yet (Phase 1 is duty-only). **Add a fail-safe before any boost.**
- PWM frequency unverified (purge period @0xFFFFAB84) — measure; retune if the boost solenoid
  needs a different frequency.
- Closed loop (target boost + Turbo Dynamics using MAP @0xFFFFABC4) = Phase 2, needs the EJ255
  sensor + 0x72810 rescale.
