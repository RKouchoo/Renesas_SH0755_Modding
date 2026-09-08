# Slow negative load-history compensation — 2026-09-08

The user's proposed wall-wetting explanation overlaps a measured software
effect: retained load-change compensation removes substantial commanded fuel
after closure. The new component replay identifies which term dominates that
subtraction. This is a specific calibration lead, not proof of an engine fix
or a CPU calculation crash. No BIN or tuning default changed.

## What the native code does

`1E7E8` consumes **conditioned engine load B438**, not a direct raw-MAF
derivative. It forms a short history difference B880 and a slower difference
B87C, then applies direction-dependent gains and publishes signed B874. The
main load path still retains its 0.06-per-update filter. The slow falling-load
history B878 uses 0.01-per-update filtering; its mathematical e-fold time is
about 2.65 seconds at 750 RPM under normal crank-synchronous scheduling.

The slow negative path is concrete:

- `1EAC0` selects float **0.04 at 76030** when B87C is negative; `1EAC4`
  multiplies that gain into the load-history difference and stores B888.
- The slow positive path separately uses **0.10 at 7602C**.
- Negative slow coolant descriptor `5F61C`, data `76D48`, gives approximately
  10.7 at 40 °C and 10.3 at 50 °C (2.0 at 80 °C, 1.0 at 90 °C).
- Negative slow RPM descriptor `5F6BC`, data `76E7E`, gives 4.0 at/below
  800 RPM, 1.2998 at 1600 RPM and 0.7002 at 2400 RPM.
- `1E994..1E9CA` combines fast and slow contributions, applies startup gain
  B890, and writes B874. `1DD04` includes B874 in the final fuel factor.

The growing low-RPM multiplier and slower elapsed-time history decay provide
a mechanism for persistent subtraction as the engine returns toward idle.
This does not establish why this calibration mismatches the current hardware:
speed-density airflow modelling, injection characteristics and actual wall-film
behaviour are not independently measured.

## Attribution to the 14:13 capture

The replay uses the SHA-pinned original idle candidate and capture from the
[recovery review](../logs/20260908_recovery_review.md). It executes 6,639 native
updates from 130 to 256 seconds with interpolated recorded load/RPM/coolant.
Over the evaluated 145–256-second interval, median absolute B874 error is
0.001995. Initial crank phase, fast sample timing and other input flags remain
fixtures. Table interpolation is mathematical; compensation arithmetic and
control flow execute ROM instructions.

| Recorded time | Logged RPM | Logged B874 | Native replay B874 | Fast term | Slow term |
|---|---:|---:|---:|---:|---:|
| 192.959 s | 837 | −0.6097 | −0.6125 | −0.0264 | −0.5861 |
| 248.188 s | 1288 | −0.4257 | −0.4687 | −0.0846 | −0.3841 |
| 248.604 s | 792 | −0.5275 | −0.5334 | 0.0000 | −0.5334 |
| 249.124 s | 558 | +0.5111 | +0.4801 | +0.3995 | +0.0806 |

At the 792-RPM point, the replayed slow difference is −0.318688 g/rev. Its
calculation is approximately:

`−0.318688 × 0.04 × 10.45996 × 4.0 = −0.53335`

The fast change term is already zero. This is **persistent history-based
subtraction**, not an FPU stall or a missing numeric result. The corresponding
recorded net pulse is at the 0.600-ms floor. At the 837-RPM point, the logged
composed fuel factor is 0.40 and net pulse is 0.763 ms. B7DC already contains
B874; applying another `1+B874` multiplier would double-count it.

## Isolated sensitivity controls

At each selected point the pre-update emulator state is cloned. Only the four
bytes of the slow negative gain at `76030` are changed in memory to 0.02 or
zero, and the same native update is repeated. Every declared transient output
other than B888/B874 remains identical, including the history and positive
correction state.

| Point | Current replay B874 | Half slow-negative gain | Zero slow-negative gain |
|---|---:|---:|---:|
| 192.959 s | −0.6125 | −0.3195 | −0.0264 |
| 248.188 s | −0.4687 | −0.2766 | −0.0846 |
| 248.604 s | −0.5334 | −0.2667 | 0.0000 |
| 249.124 s | +0.4801 | +0.4801 | +0.4801 |

Separate 100-update steady and opening controls are unchanged; a closing
control changes as expected. These are diagnostic sensitivity values, **not
recommended settings**. At fixed logged load and fixed B7DC-minus-B874, the
half-gain case at 248.604 s would command approximately 0.629 ms net rather
than the 0.600-ms floor. That calculation does not predict AFR, combustion or
whether the engine catches itself. Keeping actual engine inputs fixed removes
the feedback through which a real calibration change would affect the result.

