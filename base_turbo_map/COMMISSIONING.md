# Commissioning and First-Tune Sequence

The order matters. Stop at the first failed gate; do not compensate for a hardware or sensor fault
by adding fuel or removing timing in the ROM.

## 1. Establish the mechanical minimum-boost state

- Confirm the 45 mm wastegate spring on a regulated-air bench test rather than relying only on its
  label.
- Pressure-test the intake, intercooler, reference lines, and wastegate diaphragm.
- For the first loaded run, connect the pressure source directly to the wastegate and leave the
  EVAP/EBCS solenoid out of the pneumatic control path.
- Verify that zero electrical duty is the minimum-boost state before plumbing the solenoid.
- Check gate priority, dump-tube restriction, and turbine housing/manifold layout. A 5 psi spring
  does not guarantee 5 psi if the system boost-creeps.

The base ROM already has WGDC, Kp, and the maximum duty clamp at zero. Do not raise the clamp while
commissioning spring pressure.

## 2. Complete the fuel-system calibration

Record these values in the tune log before flashing:

- injector make, part number, nominal/tested flow, test pressure, fuel type, and individual flow
  spread;
- injector latency at every available voltage point and the pressure at which it was measured;
- base rail pressure and whether the regulator maintains a 1:1 manifold reference;
- pump voltage and measured fuel delivery at the rail pressure required at 5 psi boost;
- fuel-pressure sensor/gauge method and minimum acceptable differential pressure.

The generated baseline contains the factory A4TE002B STI-pink starting values: 552.47 cc/min
estimated and 2.788/1.488/0.980/0.684/0.380 ms at 6.5/9.0/11.5/14.0/16.5 V. It also ratio-scales
the four cranking and two tip-in tables. Do not use those numbers merely because the injectors are
pink: confirm genuine part numbers, matched condition, rail fitment, base pressure, and regulator
reference first. Validate hot idle/cruise trims, then cold/hot cranking and transient lambda across
battery voltage. Correct scalar before deadtime, and do not hide injector error in the MAF curve.
If the installed system cannot maintain injector differential pressure, stop regardless of duty
cycle or commanded lambda.

Use fresh Australian 98 RON fuel from a known source. Fuel grade is an assumption, not a sensor;
bad fuel, cross-fuelling, heat soak, and ethanol-content variation still require margin.

## 3. Validate every air and pressure measurement

- With key-on/engine-off, compare ECU MAP to a calibrated barometer/reference gauge.
- Under vacuum and regulated positive pressure, validate the complete MAP curve and confirm the
  installed sensor matches `offset=-414.0`, `multiplier=514.199951`.
- Confirm the MAF sensor, orientation, straight-pipe placement, and housing dimensions. Calibrate
  closed-loop cruise first and verify neither voltage nor the roughly 297.69 g/s table ceiling is
  approached during a pull.
- Confirm IAT is measured after the intercooler at a representative location; an upstream or
  heat-soaked sensor invalidates the protection curve.
- Validate the external post-turbo AEM wideband against free-air/calibration instructions, log its
  validity/fault state, and align its monotonic timestamps with RomRaider data.
- The MAF Limit table is already at its maximum uint16 value (about 300 g/s). If logs approach it,
  stop; the ROM cannot represent a higher value in that table without a different airflow strategy.

The retained pre-turbo factory A/F sensor remains the ECU feedback sensor. It is not a substitute
for the externally logged post-turbo wideband during boosted tuning.

## 4. Prove the two component patches without boost

Before using the combined base map under load, complete the standalone checks already listed in
`../docs/single_front_af_patch.md` and `../docs/patch_build_guide.md`:

- both factory front log channels follow the retained Bank-1 sensor;
- bank corrections remain stable and the removed-sensor DTCs behave as documented;
- both rear connectors are isolated and rear logger values are treated as invalid;
- former purge PWM frequency and polarity are scoped;
- simulated MAP proves the hard fuel cut and its recovery behavior;
- zero duty is physically the wastegate-spring state.

