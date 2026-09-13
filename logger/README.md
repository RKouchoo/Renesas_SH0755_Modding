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
| [AVLS and fuel cut](D2WD610H_avls_cut_diagnostic_profile.xml) | Both banks' software lift modes, OSV duty/current and injector inhibition, with IAM, knock, MAP and baro. Use for the September 12 transition investigation. |
| [Road tuning](D2WD610H_road_tuning_profile.xml) | IAM, feedback/learned knock, ignition timing, native MAP, load, wideband and fuel response, with speed and driver inputs. |
| [MAP source](D2WD610H_map_source_diagnostic_profile.xml) | Native and processed MAP, raw MAP voltage, barometric estimate, diagnostic flags and engine response. |
| [Idle](D2WD610H_idle_diagnostic_profile.xml) | General idle signals and wideband feedback. |
| [After-start](D2WD610H_afterstart_diagnostic_profile.xml) | Early-running fuel components. |
| [Recovery](D2WD610H_idle_recovery_profile.xml) | Pedal, transient fuel correction, base factor and lift state. |
| [Idle air](D2WD610H_idle_air_diagnostic_profile.xml) | Idle RPM request, throttle request, pedal and feedback flags. |

All seven generated capture profiles use the native limit of 43 byte addresses
per request. See the [logger reference](../docs/reference/LOGGER.md) for signal
meanings and capture evidence.

Recovery keeps 19 channels, including the direct four-byte pedal signal. It
leaves injector latency and the three extra knock channels unselected to fit
the request budget. Selecting all four as well produces a 184-byte request
that the ECU rejects, reported by RomRaider as an invalid header. Reload the
profile after changing the file; replace channels instead of adding to this
full selection. The generator now checks the byte budget before writing.

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
are retained manual test selections, separate from the seven verified captures.
[D2WD610H_master_logger_ecuparams.xml](D2WD610H_master_logger_ecuparams.xml) is
the generator's parameter fragment; select the complete definition in RomRaider.

The existing helper commands remain under `master_patch/`. From the repository
root, regenerate the seven capture profiles with:

```sh
python3 -B master_patch/logger_profiles.py
```

Regenerate the complete logger from the upstream v370 definition with:

```sh
python3 -B master_patch/install_master_logger.py \
  /path/to/logger_METRIC_EN_v370.xml \
  logger/D2WD610H_master_logger.xml
```