## Where the quoted explanation goes beyond the evidence

The linked Facebook page could not be fetched (provider throttling). Its claim
that this is the primary cause of EZ30R SD stalls is not independently verified.
The traced routine demonstrates signed load-history compensation, not a proved
physical wall-film mass model or a raw-MAF calculation dropout. The premise of
an entirely instantaneous/unfiltered load input also omits the retained load
filter. No comparison has established that MAF sensor delay is the decisive
difference.

Fuel removal on closure can be intentional; its amount and duration need to
match the engine. [Haltech's transient-throttle documentation](https://support.haltech.com/portal/en/kb/articles/transient-throttle)
describes this general function. That source does not identify Subaru's
implementation or validate the candidate gain values above.

The minimum at 558 RPM occurs after B874 turns positive, with AFR reading
13.60, so the complete recovery cannot be called continuously lean. Earlier
fuel removal could initiate the dip, but airflow/load recovery and combustion
have to be considered. The later 18:15 capture has two zero-net-pulse samples
without B874 or cut-reason channels; their cause remains open. Low opening
timing and the separate tip-in pulse are additional observations, not explained
away by this result. This evidence prioritises the **slow negative term** for
a controlled calibration investigation; it does not justify disabling every
transient correction or increasing VE everywhere.

## Reproduction

```sh
python3 master_patch/analyze_transient_components.py --output /tmp/d2wd-transient-components.json
```

The input candidate SHA is
`6af0d130b585abf9c9b275840ddb0b237485d84f8f8adf7b15df8462adc72433`;
the capture SHA is
`7b5c3fda47a64d97ee0761333bff9b1b53516d4239565681049159b2bef6d855`.
Full numeric output is retained in
[the component report](../logs/20260908_transient_components.json).

## Narrower remedy comparison: reduce the low-RPM negative multiplier

The subsequent [comparison script](compare_transient_remedies.py) executes
6,639 native updates for each of three in-memory variants: baseline, global
negative gain 0.04→0.02, and only the first negative slow RPM multiplier
4.0→2.0. The latter is a narrower diagnostic calibration proposal:

- Descriptor `5F6BC` has eight RPM points beginning at 800 and 1600 RPM.
- Data `76E7E` is uint16 scaled by 1/2048. Change only its first value from
  raw 8192 to 4096, representing 4.0→2.0.
- Full reduction applies at/below 800 RPM, tapering linearly to the original
  1.2998047 multiplier at 1600 RPM. Higher RPM remains identical.
- This is RPM-dependent, **not idle-state gated**; all loads below 1600 RPM
  are affected when the slow term is negative. It does not identify 2.0 as
  the correct final tune for the installed engine.

| Point | Baseline replay B874 | Global gain halved | First RPM multiplier halved |
|---|---:|---:|---:|
| 837 RPM | −0.6125 | −0.3195 | −0.3237 |
| 1288 RPM | −0.4687 | −0.2766 | −0.3360 |
| 792 RPM | −0.5334 | −0.2667 | −0.2667 |
| 558 RPM, positive recovery | +0.4801 | +0.4801 | +0.4801 |

Every replay update checks unchanged history, fast terms and other declared
transient outputs, allowing only the selected intermediate gain/product and
B874 to differ. Positive slow-term results remain bit-identical. The narrower
variant also requires bit-identical B874 whenever RPM is at least 1600.
Another 45 steady/opening/closing fixtures span 500–2400 RPM and 20/45/80 °C,
with 20 updates each; all controls pass.

On the fixed recorded trajectory, computed minimum-pulse samples fall from
seven to one for either alternative. These are model counts, not corrected
observations: the 792-RPM point rises only from the 0.600-ms floor to about
0.629 ms in either half-reduction case. The engine trajectory and residual
fuel factor are held fixed, so neither recovery nor AFR is predicted.

The narrower first-cell change is the preferred initial **diagnostic**
calibration comparison because it isolates the low-RPM amplification. Keep
the main load filter at 0.06 during that comparison. MAP scaling, VE, timing,
DBW, positive transient gains and the global negative gain have not been
changed. No BIN was produced by this remedy comparison.

Reproduce with:

```sh
python3 master_patch/compare_transient_remedies.py --output /tmp/d2wd-transient-remedies.json
```

[Full comparison report](../logs/20260908_transient_remedies.json).
