# Offline SD fault repair — 2026-09-08

> Archived investigation, retained for evidence and historical reproduction.
> Use the [central reference](../../reference/README.md) and [audited corrections](../../reference/FINDINGS.md) for current conclusions.
> Build identities, commands and recommendations below describe their original stage.

**Later integration decision:** the [rolling master](MAP_BOUNDARY_REPAIR.md)
integrates the narrower boundary repair with the existing SD code. The immediate
latched-cut redesign described here remains an unintegrated prototype.

An executable **in-memory prototype** now removes the reproduced low-pressure
500 g/s discontinuity and replaces invalid-calculation airflow with an explicit
latched injector inhibit. It is **outside the production builder**, has no BIN
write interface, and deliberately does not recalculate the fixture checksum.
No saved BIN, logger, MAP calibration, transient multiplier or load filter changed.
This is not a new flashing instruction or a proven cure for the vehicle's near-stall.

## Reproduced defect and correction

The unchanged native MAP electrical classifier accepts processed ADC counts
3932 through 64500. The installed transfer converts **3932..4506** to about
10.481..13.330 kPa, below the old SD minimum of 13.332 kPa. Thus **575 electrically
accepted counts** incorrectly take the fixed 500 g/s calculation fallback.
Electrical acceptance is a code property, not independent physical validation
of the sensor below its published calibration endpoints.

At 1500 RPM, 25 °C, low lift, executing the native converter and SD lookup code:

| ADC | Voltage | Direct MAP, kPa | Current airflow, g/s | Prototype airflow, g/s |
|---:|---:|---:|---:|---:|
| 3932 | 0.299988 | 10.4811 | 500.0000 | 3.54985 |
| 4194 | 0.319977 | 11.7816 | 500.0000 | 3.99031 |
| 4506 | 0.343781 | 13.3303 | 500.0000 | 4.51483 |
| 4588 | 0.350037 | 13.7373 | 4.65269 | 4.65269 |
| 5243 | 0.400009 | 16.9885 | 5.75384 | 5.75384 |
| 7864 | 0.599976 | 29.9984 | 12.20588 | 12.20588 |

The new calculation retains ABC4 as its pressure source. It checks the existing
electrical limits using the paired processed count ABC8, then requires finite
positive pressure within the existing upper bound. It clamps only the VE lookup
coordinate to the first pressure knot. Actual pressure remains in the air-mass
product. Both VE descriptors retain their existing common pressure axis.

Native task lock/unlock `3AF4/3B08` protects the ADC/MAP/IAT snapshot against task
switching. Callee-saved registers retain the snapshots across lookup calls and
any task dispatch during unlock. RPM remains the caller's captured FR15, also
used by the retained load divisor. Hardware ADC acquisition is not made
simultaneous with RPM or temperature by this change.

Every accepted ADC count below the first VE knot, **3932..5849 (1918 codes)**,
passes through the native converter and new SD code with strictly increasing
airflow. Another **108 normal-domain cases** spanning RPM, MAP, IAT and AVLS
produce bit-identical airflow to the saved candidate. The one-float boundary
immediately below 100 mmHg no longer jumps to 500 g/s.

## Explicit fault response and cut interaction

For invalid nonzero-RPM input, calibration, lookup or product, the prototype:

1. Saves the first reason and processed ADC, and increments a saturating count
   of rejected calculations. The count is not a count of independent sensor events.
2. Sets the existing BF6C/0x80 cut flag and publishes `FFFF` to the native B744
   six-channel injector-inhibit word inside the native scheduler critical section.
3. Publishes zero to the four synthetic airflow states. Injector inhibition
   comes from the explicit cut interfaces, not from zero airflow alone.
4. Wraps the retained lean/rev-limit/overboost chain so its temporary cut clear
   cannot reach the injector task before the SD latch is reasserted.

Valid samples, falling pressure, the lean-cut release rule and zero RPM do not
release an SD latch. Exact zero RPM does not create a new fault. The existing
global state initializer clears the latch/count/ADC through its two longword
zero stores; it does not clear another cut source's state.

The static initialization route is native kernel initial activation list
`4AFC = {0,17}` / count `4B04 = 2`; task-17 descriptor `4AAC` points to `6328`.
The call at `6518` reaches `FEF4`, whose call at `1033E` uses pointer `1055C`
to the installed zeroer `7EBA0`. This traces the initial route, not every possible
watchdog, diagnostic reinitialization or generic task-reactivation sequence.

