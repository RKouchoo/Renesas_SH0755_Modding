# Signals and native routines

[Reference home](README.md) · [All address claims](ADDRESS_INDEX.md)

All abbreviated RAM addresses below have prefix `FFFF`. ROM routine addresses
are zero-padded to eight digits, for example `7A14` becomes `00007A14`.
Float means big-endian single precision in memory, with
SH-2E arithmetic at runtime. An array range includes all elements at its stated
stride; individual elements may lack direct Ghidra xrefs.

## Air, pressure and driver inputs

| RAM | Type / units | Producer and meaning | Important consumers / limits |
|---|---|---|---|
| `AB04` | u16 ADC word | Hardware MAP copy, `6FF2` at `7060` | `7A14`; E519 displays raw word or volts. |
| `ABC8` | u16 filtered ADC word | `7A14`, through integer filter `25CC` | Word reads at `7A28/7A3E`; classifier `7A56`. Not a float pressure. |
| `ABC4` | float mmHg absolute | `7A14`, affine transfer using `72810/72814` | SD input; pressure guards; E518. |
| `B2A0` | float mmHg absolute | Native pressure history/substitution path | E51; stock cranking/load/pressure consumers. Not the SD input. |
| `8E04` | float mmHg absolute | Protected stored barometric estimate, `47DCC` | Selected when `737D9=0`. |
| `B3A8` | float mmHg absolute | Alternate conditioned pressure-sensor path, `16ACC` | Not selected by current `737D9=0` configuration. |
| `CFBC` | float mmHg absolute | `47DB2`, selected atmospheric estimate | Guards, compensation and E520. P24 uses its own getter, currently reading `8E04`; neither is an independent sensor reference. |
| `D26C` | u8 flags | Diagnostic/fallback state | Mask 10 affects processed MAP and barometric estimate. |
| `D26F` | u8 flags | Diagnostic/fallback state | Mask 40 feeds `65168`; both current builds bypass its load-task use. |
| `CFD0` | u8 flags | Barometric sample/learning eligibility | `47DCC` prioritizes masks 80, 40 and 20 after D26C/10. |
| `B544` | float RPM | Retained engine-speed state | SD takes the caller's already-saved FR15 value, avoiding a second epoch. Standard P8 SSM callbacks `3164A/31662` also read B544 for bytes 0E/0F; native diagnostic cut `253A8` uses this state. |
| `B3AC` | float degrees C | Conditioned coolant temperature, `16B04`; initialization also writes at `16C9C` | Fuel, idle and thermal consumers. `16CA4` initializes protected records, not this signal. |
| `B3B8` | float degrees C | Conditioned IAT, `16D1C` | SD density lookup; it is not a purge enable threshold. |
| `B538` | float km/h | Selected vehicle speed from `1A2A2`, normally B53C | Diagnostic/configuration gates can substitute 0 or 10; standard P7 logs B53C before this selection. |
| `AB08/AB0A` | u16 ADC words | Independent accelerator-pedal pair | `C5C8` pair processing; separate from wideband AB06. |
| `B4C8 -> B46C` | float percent | Conditioned pedal then snapshot, `18A68/18AEA` | P30, AVLS and idle-air release qualification. Not throttle blade opening. |
| `B314` | float throttle opening | `14DCC` processed throttle position | Throttle/load and CL/OL gates; distinguish native angle from displayed percent. |
| `B2BC` | u8 flags | Debounced throttle/idle state | Bit 1 is recognized idle, getter `15192`; E516. |
| `B51E` | u8 input flags | `193D0`; bit 80 is active-low raw AAE8/0040 test connector | `19BE2` returns that bit as boolean; standard S2 is SSM 61 bit 5. Bit 10 is the separate ignition-on input. |
| `B28C` | u8 ROM configuration copy | `148E4` copies byte `737C9` (current value 0) | Getter `148EE` reads bit 80; this is not the physical test connector. |

