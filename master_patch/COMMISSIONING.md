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
4. Confirm the HT-010206 post-intercooler installation. Treat the supplied
   1.00 kOhm curve as provisional until the input check below passes.
5. Confirm E28 MAP ground, signal, and regulated supply by measurement.
6. Disconnect and insulate all four factory oxygen-sensor connectors.
7. Confirm all six injector part numbers, test/cleaning data, base fuel
   pressure, fuel-pump delivery, and manifold-referenced pressure regulation.
8. Keep the wastegate referenced directly to the compressor/manifold source;
   leave the EBCS out of the pressure path.
9. In the matching master definition, confirm `Electronic Boost Control
   Enable` is OFF and `Overboost Fuel Cut Enable` is ON.

## 2. Bench the analog inputs before flashing

Use a fused, current-limited setup and do not backfeed an unpowered ECU.

1. Pressure-test the Omni MAP across vacuum, local atmospheric pressure, and
   the intended positive-pressure range. Compare `0xFFFFABC4` against the
   calibrated reference, not only the sensor endpoints.
2. With the IAT sensor unplugged, measure B3-4 relative to B3-5 key-on, then
   load the input with a measured 1.00 kOhm 1% resistor. A true 1.00 kOhm ECU
   pull-up gives `V_loaded / V_unloaded = 0.5000` (about 2.50 V from 5.00 V).
   Remove the resistor, reconnect the sensor, and compare logged IAT against a
   trusted reference at ambient and at least one controlled warmer point.
3. Set the supplied 50-4110-style controller to P0 or P1. Power red from its own
   switched 10-18 V / 10 A fused supply and ground black at a clean power/engine
   ground. Never connect black to B3-2/B136-31. Compare white-to-black voltage
   with B136-23-to-B136-31 voltage under normal electrical loads to quantify
   ground offset.
4. Sweep a protected 0-5 V source through the former-MAF input and verify:
   - below 0.50 V: logger AFR fault sentinel (raw 0.0), ready 0.0, EBCS command zero;
   - 0.50..4.50 V: gasoline `AFR = 2*V + 10`, ready 50.0;
   - above 4.50 V: logger AFR fault sentinel (raw 0.0), ready 0.0, EBCS command zero.
5. With the actual controller, record display and white-to-black voltage during
   cold warm-up, warmed free air, and a disconnected sensor. An in-window result
   is not proof of controller health and must not be presented as such.
6. Confirm both patched bank feedback values are identical and both inhibit
   helpers switch together. Do not substitute a 5 V rail directly without
   current limiting and a proven common reference.
7. With wideband input valid, separately move MAP, RPM, and IAT outside each SD
   validity window, below the first 1500-RPM boost breakpoint, and force the
   500 g/s SD fault sentinel. Every case must leave EBCS command at zero.
8. Confirm `Rotational Idle Enable` is OFF before first flash.

## 3. Install logging

Use the complete generated definition:

```text
master_patch/D2WD610H_master_logger.xml
```

Do not select `D2WD610H_master_logger_ecuparams.xml`; it is only the internal
fourteen-parameter fragment. To regenerate the complete file from another normal
logger release without modifying the source file:

```sh
python3 master_patch/install_master_logger.py /path/to/logger.xml
```

Fully exit RomRaider after selecting a different logger definition, then start
it again. E500--E513 and the nine high-resolution stock channels used by the
lean-out test are unconditional in this D2WD610H-only logger and must be
listed in the Data, Graph, and Dashboard parameter panes even before connecting
to the ECU. If they are absent, RomRaider is using another file or a stale
in-memory definition; reselect the exact complete path above and restart.

RomRaider keeps Data, Graph, and Dashboard selections separately. Load
`D2WD610H_idle_diagnostic_profile.xml` to select the complete cold-idle capture
in Data and place the lean-out subset of E500--E513 plus the key stock channels
on Dashboard. It intentionally omits E503--E505 (AVLS and boost-only lean-cut
state) from this stationary test to preserve K-line sample rate. If an old
profile leaves the gauges absent, load this profile or delete the stale profile
and create a new one.

Log at minimum:

- E500 external-wideband AFR (raw lambda remains an alternate conversion);
- E501 raw former-MAF ADC/input voltage;
- E502 external-wideband readiness;
- E506 raw CL/OL flags;
- E507 engine-run counter;
- E508--E513 raw after-start fueling groups/compensations;
- MAP, barometric pressure, RPM, IAT, modeled airflow, calculated load;
- standard P47 Fuel Pump Duty and battery voltage;
- commanded fuel/lambda, short- and long-term correction, CL/OL state;
- ignition timing, feedback knock, fine-learning knock, KCA, IAM;
- AVLS requested state, throttle, injector
  duty/pulse width, and battery voltage;
