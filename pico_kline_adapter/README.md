# Pico K-line adapter

This directory contains a raw USB CDC-to-K-line bridge for a Raspberry Pi Pico
and an external analogue front end. The current hardware is the standalone
Jaycar LM393/BF469 board; the salvaged ANCEL AD310 circuit below is historical.
It appears to RomRaider and FastECU as a conventional serial K-line cable.

The firmware does not implement Subaru SSM or flashing commands. The host
program remains responsible for protocol framing, checksums, echo removal and
all ECU operations. This keeps destructive logic out of the adapter.

## Current status — 2026-09-07, after the K-line pull-up

Adding two 470 Ohm resistors in series (940 Ohm total) from **raw OBD pin 16
to K_INT/BF469 collector** restored communication on the current board.
Firmware remains version **1.1.2**, with the hash recorded below. No additional
Pico firmware change was needed for this result. Use the current
[Jaycar circuit notes](standalone_board/JAYCAR_FAST_KLINE.md) and
[point-to-point wiring notes](standalone_board/JAYCAR_FAST_KLINE_WIRING.md),
including their pull-up amendment; do not wire this board from the legacy
AD310 section or assume the older SVG already includes the added pull-up.

- Native macOS FastECU completed one 512 KiB ROM read. All 16 flash-block
  CRCs reported in each of four recorded passes independently match that
  saved image. This is one full read plus repeated block-CRC verification,
  not two independently captured full reads.
- Native macOS RomRaider works with the
  [RPM-only test profile](romraider_rpm_only_profile.xml). The prior profile
  registered 89 byte addresses, exceeding the 84-address SSM request limit;
  selections retained in other views contributed to the oversized request.
- **Test Write passed at 21:17:44** with the dedicated SH7055 180nm kernel
  v1.01. Upload, runtime identity, flash initialization, RAM-buffer transfer
  and CRC validation succeeded; flash erase/programming remained disabled.
  All ECU block CRCs were unchanged afterwards. Actual erase/programming
  and a post-write read-back are still unverified. The old generic 350nm
  profile remains incompatible with this test (`7F 21 06`); use the dedicated
  profile described in [FastECU kernel work](fastecu/README.md).

The existing master target differs from the saved ECU read by 224 bytes only:
100 IAT-axis bytes, 120 low-lift VE bytes and four checksum bytes. Executable
code and hooks are identical. The target IAT curve assumes a **1.00 kOhm**
ECU pull-up, versus the read image's 2.49 kOhm assumption; installed-circuit
validation is still required. The structural audit passes but does not
establish that the engine calibration is safe. Hashes and exact ranges are in
[TEST_RESULTS.md](TEST_RESULTS.md).

## Historical AD310 wiring — not the current Jaycar board

These connections describe the earlier salvaged AD310 implementation only.
In particular, its U7 receive divider and GP1 reset connection are not the
current LM393 board's wiring.

- Pico `GP4` -> 4.7 kOhm -> Q5 lower-left/base pad: K-line transmit.
- U7 pin 7 -> 10 kOhm -> midpoint -> 10 kOhm -> common ground.
- Divider midpoint -> Pico `GP5`: K-line receive. The measured 5 V U7 output
  becomes approximately 2.5 V at the Pico.
- Pico `GP27` (physical pin 32) -> LED resistor -> TX LED anode; cathode ->
  common ground. Firmware stretches each transmit indication to 35 ms.
- Pico `GP26` (physical pin 31) -> LED resistor -> RX LED anode; cathode ->
  common ground. This indicates every byte received from K-line, including
  local echo.
- Pico `GP2` (physical pin 4) -> LED resistor -> status LED anode; cathode ->
  common ground. It mirrors the Pico's onboard LED. Use 1 kOhm per external
  LED for normal brightness; 10 kOhm is safe but will be very dim.
- Pico ground -> AD310 ground / leftmost SWD pad.
- Pico `GP1` -> AD310 U1 reset node at the U1-facing side of C3/R6.
- Pico is USB-powered and the AD310 is OBD-powered. Never connect vehicle
  battery voltage to a Pico pin, and do not connect AD310 USB while it is
  OBD-powered.

Q5 is an NPN K-line pull-down. GP4 low leaves K-line idle/high; GP4 high makes
K-line dominant/low. Firmware inverts UART TX in the RP2040 GPIO fabric so a
normal UART idle-high signal produces the required physical GP4 low state.

## Bridge behaviour

- One raw USB CDC ACM serial port with a stable RP2040-derived serial number.
- Host-selected baud rate, data bits, parity and stop bits.
- Required Subaru rates 4800, 9600, 15625 and 62500 baud are supported.
- K-line local echo is preserved for RomRaider and FastECU to validate/remove.
- USB CDC break requests drive K-line dominant for fast/five-baud initialisation
  compatibility; break is released on timeout, USB removal or USB suspend.
- GP1 continuously drives low; it held the original AD310 MCU in reset and
  is unused by the standalone Jaycar board.
- 4 KiB buffers in each direction absorb USB packet scheduling jitter.
- A one-second hardware watchdog returns GP4 to safe startup behaviour if the
  firmware stalls.
- TX LED on `GP27`: transmit activity.
- RX LED on `GP26`: receive activity, including K-line local echo.
- Status LEDs on `GP2` and the onboard LED are solid when USB is not mounted,
  off when USB is mounted with no recorded error, and rapidly flash after an
  invalid serial setting, UART error or buffer overflow.

