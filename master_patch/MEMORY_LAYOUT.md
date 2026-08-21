# Master-patch memory ownership

The master verifier treats injected flash, stock hook sites, calibration writes,
and the separate rotational-idle reservation as distinct ownership classes. A
build fails on any overlap except the explicit replacement of boost component
seed data by the final boost calibration.

## Injected flash

| Range | Owner |
|---:|---|
| `0x7D790..0x7D903` | Boost descriptors, axes, data, controller, and fuel-cut wrapper. |
| `0x7D91C` | Master wideband/O2 architecture signature. |
| `0x7DB40..0x7DCEB` | Reserved for the separate rotational-idle patch; unchanged by master. |
| `0x7DD00..0x7E39B` | Original speed-density calibration and wrapper allocation. |
| `0x7E39C..0x7E3B3` | Dual-VE portion of the speed-density wrapper allocation. |
| `0x7E3B4..0x7E3FF` | Unused speed-density reservation. |
| `0x7E400..0x7E41B` | Wideband constants. |
| `0x7E440..0x7E51B` | Wideband update routine. |
| `0x7E520..0x7E53B` | Shared closed-loop inhibit helper. |
| `0x7E560..0x7E63F` | Wideband/SD prerequisite boost guard. |
| `0x7E640..0x7E667` | Low/high dual-VE descriptors. |
| `0x7E668..0x7E6B7` | Low/high dual-VE RPM axes. |
| `0x7E6B8..0x7EAC7` | Low/high dual-VE data. |
| `0x7EAC8..0x7FAF7` | Unallocated verified free flash remaining in the checksum range. |

The critical boundary is exact: the wideband component ends at `0x7E63F` and
the speed-density component's dual-VE data segment starts at `0x7E640`. Component builders also require every destination
byte to remain `0xFF` before writing.

## Intentional composition

- The stock purge-output literal at `0x3FD8C` is one composed hook: boost first
  points it to its controller; master wideband then points it to the prerequisite
  guard, which tail-calls the boost controller only when its inputs are valid.
- Final calibration deliberately replaces only boost target data, base duty,
  Kp, maximum duty ratio, soft overboost, and hard overboost seed data. The
  verifier requires this exact intersection and rejects any other calibration
  contact with injected flash.
- Dual-VE selection is built directly into the one speed-density wrapper. There
  is no second patch stage or shared wrapper ownership.

## RAM

No component reserves new persistent RAM. Injected code uses the SH stack for
temporary register preservation and reads or publishes already-mapped stock RAM
signals: MAP/RPM/IAT/airflow/load, former-MAF ADC, front-feedback/readiness and
logger mirrors, boost duty inputs, and committed AVLS state. Consequently there
is no independent scratch-RAM allocation that can collide with another task.

`python3 master_patch/verify_master_patch.py` checks all declared blob ranges,
stock hook ranges, calibration ranges, the rotational-idle reservation,
undeclared changed bytes, fresh-rebuild equality, checksum, and pinned output
hash.
