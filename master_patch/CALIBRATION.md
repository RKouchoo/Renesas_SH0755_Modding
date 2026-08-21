# Master-patch calibration baseline

This is the exact generated starting point, not a claim that the engine will
achieve the commanded values. All pressure figures described as boost are
relative to the firmware's fixed 760 mmHg reference unless stated otherwise.

## MAP sensor

The selected Omni Power `MAP-SUP-3BR` endpoints are converted into the native
absolute-mmHg model used by `map_sensor_voltage_to_pressure_process` at
`0x7A14`:

```text
P_kPa_abs  = 65.0602409639 * volts - 9.0361445783
P_mmHg_abs = 487.9919381449 * volts - 67.7766580757
```

The two float32 values are stored at `0x72810` as offset followed by
multiplier. They reproduce 30 kPa at 0.60 V and 300 kPa at 4.75 V within
float32 rounding. The raw low-input diagnostic threshold is 0.30 V; the stock
high threshold remains approximately 4.921 V. This deliberately leaves room
for vacuum output below the published 30 kPa endpoint, but that extrapolated
region is not guaranteed by the supplied product data and must be pressure
tested on the actual sensor.

The speed-density runtime validity window is 100 through 1600 mmHg absolute.
The upper limit is about 213 kPa absolute, comfortably above this 5 psi
baseline but intentionally below the sensor's electrical ceiling. An invalid
running input selects the fixed 500 g/s high-load fail-safe value.

## Speed density

The modeled airflow is:

```text
airflow_g_s =
    VE(MAP_abs_mmHg, RPM)
    * MAP_abs_mmHg
    * RPM
    * 2.999 L
    * 1.3203052e-5
    * IAT_density_multiplier
    * global_multiplier
```

The airflow wrapper chooses one of two VE maps from committed AVLS state
`0xFFFFCD86`: mode 3 uses high lift and every other value uses low lift. Both
have 13 MAP columns covering 150..1500 mmHg absolute. Their RPM axes show only
the ranges each state can genuinely occupy under the supplied hysteresis:

- low lift: 9 rows, 0..3200 RPM;
- high lift: 11 rows, 3000..7500 RPM.

The 3000..3200 overlap is real: the selected table depends on committed state,
not RPM alone. The two supplied surfaces are resampled from the same conservative
single-map seed and agree in their shared region, so the generated baseline does
not intentionally add a fueling step. They are not measured EZ30R VE maps and
must be calibrated separately from logs. Global multiplier defaults to 1.0.
IAT correction uses `293.15 / (IAT_C + 273.15)` from -50 through 150 degrees C.

There is no MAF fallback and no speed-density OFF switch. Exact zero RPM writes
zero. Invalid nonzero-RPM MAP, RPM, IAT, calibration, lookup, or arithmetic
state writes 500 g/s so the retained stock load consumers move toward their
rich/high-load regions rather than using stale airflow.

## Wideband and stock-O2 replacement

The supplied seller-labelled 50-4110 instruction sheet gives the same 0-5 V
output in P0 (AFR display) and P1 (lambda display):

```text
gasoline AFR = 2.0 * volts + 10.0
lambda = (2.0 * volts + 10.0) / 14.64
       = 0.136612... * volts + 0.683060...
accepted voltage = 0.50..4.50 V inclusive
```

RomRaider exposes the slope/offset at `0x7E404` and voltage limits at
`0x7E40C`; do not edit them for this unit in P0/P1. P2/P3 require different
transfers and are unsupported. At each accepted sample,
the patch writes the same lambda to the two stock bank inputs at
`0xFFFFAE60/AE64`, zeroes the obsolete pump-current pair at `AE68/AE6C`, and
sets both readiness values at `AE70/AE74` to 50.0. It mirrors lambda to
`B098/B09C` for logging.

For an invalid sample it publishes 1.0 only as an internal placeholder, writes
0.0 to the logger mirrors and readiness values, returns the stock inhibited
state from both closed-loop bank gates, and forces EBCS duty to zero. The 0.0
logger value is a fault sentinel, not a physical lambda.

