# Repurposing the EVAP purge solenoid output as a boost-control solenoid

Goal: drive a boost-control (wastegate) solenoid from the ECU output that currently
runs the EVAP canister purge (CPC) solenoid — hijack its PWM duty with a boost map,
neutralize purge-specific enable gating, and mask the purge-circuit DTCs.

CALID D2WD610H (EZ30R, SH7055). All code addresses are file offsets (flash base = 0).

## Solenoid PWM output subsystem (fully reverse-engineered)

The ECU has a bank of **6 general-purpose low-side PWM solenoid channels** (indices 0–5)
sharing one hardware control register. Purge is one of these channels.

### Hardware channel descriptor table @ 0x0000FAE8 (6 entries, stride 0x18)
Per entry:
| off  | field                                   | ch0    | ch1    | ch2    | ch3    | ch4    | ch5    |
|------|-----------------------------------------|--------|--------|--------|--------|--------|--------|
| +0x00| ptr shared control reg                  | 0xFFFFF602 (all) |
| +0x04| ptr shared reg                          | 0xFFFFF666 (all) |
| +0x08| u16 **channel bit mask** in ctrl reg    | 0x0100 | 0x0200 | 0x0400 | 0x0800 | 0x1000 | 0x2000 |
| +0x0C| ptr **compare/duty reg**                | 0xF652 | 0xF654 | 0xF656 | 0xF658 | 0xF65A | (F65C) |
| +0x10| ptr reg                                 | 0xF616 | 0xF618 | 0xF61A | 0xF61C | 0xF61E | ...    |
| +0x14| ptr reg                                 | 0xF606 | 0xF608 | 0xF60A | 0xF60C | 0xF60E | ...    |

So **channel n → control bit (0x0100 << n) on 0xFFFFF602, duty/compare register 0xFFFFF652 + 2n.**
The 0xFFFFF6xx block is the SH7055 timer/PPG output area.

### Functions (renamed in Ghidra)
- `solenoid_pwm_channel_drive` @ **0x000096FC** `(physical_channel, duty_count)` — writes the
  hardware: sets/clears the channel bit in 0xFFFFF602 and loads the compare register. Called
  via thunk @ 0x000090BA.
- `solenoid_channel_output_update` @ **0x000268E8** `(duty_fraction_float, _, logical_channel)` —
  converts duty fraction to an integer count (default scale 0.25, `DAT_000269E4` = 0.25f),
  checks the inhibit gate, then calls the driver. Uses:
  - logical→physical channel map @ **0x0004B6A8** = {0,1,2,3,4,5}
  - per-channel enable flags @ **0x0004B6AE** = {1,1,1,1,1,1,0,…}
  - status-gate bit masks @ **0x0004B64C** = {0x0001,0x0002,…,0x8000}
  - inhibit gate: drives only if `(mask & status_word) == 0`.
- `solenoid_status_word_read` @ **0x00026DFC** — returns the 16-bit **solenoid inhibit/fault word
  at RAM 0xFFFFB744**. A set bit inhibits that channel (e.g. purge-circuit fault sets the purge bit).
- Master update loop @ ~**0x00011E84** — calls `solenoid_channel_output_update` for channels 0–5
  each cycle, each with a per-channel duty-float source. (This region is a nest of jump-table
  trampolines Ghidra has not defined as functions — analyze/define before editing here.)

## OPEN: identify which channel index is purge
Two cheap static routes not yet finished:
1. Trace the master loop's per-channel duty-float source; the purge channel's source is the
   purge-flow/airflow duty computation (gated by ECT warmup + EVAP monitor). Candidate duty-source
   handler pointers seen in the loop pool: 0x3AF4, 0x4EEC4, 0x3B08, 0x1D8AE, 0x2A242, 0x29C00,
   0x26200 (also 0x1D8B6, 0x34194, 0x6A6AC, 0x3107C, 0x31094, 0x2689C).
2. Find the writer that sets a bit in the inhibit word **0xFFFFB744** on the P0458/P0459 purge-
   circuit path — that bit position `(1<<n)` is the purge channel index n.

Empirical fallback (bench/car): patch each channel's duty float in turn and observe which one
actuates the purge solenoid, or datalog the 6 duty sources.

## Repurpose plan (once channel index X is known)
1. **Physical**: the former-purge output pin = control bit (0x0100<<X) / duty register 0xFFFFF652+2X.
   Wire the boost-control solenoid to the purge solenoid's existing harness pin.
2. **Duty source**: replace channel X's duty-float source with a boost-duty map lookup
   (RPM × load/target) using the descriptor-based table interpolators already RE'd
   (see D2WD610H_RE_notes.md §interpolation). Open-loop duty map is the simplest first cut;
   closed-loop (target-vs-actual MAP) is a later refinement.
3. **Gating**: neutralize purge enable conditions (ECT warmup, EVAP monitor, closed-loop
   transition) so the output is live across the boost operating range; and make sure the inhibit
   bit for channel X in 0xFFFFB744 is never force-set by leftover purge logic.
4. **DTCs**: mask purge-circuit codes P0458 (0x5BD85) / P0459 (0x5BD86) — already in the def.
   A different-impedance boost solenoid can otherwise trip the circuit diagnostic.
5. **PWM frequency**: 3-port MAC boost solenoids want ~15–30 Hz. Check the purge channel's PWM
   period (the 0xFFFFF6xx period register for that channel) and retune if the purge frequency
   differs from what the boost solenoid needs.

## Safety note
This is a naturally-aspirated EZ30R; there is no factory wastegate/turbo. This work only makes
sense as part of a forced-induction conversion. Boost control open-loop without a fail-safe
(e.g. overboost fuel cut) is dangerous on an engine not originally boosted — design the duty map
conservatively and keep an overboost cut.
