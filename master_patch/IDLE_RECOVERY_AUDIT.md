# September 8 — load-change fueling trace and idle-recovery candidate

**Follow-up:** the [14:13 candidate capture](../logs/20260908_recovery_review.md)
shows improved settled fueling but unresolved near-stall recovery. B874 is
now measured directly, and the timing drops during opening are strongly
compatible with the base-D map. The remainder records the initial offline
build/trace; its proposed first validation has now happened.

The unexplained pulse reduction now has a strong software attribution: stock
load-change compensation `B874` becomes substantially negative as modeled
load falls. The idle VE taper makes that fall larger. A separate candidate
removes the steep VE drop in the measured idle-pressure region while keeping
the stock transient routine and its calibration intact.

This candidate was produced offline; it has not resolved rev recovery. No ECU
connection, flashing or engine operation was performed by the agent.

## Retained routine identification corrected

`1E7E8` was labelled as after-start compensation B. It is a continuous,
signed **load-change fuel correction**, with additional startup gates/gain.
Its opcodes and stock lookup data are unchanged in both the 10:30 image and
the candidate. Logger E511 and the Ghidra naming script now describe it correctly.

| Value/path | Verified behavior |
|---|---|
| `B8B8..B8C4` | Four-sample history of conditioned load `B438` |
| `B880` | Current load minus the three-updates-old sample, with native limits/deadband |
| `B878` / `B87C` | Slowly followed load / current-minus-followed load; the falling-load filter moves 1% per invocation |
| `1E9E4`, `B884/B888` | Form signed fast/slow correction terms using stock load curves and scalar factors |
| `1EAD4`, `B890` | Startup gain and decay; late replay explicitly uses settled startup state |
| `1E7E8`, `B874` | Combine the terms with direction-dependent coolant/RPM factors; negative output is permitted beyond the 625-count startup gate |
| `1DD04` | Add B874 into both bank/cylinder factors, then apply base duration and remaining factors/clamps |
| `1CA38` | Normal running branch copies the six composed durations to scheduler inputs without halving them |

The update cadence is tied to crank position. Table `FA7C..FA93` selects task
6 at slots 0, 4, 8, 12, 16 and 20 of the native 24-slot / 720-degree cycle.
The route is `87F2 -> 82B6 -> FBC4/CF7E -> task 6 at 696C -> 11AD0`, whose
`11D70` slot points to `1E7E8`. In normally synchronized running this gives
one update per **120 crank degrees**, or approximately `20/RPM` seconds.
This is distinct from the engine-runtime counter's periodic task.

Consequently a 1%-per-update falling-load filter takes more wall-clock time
to settle at low RPM: its mathematical e-fold time is about 1.59 seconds at
1250 RPM and 2.65 seconds at 750 RPM. The ECU has not acquired a new fixed
millisecond decay timer. Missed activations and hardware scheduling time are
not simulated here.

## Replay against the supplied log

Input remains `romraiderlog_idle_diagnostic_20260908_123651.csv` on the
user-confirmed 10:30 `48d63c...` image. See the
[original capture review](../logs/20260908_idle_review.md) for hashes, ECU
flash-block CRC agreement and gauge confirmation.

`replay_20260908_transient.py` executes the B874 routine family, base-duration
producer `1E0C8`, and final composer `1DD04`. It interpolates the recorded
load/RPM/coolant samples and uses the crank-derived update interval. Stock
lookup helpers remain mathematical models. Unlogged corrections are explicitly
neutral; initial crank phase, sub-sample input changes and output-scheduler
delay are unknown.

| Seconds | RPM | Modeled B874 | Composed pulse, model | Scheduled pulse, log |
|---:|---:|---:|---:|---:|
| 153.873 | 750 | -0.461 | 0.948 ms | 0.908 ms |
| 157.621 | 731 | -0.349 | 1.064 ms | 1.000 ms |
| 160.950 | 774 | -0.514 | 0.840 ms | 0.788 ms |
| 161.471 | 760 | -0.399 | 1.002 ms | 0.972 ms |
| 162.717 | 957 | -0.126 | 1.656 ms | 1.650 ms |

Across 151--165.5 seconds, median absolute pulse error is 0.059 ms and mean
error is 0.182 ms. Larger discrepancies remain around the rapid opening events,
where unlogged enrichment and sampling/scheduling alignment matter. These
model values are not measurements of B874; the new profile captures that value
directly. The replay supports the attribution without proving that every
transient fuel term or physical injector event has been reconstructed.

The original VE surface also generates a negative B874 correction in a
prescribed **fixed-pressure RPM decline**, because VE alone reduces modeled
air mass per revolution. The candidate nearly eliminates that artificial
load-change contribution in the same fixture. Neither fixture predicts how
the engine's actual RPM, pressure, combustion or AFR will respond.

## Candidate: ten VE cells, existing code retained

