# Repurposing the EVAP purge solenoid output as a boost-control solenoid

Goal: drive a boost-control (wastegate) solenoid from the ECU output that currently
runs the EVAP canister purge (CPC) solenoid — hijack its PWM duty with a boost map,
neutralize purge-specific enable gating, and mask the purge-circuit DTCs.

CALID D2WD610H (EZ30R, SH7055). All code addresses are file offsets (flash base = 0).

## STATUS: purge output NOT yet located. See correction below.

A first pass reverse-engineered a 6-channel PWM output bank in detail, but on analysis
that bank turned out to be the **crank-angle-synchronized cam/valve-timing solenoid driver
(AVCS/AVLS), not the purge valve.** The purge output is a separate free-running PWM that
still needs to be found. The cam-bank work is kept below because it is directly useful to
the AVLS goal (the long-open "physical OSV port write" item).

---

## What was actually mapped: the crank-angle-synced solenoid bank (AVCS/AVLS)

This is **not** purge — it actuates solenoids inside crank-angle windows across a 720° cycle,
which is cam oil-control (AVCS) / valve-lift oil-switching (AVLS) behaviour.

### Evidence it is crank-angle-scheduled
- Scheduler `FUN_000263EE` runs off a phase index 0–23, scaled by `DAT_00026484` = **30.0**
  (16.16 fixed) → 24 × 30° = **720° crank**. Dispatch thresholds are 720.0 / 100.0.
- Per-channel config @ 0x0004B690 = {0, 360, 240, 600, 480, 120}° crank phase offsets.

### Subsystem map (renamed in Ghidra)
- `solenoid_pwm_channel_drive` @ **0x000096FC** `(physical_channel, duty_count)` — HW driver.
  6-channel HW descriptor table @ **0x0000FAE8** (stride 0x18): channel n → control bit
  `(0x0100<<n)` on register **0xFFFFF602**, duty/compare register **0xFFFFF652 + 2n**
  (0xF652..0xF65A). These are SH7055 ATU-II output-compare registers (angular timing).
- `solenoid_channel_output_update` @ **0x000268E8** `(duty_fraction, _, logical_channel)` —
  duty→count (scale 0.25), inhibit gate, calls driver. Maps @ 0x4B6A8 (logical→physical),
  0x4B6AE (enable), 0x4B64C (gate masks).
- `solenoid_status_word_read` @ **0x00026DFC** — 16-bit inhibit/fault word @ RAM **0xFFFFB744**.
  Built by `FUN_0001C5D4`; per-channel circuit diagnostics in `FUN_00024570` (fault byte
  0xFFFFBF21). Precondition AND-gate uses 0xFFFFBF6C/BF70/BF74/CE24/CF24/CFA0 (batt/ign OK).
- Control state: 6 structs @ RAM **0xFFFFBFB8** stride 0x28 (channel index at +0x0C), init by
  `FUN_00026320`; per-type actuation handlers via dispatch table @ 0x0004B670 (stride 0x10,
  handler ptr at +0x08 → e.g. `FUN_00026088`).

**This likely closes the AVLS open item** "physical OSV port write": the AVLS OSV (and AVCS OCV)
solenoids are driven here, on ATU-II compare registers 0xFFFFF652+2n / control bit on 0xFFFFF602.
Cross-check `avls_cam_mode_state_machine` (0x40168) → which of these 6 channels it commands.

---

## Re-anchor: how to actually find the purge output (next step)
The purge valve is a **free-running low-frequency PWM** (not crank-synced), so look outside the
bank above:
1. Find the purge duty computation: an airflow/purge-density map lookup, gated by ECT warmup,
   closed-loop status, and canister load; force-zeroed at idle / DFCO / cranking. Its result is a
   duty variable written to a PWM output.
2. Candidate hardware: an SH7055 PPG channel or a compare-match-timer software PWM toggling a
   port-output bit. The other ATU literal cluster 0xFFFFF444–F44E is ATU config (referenced only
   from the setup table @ 0xFA94), not a separate purge PWM — rule it out.
3. Purge-circuit DTCs P0458 (0x5BD85) / P0459 (0x5BD86): find the output-driver diagnostic that
   sets them; it references the purge output register/bit directly → identifies the pin.

## Repurpose plan (once the purge output is located)
1. Wire the boost-control solenoid to the purge solenoid's existing harness pin.
2. Replace the purge duty source with a boost-duty map (RPM × load) using the descriptor-based
   table interpolators already RE'd (see D2WD610H_RE_notes.md §3).
3. Neutralize purge enable gating (ECT/EVAP-monitor/canister-load) so the output is live under boost.
4. Mask purge-circuit DTCs P0458/P0459 (0x5BD85/0x5BD86 — already in the def).
5. Match PWM frequency: 3-port MAC boost solenoids want ~15–30 Hz; retune the purge PWM period
   if it differs.

## Safety note
NA EZ30R, no factory wastegate/turbo — this only makes sense as part of a forced-induction build.
Design the boost duty map conservatively and keep an overboost fuel cut as a fail-safe.
