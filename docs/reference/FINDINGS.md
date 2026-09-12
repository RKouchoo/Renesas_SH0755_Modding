# Audit findings and unresolved evidence

[Reference home](README.md) · [Address index](ADDRESS_INDEX.md) · [Ghidra changes](GHIDRA.md)

## Corrections from this audit

| ID | Previous claim | Corrected result and evidence | Action |
|---|---|---|---|
| C01 | RAM starts at `FFFF0000`, ends at `BFFF` or `DFFF`. | SH7055SF RAM is `FFFF6000–FFFFDFFF`, 32 KiB. Renesas section 23; stock SP is `FFFFDFA0`. | Correct setup constants and notes; live block migration remains unavailable through MCP. |
| C02 | `ABC8` is a pressure/scaled float intermediate. | It is a **u16 filtered ADC word**. `7A28/7A36/7A3E` use word accesses; `ABC4` is the float pressure output. | Correct reference and producer/classifier comments. |
| C03 | Timer table A begins at `FA90`; B at `FAE8`. | A begins **`FA94`**, 6 × 12 bytes; B begins **`FADC`**, 6 × 24 bytes. Saved records and caller literals agree. | Correct table labels, comments and record layouts. |
| C04 | `F602` is channel-enable control; `F652+2n` the full six-channel compare series. | `F602=TCNT2B`; B's down-counter series starts at `F650`. Its start register is `F666=DSTR`. `96FC` uses table A. | Correct hardware register identities and distinguish the tables. |
| C05 | `FFFFF97C/FFFFFA80` are fan relay/mode registers. | ROM literals **`3F97C/3FA80` contain `FFFFCD7F/FFFFCD80`**, RAM fan-state bytes. | Retract the false I/O addresses and annotate `3F878`. |
| C06 | Older hardware notes still identify fan PWM as purge and injector records as cam-solenoid state. | Fan: `CD54 -> E8C4 -> BFR7A`; CPC: `B6D4 -> B182`; injector records: `BFB8+0x28*n`. | Current hardware reference corrected; old research retained with explicit retraction. |
| C07 | Writes above internal checksum end `7D790` do not need checksum repair. | Separate additive descriptor covers **`2000–7FAF7` inclusive**, including injected code. | Explain both mechanisms and retain builder checksum checks. |
| C08 | Main's MAF-fault load bypass can be assumed for v2. | Audit-baseline v2 retains `173FC -> 65168`; D26F/40 selects processed-MAP fallback load. Main points to `27088`. | Reproduced during the audit; the subsequent [v2 repair](V2_LOAD_FALLBACK_FIX.md) adds the local bypass and regression coverage. |
| C09 | V2's header describes a +6-degree 2000-RPM full-boost cap. | Its calibration constant is **+10 degrees**. Final cells depend on resampling and load-specific caps. | Recorded during the audit; the later bypass repair corrects the description/output, preserving all timing bytes. |
| C10 | Two float-axis `little` labels prove swapped ROM bytes. | The installed RomRaider legacy float reader/writer still uses big-endian bytes in this configuration. | Retract the earlier review finding; no axis/BIN correction. |
| C11 | A successful MCP data-rename response proves a label changed. | This server returns “Rename data attempted” even when no defined Data exists. | Read back changes; retain failed/no-op attempts in the ledger. |
| C12 | A gap in literal references is usable scratch RAM. | Indexed records, stack and other computed accesses can occupy it. | Correct `verify_regions.py` terminology and physical bounds. |
| C13 | Standalone boost/combined verifiers describe the current cut wrapper. | Their old instruction pins predate the 88-byte locked wrapper and all-channel inhibit publication. | Correct the existing verifiers; fresh temporary component builds now pass. No firmware changed. |
| C14 | `B536` provides SH-2E FP-register support. | It initializes two protected RAM records through `49530`, with zero float values. | Correct live MCP names/comments and old notes. |
| C15 | `1B800` calculates the main engine load. | It computes purge-related limits/ratios at B714/B6F8/B6F4/B6F0, without writing B428/B438. | Correct the stale live name and remaining notebook claim; preserve its narrower airflow dependency. |
| C16 | `52DA` dispatches on H-UDI stop. | It tests MSTCR mask02, **FPU stop**; H-UDI stop is mask04. | Correct MCP, naming script and AUD notes. No evidence this branch caused the near-stall. |
| C17 | `16CA4` publishes conditioned coolant B3AC, including in the first central draft. | It initializes protected records `8100/8108`. The main B3AC publisher is **16B04**, with separate initialization at `16C9C`. | Correct the central producer attribution and record the self-correction explicitly. |
| C18 | `13330` tests B6C0 bit7. | Its literal points to **B19C**, tested as a byte with mask80. | Correct MCP, naming script and notebook. |
| C19 | `1BE8E` initializes fuel-trim state. | It clears B702 and sets B721/B722 to FF; the latter feed the purge operating-state logic. | Rename to `purge_operating_state_initialize` in MCP and source annotations. |
| C20 | `17984/179EE/17A24/17B2A/17C40` include airflow/load filters and bank-charge calculations. | They dispatch, initialize, validate, filter and learn **paired-pedal** state, including protected offsets `8110/8118/8120`. | Correct five MCP names and annotate the pedal role. Old plate comments can remain; see the MCP limitation in Ghidra notes. |
| C21 | `A9A8` is specifically an injector-control lookup sequence. | AC00-indexed lookups and AE-state updates are proven; an injector-only physical role is not. | Narrow name and documentation to the demonstrated operations. |
| C22 | `1917A` directly reads readiness `AE70/AE74`; `192A8` clamps pump-current conversion. | `1917A` reads filtered lambda and upstream status; `192A8` performs guarded affine scaling with no explicit clamp. | Correct MCP names/comments and source annotations. |
| C23 | `3FDBC` calls the OSV actuation gate after the AVLS mode copy. | It tails `40682`, a conditional mode reset. **11958 separately calls 405CC**. | Correct task-order documentation and MCP comments. |
| C24 | `216EA/217B8/230E8` update airflow or engine load. | They classify airflow for trim regions, dispatch the legacy O₂ loop, and normalize purge compensation respectively. | Narrow MCP names, naming scripts and old notes to demonstrated operations. |
| C25 | `1F1DC` is a running short-term correction publisher; a “21-element” coefficient vector occupies 21 floats. | `1F1DC` is conditional initialization. Coefficients use 22 float slots, with indices 1–21 generated by `1FB16`; feedback histories have 21 slots. | Correct MCP and document the separate allocations. No firmware overflow was found here. |
| C26 | `3D916` tests whether any cylinder correction is active. | It tests six protected records through `4963A`, returning 1 if any is invalid. | Rename the integrity check and document checksum-copy repair. |
| C27 | Valid oil temperature always passes through `47000`; KCA always selects one of two tables. | A qualified oil-temperature latch can apply a 70 °C floor; intermediate AVLS states can hold the previous KCA limit. | Add the missing conditional behavior to MCP and the reviewed contracts. |
| C28 | `4B1CC` is a 154-entry SSM RAM table. | It is a 20-byte bank feedback descriptor, paired with `4B1E0`. Standard SSM handler pointers begin at `4B6FC`. | Rename the defined descriptor through MCP and annotate its caller. |
| C29 | `46864` is an increment helper; `4684E` is its RAM fault byte. | Those are ROM literals: `46864` contains helper address `251C`; the word at `4684E` resolves to RAM `FFFFCF7B`. | Correct the literal/target distinction in MCP and the index. |
| C30 | `7BDFC` is fan case-7 table data. | It is the axis of `609EC`, whose u16 data are at `7BE0C`. Caller `33830` publishes auxiliary duty `C858`; the physical output is unresolved. | Retract the fan-table claim and annotate the actual caller. |
| C31 | `E8B4` writes fan compare `F590`; the pump's 3750-count gate takes 37.5 seconds. | `E8B4` updates period `F588/AB84`. The nominal 8-ms run counter makes the pump gate 30 seconds, so a 34.813-second capture cannot exclude it by duration. | Correct writer scope and withdraw the invalid capture-timing argument. |
| C32 | The idle threshold at `737DC` can be treated as an opening calibration. | Native word reads compare the value 3 with debounce counter `B2FC`. It is a call-count limit. | Record the width and annotate the comparison through MCP. |
| C33 | Historical front/rear wrappers and old wrapper ends describe current main. | The old `7D920–7DB3B` code area is erased in main/v2. Current hard-cut/SD/lean wrappers are 88/536/512 bytes, with the contiguous free tail at `7EE00`. | Separate standalone/history from current image ownership. |
| C34 | The native rev limiter is stateless. | `BF6D/80` and `/40` hold state between their engage and resume thresholds before final selection. | Document hysteresis and annotate `24B36` through MCP. |
| C35 | `7D4B0/B4` are fixed/fallback pedal thresholds and should be raised to 110 percent. | `403C4` compares them against **CF94 oil temperature** in the stationary AVLS path. Raising stock 15 C to 110 C blocks the intended warm neutral transition. | [September 12 native execution and repair](V2_AVLS_NEUTRAL_20260912.md): restore 15 C in both rolling builds, correct labels and add regression coverage. The loaded misfire remains unresolved. |
| C36 | Changing injector duration scaling leaves all native fuel-pump demand inputs consistent. | `13CA8` converts effective pulse through separate `72D54=4.59` into B1C4; `2A910` consumes it for pump demand. The coefficient remained stock while the main duration scalar approximately halved. | [Repair](FUEL_PUMP_SCALING_20260912.md): pair the coefficient inversely with duration scaling, approximately 9.379054, in both rolling builds. Actual pump mode/pressure during the rich bog is unlogged; root cause remains unresolved. |