| Offline allocation | Use |
|---|---|
| `7EE00`, 724 bytes | New SD wrapper |
| `7F200`, 116 bytes | Latched fault publication |
| `7F300`, 68 bytes | Outer cut composition |
| `FFFFC85E`, uint16 | Saturating rejected-calculation count |
| `FFFFC861`, uint8 | First reason, also latch |
| `FFFFC862`, uint16 | First processed ADC; FFFF if RPM was NaN before acquisition |

The RAM occupies unused bytes within the two already-retired rear-O2 slots.
Their traced old runtime tasks are bypassed and checked before building the
fixture. No direct native xrefs were found to the three new subfield addresses;
this is not a substitute for the retirement check on the original whole slots.
Only the free-tail code and pointers `1743C` / `11D3C` differ in memory.

## Downstream consequence, with unchanged calibration

A supplied test trajectory holds 1500 RPM and 45 °C, starts at ADC 7864, supplies
one ADC-3932 call, then returns to 7864. Each SD result feeds the retained load
and transient instructions with normal fixture flags and one transient update
per load call. This is not a recorded engine trajectory.

| Result | Current code | Prototype |
|---|---:|---:|
| Initial conditioned load | 0.48824 | 0.48824 |
| Conditioned load after low-pressure call | 0.69894 | 0.46746 |
| B874 after low-pressure call | +1.80882 | −0.14246 |
| B874 range over 100 calls | −0.11374..+1.83347 | −0.14246..+0.01765 |

The erroneous positive load/fueling disturbance disappears without editing the
MAP offset, VE surfaces, negative transient gain or 0.06 load filter. The valid
negative correction remains. No injector pulse, AFR or engine recovery is
predicted by this fixture, and it does not establish that the old capture
contained an unlogged ADC excursion into this band.

## Verification and remaining work

**16 native execution test groups pass.** They cover normal/boundary calculation,
fault reasons, malformed calibration and lookup results, count saturation,
first-fault retention, zero RPM, initialization, all 16 caller interrupt masks,
other cut reasons, lean-cut release interaction, all six injector scheduler
channels, and IRQ-triggered task dispatch during input snapshot and cut publication.
Deliberately removing the new outer lock allows an injector task to see the
stock limiter's temporary clear and enqueue output; the intact wrapper prevents
that case. These tests validate the relevant instruction-level mechanism.

The principal unresolved design question is the **physical electrical fault
boundary and response**. Immediate latched inhibition below the current 0.30 V
threshold differs from the stock debounced MAP DTC response. A plausible engine
vacuum or brief electrical noise must not be mislabeled a hard sensor failure.
The installed sensor's physical behavior below the supplied 0.60 V / 30 kPa
endpoint is still not independently established. This is why the prototype
has not been promoted to a flash candidate.

The manufacturer's current [Supra sensor page](https://omnipowerusa.com/product/toyota-supra-1993-1998-map/)
describes linear vacuum/boost response but supplies no numerical electrical
fault threshold. Its [Legacy product page](https://omnipowerusa.com/product/subaru-legacy-gt-05-09-08-14-wrx/)
also supplies no threshold. These pages were checked on 2026-09-08; they do not
justify adopting 0.30 V as an immediate, latched injector-cut boundary. No new
physical sensor limit was inferred from their general linearity claims.

Production integration also needs declared memory ownership, logger/profile
space for latched state, reset-policy review and the complete integrated verifier.
Native hardware startup, CPU deadlines, arbitrary interrupt timing, actual
injector electrical delivery and combustion are outside these fixtures. The
normal code path adds roughly 90–94 interpreted native instructions in the
reported cases, including the snapshot lock and diagnostic checks; this is not
a measured execution-time result. No repeat engine run is requested by this audit.

Reproduce:

```sh
python3 tools/analysis/audit_sd_fault_repair_prototype.py --output /tmp/d2wd-sd-repair.json
```

Sources: [prototype](../../../tools/analysis/prototype_sd_fault_repair.py),
[native tests](../../../tests/test_sd_fault_repair_prototype.py),
[audit runner](../../../tools/analysis/audit_sd_fault_repair_prototype.py),
[numeric report](../../../logs/20260908_sd_fault_repair_prototype.json).
Input remains SHA-256
`2f80b8e5cb80361cdee170655bc26aa8ed8a41bcf4cd7f7249fe3f8c8eaa1f1c`.