P0458/P0459 remain enabled. Diagnose them rather than automatically disabling an electrical fault
that may now identify a wiring problem in the repurposed solenoid circuit.

## 5. First start and no-boost validation

1. Flash a checksum-verified working copy only after the pinned STI-pink calibration matches the
   installed injectors and the installed MAF/housing data is established.
2. Reset learned fuel trims and IAM only as required by the tuning workflow; record the reset.
3. Check fuel leaks and rail pressure before starting.
4. Warm the engine without entering boost. Verify coolant, IAT, MAP, MAF, battery voltage, both
   front A/F log channels, trims, ignition timing, and all DTCs.
5. Validate idle and cruise fueling across the MAF curve. Do not use positive-pressure operation to
   repair a poor cruise calibration.
6. Confirm open-loop state occurs before positive manifold pressure during a brief unloaded
   throttle test.
7. Log AVLS command/feedback if available and confirm the load-requested transition can occur from
   2500 RPM, with a clean forced transition at 3200 RPM and release at 3000 RPM. Stop for chatter,
   oil-pressure concerns, a lambda step, or repeatable knock at crossover.

## 6. Spring-pressure dyno pulls

Use a load-controlled dyno with an operator able to abort immediately. Begin below the intended
spool region and use short, low-RPM sweeps before extending RPM. Log at the highest reliable sample
rate:

- RPM, throttle, requested/actual throttle, MAP, MAF voltage and g/s, engine load;
- open/closed-loop state, commanded Primary OL target, injector pulse width/duty estimate;
- both front A/F channels and fuel corrections;
- post-turbo wideband lambda plus validity/fault status;
- ignition timing, IAM, feedback knock correction, fine knock correction;
- AVLS command/state and the exact transition RPM/load;
- IAT, coolant temperature, battery voltage, vehicle speed;
- fuel pressure and oil pressure through the external logger.

Abort immediately for any of the following:

- actual lambda trends leaner than 0.82 once MAP becomes positive, or differs materially from the
  commanded target after accounting for sensor transport delay;
- loss of fuel-pressure differential, injector saturation, MAF/MAP clipping, or invalid wideband
  status;
- repeatable knock correction, abnormal noise, misfire, smoke, rising crankcase pressure, or oil
  pressure loss;
- MAP above the intended 5 psi spring level, especially approach to the 5.5/6.5 psi software
  thresholds;
- uncontrolled IAT or coolant rise.
- an unstable AVLS transition, oil-pressure anomaly, or repeatable torque/lambda discontinuity at
  the 2500–3200 RPM crossover.

These are abort gates for the first run, not final tuning targets. Do not tune through a hard fuel
cut; resolve boost creep or sensor/calibration error first. Extend pulls toward the 6800 RPM
limiter only after the preceding RPM range is clean. Setting that limit is not proof that
the turbo oiling, valve train, fuel system, or engine is safe at that speed.

## 7. Tune fuel, then timing

Correct the MAF/injector model so measured lambda follows the commanded table before changing the
command to chase the measurement. Keep both banks matched unless independent, trustworthy bank
measurement proves a real difference. Tune timing only after fuel delivery, lambda, charge
temperature, and boost are repeatable. Use conservative steps and confirm exhaust-temperature and
knock behavior; a very retarded map can overheat the exhaust side.

The initial high-load lambda and timing values are deliberately conservative. They are not a power
target and should not be copied to higher boost.

## 8. Electronic boost control comes later

A 5 psi spring normally needs no positive duty to achieve a 5 psi target. Only introduce EBCS duty
if logs show a controlled reason, such as high-RPM spring droop, after polarity and plumbing are
proven.

When that stage is reached:

1. keep Kp at zero;
2. raise the maximum duty clamp from zero in very small steps;
3. build the feed-forward curve with 2–3 percentage-point changes while watching boost slope;
4. only then add a small proportional gain;
5. retain a mechanical pressure path and independently tested overboost response.

The current controller is RPM-only, proportional + feed-forward, has no integral term, no target
atmospheric compensation, and no hard-cut hysteresis. It is not equivalent to a full factory turbo
controller.
