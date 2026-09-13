# Denso scaling and SH-2E arithmetic

[Reference home](README.md) · [Methods](METHODS.md) · [Dependency review](PATCH_PROCESS_FLOW.md)

The earlier version of this page gave incorrect wideband addresses, mixed
instruction issue rate with result latency, and asserted unmeasured execution
times. Those claims must not be used to close the scheduler dependency audit.
The observations below distinguish saved instructions from hardware timing.

## Hardware timing

The Renesas SH7055S manual lists `FDIV` at 13 execution cycles. For
`FADD`, `FSUB`, `FMUL` and `FMAC`, it distinguishes a one-cycle execution pitch
from a two-cycle instruction delay. Instruction counts alone do not establish
elapsed time with dependencies, memory traffic or interrupts. The device's
40-MHz maximum is not a measurement of this ECU's operating clock.
[Renesas manual, tables 1.1 and 2.18](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual).

A dependent instruction can wait for an FPU result. That is not evidence that
the ECU has lost synchronization or missed an injector/ignition deadline.
There is no measured deadline margin for the complete patched task graph.

## Installed code and observed instruction paths

The opcode census runs saved machine instructions, including the native SD
lookup routines. It does not estimate microseconds. Current main SHA-256:
`3e95b7508427f544e30a96c7aa78298b32560a6f3caf5c180e7949b8c2adc388`.

| Path | Evidence |
|---|---|
| SD wrapper `7E18C` | Six emitted `FMUL` instructions and no emitted `FDIV`. Native lookup calls remain part of its execution. |
| Interior SD fixtures | Three native lookup divisions; sampled full paths execute 424–537 instructions. These are selected cases, not worst-case timing bounds. |
| Clamped SD fixtures | Zero to two lookup divisions, depending on which axes require interpolation. |
| Stopped / invalid-MAP SD fixtures | 27 / 33 instructions in the sampled early-return paths. |
| Wideband update `7E440`, entered through `B690` | Reads unsigned ADC `FFFFAB06`; accepted fixture executes 58 added instructions, rejected fixture 36. |
| Accepted wideband arithmetic | Two `FMUL`, one `FADD`, one `FLOAT`, plus comparisons, loads, stores and branches. No `FDIV`. |
| Lean initializer `7EBA0` after the OCV repair | Twelve emitted instructions, plus the native `33964` call that initializes both AVCS integrators to 1.0. This is startup work, not added to every lean-cut update. |

The previously stated wideband entry `7F100`, ADC `FFFF87E2`, sub-40-cycle
execution, and SD total of about 150 cycles do not describe this build.
The stock MAF converter uses a table lookup; a polynomial was not established.

Reproduce the census with:

```sh
python3 -B tools/analysis/audit_fpu_usage.py
```

That command currently expects main's default-OFF rotational-idle allocation.
V2 removes that allocation. Matching shared wrapper bytes establishes their
instruction identity, but does not make every main fixture a v2 calibration
or whole-scheduler test.

## Integer storage and native lookup results

A 16-bit table element is not proof of integer-only runtime arithmetic.
The descriptor selects a data format and supplies scale/offset values; the
native helper's instructions determine whether the result is raw integer or
scaled float. See [lookup contracts](METHODS.md).

For a 64-bit product `P`, division by 65,536 selects `P >> 16`. `MACH` alone
contains `P >> 32`, so reading `MACH` is not generally division by 65,536.
The earlier explanation conflated these operations.

| Descriptor / storage | Verified interpretation |
|---|---|
| DBW descriptor `607D4`, data `7A738` | Native u16 scaling is `125/65536` into the requested-angle path. |
| DBW XML factor near `0.002270655357` | Display conversion differs from the native scale. It does not prove the throttle body's physical travel or describe P13's separate logger conversion. |
| Idle-air descriptors, data `79C9C/79CBC` | Scale `100/65536` produces the lookup's float result. It does not establish a multiply-and-drop-halfword implementation. |
| Tracking descriptors `5EFE8/5EFDC` | Requested/measured position axes, not RPM. The first returns scaled float tolerance through `209C`; the second returns raw integer persistence through `2118`. Both still execute FPU interpolation internally. [Native flow](PATCH_PROCESS_FLOW.md#tracking-enable-position-axes-latches-and-cut-selection). |

## Optimization boundary

SD tabulates the IAT density factor, but still calls the native interpolation
helpers. The complete caller subsequently divides airflow by RPM to obtain
load. It is incorrect to describe the entire path as division-free.

A useful optimization would need equivalent results at table boundaries,
invalid inputs and state changes, preservation of the native calling convention,
and evidence that the affected task lacks time margin. None of the current
opcode counts establishes FPU interlocks as the cause of the loaded cut.
