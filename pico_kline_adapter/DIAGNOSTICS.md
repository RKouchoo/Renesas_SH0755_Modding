# Read-only Pico diagnostics

Firmware 1.1.2 adds a USB control status request so the host can inspect the
adapter without a multimeter or changes to the circuit. The normal serial
port still carries only raw K-line traffic. Diagnostics do not send ECU
commands, change GPIOs, clear error counters, or consume UART bytes.

## Running the status reader

With firmware 1.1.2 installed and the Pico connected over USB:

```sh
python3 pico_kline_adapter/read_diagnostics.py --serial E46340134F22472C
python3 pico_kline_adapter/read_diagnostics.py --serial E46340134F22472C --watch 5
```

The reader uses Python's standard library and the existing native `libusb`
library. On this Mac, a normal device-descriptor read through libusb already
succeeded without claiming the CDC interface or detaching its driver. The
reader leaves the serial data channel alone. Close serial test applications
before sending separate ECU identity requests so those applications do not
transmit simultaneously.

Older firmware does not implement the request and should return an unsupported
request/USB pipe error. BOOTSEL installation is required; a USB reconnection
by itself does not update firmware.

## What it can establish

With the bridge idle, TX GPIO CTRL should be `0x102`, RX GPIO CTRL `0x2`,
GP4 should sample low, and GP5 should sample high. These are digital samples
at the Pico pads. GP5 high does not prove that K-line is at the correct vehicle
voltage, and GP5 low alone cannot distinguish a missing pull-up from a
comparator, transistor, or wiring fault. GP4's level does not prove the external
transistor is correctly connected or switching the vehicle line.

Compare snapshots before and after a normal six-byte SSM identity request:

| Observation | Meaning |
|---|---|
| Host RX and UART TX each increase by six | USB bytes reached the UART transmit register |
| UART RX does not increase | No UART byte was decoded during that request |
| UART RX increases with error bits | There is receive activity, but UART errors were recorded |
| UART RX increases, USB queued count does not | Inspect USB mount/break state and pending receive queue |
| USB queued count increases but host receives nothing | Inspect USB delivery and the host serial reader |

Counters include local echo and noise, not just ECU replies. An ECU response
still requires valid SSM framing and checksum on the serial channel. The USB
queued count records bytes accepted by TinyUSB; it does not prove the host
read them. Counters and uptime wrap modulo 2^32. UART RX counts cover the
normal receive path; bytes deliberately discarded during an active break are
not included. Error bits accumulate until reboot.

## USB protocol, ABI KLD1

Read exactly 64 bytes using a device-recipient vendor IN request:

```text
bmRequestType = 0xC0
bRequest      = 0x40
wValue        = 0
wIndex        = 0
wLength       = 64
```

Only that request is accepted. The response is sixteen little-endian uint32
words captured in the main loop's USB callback:

| Word | Field |
|---:|---|
| 0 | Magic `0x31444C4B`, bytes `KLD1` |
| 1 | Firmware version: major bits 16–23, minor 8–15, patch 0–7 |
| 2 | Milliseconds since boot, modulo 2^32 |
| 3 | Flags listed below |
| 4 | GPIO4 control register |
| 5 | GPIO5 control register |
| 6 | Latest requested baud rate |
| 7 | Actual baud reported by the SDK UART configuration |
| 8 | Bytes read from USB CDC into host-to-line queue |
| 9 | Bytes written to the UART transmit register |
| 10 | Bytes read from the UART receive register in the normal receive path |
| 11 | Bytes accepted by TinyUSB's CDC transmit queue |
| 12 | Existing aggregate error-event counter |
| 13 | Accumulated UART RSR error bits: framing 0, parity 1, break 2, overrun 3 |
| 14 | Bytes pending in the host-to-line software queue |
| 15 | Bytes pending in the line-to-host software queue |

Flag bits: 0 USB mounted, 1 TinyUSB ready, 2 DTR, 3 RTS, 4 break active,
5 line coding pending, 6 GP4 digital high, 7 GP5 digital high. Other bits are
reserved. Reading a report has no counter-reset or control operation.

This diagnostic facility does not validate 62,500-baud operation, full ROM
reads, or flashing. Those still need independent end-to-end tests.
