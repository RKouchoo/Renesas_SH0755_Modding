# RomRaider logger definitions and profiles

These files are shared by the current v1 and v2 patches. Select
[D2WD610H_master_logger.xml](D2WD610H_master_logger.xml) as the complete logger
definition, then load one capture profile:

The current rolling BINs require this updated complete definition: E500 now
reads `FFAE8C`, E504 reads `FFAEA0`, and E505 reads `FFAE9C`. Older definitions
read native cam-control state at those IDs after the AVCS repair. Channel IDs,
conversions and profile selections are unchanged. Preserve historical
definition/image pairings when replaying old captures; see the
[RAM migration](../docs/reference/AVCS_OCV_REPAIR_20260913.md).

| Profile | Purpose |
|---|---|
| [Cut trace](D2WD610H_cut_trace_profile.xml) | Next capture for the persisting loaded cut: separate spark/injector gates, synchronization/timeout and native missed-task counters, retaining IAM, knock, AFR and driver context. Existing repaired v2 requires no reflash. |
| [AVCS repair](D2WD610H_avcs_repair_profile.xml) | Both cam angles, restored normal OCV output duty and measured current, with IAM, knock, AFR, MAP and injector/lean-cut state. Use with the repaired rolling v2 and the updated complete definition. |
| [AVLS and fuel cut](D2WD610H_avls_cut_diagnostic_profile.xml) | Both banks' software lift modes, OSV duty/current and injector inhibition, with IAM, knock, MAP and baro. Use for the September 12 transition investigation. |
| [Road tuning](D2WD610H_road_tuning_profile.xml) | IAM, feedback/learned knock, ignition timing, native MAP, load, wideband and fuel response, with speed and driver inputs. |
| [MAP source](D2WD610H_map_source_diagnostic_profile.xml) | Native and processed MAP, raw MAP voltage, barometric estimate, diagnostic flags and engine response. |
| [Idle](D2WD610H_idle_diagnostic_profile.xml) | General idle signals and wideband feedback. |
| [After-start](D2WD610H_afterstart_diagnostic_profile.xml) | Early-running fuel components. |
| [Recovery](D2WD610H_idle_recovery_profile.xml) | Pedal, transient fuel correction, base factor and lift state. |
| [Idle air](D2WD610H_idle_air_diagnostic_profile.xml) | Idle RPM request, throttle request, pedal and feedback flags. |

All nine generated capture profiles use the native limit of 43 byte addresses
per request. See the [logger reference](../docs/reference/LOGGER.md) for signal
meanings and capture evidence.

Recovery keeps 19 channels, including the direct four-byte pedal signal. It
leaves injector latency and the three extra knock channels unselected to fit
the request budget. Selecting all four as well produces a 184-byte request
that the ECU rejects, reported by RomRaider as an invalid header. Reload the
profile after changing the file; replace channels instead of adding to this
full selection. The generator now checks the byte budget before writing.

## Loaded-cut trace

The AVCS repair did not cure the loaded cut. The last capture showed B744=0
during high demand, but did not record the separate spark mask, synchronization
or missed scheduling. Use [D2WD610H_cut_trace_profile.xml](D2WD610H_cut_trace_profile.xml)
with the newly updated [complete definition](D2WD610H_master_logger.xml).
Reload the definition or restart RomRaider, then **File → Load Profile**.
New E530–E537 read existing native RAM; no ROM or calibration change is needed.

| Signals | IDs | Requested bytes |
|---|---|---:|
| Spark inhibit, ignition mode and auxiliary spark mask | E530–E532 | 5 |
| Crank synchronization, runtime flags and engine timeout | E533, E534, E537 | 3 |
| Missed output-task and airflow-task activations | E535, E536 | 2 |
| Injector inhibit, added lean-cut state and committed lift mode | E525, E504, E503 | 4 |
| IAM and feedback/fine knock correction | E31, E39, E41 | 12 |
| Wideband AFR and native MAP | E500, E518 | 8 |
| RPM, speed, timing, pedal, throttle, pulse width, coolant and battery | P8, P9, P10, P30, P13, P21, P2, P17 | 9 |
| **24 channels** | | **43** |