- purge/repurposed EBCS duty; and
- independently measured fuel pressure and wideband/controller status with a
  common timestamp.

Add E503 for an AVLS/VE transition capture. Add E504 and E505 for positive-
pressure lean-cut commissioning; they are not useful in the stationary
vacuum-only lean-out test.

E500 equal to zero means invalid input. Never treat it as an extremely rich
sample or average it into tuning data.

For a stationary full-speed fuel-pump mode test, edit a copy of the generated
master BIN with the matching ECU definition: set `Fuel Pump Low-Speed Command`
and `Fuel Pump Medium-Speed Command` to `100.0`. The fixed high-mode/PWM-scale
constant remains 100.0 and is intentionally not exposed. Do not edit the stock
root BIN. Capture P47 from before cranking
through at least 45 seconds and measure voltage across both pump terminals,
rail-pressure differential, AFR and current/temperature where practical. The
test leaves the pump-off state intact. Restore the stock 33.3/66.7/100.0 values
after diagnosis unless continuous full-speed operation has been validated.

## 4. First start with no boost route

1. Keep the engine physically unable to enter boost and force open-loop where
   appropriate for controlled commissioning.
2. Validate cranking and hot/cold restart pulse widths before extended running.
3. Compare the controller gauge, ECU lambda, raw ADC voltage, and an independent dyno
   lambda reference. Resolve any offset before changing VE or injector data.
4. Calibrate idle and vacuum VE cells on a load-controlled dyno. Confirm MAP,
   IAT, airflow, load, fuel correction, and injector pulse width are plausible.
5. Validate deceleration, tip-in, heat soak, fan operation, and the fixed
   3200-RPM engage / 3000-RPM release AVLS transition. Confirm E503 changes as
   expected and independently verify physical OSV/lift operation; do not assign
   VE samples from requested state alone.
   A 500 g/s airflow value while running is a fault indication: stop and find
   the invalid SD input rather than tuning around it.

Stop immediately for loss of fuel-pressure differential, lambda leaner than
command, knock, unstable timing/load, sensor invalidity, clipping, severe bank
imbalance evidence, or disagreement between ECU and independent instruments.

## 5. Prove protections without relying on engine overboost

Bench-simulate MAP and wideband inputs, or use an equivalent controlled test,
to show that throttle, invalid-wideband, invalid MAP/RPM/IAT, below-minimum-RPM,
and 500 g/s SD-fault gates command zero duty, 5.5 psi commands zero duty, and
6.5 psi reaches the stock fuel-cut aggregation path. Separately confirm that
the pressure guard revokes closed-loop permission at baro minus 0.5 psi, then
exercise the 50-call delay, eight-sample 13.0-AFR trip, latch persistence, and
-0.5-psi release without relying on live combustion.
Confirm the 6800/6770 limiter behavior. Do not deliberately overboost the
engine just to test the hard cut.

Scope the original purge output unloaded to establish frequency and polarity.
If electronic control is not being commissioned, leave the EBCS electrically
and pneumatically out of the boost path. If it is added later, first prove that
ECU zero duty maps to the valve state that gives minimum boost and resolve
flyback, current, heat, and fail-state behavior before attaching pressure hoses.

With the engine already stable and all fueling checks complete, rotational idle
may be commissioned separately. First log the six/factory-visible final timing
results with the switch OFF. Enable only at a fully warm stationary idle and
confirm the feature exits immediately for throttle, RPM, MAP, speed, or coolant
outside its window. Disable it for any stall tendency, knock/misfire activity,
excess exhaust temperature, or timing result outside the documented bounds.

## 6. Spring-only load testing

Only after the naturally aspirated/vacuum region is stable:

1. Retain zero feed-forward duty, zero Kp, and zero maximum duty ratio.
2. Verify the 45 mm gate really produces approximately 5 psi and cannot creep
   above the hard limit throughout the RPM/load range.
3. Tune VE, commanded lambda, injector data, and timing in small steady-state
   steps using synchronized data and conservative knock limits.
4. Tune low- and high-lift VE separately using E503. Discard transition samples,
   then validate the 3000..3200 hysteresis overlap, transients, restarts, heat
   soak, and altitude.

Do not add electronic duty until spring-only control and every protection have
passed. Any later RomRaider edit creates a new calibration that no longer has
the generated baseline hash and requires a fresh checksum and change audit.
