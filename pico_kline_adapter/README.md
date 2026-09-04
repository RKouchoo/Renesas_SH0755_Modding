# Pico + ANCEL AD310 K-line adapter

This directory contains a raw USB CDC-to-K-line bridge for a Raspberry Pi Pico
and the salvaged ANCEL AD310 analogue front end. It is intended to appear to
RomRaider and FastECU as a conventional serial K-line cable.

The firmware does not implement Subaru SSM or flashing commands. The host
program remains responsible for protocol framing, checksums, echo removal and
all ECU operations. This keeps destructive logic out of the adapter.

## Confirmed wiring

- Pico `GP4` -> 4.7 kOhm -> Q5 lower-left/base pad: K-line transmit.
- U7 pin 7 -> 10 kOhm -> midpoint -> 10 kOhm -> common ground.
- Divider midpoint -> Pico `GP5`: K-line receive. The measured 5 V U7 output
  becomes approximately 2.5 V at the Pico.
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
- GP1 continuously holds the original AD310 MCU in reset.
- 4 KiB buffers in each direction absorb USB packet scheduling jitter.
- A one-second hardware watchdog returns GP4 to safe startup behaviour if the
  firmware stalls.
- LED solid: USB configured and no detected errors. LED rapidly flashing:
  invalid serial settings or a UART/buffer error. LED off: USB absent/suspended
  or an intentional break is active.

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

The release artifact is `pico_ad310_kline_bridge.uf2`. Version 1.0.0 was built
with Pico SDK 2.3.0 and has SHA-256:

```
db17fb9740c69eb7c4b6de27795dcb936bb7072d16d3d7436550f639fcacecda
```

`ad310_kline_safe_test.uf2` is retained as the earlier manual pulse-test image;
it is not a serial bridge.

## Installation

1. Disconnect the AD310 from OBD.
2. Hold Pico BOOTSEL while connecting Pico USB.
3. Copy `pico_ad310_kline_bridge.uf2` to the `RPI-RP2` volume.
4. Let the Pico reboot. On macOS it should appear as a device similar to
   `/dev/cu.usbmodem...` with product name `Pico AD310 K-Line`.
5. Power Pico USB before connecting the AD310 to OBD.

Do not use a terminal expecting a greeting: the port is intentionally silent
until K-line traffic exists.

## Commissioning order

1. With ignition off, verify GP4 is approximately 0 V, the GP5 divider midpoint
   is approximately 2.5 V, and OBD pin 7 is near battery voltage.
2. Perform a read-only SSM ECU-init/identity test at 4800 8N1.
3. Confirm native macOS RomRaider logging using the D2WD610H logger definition.
4. Use FastECU's generic serial adapter path and `sti04` method to make at least
   two complete ROM reads.
5. Require both reads to be byte-identical. The known canonical stock ROM
   `2005 BLE MT.bin` has SHA-256
   `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`.
6. Validate FastECU's test-write operation before considering a real write.

The production bridge has been source-reviewed and cleanly compiled, while the
AD310/Pico physical layer was previously loopback-tested in the vehicle. The
production UART bridge itself has not yet communicated with the ECU. Do not use
it for an ECU write until the read-only stages above pass.

## Scope

This adapter is K-line only. It is not a J2534 device, does not emulate an
OpenPort 2.0 USB protocol, and is not expected to work with EcuFlash. RomRaider
logging and FastECU's generic serial `sti04` path are the intended clients.

## Upstream attribution

The USB/UART bridge structure and USB descriptor approach were informed by the
MIT-licensed [Noltari/pico-uart-bridge](https://github.com/Noltari/pico-uart-bridge).
TinyUSB and the Raspberry Pi Pico SDK are used under their respective licenses.
