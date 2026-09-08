# D2WD610H master turbo patch

> **September 8 static repair built:** the current image restores stock
> radiator-fan control and deletes actual canister-purge duty and fuel
> subtraction. Electronic boost control is removed; hard-overboost fuel cut
> remains. **Do not run earlier pre-fix images, including the first-VE ROM:**
> EBCS OFF did not restore their hijacked fan command. The corrected image is
> not vehicle-validated, and these fixes are not a demonstrated lean-out cure. See
> [the repair audit](GHIDRA_AUDIT.md#2026-09-08--fan-restoration-purge-delete-and-idle-timing-clarification).

This directory contains the single current integration target for the 2005 ADM
Liberty 3.0R manual ECU (`D2WD610H`). It combines the previously separate
firmware work into one deterministic stock-to-output build:

- always-on MAFless speed density with committed-state low/high-lift AVLS VE
  tables and a provisional Haltech HT-010206 post-intercooler IAT calibration
  based on an assumed 1.00 kOhm ECU pull-up;
- Omni Power `MAP-SUP-3BR` 3-bar MAP scaling;
- mechanical wastegate-spring boost control with independent hard-overboost
  fuel cut, and the stock radiator-fan command route restored;
- permanent actual CPC purge-duty, modeled-airflow and bank fuel-subtraction
  delete for the removed/capped purge plumbing;
- the former MAF ADC repurposed for the supplied seller-labelled `AEM 50-4110`
  / 30-4110-style P0/P1 0-5 V lambda signal;
- main stock front A/F and rear O2 processing bypassed, 18 mapped O2 DTC
  switches disabled, and identified legacy-voltage fuel contributions neutralized;
- the bounded per-cylinder rotational-idle timing post-processor, installed but
  default OFF;
- a live-barometric pressure failsafe that requests open loop before boost and
  a delayed, confirmed, pressure-release-latched 13.0-AFR fuel cut;
- a factory-ROM-derived 2003 JDM STI `A4TE002B` injector scalar/deadtime
  profile matching the installed Subaru `16611AA510` injector application;
- a conservative 5 psi / 98 RON fuel, ignition, AVLS, and 6800 RPM starting
  calibration with every active engine-load axis extended to 4.0 g/rev, plus
  a bounded low-lift idle/vacuum VE correction from two stationary runs;
  and
- focused, self-contained D2WD610H RomRaider ECU and logger definitions.

The generated baseline is `D2WD610H_master_patch.bin`, SHA-256
`48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0`.
It is 512 KiB, contains CALID `D2WD610H`, and has a valid Subaru additive
checksum (`0x1923EC61`). It is a development artifact, not a vehicle-tested tune.
Its second idle-VE increase is an unvalidated trial derived from a still-rising
AFR endpoint. The old recommendation to continue running the first-VE ROM is
withdrawn: that image also used the erroneous fan hook. Any future first-VE
comparison must use the corrected firmware, not the old BIN. See the
reassessment in [GHIDRA_AUDIT.md](GHIDRA_AUDIT.md).

The September 8 12:36 capture now confirms complete logging on this 10:30
image. Steady idle is substantially improved, but the throttle blips produce
near-stall RPM followed by a sustained lean recovery. The subsequent
[idle-recovery audit](IDLE_RECOVERY_AUDIT.md) traces the extra pulse reduction
to retained signed load-change compensation, amplified by the low-RPM VE
taper. A separate [calibration candidate](candidates/README.md), SHA-256
`6af0d130b585abf9c9b275840ddb0b237485d84f8f8adf7b15df8462adc72433`,
changes ten idle VE cells and checksum while retaining all code. The
[14:13 candidate capture](../logs/20260908_recovery_review.md) now shows
improved settled fueling near 970--1000 RPM / 14.1 AFR, but blips still cause
near-stalls down to 558 RPM. Timing reaches 0 degrees during opening and
is back at 15 degrees at the deepest trough; conditional base-D lookups closely
match the opening drop. Recovery remains unresolved; neither BIN has been
changed or promoted to a finished tune. The main BIN above remains the logged
10:30 baseline. See also the [first log review](../logs/20260908_idle_review.md).

The [load/idle-air follow-up](IDLE_AIR_RECOVERY_AUDIT.md) reproduces retained
load filtering and transient compensation with native instruction replay.
Faster filtering has mixed fuel effects; no further ROM change was made.
The new 19-channel `D2WD610H_idle_air_diagnostic_profile.xml` adds effective
idle RPM target, combined throttle request, pedal position and idle flags
within 43 addresses. **The repeat rev test is withdrawn:** the unchanged
candidate is still expected to nearly stall. The next work is offline
idle-air tracing; leave the car off for now.

The September 8 hook hardening uses saved caller RPM and single-read MAP/IAT,
and removes only this load task's obsolete MAF-fault fallback. Cranking and
signal-timeout protections remain. `Speed Density Load Filter Response` is now
explicit under `01.5 - Air Model - Load Calculation`, still at stock 6% per
update. The subsequent fan/purge repair changes no VE, injector, timing or AVLS
calibration either; no new cam-hold policy was selected. The rebuilt master
still contains the existing second-VE trial and is not a like-for-like
calibration comparison with the previously logged first-VE ROM.
The subsequent [retained-routine audit](RETAINED_ROUTINE_AUDIT.md) neutralizes
factory lambda atmospheric compensation, auxiliary fuel adders and two
feedback-target contributions driven by removed stock O2 voltage channels.
It changes 20 bytes from `fbc1a8...`, including two instruction words and the
checksum. The second pass changes ten bytes from `89ce82...`. No VE, injector,
timing or after-start data changes. Removing positive fuel corrections can
reduce fuel wherever they previously activated; this is an architecture repair,
not a proved lean-out cure. Main lambda feedback and its ordinary learned trims
remain; the target ignores the separate voltage trim, including stored history.
Other raw-voltage consumers and closed-loop transport dynamics remain audit
limits; this does not establish total independence from the removed circuits.
The complete generated logger definition has SHA-256
`3ff3a49fb332551c411a635ddcac49d04fea5f3ee1c308d917fa0145b8d5925e`.
E511 now correctly identifies the signed transient load correction at B874.
E503/E504 units use semicolons to prevent RomRaider splitting CSV headers.

The [guard execution audit](GUARD_EXECUTION_AUDIT.md) subsequently found and
fixed a lean-confirmation gap: a zero logger fault sentinel with stale valid
readiness was treated as rich. Lambda must now be positive before it can
clear confirmation. This changes 17 bytes from `5a1b3e...`, including checksum,
with unchanged allocations and calibration. Twelve new execution test groups
cover the wideband hooks, nested cut wrappers, retained rev limiter/aggregator,
stock resets, boundaries and fault handling, and run in the master verifier.
Scheduler timing, physical controller behavior and the VE baseline remain
validation limits.

The [primary-fueling execution audit](PRIMARY_FUEL_EXECUTION_AUDIT.md) adds
eight groups that execute the stock target, transition and final bank/cylinder
fuel calculations, plus five FPU groups that correct a host-rounding mismatch
in the shared test interpreter. Pressure
forced open loop preserves the stock enrichment calculation and its delay;
it does not guarantee a rich target when modeled load is low.

Further downstream execution found a separate [injector-cut publication
defect](INJECTOR_CUT_EXECUTION_AUDIT.md): the added cuts set the status flag
after the stock limiter had already built the scheduler's inhibit word. Both
now publish the stock all-channel inhibit value too. The `aea793...` stage
changes 169 bytes from `5fff8b...`, with unchanged calibration and no new RAM.
Six new execution groups cover native word construction, downstream channel
gates, release and negative controls; all pass. The old “cam-solenoid bank”
identification of this six-channel scheduler is corrected to injector scheduling.
The current [scheduler follow-up](INJECTOR_SCHEDULER_EXECUTION_AUDIT.md) fixes
a further temporary release during each continuing cut update. Both wrappers
use the native scheduler lock, preserving the incoming mask and protecting the
complete nested decision. Twelve new execution groups cover queue cancellation,
phase boundaries, release, startup/resync and damaged-lock reproductions.
Current `48d63c...` changes 543 bytes from `aea793...`, confined to two wrappers
and checksum. No calibration or static RAM changes; hardware timing remains unvalidated.
The subsequent IRQ/context follow-up adds eight execution groups covering native
interrupt entry/exit, pending-task dispatch, nested IRQs and register restoration.
Removing either wrapper lock or the native saved-mask gate reproduces the cut
release through actual dispatch. The full verifier passes without further ROM
changes. Real timing, injector delivery and the calibration still need controlled
commissioning; see the same audit for the scripted hardware/task boundaries.

`Overboost Fuel Cut Enable` remains in RomRaider, defaults ON, and retains the
6.5 psi hard MAP cut relative to 760 mmHg. Electronic boost enable, target,
duty, gain and soft-duty-cut controls are no longer exposed. Their former
controller and guard allocations contain only a return followed by erased
bytes; changing the old enable byte cannot reactivate them. `0x3FD8C` again
points directly to the stock fan writer at `0xE8C4`.

The separate purge delete clears actual CPC duty and modeled airflow at
`0x1BAF0`, sends zero to the unchanged CPC request writer at `0xB182`, and
zeros both bank fuel-subtraction terms through `0x23054`. Only verified purge
circuit switches P0458/P0459 are disabled. MAFless airflow, the stock-O2
replacement, and purge delete are permanent in this architecture.

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

The IAT transfer uses the published Haltech HT-010206 voltage/temperature
points, which Haltech documents for a 1 kOhm pull-up to 5 V. The builder
now assumes the D2WD610H input also has a 1 kOhm pull-up, so the eight published
knots retain their Haltech voltages. That ECU resistance is based on the
reported value and has not been confirmed from a D2WD610H primary source or an
installed-circuit measurement. The cold tail below -10 C is extrapolated. It is
therefore a useful starting reference, not a verified sensor calibration; see
[CALIBRATION.md](CALIBRATION.md) and [COMMISSIONING.md](COMMISSIONING.md).

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

The matching logger artifact is `D2WD610H_master_logger.xml`. It is a complete
metric SSM K-line ECU logger definition, not an XML fragment. It deliberately
reduces the upstream global catalogue to 63 H6-MT standard parameters, 46
relevant switches, and 35 useful stock extended parameters. Nine stock
high-resolution channels required for the lean-out capture are converted to
unconditional direct SSM-address entries; the other 26 remain restricted to ECU
ID `3C5A387116`. Project parameters E500--E516 are also unconditional. The
complete diagnostic set therefore remains visible in Data, Graph, and Dashboard
before RomRaider completes ECU identification. TCU/DCCD, diesel/common-rail/DPF,
removed stock-O2/MAF, and unrelated-model dashboard entries are omitted. The
smaller `*_ecuparams.xml` file is builder input only and must not be selected
as a complete logger definition.

The master definition uses numbered workflow categories so related stock and
patched calibrations stay together in RomRaider: air model, fueling, wideband,
ignition, cam control, boost, protection, throttle, idle, sensors/cooling, then
the checksum entry. The numbering controls RomRaider's otherwise alphabetical
flat category list; it does not affect ROM addresses or calibration data.

The executable hook regression check is
`python3 speed_density/test_hook_execution.py master_patch/D2WD610H_master_patch.bin`
from the repository root. It executes wrapper opcodes against descriptor-based
lookup models; it is not a whole-ECU emulator or CPU-timing measurement.
`02.8 - Fueling - Fuel Pump Control` exposes the Ghidra-verified stock 33.3 and
66.7-percent FPCU command literals. Their generated values remain stock; they
are present so a copied BIN can run the documented stationary full-speed mode
diagnostic while P47 is logged. The shared 100-percent high-mode/PWM
normalization constant is deliberately fixed and omitted from the editor.

## Build and verify

Run from the repository root:

```sh
python3 master_patch/build_master_patch.py
python3 master_patch/build_definition.py
python3 master_patch/verify_master_patch.py
```

The checked-in complete logger was generated from the metric-English file in
the [RomRaider logger v370 package](https://www.romraider.com/forum/viewtopic.php?start=1&t=1642),
`logger_METRIC_EN_v370.xml` (source SHA-256
`e5fa42e381eae904437f87319bd891cc497340d1c4758dde6f652f8eeeccc68f`):

```sh
python3 master_patch/install_master_logger.py \
  /path/to/logger_METRIC_EN_v370.xml \
  master_patch/D2WD610H_master_logger.xml
```

The builder reads only the immutable root `2005 BLE MT.bin`, verifies its
SHA-256, checks the byte-identical `base_roms` copy and de-encapsulated original
SRF payload, applies each component to an in-memory copy, then writes the
separate output. Generated ROMs are never accepted as build inputs.

`verify_master_patch.py` independently reconstructs the image, audits changed
regions, disassembles new firmware, tests sensor boundary policy, checks every
hook and diagnostic switch, runs the independent master-calibration policy
checks, validates both complete RomRaider definitions and the logger fragment,
and verifies provenance and checksum.

## Files

| File | Purpose |
|---|---|
| `build_master_patch.py` | Deterministic stock-to-master builder. |
| `master_calibration.py` | IAT, fuel, timing, KCA, AVCS, pinned A4TE002B JDM-STI injector, spring-only boost, rev-limit, and Subaru-checksum implementation. |
| `verify_master_calibration.py` | Independent IAT, fuel, timing, KCA, AVCS, injector, boost, limiter, and checksum policy checks used by the master verifier. |
| `../speed_density/patch_speed_density.py` | Single MAFless SD component containing committed-state dual VE and predictable 3200/3000 RPM AVLS calibration. |
| `wideband_component.py` | Permanent four-stock-O2 delete and former-MAF external-wideband input firmware. |
| `purge_delete_component.py` | Guarded in-place CPC duty, modeled-flow and bank fuel-subtraction delete; no new RAM or free-flash allocation. |
| `test_purge_delete.py` | Executable leaf/ABI tests for zero CPC request and both bank subtraction terms, plus ownership and refusal checks. |
| `RETAINED_ROUTINE_AUDIT.md` | Stock sensor-assumption mismatches, fuel-adder/target repairs, cold-idle evidence and remaining audit limits. |
| `test_stock_sensor_corrections.py` | Retained auxiliary-adder, bank-offset and lambda-target opcode execution, atmospheric lambda model, negative controls and guarded ownership. |
| `GUARD_EXECUTION_AUDIT.md` | Lean fault-sentinel repair, generated-code execution evidence and further stock-state tracing. |
| `test_wideband_fuel_guard_execution.py` | Executes wideband hooks, guard chain, retained limiter/aggregator and reset paths, with boundary and negative-control cases. |
| `PRIMARY_FUEL_EXECUTION_AUDIT.md` | Corrected SH-2E arithmetic model, actual primary target/transition/composer execution and precise pressure-override limits. |
| `INJECTOR_CUT_EXECUTION_AUDIT.md` | Added cut flags versus native injector inhibit word, repaired publication and downstream execution evidence. |
| `test_injector_cut_execution.py` | Actual inhibit builder/getters and channel gate; native fault preservation, release, missing-store negative controls and contract refusals. |
| `test_primary_fueling_execution.py` | Stock target and final bank/cylinder fuel calculations with actual scalar helpers, modeled table lookups, and negative controls. |
| `../speed_density/sh2e_test_fpu.py` / `../speed_density/test_sh2e_fpu.py` | Shared interpreter value semantics, manual vectors and exact arithmetic bounds; no hardware exception delivery. |
| `../fueling_safety/fueling_safety_component.py` | Pressure-forced-open-loop and latched lean-cut component. |
| `../patch/patch_rotational_idle.py` | Reusable bounded rotational-idle component, integrated default OFF. |
| `verify_master_patch.py` | Independent binary, opcode, calibration, XML, logger, and provenance audit. |
| `MEMORY_LAYOUT.md` | Exact injected-flash boundaries and collision policy. |
| `build_definition.py` | Generates the focused D2WD610H RomRaider definition. |
| `D2WD610H_master_patch.xml` | Matching self-contained metric RomRaider definition. |
| `D2WD610H_master_logger.xml` | Complete metric, SSM-only logger definition for ECU ID `3C5A387116`; ready artifact generated from logger v370. |
| `D2WD610H_master_logger_ecuparams.xml` | Internal seventeen-parameter fragment used to generate the complete logger definition. |
| `D2WD610H_idle_diagnostic_profile.xml` | First-idle capture: wideband/raw/ready, MAP/load, immediate/learned trims, pulse/latency, pump/battery and operating conditions. 43 addresses, 136-byte request. |
| `D2WD610H_afterstart_diagnostic_profile.xml` | Separate follow-up: six retained fuel terms (including transient E511), composed base factor/runtime, AFR, pulse and operating conditions. 43 addresses, 136-byte request. |
| `D2WD610H_idle_recovery_profile.xml` | Previous recovery capture: 19 channels including signed transient E511, base factor E123 and committed AVLS E503. 43 addresses, 136-byte request. Load separately. |
| `D2WD610H_idle_air_diagnostic_profile.xml` | Prepared profile; live test deferred. Idle RPM target, combined throttle request, pedal/idle flags and fuel response. 19 channels; 43 addresses. |
| `IDLE_AIR_RECOVERY_AUDIT.md` / `test_load_conditioning_execution.py` / `replay_20260908_load_recovery.py` | Native load/transient replay and idle-air investigation; repeat rev test withdrawn. |
| `test_idle_air_execution.py` | Native pedal-release and idle-air eligibility, pressure-demand mode, and P30 identity; seven bounded groups, no engine-response proof. |
| `test_pedal_patch_dependencies.py` | Five groups isolate added decisions from pedal state, verify the separate speed channel and check in-memory mistaken-address negative controls. |
| `IDLE_RECOVERY_AUDIT.md` / `idle_recovery_candidate.py` | Native load-change trace and isolated ten-cell VE candidate; settled fueling improved in first candidate capture, blip recovery unresolved. |
| `analyze_20260908_recovery.py` / `test_idle_timing_execution.py` | Candidate log analysis, flash CRC check and native idle/base timing selection fixtures. |
| `LOGGER_CONNECTION_AUDIT.md` | Native 43-address receive limit, RomRaider subscription-queue repair, and the successful complete 12:36 idle capture. |
| `install_master_logger.py` | Generates a complete D2WD610H-only logger from a normal complete logger XML, retaining its DTD and applicable stock channels. |
| `ghidra_scripts/ApplyMasterNames.java` | Reproducibly reapplies the names/comments confirmed in live Ghidra. |

## Hard limitations

- The base VE table is mathematical, not measured on this engine.
- The HT-010206 IAT curve assumes a 1.00 kOhm ECU pull-up. A wrong pull-up,
  sensor-ground offset, or cold-tail extrapolation directly biases
  speed-density airflow and all load-indexed tuning.
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
- The nominal 5 psi spring cannot limit boost caused by wastegate spring error or boost
  creep. Use an independent mechanical pressure test and a load-controlled dyno.
