# Master-patch commissioning order

> **September 8 corrected development image:** SHA-256
> `48d63cf3b7085afc672dd809cf08f4aef2b1aaae8a880f421e656467b7aaf8f0`,
> checksum `0x1923EC61`, restores `0x3FD8C -> 0xE8C4` stock fan control and
> deletes actual CPC purge duty/modeled flow/fuel subtraction. Electronic boost
> control is removed. Do not run earlier images with the erroneous fan hook,
> including the first-VE ROM. Static checks pass; vehicle behavior and a cure
> for the lean-out have not been demonstrated. See `GHIDRA_AUDIT.md`.

Do not start with a flashed car and a connected turbo control valve. The static
checks in this repository prove composition and code structure, not the wiring,
sensors, fuel system, engine, or tune. Use a disposable ROM copy for every edit
and keep the root stock image unchanged.

The September 8 SD hook hardening and fan/purge correction are code/definition
work, not a demonstrated lean-out repair. Their tests do not prove timing or
physical fueling.
The rebuilt master retains the existing unvalidated second-VE trial; the last
usable log was from the first-VE ROM. Establish the intended calibration
baseline before flashing so a code comparison is not mixed with that VE change.
Any first-VE comparison must be derived from corrected firmware; do not reuse
the old first-VE BIN. VE, injector, timing and AVLS calibrations were not changed
by the fan/purge correction, and no new cam-hold policy was selected.
Leave the newly exposed load-filter response at stock 6% for the initial
comparison; its presence alone is not justification for setting it to 100%.

The retained-sensor correction also makes factory lambda atmospheric
compensation unity and neutralizes O2-voltage-dependent fuel adders, bank
offsets and separate voltage trims in the lambda target. Main lambda feedback,
its ordinary learned fuel corrections and all after-start enrichment remain.
Removing a formerly active positive correction can lower delivered fuel, so do
not assume this repair will richen idle or cure the observed lean-out. Compare external lambda with stock
conditioned bank lambda, and capture final fuel factors and injector duration.
See [the audit](RETAINED_ROUTINE_AUDIT.md) for exact scope and remaining paths.

The later [guard execution pass](GUARD_EXECUTION_AUDIT.md) fixes a stale-ready/
zero-lambda case that could reset lean confirmation. The 12 new instruction
test groups pass, including preserved stock cuts, reset behavior and exact
confirmation counts. They do not measure scheduler timing or validate controller
fault outputs. The current image still needs the intended VE baseline and
physical commissioning checks below before engine/load validation.
The subsequent [primary-fueling pass](PRIMARY_FUEL_EXECUTION_AUDIT.md) executes
the stock target/transition/composer and corrects the test FPU. It confirms
that pressure-forced open loop preserves stock enrichment delays and can still
select zero enrichment at low modeled load. These passing tests do not validate
boost-entry response or the tune; this pass changes no ROM bytes.
The later [injector-cut repair](INJECTOR_CUT_EXECUTION_AUDIT.md) does change
the ROM: both added cuts now publish the native scheduler inhibit word, fixing
the flag-only mismatch in `5fff8b...`. The subsequent
[scheduler repair](INJECTOR_SCHEDULER_EXECUTION_AUDIT.md) protects the complete
update against a higher-priority injector task seeing a temporary clear.
Use the current `48d63c...` artifact. Queued-state, release and lock execution
tests pass; interrupt timing and physical delivery remain unmeasured. A nonzero
logged pulse width may persist for a pulse already handed to the timer after
the global inhibit word becomes FFFF; the logger is not a physical on-time probe.
The IRQ/context follow-up now executes native interrupt returns and task
switching, including nested IRQs and pending-task resumption after both cut
wrappers. All eight groups and the full verifier pass on the unchanged image.
This supports proceeding to controlled bench/idle commissioning once the input
checks and intended VE baseline above are established. It does not validate
real-time deadlines, physical injector delivery or loaded operation.

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
9. In the matching master definition, confirm `Overboost Fuel Cut Enable` is
   ON and no electronic boost enable/duty/target controls are present.
10. Confirm the normal fan wiring is intact and the removed purge plumbing is
    isolated from the manifold. The old fan-output identification must not be
    used to connect an EBCS.

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
   - below 0.50 V: logger AFR fault sentinel (raw 0.0), ready 0.0, feedback inhibited;
   - 0.50..4.50 V: gasoline `AFR = 2*V + 10`, ready 50.0;
   - above 4.50 V: logger AFR fault sentinel (raw 0.0), ready 0.0, feedback inhibited.
5. With the actual controller, record display and white-to-black voltage during
   cold warm-up, warmed free air, and a disconnected sensor. An in-window result
   is not proof of controller health and must not be presented as such.
6. Confirm both patched bank feedback values are identical and both inhibit
   helpers switch together. Do not substitute a 5 V rail directly without
   current limiting and a proven common reference.
7. Separately move MAP, RPM, and IAT outside each SD validity window and check
   the documented SD fault indication. Confirm wideband/SD validity no longer
   overrides the stock radiator-fan command. No electronic boost command exists.
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
in both Data and Dashboard. Every entry includes an exact unit conversion so
older RomRaider builds do not reject or silently ignore it. It includes E503
to prove which AVLS VE surface is active and omits only boost-only lean-cut
state E504/E505. P3/P5 are the immediate bank corrections; P4/P6 additionally
capture learned trims. P38/P92 capture purge and fan commands. Neutral, idle,
and starter switches are also selected for the clutch-stall diagnosis. If an old profile leaves the
gauges absent, load this profile or delete the stale profile and create a new
one. The current profile uses 83 distinct SSM read addresses, below the
84-address request limit. E81/E105 remain defined but are explicitly deselected
because P3/P5 already record both bank corrections. Clear unrelated selections
in Data, Graph and Dashboard first: hidden selections also consume request
addresses. Start recording before cranking and check that the actual CSV
header includes MAP, E60 pulse width, E50 latency, E123 base factor and the
after-start channels. Dashboard display alone does not record a value.

