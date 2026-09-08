# The patch's story and how it works

[Reference home](README.md) · [Current image differences](IMAGES.md)

## From factory ECU to a MAFless turbo build

The starting image is the 512-KiB D2WD610H ROM for an ADM 2005 Liberty 3.0R
manual. The project keeps the factory scheduler, DBW, injector scheduling,
AVCS/AVLS and most fuel/ignition control, adding small routines in erased flash
and changing specific call literals and calibrations.

Early work identified table interpolation, the six timing maps and AVLS
switching. Separate boost, single-front-A/F and rotational-idle components
followed. The timing investigation established that A/D and C/F are AVCS
tracking endpoints selected by lift state; the blend variable is not IAM.
The older single-front-A/F component mirrored one factory sensor. It is a
different sensor architecture from the current external-wideband master.

The MAFless integration supplies modeled air mass at the factory airflow
publication point. `172A4` still performs downstream load conditioning. Its
helper pointer at `1743C` calls `7E18C`; the helper returns airflow in FR0,
and the retained caller publishes `B420`. The helper also makes
`B448/B458/B45C` agree with modeled airflow so retained state does not come
from an obsolete MAF producer on the next cycle.

The model combines absolute MAP, displacement/VE, RPM and an IAT density
factor. Native table lookups choose the low- or high-lift VE surface using
**committed** `CD86`, with mode 3 selecting high lift. Requested `CD87` is
not substituted for committed state. Temperature density is tabulated;
the emitted SD arithmetic does not divide by temperature.

## Corrections that changed the architecture

The first proposed boost actuator used a misidentified output. The
`3FC0A -> CD54 -> E8C4` path is radiator-fan control. An EBCS-OFF switch
did not restore that old hook to stock. The repair restored `3FD8C -> E8C4`,
retired the actuator and guard bodies, and retained the independent
hard-overboost cut for mechanical wastegate control. Actual CPC purge has a
separate `1BAF0 -> B182` request path and `23054` bank fuel subtraction
publisher. Both are explicitly zeroed in the current master. See commit
`03eb868` and the [original trace](../../master_patch/GHIDRA_AUDIT.md).

Repurposing the former MAF ADC for a wideband required more than replacing
one sensor reader. `AB06` still receives hardware samples. The patch produces
the two bank lambda values and readiness, while retained feedback code
continues to consume them. Later passes neutralized factory atmospheric
lambda correction, selected old-voltage fuel adders, and two legacy-voltage
trim contributions to lambda targets. Other learning, transport-delay and
diagnostic paths still exist.

The safety trace then found separate cut defects. Invalid zero lambda could
reset lean confirmation despite stale readiness; the guard now requires
positive lambda. Added cuts also had to publish native `B744` injector
inhibition, not only `BF6C` bit 7. Finally, the complete native-plus-added
decision needed the `3AF4/3B08` scheduler lock because the injector phase task
can preempt the cut task. Negative controls reproduce the failure when the
publication or lock is removed.

## The idle and throttle-recovery investigation

September 7 and September 8 captures showed lean running and near-stalls after
throttle blips. Oversized SSM requests and a local RomRaider queue/reload bug
initially obscured the evidence. Complete later captures were tied to their
actual flashed image using saved flash CRCs, not filenames or timestamps alone.
The user's gauge followed logged AFR; the final shutdown in the 14:13 run
was intentional.

Tracing corrected `B874` from an after-start-only label to **signed transient
load-change fuel correction**. It remains active in synchronized running and
updates every 120 crank degrees on the traced path. Its slow falling-load
history can sustain negative correction after airflow/load falls. Replays
using logged `B438` reproduce much of logged `B874`, but do not model
combustion, wall-film mass or the complete air-control response.

The ten-cell idle-VE plateau improved settled fueling in its recorded test but
did not remove the near-stall. Pedal identification was corrected to `B46C`;
SD does not use that signal. Idle timing, DBW requests, feedback eligibility,
throttle-link status and override paths were then traced. Those checks explain
available paths and show that normal idle air survives zero pedal; they do not
establish the unlogged fault/actuator state of the car.

Two MAP hypotheses also needed separation. Old E51 logs contain processed
`B2A0`, whereas SD consumes ADC-derived `ABC4`. Processed MAP can be substituted
from load, and the ECU's barometric channel is normally an estimate. Neither
is independent evidence of a 33.77-kPa ADC-pressure floor. The full native ADC
sweep found no such floor, so no arbitrary intercept reduction was made.

A real boundary inconsistency was repaired: accepted ADC codes could produce
pressure below SD's old 100-mmHg validity minimum. Current `7DD10` holds the
native converter's accepted lower result, 78.6149597 mmHg, about 10.48113 kPa.
This is a validation-boundary repair, not a change to sensor transfer or proof
that the 500-g/s fallback caused a capture. Commit `404bed5` carries the main
integration; `2d95301` carries the corresponding v2 integration.

## Main, v2 and experiments

The rolling master incorporates the boundary and idle-VE repair. Its DBW and
dashpot calibration remain stock. The user's independent dashpot BIN is
preserved only for matching historical captures; it was not integrated.

V2 arrived in `536d29f`, with timing, tip-in pressure compensation, VE,
transient-history and air-decay changes. It now shares the lower SD bound,
but retains the MAF-fault load substitution that main bypasses. Its existing
verifier does not exercise that branch. The [image comparison](IMAGES.md)
records these differences without silently making v2 equivalent to main.

FPU reuse and sensor-fault/injector-inhibit experiments remain memory-only
prototypes. They are not newly generated flash candidates. The project uses
the rolling repository and pinned historical images to reproduce regressions.