The controller advertises a legitimate 0-5 V span. The narrower 0.50-4.50 V
range is an operating plausibility gate corresponding to 11-19 gasoline AFR;
it is not a sensor-health diagnostic. A disconnected or warming controller can
still produce an accepted voltage. Its physical fault outputs and installed
white-to-black versus ECU-reference offset must be measured during commissioning.

One sensor feeds both banks. No calibration can recover per-bank fault
detection, and the post-turbo location adds delay that must be represented when
interpreting fuel corrections.

## Injectors and fuel

The injector seed is translated from a SHA-pinned factory 2003 JDM STI
`A4TE002B` ROM. In D2WD610H display units it corresponds to an estimated
552.47 cc/min, with these donor deadtimes:

| Battery voltage | Deadtime |
|---:|---:|
| 6.5 V | 2.788 ms |
| 9.0 V | 1.488 ms |
| 11.5 V | 0.980 ms |
| 14.0 V | 0.684 ms |
| 16.5 V | 0.380 ms |

That is the closest pinned factory evidence for the requested STI pink top-feed
injectors; it is not proof that injectors sold or described as 565 cc/min have
those exact characteristics. The builder ratio-scales all four cranking-IPW
maps, both tip-in maps, and the tip-in activation threshold as starting values.
Confirm part numbers, base differential pressure, condition, flow spread, and
fuel compatibility before use.

Both Primary Open Loop maps use load axes extended to 3.0 g/rev. Existing cells
are never made leaner; high-load caps progress through lambda 0.93, 0.88, 0.83,
0.80, and 0.78, with another 0.01 enrichment at 6000 RPM and above from
1.22 g/rev. The stock atmospheric CL-to-OL delay is cleared. These values are
command targets only.

## Ignition, knock, AVCS, and AVLS

All six stock base-timing surfaces are calibrated, even though live Ghidra
proves B/E are dormant in the stock selector and the focused definition omits
them. The active surfaces are:

- normal/AVLS-low-cam AVCS-tracking-ratio 1.0 and 0.0 endpoints;
- AVLS-high-cam AVCS-tracking-ratio 1.0 and 0.0 endpoints; and
- normal/high-cam KCA limits A and B.

The letters in the source definition were anonymous reverse-engineering
placeholders, not six tune modes. Live stock code establishes this calculation
for whichever cam path is active:

```text
selected_base_timing = avcs_ratio_1.0_table * k
                     + avcs_ratio_0.0_table * (1 - k)

k = clamp((measured_intake_avcs_left + measured_intake_avcs_right)
        / (commanded_intake_avcs_left + commanded_intake_avcs_right), 0, 1)
```

Here `k` is the intake-AVCS tracking factor at `0xFFFFC17C`. A near-zero summed
command produces zero; other verified stock status logic can force it to 1.0.
It is not the learned Ignition Advance Multiplier (IAM). The normal-cam pair is
used below the verified high-cam state; the AVLS pair is used in high cam. The
definition hides the unreachable third legacy pair. Neither ratio endpoint has
a universal requirement to be the more advanced or more retarded table: the
pair compensates timing for the intake-cam angle actually achieved.

The two intake AVCS target tables are a separate selector:

- **Intake AVCS Target - AVLS Low Cam** is legacy table A at `0x7C5B0`, selected
  when committed AVLS mode `0xFFFFCD86` is 1 (low lift).
- **Intake AVCS Target - AVLS High Cam** is legacy table B at `0x7C764`, selected
  when committed AVLS mode is 3 (high lift).

They are not left/right-bank tables and the ECU does not blend A with B. It
selects one target surface for the current AVLS lift state, then the downstream
AVCS controller conditions that target for the two banks. Both target maps use
the same 14-point load axis, ending at 2.00 g/rev. Above 2.00 g/rev the lookup
uses the last column; RomRaider can rescale the existing axis breakpoints but
cannot add columns without a firmware/layout change. The low-cam map has 11 RPM
rows from 500 through 4000 RPM; the high-cam map has 18 rows from 1000 through
6800 RPM. Leave the supplied stock AVCS targets unchanged during initial turbo
commissioning; optimize them only after the sensor, VE, fuel, and ignition
models are repeatable on a load-controlled dyno.