The [image-contract script](../../tools/audit_image_contracts.py) pins all three
images, checks the descriptor records and fan pointers, and reproduces C08.
The [MCP evidence](evidence/ghidra_evidence.json) records disassembly and xrefs.
The hardware identities use the
[Renesas manual](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual),
not inferred load names.

## Earlier findings rechecked and carried forward

| Area | Current conclusion | Limit |
|---|---|---|
| MAP floor / intercept | Native converter does not impose the claimed 33.77-kPa floor. SD uses ABC4, older E51 logs use B2A0. | Physical sensor curve and simultaneous direct-MAP behavior remain unvalidated. |
| Low-pressure rejection | Current main/v2 accept the converted lower electrical boundary at about 10.48 kPa. | No capture proves this branch caused the historical near-stall. |
| 500-g/s fallback | Running invalid-calculation path still publishes fixed 500 g/s; zero RPM publishes zero. | It is not an injector-inhibit command. Replacing it requires a separately validated fault/reset policy. |
| Transient correction | B874 is signed load-change compensation, active beyond startup. | “Wall wetting caused the stall” is a physical hypothesis, not established by the routine's name or replay. |
| Pedal | B46C is conditioned accelerator percent; SD uses no pedal input. | This does not establish every physical DBW state during a capture. |
| Ignition | C17C is AVCS tracking ratio; C0EC–C100 are final angles, CCC8–CCDC corrections. | Logged timing and conditional table agreement do not prove actual cam tracking. |
| Pressure-forced OL | Wrapper clears permission after native primary calculation. | Native enrichment ramps/delays remain. |
| Added cuts | Native inhibit publication and scheduler locking are required and tested. | Already-scheduled pulses and hardware timing retain separate boundaries. |
| FPU | Native interlocks are expected; emitted SD has no FDIV, but lookup helpers can divide. | No measured utilization, stack margin or deadline proof. |