The previous instruction to capture on the installed first-VE ROM is withdrawn
because that firmware also hijacked fan control. Use only a corrected-code
calibration selected for the comparison. The generated second-VE increase is
still an unvalidated trial based on an AFR endpoint that was changing; do not
treat it as the resolved tune. See the reassessment in `GHIDRA_AUDIT.md`.

The focused first-idle profile records:

- E500 external-wideband AFR (raw lambda remains an alternate conversion);
- E501 raw former-MAF ADC/input voltage;
- E502 external-wideband readiness;
- E506 raw CL/OL flags;
- E507 engine-run counter;
- E508--E513 raw after-start fueling groups/compensations;
- MAP, barometric pressure, RPM, IAT, modeled airflow, calculated load;
- standard P47 Fuel Pump Duty and battery voltage;
- E84 primary OL enrichment and E123 composed base fuel factor, displayed as
  estimated AFR; these are neither measured AFR nor the complete injector command;
- both immediate and learned bank corrections, plus CL/OL state;
- total ignition timing, E503 committed AVLS VE state and throttle;
- E60 scheduled pulse without latency, E50 latency and P21 inclusive pulse;
- actual CPC request (P38, expected zero) and radiator-fan request (P92); and
- neutral, idle and starter switches.

Record independently measured fuel pressure and wideband/controller status with
a common timestamp alongside the CSV. The profile cannot measure rail pressure,
actual injector delivery or physical fan motion. Warm feedback, cam-control,
knock and boost validation require separate captures with their own channel
budgets. E504/E505 are for positive-pressure lean-cut commissioning and are not
needed in this stationary vacuum-only test.

E500 equal to zero means invalid input. Never treat it as an extremely rich
sample or average it into tuning data.

For this first corrected-code idle capture, record 5–10 seconds key-on before
cranking, then aim for **60 seconds from engine start** at untouched idle. This
extends beyond the roughly 30-second lean-out window in the earlier runs.
Continue to at most 90 seconds only if lambda, fuel pressure and running remain
stable; reaching full operating temperature or a fan cycle is not the aim of
this first capture. Shut down sooner if the lean trend returns, the rich/rough
running limits below are reached, fuel pressure falls or an input is invalid.
Do not keep a faulting engine running to meet the requested duration. Save the
whole CSV including startup and note which exact BIN and VE calibration ran.

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
4. Revalidate the bounded low-lift idle correction after after-start enrichment
   has fully decayed. Its example site is 1300 RPM/315 mmHg; MAP was not captured
   in the latest usable log, so that pressure is an assumption, not a measured
   idle site. The increase applies through a tapered neighbourhood. Because the
   unchanged stock
   after-start enrichment may have concealed a lean base model, the first
   seconds may now be visibly richer than the prior start. Stop immediately
   below 11 AFR, if AFR stays below 12 after the first ten seconds, if it
   remains below 12 after enrichment should have decayed, if the engine fouls
   or misfires,
   or AFR still trends lean. Confirm MAP, IAT, airflow, load, fuel correction,
   and injector pulse width are plausible before expanding calibration into
   other vacuum cells.
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
to show that the 6.5-psi hard MAP limit reaches the stock fuel-cut aggregation
path. The former electronic-duty gates and 5.5-psi soft-duty cut are retired,
not active protections. Separately confirm that
the pressure guard revokes closed-loop permission at baro minus 0.5 psi, then
exercise the 50-call delay, eight-sample 13.0-AFR trip, latch persistence, and
-0.5-psi release without relying on live combustion.
Confirm the 6800/6770 limiter behavior. Do not deliberately overboost the
engine just to test the hard cut.

Verify real fan response to the restored stock command and confirm the actual
CPC request remains zero. Logger P92 reports a command, not proof of fan
motion or electrical output. Leave an EBCS electrically and pneumatically out
of the boost path. A future electronic controller requires a separately
verified hardware/output design; no RomRaider switch can restore it here.

With the engine already stable and all fueling checks complete, rotational idle
may be commissioned separately. First log the six/factory-visible final timing
results with the switch OFF. Enable only at a fully warm stationary idle and
confirm the feature exits immediately for throttle, RPM, MAP, speed, or coolant
outside its window. Disable it for any stall tendency, knock/misfire activity,
excess exhaust temperature, or timing result outside the documented bounds.

## 6. Spring-only load testing

Only after the naturally aspirated/vacuum region is stable:

1. Retain direct mechanical wastegate control; no electronic duty is available.
2. Verify the 45 mm gate really produces approximately 5 psi and cannot creep
   above the hard limit throughout the RPM/load range.
3. Tune VE, commanded lambda, injector data, and timing in small steady-state
   steps using synchronized data and conservative knock limits.
4. Tune low- and high-lift VE separately using E503. Discard transition samples,
   then validate the 3000..3200 hysteresis overlap, transients, restarts, heat
   soak, and altitude.

Electronic boost control is not implemented in this image. Any later
RomRaider edit creates a new calibration that no longer has
the generated baseline hash and requires a fresh checksum and change audit.
