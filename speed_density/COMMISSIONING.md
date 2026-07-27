# Speed-density commissioning

This component can command fueling and select load-dependent timing indirectly through modeled
airflow. A plausible-looking but incorrect VE value can therefore create a lean mixture or an
incorrect load estimate. Treat first enable as a sensor/model validation exercise, not a tuning
pull.

## Before enabling

1. Build and verify the standalone image. Confirm the root `2005 BLE MT.bin` SHA-256 remains
   `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
2. Apply a valid Subaru checksum to a disposable working copy and re-run an independent binary
   comparison.
3. Pressure-calibrate MAP against a reference at key-on atmospheric pressure, several vacuum
   points, 0 psi gauge, and regulated positive pressure beyond the intended 5 psi target.
4. Put IAT after the intercooler and validate its displayed temperature against a reference.
5. Keep the MAF installed, correctly scaled, and logged. It is the commissioning reference and
   the wrapper's fallback when an SD gate fails.
6. Synchronize the external post-turbo wideband log with ECU RPM/MAP/IAT/airflow/load/fueling
   data. Verify wideband validity status and transport delay.

## Enable sequence

1. Start and fully warm the engine with the switch OFF. Save a baseline log.
2. Enable the component only in a checksum-corrected working ROM.
3. First start with wastegate control disabled and no opportunity to enter boost.
4. At idle, compare modeled airflow with the retained MAF. Stop for a step change large enough
   to disturb lambda, idle control, or load.
5. Validate steady no-load RPM sites, then light-load cells on a load-controlled dyno. Adjust the
   VE surface, not injector scaling, to correct a repeatable MAP/RPM airflow-model error.
6. Validate IAT correction at stable MAP/RPM using controlled temperature data. Do not use a
   heat-soaked stationary sensor sample to reshape the entire curve.
7. Progress through vacuum cells before approaching atmospheric pressure. Verify closed-loop
   trims remain bounded and the external wideband agrees after transport-delay alignment.
8. Enter positive pressure only after the 5 psi boost hardware, fuel-pressure differential,
   injector duty, ignition, knock monitoring, and mechanical wastegate fallback have separately
   passed their commissioning checks.

## Required high-rate channels

- RPM, absolute MAP, IAT, throttle, speed-density/MAF g/s, retained raw MAF voltage if available;
- calculated engine load and every load signal used by the active definition;
- commanded fueling, injector pulse width/duty estimate, closed/open-loop state, trims;
- retained factory front A/F channel plus external post-turbo wideband lambda and validity;
- ignition timing, IAM, feedback knock correction, fine knock learning;
- AVLS command/state and the 2500–3200 RPM transition;
- fuel-pressure differential, oil pressure, coolant temperature, battery voltage.

Abort for invalid or frozen MAP/IAT, a modeled-airflow discontinuity, unexpected load decrease
as MAP rises, leaner-than-commanded lambda, loss of fuel-pressure differential, injector
saturation, knock correction, boost above the intended limit, or any unexplained difference
between retained MAF and modeled airflow. Revert the switch to OFF and diagnose the model/sensor
path; do not tune through an invalid gate.
