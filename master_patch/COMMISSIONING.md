# Master-patch commissioning order

Do not start with a flashed car and a connected turbo control valve. The static
checks in this repository prove composition and code structure, not the wiring,
sensors, fuel system, engine, or tune. Use a disposable ROM copy for every edit
and keep the root stock image unchanged.

## 1. Confirm parts and harness with power off

1. Confirm the ECU reports CALID `D2WD610H` and ECU ID `3C5A387116`.
2. Verify root stock, `base_roms` stock, and original SRF payload hashes using
   the master verifier.
3. Trace B3-2/B3-3 to B136-31/B136-23 and B3-4/B3-5 to B136-13/B136-35.
4. Confirm the separate IAT sensor curve and post-intercooler installation.
5. Confirm E28 MAP ground, signal, and regulated supply by measurement.
6. Disconnect and insulate all four factory oxygen-sensor connectors.
7. Confirm all six injector part numbers, test/cleaning data, base fuel
   pressure, fuel-pump delivery, and manifold-referenced pressure regulation.
8. Keep the wastegate referenced directly to the compressor/manifold source;
   leave the EBCS out of the pressure path.

## 2. Bench the analog inputs before flashing

Use a fused, current-limited setup and do not backfeed an unpowered ECU.

1. Pressure-test the Omni MAP across vacuum, local atmospheric pressure, and
   the intended positive-pressure range. Compare `0xFFFFABC4` against the
   calibrated reference, not only the sensor endpoints.
2. Set the supplied 50-4110-style controller to P0 or P1. Power red from its own
   switched 10-18 V / 10 A fused supply and ground black at a clean power/engine
   ground. Never connect black to B3-2/B136-31. Compare white-to-black voltage
   with B136-23-to-B136-31 voltage under normal electrical loads to quantify
   ground offset.
3. Sweep a protected 0-5 V source through the former-MAF input and verify:
   - below 0.50 V: logger lambda 0.0, ready 0.0, EBCS command zero;
   - 0.50..4.50 V: `lambda = (2*V + 10)/14.64`, ready 50.0;
   - above 4.50 V: logger lambda 0.0, ready 0.0, EBCS command zero.
4. With the actual controller, record display and white-to-black voltage during
   cold warm-up, warmed free air, and a disconnected sensor. An in-window result
   is not proof of controller health and must not be presented as such.
5. Confirm both patched bank feedback values are identical and both inhibit
   helpers switch together. Do not substitute a 5 V rail directly without
   current limiting and a proven common reference.
6. With wideband input valid, separately move MAP, RPM, and IAT outside each SD
   validity window, below the first 1500-RPM boost breakpoint, and force the
   500 g/s SD fault sentinel. Every case must leave EBCS command at zero.

## 3. Install logging

Add the project fragment to a copy of a normal SSM logger definition:

```sh
python3 master_patch/install_master_logger.py /path/to/logger.xml
```

Log at minimum:

- E500 external-wideband lambda/estimated AFR;
- E501 raw former-MAF ADC/input voltage;
- E502 external-wideband readiness;
- MAP, barometric pressure, RPM, IAT, modeled airflow, calculated load;
- commanded fuel/lambda, short- and long-term correction, CL/OL state;
- ignition timing, feedback knock, fine-learning knock, KCA, IAM;
- AVLS requested/committed state, vehicle speed, engine-oil temperature, throttle, injector
  duty/pulse width, and battery voltage;
- purge/repurposed EBCS duty; and
- independently measured fuel pressure and wideband/controller status with a
  common timestamp.

E500 equal to zero means invalid input. Never treat it as an extremely rich
sample or average it into tuning data.

## 4. First start with no boost route

1. Keep the engine physically unable to enter boost and force open-loop where
   appropriate for controlled commissioning.
2. Validate cranking and hot/cold restart pulse widths before extended running.
3. Compare the controller gauge, ECU lambda, raw ADC voltage, and an independent dyno
   lambda reference. Resolve any offset before changing VE or injector data.
4. Calibrate idle and vacuum VE cells on a load-controlled dyno. Confirm MAP,
   IAT, airflow, load, fuel correction, and injector pulse width are plausible.
5. Validate deceleration, tip-in, heat soak, fan operation, and the oil-temperature-selected,
   vehicle-speed-gated AVLS transition.
   A 500 g/s airflow value while running is a fault indication: stop and find
   the invalid SD input rather than tuning around it.

Stop immediately for loss of fuel-pressure differential, lambda leaner than
command, knock, unstable timing/load, sensor invalidity, clipping, severe bank
imbalance evidence, or disagreement between ECU and independent instruments.

## 5. Prove protections without relying on engine overboost

Bench-simulate MAP and wideband inputs, or use an equivalent controlled test,
to show that throttle, invalid-wideband, invalid MAP/RPM/IAT, below-minimum-RPM,
and 500 g/s SD-fault gates command zero duty, 5.5 psi commands zero duty, and
6.5 psi reaches the stock fuel-cut aggregation path.
Confirm the 6800/6770 limiter behavior. Do not deliberately overboost the
engine just to test the hard cut.

Scope the original purge output unloaded to establish frequency and polarity.
Then drive the intended EBCS on a fused bench circuit and prove that ECU zero
duty maps to the valve state that gives minimum boost. Resolve flyback,
current, heat, and fail-state behavior before attaching pressure hoses.

## 6. Spring-only load testing

Only after the naturally aspirated/vacuum region is stable:

1. Retain zero feed-forward duty, zero Kp, and zero maximum duty ratio.
2. Verify the 45 mm gate really produces approximately 5 psi and cannot creep
   above the hard limit throughout the RPM/load range.
3. Tune VE, commanded lambda, injector data, and timing in small steady-state
   steps using synchronized data and conservative knock limits.
4. Validate each AVLS side and the transition separately, then transients,
   restarts, heat soak, and altitude.

Do not add electronic duty until spring-only control and every protection have
passed. Any later RomRaider edit creates a new calibration that no longer has
the generated baseline hash and requires a fresh checksum and change audit.
