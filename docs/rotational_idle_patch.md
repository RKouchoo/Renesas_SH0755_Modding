# Rotational-Idle Component and Master Integration

Target: D2WD610H / ECU ID `3C5A387116`, Renesas SH7055. The guarded component is now
integrated into `master_patch` and defaults OFF. It remains absent from the historical
combined patch and `base_turbo_map` calibration source.

## What it does

The stock task `ign_final_timing_per_cylinder_update` at `0x279CC` calculates six final ignition
angles at RAM `0xFFFFC0EC..0xFFFFC100`. Periodic-dispatcher pointer `0x11E30` normally calls that
task directly. The component redirects only that pointer to a wrapper at `0x7DB90`.

Every invocation follows this order:

1. Run the complete stock final-timing task.
2. Require the flash enable byte at `0x7DB40` to equal exactly `01`.
3. Require all warm-idle gates to be inside their inclusive calibrated windows.
4. Apply one bounded offset to each of the six stock final angles.
5. Return the results through the original six RAM locations for the unchanged scheduling path.

It does not cut fuel, add fuel, command throttle or idle air, force AVLS, disable misfire
diagnostics, alter the rev limiter, or allocate persistent RAM. The result is a conservative
alternating-torque idle experiment, not an anti-lag strategy. Whether it produces the desired
"lumpy" sound depends on the engine's stock idle controller, airflow, exhaust, and actual timing;
the binary analysis cannot establish that effect.

## Retard-only policy

For each cylinder, the wrapper implements:

```text
requested = min(calibrated_offset, 0)          # positive values cannot add advance
requested = max(requested, -maximum_retard)
candidate = max(stock_final + requested, minimum_final_timing)
result    = min(candidate, stock_final)         # final no-advance ceiling
```

The last ceiling is important when stock timing is already below the configured floor. In that
case the wrapper retains the lower stock value instead of advancing it to the floor. With the
supplied calibration, requested offsets are `{-6, 0, -6, 0, -6, 0}` degrees, maximum retard is
8 degrees, and the floor is 5 degrees BTDC. Cylinder 1 is included in the retarded group so the
standard Ignition Timing logger, which follows the first final-angle output, can show activity.

## Default operating window

| Calibration | Flash address | Default | Live input |
|---|---:|---:|---|
| Enable | `0x7DB40` | `00` (OFF) | exact `01` only |
| Minimum / maximum ECT | `0x7DB44` / `0x7DB48` | 80 / 105 C | `0xFFFFB3AC` |
| Minimum / maximum RPM | `0x7DB4C` / `0x7DB50` | 600 / 1050 RPM | `0xFFFFB544` |
| Maximum throttle | `0x7DB54` | 1.68 native, about 2.0% | `0xFFFFB314` |
| Maximum vehicle speed | `0x7DB58` | 1.0 km/h | `0xFFFFB538` |
| Minimum / maximum MAP | `0x7DB5C` / `0x7DB60` | 150 / 550 mmHg absolute | `0xFFFFABC4` |
| Maximum retard | `0x7DB64` | 8 degrees | calibration |
| Minimum final timing | `0x7DB68` | 5 degrees BTDC | calibration |
| Six cylinder offsets | `0x7DB6C` | `-6, 0, -6, 0, -6, 0` | calibration |

The MAP window is approximately 20.0–73.3 kPa absolute. Equality passes every boundary; leaving
any boundary returns all six values to the newly calculated stock results on that task cycle.
Every live input and gate threshold is checked for NaN first; invalid data also returns to stock.
A NaN offset or non-positive/NaN Maximum Retard becomes zero offset, while a NaN timing floor
retains the original stock angle. The patch does not add hysteresis or retain state.

## Files and build

| File | Purpose |
|---|---|
| `patch/patch_rotational_idle.py` | Reusable guarded component API; can still build a local standalone test image |
| `patch/verify_rotational_idle.py` | Standalone opcode, policy, and ownership audit |
| `master_patch/D2WD610H_master_patch.bin` | Only committed flashable generated image; includes this component OFF |
| `master_patch/D2WD610H_master_patch.xml` | Current definition containing all rotational-idle controls |

From the repository root:

```sh
python3 master_patch/build_master_patch.py
python3 master_patch/build_definition.py
python3 master_patch/verify_master_patch.py
```

The master builder always reads the canonical root `2005 BLE MT.bin`, verifies its pinned
SHA-256 and SRF/base copies, and writes a checksum-valid separate output. The standalone
builder remains only as a local component test and its generated BIN is no longer committed.

## Allocation and master boundary

| Item | Address / extent |
|---|---:|
| Enable and ten scalar gates/limits | `0x7DB40..0x7DB6B` |
| Six offsets | `0x7DB6C..0x7DB83` |
| Wrapper and literal pool | `0x7DB90..0x7DCEB` |
| Reserved component ceiling | `0x7DCFF` |
| Stock final-timing task-pointer hook | `0x11E30`: `0x279CC` -> `0x7DB90` |

The rotational component begins at `0x7DB40` and ends at `0x7DCEB`; speed density starts at
`0x7DD00`. The master verifier owns every component blob and hook, decodes this wrapper,
executes its policy model, and rejects any overlap with boost, SD, wideband, fueling safety,
calibration, or RAM state.

## Commissioning limits

This image is binary-verified, not ECU-, engine-, or vehicle-verified. Deliberately uneven
combustion torque can increase vibration, misfire counts, exhaust temperature, turbo heat,
catalyst stress, and engine-mount load. The conservative BTDC floor reduces those risks but does
not remove them.

Before enabling it:

1. Verify the generated master checksum, then first run the master image with the switch OFF.
2. Confirm stock idle quality and log ECT, RPM, throttle, vehicle speed, MAP, Ignition Timing,
   battery voltage, both fuel corrections, lambda, and all six misfire counters.
3. Test only fully warm, stationary, in neutral, with working cooling and an immediate shutdown
   path. Keep boost control out of this first test.
4. Enable the switch with the supplied mild offsets. Confirm the first timing logger changes only
   inside the documented window and returns immediately outside it.
5. Stop for unstable RPM, increasing misfire counts, lean lambda, abnormal oil pressure,
   excessive exhaust/turbo temperature, detonation, or unexpected throttle behavior.
6. Do not disable misfire protection to hide the result. Increase the effect only after measured
   timing and thermal behavior are understood.

Merge into the main patch only after this standalone sequence passes. At that point the combined
builder and combined RomRaider definition should import the existing component unchanged, and a
new exact-union verifier should cover all three installed switches/components.