Begin logging before engine start so the native loss counters have a baseline.
The useful recording includes pre-event running, the onset and release of
the cut, and several seconds afterward. A prolonged hold against the cut
adds no useful requirement. Keep test connectors disconnected and the OBD
logging cable connected. Preserve the supplied selections; adding channels
can exceed the ECU's receive limit.

Interpretation is conditional:

- E530 is the independent C0DC spark mask. E531=0 also inhibits every spark
  slot even if E530=0. E532=4032 (`0FC0`) is the normal secondary-slot mask,
  **not** an all-coil cut. The effective mask is
  `E532 | (E531 != 0 ? E530 : 65535)`; read timing relationships cautiously.
- E533 normally reports synchronized state1 while running. E537 reports the
  selected timeout, with E534 bit128 its later stopped-state publication.
  Startup/shutdown values must be separated from an in-event transition.
- E535/E536 are native saturating counters. An increase records a missed
  task activation; it does not by itself establish the cause or a missed
  electrical pulse. At255 they cannot show additional losses.

The counters can expose losses between samples. Other flags are instantaneous;
a clean roughly104ms trace cannot exclude short interruptions. This profile
does not measure physical injector/coil pulses or fuel pressure. Persistent
normal states would narrow the next investigation but would not by themselves
prove a hardware fault. See the [channel evidence](../docs/reference/CUT_TRACE_LOGGER_20260913.md).

## AVCS repair validation

Select the updated [complete definition](D2WD610H_master_logger.xml), then
load [D2WD610H_avcs_repair_profile.xml](D2WD610H_avcs_repair_profile.xml) through
RomRaider's **File → Load Profile**. Reload the definition or restart RomRaider
if E528/E529 are absent. Load one profile at a time and keep the selection as
provided: it uses all 43 available byte addresses.

| AVCS signals | Parameter IDs | Requested bytes |
|---|---|---:|
| Actual cam angle and ADC-derived OCV current for both banks | P48, P49, P52, P53 | 4 |
| Normal output duty from the restored feedback stage | E528, E529 | 8 |
| IAM and feedback/learned knock corrections | E31, E39, E41 | 12 |
| Wideband AFR and native MAP | E500, E518 | 8 |
| Injector-inhibit word and added lean-cut state | E525, E504 | 3 |
| RPM, speed, timing, pedal, plate, gross pulse width and coolant | P8, P9, P10, P30, P13, P21, P2 | 8 |
| **Total: 20 channels** | | **43** |

Standard P50/P51 read upstream duty demand `C914/C918`. E528/E529 instead
read `C91C/C920`, after restored `34BE4` applies the current integrator and
enable/fault gates. Later diagnostic overrides and the hardware PWM remain
separate; these channels report the normal output command. P52/P53 read native
`B098/B09C` through `DFB4`, at 32 mA per byte count. P48/P49 read native
`C8C8/C8CC`, at one degree per byte count. Right/Left labels correspond to
software bank indices 0/1; harness assignment is not independently established.

Native callbacks and capability bits are verified. The complete selected
request is 136 bytes and both continuous 49-byte responses pass the native
SSM tests, including distinct demand/output values. This is an offline
protocol check, not a live connection or proof of hydraulic cam response.
The profile omits cam targets, load, IAT and AVLS mode to retain knock and
cut context; it cannot alone prove target tracking. It reads existing RAM
and requires no additional ROM change.

## AVLS and cut diagnosis

Load the updated complete definition above, then
[D2WD610H_avls_cut_diagnostic_profile.xml](D2WD610H_avls_cut_diagnostic_profile.xml).
The complete definition adds E525–E527; an older copy will not contain these
channels. E524's existing pedal address/scaling is preserved and is now part
of the canonical fragment, so regenerating the definition retains it.

