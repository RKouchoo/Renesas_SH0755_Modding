# Injector scaling and retained fuel-pump demand

[Reference home](README.md) · [Image identities](IMAGES.md) · [Word-level evidence](evidence/fuel_pump_scaling_20260912.json) · [Log replay](../../logs/20260912_pump_demand_review.json)

The injector change left a separate pulse-to-fuel-consumption coefficient at
its stock value. That is a verified calibration inconsistency affecting native
pump demand and telemetry. Both rolling builds now correct it. **The rich
loaded bog remains unresolved; this is not a demonstrated cure.**

## Native dependency

The first 31 instructions of `13CA8`, through the store at `13CE4`, calculate:

```
B1C4 = B544 / 60 * ROM[72D54] * C0B8 * 0.000003
```

B544 is RPM; C0B8 is effective scheduled injector pulse in microseconds,
excluding the independent latency C0D8. The rest of `13CA8` converts the value
for telemetry. Native `2A910` also reads B1C4, multiplies it by 3.6, stores
C2A0 and filters it into C2A4 before selecting pump mode. The model follows
the **current** value with coefficient 0.99; 0.01 is a snap tolerance, not its
current-value filter weight. BE40 can separately add 80 through C29C.

Threshold descriptors `60204/60220` use battery voltage ABB4 and **processed
relative pressure B2A4**, not the logged direct SD pressure ABC4. At relative
pressure zero their high/medium thresholds are 60/5.8 native demand units;
at -400 mmHg they are 73.3/19.1. The voltage columns are identical. C2AC
encodes the selected mode; `2A53A` publishes 33.3, 66.7 or 100 percent to
C298 and hands the ratio to PWM writer DEAA. C2AD/01 can still force zero.
The higher-level `2A614` startup, test and operating gates remain separate.

## Correction

Main injector duration scalar `76014` changed from 6675 to approximately
3266.66724. For the same modeled fuel quantity, effective pulse is therefore
about 0.48939 of stock. Leaving `72D54=4.59` unchanged scales the consumption
estimate down by the same amount. Both builders now maintain the invariant:

```
new consumption coefficient = stock coefficient * stock duration scalar / new duration scalar
                            = 4.58999968 * 6675 / 3266.66724
                            ≈ 9.37905383
```

The stored float is `4116109B`. Only this float and the Subaru checksum changed
in each BIN. Injector flow, latency, VE, AFR targets, timing, pump command
percentages and operating gates retain their previous bytes. Both definitions
now expose the coefficient and explain its relationship to injector scaling.
The correction makes the internal model consistent with the selected injector
calibration; it does not independently validate physical injector flow.

## Comparison with the existing drive

The 14:42 log's 77–85.25 s bog remains rich: AFR 11.06–12.17, median 11.58.
It does not log pump command, rail pressure, battery voltage, B2A4 or BE40.
The replay therefore imposes those missing inputs explicitly: 11.5/14/16.5 V
with their installed latency values, relative-pressure endpoints -400/0 mmHg,
zero BE40, normal running selection and P21 quantization offsets ±0.128 ms.
Each sample is held settled; no task timing or gauge boost is inferred.

For the 80 bog samples, all **720 comparisons at relative pressure zero**
select 66.7 percent both before and after. At the -400-mmHg endpoint, 574 of
720 comparisons change from 33.3 to 66.7 percent; the rest retain 66.7. These
are alternative input fixtures, not observed pump modes. Some samples near
4100 RPM in the 130.6–132 s window select 100 percent after the correction.
That window also contains unlogged gear/clutch state; it is not declared a
successful loaded pull or proof of pump starvation.

The scaling defect is real, but the existing rich-bog data do not establish
that insufficient pump output caused it. No new drive, capture or flash was
requested or performed for this repair.

## Verification and Ghidra

Six focused groups execute native pulse conversion, mode selection, filter
and command publication on both builds. A stock-coefficient negative control
reproduces the roughly halved demand; the paired-scalar case preserves demand
when pulse duration is rescaled. Table interpolation and physical PWM handoff
remain modeled boundaries. The tests do not simulate rail pressure or combustion.
The complete main verifier and all ten v2 verifier groups pass. Historical
drive/fueling analysis still reconstructs the original captured images and
passes its original flash/hash checks after the rolling images advance.

Ghidra MCP timed out on `13CA8`. Local disassembly of the pinned stock image
and native execution provide this evidence. Proposed comments are retained in
the evidence JSON; no new Ghidra annotation is confirmed saved.

```sh
python3 -B tests/test_fuel_pump_demand_execution.py
python3 -B tools/analysis/analyze_20260912_pump_demand.py
```
