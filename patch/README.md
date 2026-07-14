# patch/ — D2WD610H boost-control patch

Scripts + build artifacts for repurposing the EVAP purge PWM output as an open-loop
boost/wastegate solenoid driver. Background: [../docs/boost_repurpose_notes.md](../docs/boost_repurpose_notes.md),
[../docs/patch_build_guide.md](../docs/patch_build_guide.md).

## Files
| File | What |
|---|---|
| `patch_boost.py` | **Phase 1** patcher (open-loop RPM→duty) — stock `.bin` → patched `.bin`. |
| `patch_boost_p2.py` | **Phase 2** patcher (closed-loop proportional + feed-forward) — stock `.bin` → patched `.bin`. |
| `sh2_asm.py` | Minimal two-pass SH-2E assembler (labels + literal pool). Self-tests against the verified Phase-1 stub. |
| `sh2_disasm.py` | Minimal SH-2E disassembler used to build/verify the patches. |
| `verify_regions.py` | Audits free-flash + scratch-RAM assumptions (direct refs + known computed regions). |
| `D2WD610H_boost_p1.bin` / `_p2.bin` | Build outputs (generated; not the stock image). |

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

## Phase 2 — closed-loop proportional + feed-forward (`patch_boost_p2.py`)
Apply to the **stock** bin (not on top of Phase 1). Adds, in free space:
- feed-forward base duty map (same table as Phase 1),
- target boost map (RPM → target, float),
- Kp / Max-Duty-Ratio / Overboost gains (tunable floats),
- a **stateless** controller stub, hijacking the same literal @0x3FD8C.

Controller each cycle: `ratio = clamp(base + Kp·err, 0, MaxRatio)`, `err = target − MAP(0xFFFFABC4)`;
if `MAP > Overboost` → `ratio 0`. **No persistent state / no RAM scratch** — reads only RPM, MAP,
and flash constants; writes nothing but the stack.

> **Why P-only, not PI?** `verify_regions.py` showed no RAM word can be *proven* free on this ROM:
> the top-of-RAM candidates fall inside the cam-solenoid struct array (computed base+index access,
> invisible to a plain xref check), and the large unreferenced RAM gaps are computed-access buffers /
> jump tables. Rather than risk corrupting another subsystem, the integral term is omitted. Adding I
> later needs a rigorously-verified scratch (or reclaiming purge RAM by NOP-ing the stock writes).

**Ships safe:** default `Kp=0` ⇒ pure feed-forward (= Phase 1). Overboost cut active.

**PREREQUISITE:** MAP (0xFFFFABC4) must read real boost — fit the **EJ255 (turbo) MAP sensor** and
rescale table **0x72810** first. Do NOT raise Kp on the stock ~1-bar sensor. Binary-verified
only; bench-validate and keep an independent overboost **fuel** cut. Tune in
[../defs/D2WD610H_boost_patch.xml](../defs/D2WD610H_boost_patch.xml) (category "Boost Control (patch)").

### Phase 2 layout (matches the def)
| Item | Addr | | Item | Addr |
|---|---|---|---|---|
| base_desc | 0x7D790 | | target_data | 0x7D7E0 |
| rpm_axis (shared) | 0x7D7A4 | | Kp / MaxRatio / Overboost | 0x7D800 / 0x7D804 / 0x7D808 |
| base_data | 0x7D7C4 | | controller stub | 0x7D80C |
| target_desc | 0x7D7CC | | scratch RAM | none (stateless) |
