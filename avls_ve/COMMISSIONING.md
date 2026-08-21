# AVLS dual-VE commissioning

Do not tune the transition until MAP, IAT, injector characterization, fuel
pressure, commanded lambda, and wideband logging are trustworthy.

1. Rebuild and run `python3 avls_ve/verify_avls_ve.py`; keep the root stock ROM
   unchanged.
2. Confirm the AVLS hardware enters committed mode 3 above 3200 RPM and returns
   from mode 3 below 3000 RPM. Requested state alone is not sufficient.
3. Begin with the identical seeded values in both tables. Tune stable low-lift
   samples against the low table and stable committed-mode-3 samples against the
   high table.
4. Discard samples during the request/commit transition, acceleration enrichment,
   deceleration, closed-loop correction changes, knock response, or unstable
   fuel pressure. The 3000..3200 overlap must be assigned by committed state.
5. Correct a populated cell approximately by
   `new_VE = old_VE * measured_lambda / commanded_lambda`, then use small,
   smoothed changes and repeat the measurement. Confirm the logger's lambda
   convention before applying this relationship.
6. After each side is repeatable, cross 3000/3200 RPM slowly at several loads.
   Resolve any lambda, torque, or timing step before boost testing.

Do not tune around a 500 g/s speed-density fail-safe value. Stop for lean lambda,
knock, loss of differential fuel pressure, unexpected lift state, or sensor
disagreement. A load-controlled dyno and independent knock monitoring remain
the appropriate validation environment.