Load axes extend to 3.0 g/rev. Timing is never increased by the builder. At
1.60 g/rev and above the full-load ceiling rises from -2 degrees at 2000 RPM to
13 degrees at 6800 RPM, with extra conservative offsets in the 1.09, 1.22, and
1.40 g/rev columns. Positive Knock Correction Advance is zero from 1.22 g/rev
up. High-IAT compensation reaches approximately -10.2 degrees at 110 C.

The master baseline makes AVLS predictable: high lift engages at 3200 RPM and
releases at 3000 RPM. Actuation minimum is 3000 RPM. Both RPM-indexed
vehicle-speed request maps and both fixed/fallback thresholds are set to
110 km/h, above the Ghidra-verified 100 km/h conditioned-speed cap. Therefore
the old vehicle-speed/oil-band request route cannot select high lift. The stock
request/commit delay, status gates, and OSV actuation remain in place.

The master definition exposes only the 3200/3000 engage/release pair and omits
the now-inoperative speed curves, speed hysteresis, oil-band selector thresholds,
and actuation-minimum calibration. Committed state—not requested state—is the
authority for VE, AVCS-target, ignition, and KCA table selection. Continuous
intake AVCS angle can still alter VE inside either lift map; the patch does not
attempt a time fade or cam-angle VE dimension.

### How to tune the four exposed base-timing surfaces

1. Calibrate the IAT sensor, MAP transfer, injector model, speed-density VE,
   commanded lambda, and fuel pressure before attempting ignition optimization.
   An airflow or mixture error makes a timing result meaningless.
2. Log engine speed, calculated load, MAP, IAT, lambda, final ignition timing,
   IAM, feedback knock, fine-learning knock, AVLS state, and left/right intake
   VVT actual angle. Log commanded intake AVCS or the tracking factor if a
   verified logger parameter is available. Use a load-controlled dyno and
   independent knock monitoring.
3. Tune the ratio endpoint that corresponds to the measured AVCS tracking in
   the logged cell. Change only well-populated cells and smooth their
   neighbours; use small changes, normally no more than about one degree per
   validated run.
4. Treat the ratio-0.0 and ratio-1.0 surfaces as a phasing-compensation pair,
   not aggressive and fallback maps. Confirm the interpolated final timing at
   intermediate tracking. Do not impose a fixed advance ordering between them.
5. Check both sides of the AVLS transition under steady load. Assign samples to
   the low/high VE table by committed AVLS state and discard samples while state
   is changing. A step in torque, lambda, or final timing means the corresponding
   low/high VE, timing, or AVCS surfaces need correction before another power run.
6. Leave positive high-load KCA at the supplied zero baseline until fueling,
   charge temperature, knock response, and repeatability are established. KCA
   is additional advance authority; it is not another base-timing map.

Stop adding timing if torque no longer rises, knock activity appears, lambda or
fuel pressure moves out of bounds, or the result is not repeatable. The supplied
timing is a conservative commissioning surface, not a finished optimum tune.

## Boost and RPM

- electronic boost-control switch: OFF (`0x7D80C = 00`), so the actuator path
  cannot command duty;
- independent hard-overboost switch: ON (`0x7D80D = 01`), so disabling the
  actuator does not disable the last-resort MAP fuel cut;
- target: reaches 5.0 psi at 2500 RPM and remains there through the table;
- feed-forward wastegate duty: 0 at every breakpoint;
- proportional gain: 0;
- final maximum duty ratio: 0;
- throttle gate: duty zero at or below processed value 30.0;
- wideband gate: duty zero unless readiness is greater than 35.0;
- SD-input gate: duty zero unless MAP, RPM, and IAT are finite and inside their
  editable speed-density validity windows;
- minimum control speed: duty zero below the first shared boost-table RPM
  breakpoint, 1500 RPM in the baseline;
- SD-result gate: duty zero when modeled airflow is non-finite or equals the
  fixed 500 g/s invalid-state sentinel;
- soft MAP limit: 5.5 psi, commands zero EBCS duty;
- hard MAP limit: 6.5 psi, sets the verified stock fuel-cut flag path;
- RPM limit: 6800 RPM cut / 6770 RPM resume.

Thus the generated baseline is mechanically spring-controlled even though the
boost firmware and independent switches are installed. There is no integral
term. A target table does not restrain a spring, incorrect hose routing, an
undersized/mispositioned gate, or boost creep.