The serial port carries binary vehicle traffic only. There is deliberately no
text console because diagnostic text would corrupt SSM or flashing packets.

## Build

Use the official Raspberry Pi Pico SDK and a complete Arm embedded toolchain:

```sh
export PICO_SDK_PATH=/absolute/path/to/pico-sdk
export PICO_TOOLCHAIN_PATH=/absolute/path/to/arm-toolchain
cmake -S . -B build-bridge -G Ninja -DPICO_BOARD=pico
cmake --build build-bridge
```

The release artifact is `pico_ad310_kline_bridge.uf2`. Version 1.1.2 was built
with Pico SDK 2.3.0 and has SHA-256:

```
f04d6d916b6c4ecddfa73489b07ebda79c2cc53a3d66caea63f8558cfed8c65f
```

Version 1.1.1 fixes a confirmed startup TX polarity bug in 1.1.0:
`gpio_set_function()` cleared the inversion configured immediately before it.
Startup now selects UART and inverted output together in one atomic GPIO
control-register update, leaving GP4 low at idle. This applies to both the
AD310 and the current Jaycar LM393/BF469 circuit. See
[TEST_RESULTS.md](TEST_RESULTS.md) for live-test evidence and remaining checks.

Version 1.1.2 retains that fix and adds a read-only USB control status report
for digital pin levels, UART errors and byte counters. This report is separate
from the raw serial stream. Usage and limitations are in
[DIAGNOSTICS.md](DIAGNOSTICS.md). Version 1.1.2 has now been uploaded through
BOOTSEL, and the device reports its version and status successfully over USB.
Following the hardware pull-up addition, ECU identification, full ROM reading
and the minimal RomRaider logging profile work; flashing remains unvalidated.

`ad310_kline_safe_test.uf2` is retained as the earlier manual pulse-test image;
it is not a serial bridge.

## Installation

1. Disconnect the adapter from OBD.
2. Hold Pico BOOTSEL while connecting Pico USB.
3. Copy `pico_ad310_kline_bridge.uf2` to the `RPI-RP2` volume.
4. Let the Pico reboot. On macOS it should appear as a device similar to
   `/dev/cu.usbmodem...` with product name `Pico AD310 K-Line`.
5. Power Pico USB before connecting the adapter to OBD.

Do not use a terminal expecting a greeting: the port is intentionally silent
until K-line traffic exists.

## Commissioning order

1. Verify the current Jaycar board's electrical levels: GP4 near 0 V at idle,
   GP5/LM393 pin 7 near 3.3 V and OBD pin 7 near battery voltage. These are
   expected levels, not newly measured values. The legacy AD310 2.5 V receive
   divider does not apply to this board.
2. Perform a read-only SSM ECU-init/identity test at 4800 8N1.
3. Confirm native macOS RomRaider logging using the D2WD610H logger definition.
4. Use FastECU's generic serial adapter path and `sti04` method to make at least
   two complete ROM reads.
5. Require both reads to be byte-identical. So far, one full read and four
   matching 16-block CRC passes are recorded, not two full reads. The known
   canonical stock ROM
   `2005 BLE MT.bin` has SHA-256
   `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
6. Validate FastECU's test-write operation before considering a real write.

The earlier no-echo/GP5-low results are retained chronologically in
[TEST_RESULTS.md](TEST_RESULTS.md). They preceded the successful 940 Ohm
pull-up addition and no longer describe the current communication result.
The confirmed startup inversion defect and the missing external bus bias
were separate issues. Do not treat successful reading or minimal logging as
proof that the replacement flash kernel is ready for a real write.

## Scope

This adapter is K-line only. It is not a J2534 device, does not emulate an
OpenPort 2.0 USB protocol, and is not expected to work with EcuFlash. RomRaider
logging and FastECU's generic serial `sti04` path are the intended clients.

## Upstream attribution

The USB/UART bridge structure and USB descriptor approach were informed by the
MIT-licensed [Noltari/pico-uart-bridge](https://github.com/Noltari/pico-uart-bridge).
TinyUSB and the Raspberry Pi Pico SDK are used under their respective licenses.

## Future standalone hardware

The replacement-board architecture that removes the AD310 entirely is captured
in [standalone_board/BOARD_PLAN.md](standalone_board/BOARD_PLAN.md). It uses a
Pico carrier and an ST L9637D ISO 9141 transceiver, with a staged bench and
vehicle qualification plan. It is a design plan, not yet an ECU-write-qualified
schematic.

A concrete expandable proto-board circuit using the AD310's salvaged LM2903
comparator and Q5 transistor is documented separately in
[standalone_board/LM2903_PROTO.md](standalone_board/LM2903_PROTO.md).

The current all-Jaycar, through-hole standalone build is documented in
[standalone_board/JAYCAR_FAST_KLINE.md](standalone_board/JAYCAR_FAST_KLINE.md).
Read its 940 Ohm pull-up amendment alongside the SVG for the deliberately
simple high-speed BF469/LM393 revision; the older drawing alone is incomplete.

A non-schematic, point-to-point assembly view is available in
[standalone_board/JAYCAR_FAST_KLINE_WIRING.md](standalone_board/JAYCAR_FAST_KLINE_WIRING.md).
