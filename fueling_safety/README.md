# Fueling safety component

This master-only firmware component adds two independently switchable guards:

- **Pressure-based closed-loop to open-loop failsafe:** the stock primary
  fueling target task runs unchanged, then the wrapper clears only the verified
  closed-loop-permission bit when MAP is at or above barometric pressure minus
  the calibrated margin. The default 0.5 psi margin requests open loop before
  positive boost even if the normal load/RPM transition is late.
- **Lean fuel cut:** above 0.5 psi gauge pressure, wait 50 periodic task calls
  for the post-turbo sensor transport delay, then require eight consecutive
  invalid/not-ready or leaner-than-13.0-AFR samples before setting the stock
  rev-limiter fuel-cut flag. The decision latches and ignores AFR after fuel is
  cut; it releases only below -0.5 psi gauge pressure.

The lean wrapper first calls the existing composed stock-rev-limit and hard-
overboost wrapper. It can add a cut but cannot suppress either existing cut.
Both protections default on and have exact-`01` RomRaider enable switches.

The component reclaims `0xFFFFC85C` (counter) and `0xFFFFC860` (state) from the
deleted rear-O2 response integrator. Every traced runtime rear-O2 task is
bypassed by the required master wideband component. Because the stock startup
task writes float 1.0 rather than zero, this component also repoints it to an
explicit integer-zero initializer. Do not install this component without those guards.

The delay values are task-call counts, not milliseconds. Log the new state and
counter and measure the installed AEM sensor's delay before treating the
defaults as validated. This remains a development image requiring controlled
physical validation.