| AVLS/cut signals | Parameter IDs | Requested bytes |
|---|---|---:|
| IAM and feedback/learned knock corrections | E31, E39, E41 | 12 |
| Wideband AFR, native MAP and selected barometric estimate | E500, E518, E520 | 12 |
| Committed mode and two bank software copies | E503, E526, E527 | 3 |
| OSV duty and ADC-derived current for both banks | P123–P126 | 4 |
| Lean-cut state and native injector-inhibit word | E504, E525 | 3 |
| RPM, speed, final timing, pedal, plate and gross pulse width | P8, P9, P10, P30, P13, P21 | 7 |
| Coolant and converted oil temperatures | P2, P122 | 2 |
| **Total: 23 channels** | | **43** |

P123/P125 correspond to software bank index 0 (upstream label Right), and
P124/P126 to index 1 (Left). Their native callbacks and SSM capability bits
were checked in the ROM. The current channels measure an electrical response;
they do not confirm that either bank completed its hydraulic lift change.
Brief bank-mode differences can result from phase-qualified updates and
non-atomic logging. Diagnose sustained disagreement in context.

E504 = 3 identifies the added lean-cut latch. E525 = 65535 means global
injector inhibition; other masks can inhibit individual channels. Neither
P21's calculated pulse nor a lean wideband reading alone proves the cause.
The [September 12 review](../docs/reference/V2_AVLS_MISFIRE_20260912.md)
sets out the stationary-first check and decision points.

This profile only reads existing channels and needs no additional ROM changes.
The rolling v2 BIN separately contains the lean-cut release correction.

The [13:16 neutral capture](../docs/reference/V2_AVLS_NEUTRAL_20260912.md)
stayed in low lift and identified erroneous stationary oil thresholds. The
current rolling v2 restores those thresholds to stock 15 C. The same profile
captured two high-lift entries in the 13:37 follow-up, with both bank currents
responding and no pedal-applied injector inhibition. No profile or definition
change was needed. It omits load, IAT, fuel factor and CL/OL status; use the
existing road-tuning selection below when investigating the measured richening.

## Road tuning

The road-tuning profile selects 18 channels on Data and Dashboard. Load
[D2WD610H_road_tuning_profile.xml](D2WD610H_road_tuning_profile.xml) through
RomRaider's **File → Load Profile** with the complete master logger definition
above. IAM and the knock channels become available when the ECU is identified.

| Road signals | Parameter IDs | Requested bytes |
|---|---|---:|
| IAM, feedback knock correction, fine learning knock correction | E31, E39, E41 | 12 |
| Load, native SD MAP in kPa absolute, wideband AFR | E32, E518, E500 | 12 |
| Final fueling factor, signed transient fuel correction | E123, E511 | 8 |
| RPM, vehicle speed, ignition timing | P8, P9, P10 | 4 |
| Pedal, throttle opening, coolant and intake temperatures | P30, P13, P2, P11 | 4 |
| Injector pulse width, CL/OL status, committed AVLS mode | P21, E33, E503 | 3 |
| **Total: 18 channels** | | **43** |

P21 includes injector latency and has 0.256-ms resolution; it differs from
E60's net pulse width. E123 is the composed fuel-air factor, including
corrections, rather than a standalone commanded AFR target. E511 helps
identify transient samples. These choices keep IAM and both knock corrections
in the same capture without exceeding the 136-byte request size. The road
profile continues to use its existing channel definitions.

[testinglogger.xml](testinglogger.xml) and [testprofile.xml](testprofile.xml)
are retained manual test selections, separate from the nine generated captures.
[D2WD610H_master_logger_ecuparams.xml](D2WD610H_master_logger_ecuparams.xml) is
the generator's parameter fragment; select the complete definition in RomRaider.

The existing helper commands remain under `master_patch/`. From the repository
root, regenerate the nine capture profiles with:

```sh
python3 -B master_patch/logger_profiles.py
```

Regenerate the complete logger from the upstream v370 definition with:

```sh
python3 -B master_patch/install_master_logger.py \
  /path/to/logger_METRIC_EN_v370.xml \
  logger/D2WD610H_master_logger.xml
```