The separate native diagnostic cut `253A8` consumes `D273/02`. RPM hysteresis
at `764C4/C8` sets `BF93/80` at 3000 and releases below 2500; with that request
active, `BF90=FE` yields injector inhibit `B744=003F` (all six channels).
Other branches of the same selector can remain active below 2500 RPM.
`30B26` reads received `C6F7/40` directly; `2564C` classifies RPM and pedal
`B46C` into no cut, three-channel `0015` or all-six `003F` when a diagnostic
request qualifies it. `6508E` reads the distinct `D26F/20` P0519 status,
not the MAF-load `D26F/40` bit. These are verified fault-response mechanisms,
not observed vehicle states; see the [limp follow-up](V2_AVLS_MISFIRE_20260912.md#follow-up-other-factory-limp-responses-remain-possible).
`64874` derives the request from local/received diagnostics. These are traced
native states, not new patch RAM allocations or observed faults in the latest
driving log. See the [execution evidence and limits](V2_AVLS_MISFIRE_20260912.md#all-cylinder-cut-test-connector-and-empty-dtc-scan).

`7A14` converts ADC to volts using `5/65536`, then applies the image's
pressure offset/slope. Native storage is mmHg. Displaying kPa requires a
conversion; a renamed XML unit does not change the stored value.

`47DCC` can sample ABC4, update from B2A0 plus pressure-loss compensation,
increment or hold the estimate, then clamp it to 570–770 mmHg. That clamp
does not create a floor in ABC4. Moving SD to B2A0 risks a load-to-pressure-to-
load dependency because a fault path derives B2A0 from load.

## Airflow, load and transient fuel

| RAM | Type / units | Producer and contract |
|---|---|---|
| `B420` | float g/s | Final retained airflow publication after helper `1743C`. |
| `B448/B458/B45C` | float airflow state | Main SD mirrors its output into these retained MAF-history locations. |
| `B424` | float filtered airflow | Retained slow filter; not a second physical sensor. |
| `B428` | float g/rev | Raw `B420 * 60 / RPM`, bounded by native load logic. |
| `B42C/B438` | float g/rev | Normally 6%-per-update conditioning; B438 is consumed by fuel, AVCS and timing. |
| `B430/B43C/B440` | float load-related state | Compensation, delta and retained history; use the complete routine for branch-specific meaning. |
| `B444` | u8 flags | Retained load/filter branch state; bit 20 can select hold/bypass behavior under separate gates. |
| `B82C` | float microseconds | Base injector duration from load and flow scalar, `1E0C8`. |
| `B874` | float signed fraction | `1E7E8` transient load-change correction, added by `1DD04`; E511. |
| `B878/B87C` | float load / load difference | Slowly followed load and current-minus-followed load. |
| `B880` | float load difference | Fast difference versus the three-updates-old sample, with limits/deadband. |
| `B884/B888/B890` | floats | Fast term, slow term and startup gain used in B874 composition. |
| `B8B8–B8C4` | 4 floats | Four-sample load history; stride 4. |
| `B7DC` | float factor | E123: bank-0 composed additive fueling factor from `1DD04`, including primary and B874 transient terms. Separate multiplicative bank corrections and hot-IAT scaling are downstream; this is not a measured CL trim. |
| `B688` | u16 counter | Engine-run counter, `1A838`; logger time conversion assumes the documented task period. |

`73968=0.06` filters conditioned load. `76050=0.01` in main, `0.08` in v2,
filters **falling transient history**. `76030=0.04` is the slow-negative gain.
They are different quantities. Changing one can alter both base load and its
transient derivative, so a faster filter is not automatically more fueling.

`B874` is not a measured wall-film mass. Its signed arithmetic explains a
software correction; the physical reason the modified engine needs different
transient behavior remains unproven. Reapplying `1+B874` to an already-composed
fuel factor double-counts the correction. Conversely, B7DC alone does not
include every multiplier affecting injector duration; see the independently
varied composer cases in `tests/test_primary_fueling_execution.py`.

## Wideband and retained fuel control

E33 reads second-bank fuel-system status `DA4E` with conversion `x+6`.
Updater `4EF96` can retain raw 1 (displayed 7) after warm-up until that bank's
first CL entry. The generic “insufficient ECT” label is therefore not a
direct coolant-temperature verdict. Front-sensor retirement alone does not
establish permanent OL: native feedback consumers remain. See the
[September 12 warm fueling review](V2_AVLS_NEUTRAL_20260912.md).

| RAM | Stock meaning | Main/v2 meaning and evidence |
|---|---|---|
| `AB06`, u16 | MAF raw ADC | External-wideband analog input; hardware sampling remains. |
| `AE60/AE64`, floats | Front-bank processed sensor values | Same synthetic lambda in both banks when valid. |
| `AE68/AE6C`, floats | Pump-current-like values | Zero placeholders. |
| `AE70/AE74`, floats | Front-sensor readiness | 50 valid / 0 invalid; inhibit helper requires greater than 35. |
| `B098/B09C`, floats | Rear O2 voltage results | External-wideband logger mirrors; 0 is a fault sentinel, not lambda zero. |
| `B4E8/B4EC`, floats | Conditioned front feedback | Retained conditioning follows synthetic bank lambda. |
| `ABCC/ABD0`, floats | Legacy front-O2 voltages | Still produced from AB22/AB0E; distinct from wideband. |
| `BC64/BC68`, floats | Voltage snapshots | Retained `1F0D8` path. |
| `BD20/BD24`, floats | Filtered legacy voltage | Retained `219C6` path. |
| `BD04/BD08`, floats | Voltage-loop trims | Still exist, but their two target-composer reads are replaced at `202CC/202D0`. |
| `B900/B904`, floats | Legacy-voltage target offsets | Both selectable values are zero in current calibration. |
| `D114/D118`, floats | Auxiliary O2-dependent fuel adders | `49B20` now publishes zero through its zeroed constants. |
| `B8F4/B8F8`, floats | Bank feedback targets | Produced by `202B8`; main lambda control remains. |
| `BE60/BE64`, floats | Bank purge subtractions | Independently forced to zero by patched `23054`. |
| `C85C`, u16; `C860`, u8 | Rear-response state storage | Reclaimed lean confirmation counter/state after runtime tasks are bypassed and initializer replaced. |

`BE38` is the CL/OL flag byte. Bits 40 and 20 reflect threshold state;
bit 80 permits CL in the primary target path. `22454` produces selected/ramped
primary enrichment through `BE20/BE24/BE00`, `BDFC/BE04`, then `BDF8`.
The pressure wrapper runs `22454` first and may clear bit 80 afterward. It
does not synthesize immediate enrichment or bypass every native delay.

## Ignition, AVLS and idle requests

| RAM | Contract |
|---|---|
| `C154–C168`, six floats | Raw base timing A–F. |
| `C16C/C170/C174`, floats | A/D, B/E, C/F blends from `28418`. |
| `C17C`, float 0–1 | AVCS tracking ratio from measured `C8C8/C8CC` and targets `C974/C978`; not IAM. |
| `C180`, u8; `C184`, float | Selection flags and selected base timing, `284B8`. |
| `C150/C188`, floats | Subsequent base timing values. |
| `C134/C138`, floats | Idle/base blend and separate idle timing target. |
| `CCC8–CCDC`, six floats | Per-cylinder correction array. |
| `C0EC–C100`, six floats | Final per-cylinder ignition angles, `279CC`; distinct from the correction array. |
| `CD86/CD87`, u8 | Committed/requested AVLS mode. Mode 3 is high lift. |
| `CD89/CD8A`, u8 | Phase-qualified bank-index-0/1 software mode copies, written by `405CC`. E526/E527; these are not hydraulic feedback. |
| `CDF8/CDFC`, float percent | Bank-index-0/1 OSV output duty from `40CE6`, published through `F12A`. P123/P124 quantize to 100/255 percent per count. |
| `B118/B11A`, u16; `B11C/B120`, float amps | Raw OSV current copies and converted measurements from `F39C`. `F298(0/1)` supplies P125/P126 at 32 mA per count. |
| `CD9C`, u8 | Oil-temperature-selected AVLS curve state. |
| `B124/CF94`, floats C | Converted and validated/fallback oil temperature. |
| `C984`, float | Intake AVCS target selected by committed lift state, `353B0`. |
| `C468`, float RPM | Effective idle-speed request published at `2C70E`; E514. |
| `C2B8`, float native angle | Combined relative throttle request, `2AB06`; E515 divides by 0.84 for percent. |
| `C4D9`, u8 | Idle-air feedback flags; bit 3 permits feedback, with a separate update boundary. |

Stock timing selector B/E requires `27088` to return 1, but that helper
returns zero. A/D is the normal pair; C/F is selected by high-lift state and
the debounced flag. Main rotational idle runs the stock final-timing task,
then may retard the six final angles; its current enable is OFF.

The stationary AVLS RPM-override branch compares **CF94 oil temperature**
with `7D4B0/7D4B4` at `403C4`. These are stock 15 C thresholds, not pedal
limits. The [September 12 repair](V2_AVLS_NEUTRAL_20260912.md) restores them
from the erroneous 110 value in both builds. Actual pedal curves at
`7D67C/7D6B4` remain 110 percent; the two inputs must not be conflated.

Effective idle target and relative throttle request are requests, not measured
air delivery or motor duty. `2AAAC` adds the learned offset and selects fault
overrides later. The captured flags do not cover every received throttle-link
fault or actuator state.

The paired-pedal task at `17984` begins with protected offset validity `17A24`
and initialization `179EE`. `17B2A` filters AF80/AF84 into B488/B48C and
computes their deltas; `17C40` learns offsets `8110/8118/8120` under its retained
qualifiers. Earlier airflow/load and bank-charge names for these routines
were incorrect (C20). The corrected identity changes analysis, not ROM bytes.

## Fuel consumption and pump demand

| Address | Type / meaning | Producer and consumer |
|---|---|---|
| ROM `72D54` | float pulse-to-consumption coefficient | `13CA8` multiplies it by RPM and effective pulse. Both builders now pair it inversely with injector duration scalar `76014`. |
| RAM `B1C4` | float modeled fuel consumption | `13CA8` prefix: `B544/60 * ROM[72D54] * C0B8 * 3e-6`; telemetry and `2A910` consume it. |
| RAM `B2A4` | float mmHg relative, processed | Native `14AAC..14ABE` subtracts CFBC from processed B2A0. Pump threshold lookups use it; direct SD ABC4 is distinct. |
| RAM `C29C/C2A0/C2A4` | floats offset/current/filtered pump demand | `2A910`; BE40 can select offset 80, B1C4 is multiplied by 3.6, native filter uses 0.99 current weight. |
| RAM `C2AC/C2AD` | u8 mode / operating flags | Mode selector and separate operating gates; C2AD/01 forces command off. |
| RAM `C298` | float commanded percent | `2A53A` publishes 0/33.3/66.7/100, standard P47 logs it and DEAA receives the ratio. |

See the [injector/pump correction](FUEL_PUMP_SCALING_20260912.md) for exact
execution boundaries, table endpoints and missing-input fixtures. The loaded
drive does not establish actual pump duty, B2A4 or rail pressure.
