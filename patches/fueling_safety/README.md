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

The integration can override these component defaults. Current v2 arms at
**+2.5 psi** and releases at **+1.5 psi**, with a **12.8 AFR** threshold. The
release guard accepts negative, zero or positive reset pressure provided it
is strictly below the arm pressure. The former negative-only check prevented
v2 from releasing a latched cut even in vacuum; the September 12 correction
changes this check without changing either integration's pressure calibration.
`tests/test_lean_cut_hysteresis_execution.py` executes the release behavior.

The component reclaims four bytes at `0xFFFFAE9C` (16-bit counter) and four at
`0xFFFFAEA0` (8-bit state) from the bypassed front-A/F processor `0xB8CC`.
Its initializer calls native `0x33964` first, preserving the AVCS current
integrators at `0xFFFFC85C/0xFFFFC860`, then zeros both new slots. Builders
check the front-A/F ownership and preserved AVCS task/code contracts. The
previous rear-O2 identification was wrong; those integrators and their normal
PWM output must remain active. See the
[AVCS dependency repair](../../docs/reference/AVCS_OCV_REPAIR_20260913.md).

The delay values are task-call counts, not milliseconds. Log the new state and
counter and measure the installed AEM sensor's delay before treating the
defaults as validated. This remains a development image requiring controlled
physical validation.