File: [D2WD610H_idle_recovery_candidate.bin](candidates/D2WD610H_idle_recovery_candidate.bin).

- SHA-256: `6af0d130b585abf9c9b275840ddb0b237485d84f8f8adf7b15df8462adc72433`.
- Subaru checksum: `0x16CB75E9`.
- Rebuilt from canonical stock through the pinned 10:30 baseline; not built
  from an arbitrary supplied tuned image.
- Changes the 500/800-RPM cells at 250 and 350 mmHg to the existing 1200-RPM
  row. The 450/550/650-mmHg cells then bridge pressure times VE to each row's
  unchanged 760-mmHg value. Ten cells and checksum differ:
  **34 actual differing bytes**.
- Main `D2WD610H_master_patch.bin` remains the 10:30 baseline. All machine
  code, transient tables, injector data, cut behavior and table addresses are
  byte-identical between baseline and candidate.

The pressure sweep caught an air-mass reversal in an earlier, narrower VE
blend. The final transition interpolates pressure times VE at the table
knots. An analytic check of both ends of every linear-VE segment also verifies
that modeled air mass rises with pressure between those knots. The candidate
rejoins the baseline at 760 mmHg; the measured idle-pressure correction is
unchanged by this transition repair.

At fixed 41.32 kPa absolute:

| RPM | Baseline VE | Candidate VE | Modeled air-mass increase |
|---:|---:|---:|---:|
| 1252 | 0.973 | 0.973 | 0% |
| 1069 | 0.860 | 0.962 | 11.9% |
| 800 | 0.651 | 0.962 | 47.9% |
| 734 | 0.624 | 0.962 | 54.3% |
| 500 | 0.527 | 0.962 | 82.5% |

The measured settled 1069-RPM / 16.61-AFR point would become about **14.85 AFR**
under unchanged physical VE and other fuel effects. That is a conditional
estimate, not a promised measured AFR. Holding the existing 1200-RPM row avoids
fitting an exact correction to the transient AFR trace. The larger increases
below 800 RPM are an extrapolation that needs particular care during validation.
Interpolation below 500 RPM also changes; unchanged cranking tables do not
establish unchanged startup behavior. Higher modeled load can change timing
and other load-indexed decisions even though their table bytes are unchanged.

There is not yet evidence to disable the stock transient routine or guess new
deceleration multipliers. Establishing the base fuel map before adjusting
transient compensation is also the order recommended in
[Haltech's transient tuning guidance](https://support.haltech.com/portal/en/kb/articles/tuning).
That general guidance does not validate this Subaru calibration.

## Initial checks and proposed first measurement

- Eight retained-code execution groups cover neutral steady load, signed
  responses long after startup, slow-history decay, startup/flag gates, both
  bank/cylinder composition, normal duration selection, crank-slot routing
  and negative controls that remove the history or fuel contribution.
- Seven candidate groups cover deterministic build/hash, exact byte scope,
  checksum, pressure/RPM boundaries, air-mass monotonicity across pressure
  segments, the actual SD wrapper's fixed-pressure air mass per revolution,
  and the induced transient interaction.
- The full master audit passes on the unchanged 10:30 baseline, including
  the added transient tests and all three logger profiles. The separate
  candidate tests establish its bounded calibration difference; this is not
  an engine validation or a claim that the baseline hash check accepts it.
- RomRaider's real queue and A8 builder retain all 19 recovery channels after
  reload, producing a checksum-valid 43-address / 136-byte request. This new
  selection subsequently produced the complete 14:13 capture. Its units-label
  comma required the header correction documented in the follow-up.

For the next controlled validation use the
[idle recovery profile](D2WD610H_idle_recovery_profile.xml) with the updated
[master logger definition](D2WD610H_master_logger.xml). It retains RPM, MAP,
load, airflow, throttle, temperatures, pulse/latency, pump, battery, CL/OL and
wideband/raw input, while adding **E511 signed transient correction**, **E123
base equivalence ratio**, and **E503 committed lift mode**. E123 is a fuel
factor here, not measured AFR. Load this profile by itself; it uses the full
native 43-address budget.

The next engine validation should be untouched idle, not another sequence of
blips. Review fueling as it settles below 1200 RPM before testing rev recovery.
Do not continue a run through another lean/rough trend. The car can remain
parked until that controlled test is arranged; no extra run is needed to
finish the offline work in this audit.

Reproduce:

```sh
python3 master_patch/test_transient_fuel_execution.py
python3 master_patch/test_idle_recovery_candidate.py
python3 master_patch/idle_recovery_candidate.py
python3 master_patch/replay_20260908_transient.py
python3 master_patch/verify_master_patch.py
```

The complete numerical replay is saved in
[20260908_transient_replay.json](../logs/20260908_transient_replay.json), with
explicit model assumptions. The original CSV and 10:30 BIN are unchanged.
