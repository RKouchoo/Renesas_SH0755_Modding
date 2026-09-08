# RomRaider logger definitions and profiles

These files are shared by the current v1 and v2 patches. Select
[D2WD610H_master_logger.xml](D2WD610H_master_logger.xml) as the complete logger
definition, then load one capture profile:

| Profile | Purpose |
|---|---|
| [MAP source](D2WD610H_map_source_diagnostic_profile.xml) | Native and processed MAP, raw MAP voltage, barometric estimate, diagnostic flags and engine response. |
| [Idle](D2WD610H_idle_diagnostic_profile.xml) | General idle signals and wideband feedback. |
| [After-start](D2WD610H_afterstart_diagnostic_profile.xml) | Early-running fuel components. |
| [Recovery](D2WD610H_idle_recovery_profile.xml) | Transient fuel correction, base factor and lift state. |
| [Idle air](D2WD610H_idle_air_diagnostic_profile.xml) | Idle RPM request, throttle request, pedal and feedback flags. |

All five generated capture profiles use the native limit of 43 byte addresses
per request. See the [logger reference](../docs/reference/LOGGER.md) for signal
meanings and capture evidence.

[testinglogger.xml](testinglogger.xml) and [testprofile.xml](testprofile.xml)
are retained manual test selections, separate from the five verified captures.
[D2WD610H_master_logger_ecuparams.xml](D2WD610H_master_logger_ecuparams.xml) is
the generator's parameter fragment; select the complete definition in RomRaider.

The existing helper commands remain under `master_patch/`. From the repository
root, regenerate the five capture profiles with:

```sh
python3 -B master_patch/logger_profiles.py
```

Regenerate the complete logger from the upstream v370 definition with:

```sh
python3 -B master_patch/install_master_logger.py \
  /path/to/logger_METRIC_EN_v370.xml \
  logger/D2WD610H_master_logger.xml
```