## Evidence still missing, with the exact scope

1. **Vehicle root cause:** no complete observed chain yet ties MAP/air request,
   actuator response, fuel delivery and combustion to the delayed near-stall.
   The replay is useful for software dependencies, not a substitute engine.
2. **V2 fault activation:** the conditional fallback is reproduced, but actual
   D26F/40 state during the historical runs is not established. Main and v2
   require their own image-specific conclusions.
3. **Physical calibration:** installed MAP and wideband analog transfers, IAT
   pull-up, fuel pressure/injector behavior and actual oscillator rate remain
   physical assumptions. Estimated baro cannot validate its own source sensor.
4. **Output mapping:** table B's physical load and the final CPC pin/polarity
   are not established by descriptor layout or a RAM duty publication. Old
   AVCS/AVLS and relay assignments must not be reused to select pins.
5. **Whole-system execution:** unmodeled device operations, exception flags,
   asynchronous sensor epochs and measured interrupt/bus latency remain
   outside the fixtures. Native branch coverage is bounded by supplied cases.
6. **Bounded meanings:** every inventoried address now has an authored review
   outcome. Some establish only an access width, dependency, historical range
   or a qualified branch. Broad `engine_load_dependent_*` labels certify the
   stated dependency, not an unknown complete algorithm or physical role.
   The auxiliary output behind `33830` and table-B physical mapping remain
   explicitly unresolved despite their reviewed software relationships.
7. **Ghidra persistence and geometry:** live annotation readbacks succeeded,
   but memory-block repair, defining missing data and explicit save/reopen
   verification are not exposed by this MCP server.

These are audit results and follow-up boundaries. The completed offline
checks do not support a “100% flash-safe” or resolved-engine claim.
