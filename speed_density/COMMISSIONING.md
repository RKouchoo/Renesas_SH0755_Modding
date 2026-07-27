# MAFless speed-density commissioning

This image is always speed density. There is no switch back to MAF inside the patched ROM. A
plausible but incorrect VE cell can create lean fueling or select too little calculated load, so
first operation must be treated as controlled model validation.

## Before flashing

1. Rebuild and verify the standalone image. Confirm the canonical root ROM still hashes to
   `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
2. Apply the correct Subaru checksum only to a disposable working copy, then independently compare
   it with the deterministic patch output.
3. Fit and validate a standalone post-intercooler IAT sensor on the ECU's original IAT circuit.
   Check the actual car's wiring diagram and measure the circuit; do not infer pins from another
   market or model-year diagram.
4. Pressure-calibrate MAP against a reference at key-on atmospheric pressure, several vacuum
   points, 0 psi gauge, and regulated pressure beyond the intended 5 psi target.
5. Verify injector identity, latency, scaling, base pressure, and fuel-pressure differential.
6. Synchronize the external post-turbo wideband log with ECU RPM, MAP, IAT, airflow, calculated
   load, fueling, and ignition data. Account for downpipe transport delay.
7. Mechanically constrain the first start so it cannot enter boost. Keep the wastegate on its
   5 psi spring and command zero electronic duty.

## First-start sequence

1. Key on without starting. MAP must agree with barometric pressure and IAT must agree with a
   reference. Do not crank if either signal is frozen, implausible, or has an active fault.
2. Start only with immediate lambda, fuel-pressure, MAP, RPM, IAT, and calculated-airflow logging.
3. At exact zero RPM the task should publish zero airflow. A running value pinned near 500 g/s
   means the fixed fail-safe is active: shut down and diagnose the input/calibration path.
4. Validate hot idle, then steady no-load RPM sites. Stop for a discontinuity in lambda, injector
   pulse width, calculated load, or modeled airflow.
5. Validate light-load vacuum cells on a load-controlled dyno. Correct repeatable MAP/RPM model
   error in the VE surface; do not disguise it with injector scaling.
6. Validate IAT correction at stable MAP/RPM using controlled temperature data.
7. Progress through all vacuum cells before atmospheric pressure. Require bounded trims and
   agreement between commanded lambda and the time-aligned external wideband.
8. Enter positive pressure only after fuel-pressure differential, injector duty, ignition,
   knock response, AVLS transition, wastegate behavior, and the 5 psi boost limit have each passed.

## Required high-rate channels

- RPM, absolute MAP, post-intercooler IAT, throttle, modeled airflow, and calculated load;
- commanded fueling, injector pulse width/duty estimate, closed/open-loop state, and trims;
- retained factory front A/F channel plus external post-turbo wideband lambda and validity;
- ignition timing, IAM, feedback knock correction, and fine knock learning;
- AVLS command/state, especially through the 2500–3200 RPM region;
- boost target/duty, fuel-pressure differential, oil pressure, coolant temperature, and battery
  voltage.

Abort immediately for the 500 g/s fail-safe value, invalid/frozen MAP or IAT, an airflow/load
decrease as MAP rises, leaner-than-commanded lambda, lost fuel-pressure differential, injector
saturation, knock correction, unexpected boost, or any unexplained modeled-airflow step. Reflash
a known-good stock-derived image to disable this component; there is no MAF fallback to select.
