# SH7055 direct-attach AUD logger and live-calibration interface

Target: D2WD610H / Renesas SH7055SF (`HD64F7055S`, FP-256H).

Status: architecture and stock-ROM initialization are verified; the ECU PCB pad routing and
physical interface are not yet verified. Build the first hardware as a read-only prototype.

## Outcome

The SH7055's Advanced User Debugger (AUD) RAM-monitor mode is the correct interface for a
direct-attached logger. It can read and write internal-bus addresses while the engine-control CPU
continues to execute. Renesas explicitly describes the mode as supporting RAM monitoring and
tuning.

For this ROM:

- ordinary logging can be implemented without an ECU firmware patch;
- a Pico/RP2040 is fast enough for the first logger, provided PIO owns the bus timing;
- the electrical interface must translate/protect the SH7055's **5 V PVCC2-domain AUD pins**;
- H-UDI/JTAG is not the preferred running logger because it is halt-oriented and the stock ROM
  stops its module clock;
- live changes to existing RAM variables are possible, but stock flash-resident maps cannot be
  transparently edited through AUD;
- safe live map tuning needs a later ECU patch that reserves a calibration shadow in proven RAM
  and redirects selected map descriptors/lookups to it;
- the SH7055 `RAMER` flash-to-RAM overlay is not usable on this ROM without major RAM/flash
  relocation.

The recommended development path is therefore:

1. Pico + level shifting, read only, 0.5--1 MHz AUD clock.
2. Prove reads against known ROM constants and the mapped RPM/MAP/IAT RAM variables.
3. Measure logging rate and engine-task disturbance before increasing toward 10 MHz.
4. Add a physically gated RAM-write mode restricted to a calibration-shadow allowlist.
5. Add the ECU-side calibration-shadow patch only after a complete RAM-ownership audit.
6. Commit a validated tune to flash only with the engine stopped.

## Why AUD rather than K-line, CAN, or H-UDI

| Interface | Firmware patch | Running bandwidth | Main limitation |
|---|---:|---:|---|
| AUD RAM monitor | No for reads | Highest; approximately 1.8--2.2 MB/s theoretical at 10 MHz | Requires access to eight dedicated CPU pins and careful 5 V interfacing |
| K-line/SSM | No for existing parameters | Low | ECU request/response overhead and a limited stock parameter set |
| Custom CAN logger | Yes | Tens of kB/s at 500 kbit/s | Requires ECU scheduler/HCAN work and consumes flash/CPU time |
| H-UDI/JTAG | Usually debugger-controlled | High when halted | Can stop or disturb execution; stock firmware stops its module clock |
| External memory-bus tap | Major | Potentially high | Too many fine-pitch pins; flash and RAM are on-chip |

AUD is not literally zero-impact. It arbitrates for internal-bus access and aggressive reads can
stall or contend with CPU accesses. Renesas calls the mode real-time tuning, but does not quantify
the application-task penalty. That penalty must be measured on this ECU.

## SH7055SF pin group

All required AUD pins are clustered within one eleven-pin span of the 0.5 mm-pitch FP-256H
package. This makes a small flex-PCB solder comb or an identified group of factory test pads much
more realistic than individual fly wires.

| CPU pin | Signal | RAM-monitor direction | Notes |
|---:|---|---|---|
| 237 | VCC | sense only | 3.3 V core/H-UDI supply; do not use as the main module supply |
| 238 | `/AUDRST` | host to ECU | Active low; internal pull-down |
| 239 | VSS | common reference | Convenient ground between reset and mode pins |
| 240 | `AUDMD` | host to ECU | High selects RAM-monitor mode; internal pull-up |
| 241 | `AUDATA0` | bidirectional | Least-significant bit of each protocol nibble |
| 242 | `AUDATA1` | bidirectional | 5 V PVCC2-domain output |
| 243 | `AUDATA2` | bidirectional | 5 V PVCC2-domain output |
| 244 | `AUDATA3` | bidirectional | Most-significant bit of each protocol nibble |
| 245 | `AUDCK` | host to ECU | Maximum one quarter of CPU clock |
| 246 | `AUDSYNC` | host to ECU | Marks command/address/data framing |
| 247 | PVCC2 | sense / buffer rail | 5.0 V nominal AUD I/O supply; do not feed a 3.3 V MCU pin |

The SH7055 core supply is 3.3 V, but pins 238 and 240--246 tolerate/use the 5 V PVCC2 domain,
and AUDATA outputs are powered from PVCC2. The manual specifies a 2.2 V minimum high input for
ordinary AUD data/clock/sync inputs, while `AUDRST` and `AUDMD` use a higher threshold tied to the
3.3 V core supply. Direct connection to a non-5-V-tolerant MCU is therefore prohibited.

Do not assume a commercial Denso boot/programming pad is AUD. `FWE`, mode, watchdog, SCI and
AUD pads are different signals. The exact D2WD610H PCB must be continuity-mapped from pins
238 and 240--246 before any connection is made.

## Stock-ROM enable state (Ghidra verified)

The canonical root ROM remains unchanged. The following functions were inspected and renamed in
the stock Ghidra project using the established underscore convention:

| ROM address | Name | Relevant behavior |
|---:|---|---|
| `0x09F4` | `bus_state_controller_and_ram_emulation_initialize` | Initializes BSC registers, writes protected `MSTCR=0x3C04`, and clears RAMER through the `0xFFFFEC20` register block |
| `0x0A1E` | `bus_and_port_registers_initialize_a1e` | Alternate/startup register set writes `PDDR=0x3EFF`; bit 13 remains set |
| `0x1B4A` | `port_registers_initialize_1b4a` | Another register-initialization set writes `PDDR=0x3CFF`; bit 13 remains set |
| `0x5082` | `port_registers_initialize_5082` | Writes `PDDR=0x287F`; Port-D bit 13 is set |
| `0x50CA` | `port_registers_initialize_50ca` | Continues the startup port-register initialization |
| `0x529C` | `flash_ram_emulation_disable` | Writes zero to `RAMER` at `0xFFFFEC26` |
| `0x52A4` | `flash_ram_emulation_disable_thunk` | Tail-branches to the RAMER-clear function |
| `0x52A8` | `aud_system_control_and_module_standby_initialize` | Writes `SYSCR=0x01`; selects the protected MSTCR word from PDDR bit 13 |
| `0x52DA` | `ram_enable_and_fpu_stop_dispatch` | Reasserts `SYSCR=0x01`, reads MSTCR and dispatches to `0xD210` on mask `0x02` (FPU stop); previous H-UDI identity was wrong |

Every direct PDDR write found in the Ghidra xref pass (`0x3EFF`, `0x3CFF`, and `0x287F`)
keeps bit 13 set. At normal startup that condition selects a word write of `0x3C04` to
`0xFFFFF70A`.
`0x3C` is the protected-write key and the low byte becomes MSTCR `0x04`:

- `MSTOP3=0`: AUD clock operates;
- `MSTOP2=1`: H-UDI clock is stopped;
- `MSTOP1=0`: FPU operates;
- `MSTOP0=0`: UBC operates.

`SYSCR=0x01` means `RAME=1` and `AUDSRST=0`, so on-chip RAM and AUD are enabled. Ghidra
shows the two named startup writes of `SYSCR=0x01`, plus a separate standby/error path at
`0x5392` that can clear RAME and loop forever. The MSTCR write xrefs are the direct `0x3C04`
initialization in `bus_state_controller_and_ram_emulation_initialize` and the two conditional
writes in `aud_system_control_and_module_standby_initialize`; its only indexed read is in
`aud_enable_and_hudi_module_stop_dispatch`. Both RAMER write xrefs clear the register. This is
strong static evidence that an external AUD reset/mode sequence can start RAM-monitor operation
without an ECU patch during normal running. Physical confirmation is still required.

## Electrical prototype

### Recommended first build

- Existing Raspberry Pi Pico / RP2040, USB powered.
- RP2040 PIO state machine for deterministic four-bit bus timing.
- `SN74LVC245A` powered at 3.3 V for `AUDATA[3:0]`:
  - inputs tolerate the ECU's 5 V data output;
  - outputs are 3.3 V, above the SH7055 AUD-data 2.2 V minimum high threshold;
  - `DIR` and `/OE` are driven by PIO;
  - `/OE` has a 10 kOhm pull-up so the interface starts isolated.
- `SN74AHCT125-Q1` powered from a sensed/qualified 5 V rail for the four host-to-ECU controls:
  `/AUDRST`, `AUDMD`, `AUDCK`, and `AUDSYNC`.
- 22--47 Ohm source-series resistor on every driven AUD signal.
- 100 nF local decoupling at each logic IC plus 1 uF nearby bulk decoupling.
- Target VCC and PVCC2 voltage sensing; all drivers disabled unless the ECU rails are valid.
- Common signal ground at CPU pin 239 or the matching nearby ground plane/test point.

The data buffer's A side is the Pico and B side is the ECU. Disable `/OE` before changing `DIR`.
For a read, switch from A-to-B to B-to-A during the low half of `AUDCK`, then re-enable the buffer.
At 10 MHz the half-cycle is only 50 ns, so this transition must be performed by PIO or FPGA, not
interrupt-driven C code. Begin at 0.5--1 MHz, where probing and fault diagnosis are far easier.

For a more conservative dual-rail implementation, an `SN74LVC8T245` can be used only for the
four data bits with VCCA=3.3 V and VCCB=5 V. It cannot also carry the four fixed-direction control
signals because all eight channels share one direction control.

### Safe inactive state

- Buffer outputs disabled until both host firmware and ECU rail sensing are valid.
- `/AUDRST` then falls back to the SH7055 internal pull-down, resetting only the AUD block.
- `AUDMD` falls back high, selecting RAM-monitor mode for the next deliberate AUD release.
- No interface output may drive an unpowered ECU.
- The prototype must not power the ECU through a signal or sense pin.

For an in-vehicle permanent module, use a protected automotive input supply rather than drawing
the whole module from CPU VCC/PVCC2: reverse-polarity protection, load-dump-rated TVS/front end,
brownout supervision, and controlled driver isolation are required.

## RAM-monitor wire protocol

The protocol is synchronous and transfers one four-bit nibble per `AUDCK` cycle. Change host
outputs at the falling edge and sample ECU output at the rising edge, matching the Renesas sample.

### Command nibble

| Operation | Byte | Word | Longword |
|---|---:|---:|---:|
| Read | `1000` | `1001` | `1010` |
| Write | `1100` | `1101` | `1110` |

Bit 3 is fixed at one, bit 2 is direction (`0` read, `1` write), and bits 1:0 select byte, word or
longword. `11` is invalid.

### Longword read sequence

1. Drive the data bus toward the ECU.
2. Assert `AUDSYNC` and clock dummy nibble `0000`.
3. Clock command nibble `1010`.
4. Clock the 32-bit address as eight nibbles, least-significant nibble first.
5. Disable the data buffer, reverse it toward the host, then re-enable it.
6. Clock until ready nibble bit 0 is one; treat status bits 1/2 as command/bus errors.
7. Negate `AUDSYNC` after ready.
8. Clock eight data nibbles, least-significant nibble first, and reconstruct the 32-bit value.

The write sequence clocks `1110`, the address, and then eight least-significant-first data
nibbles before turning the bus around and polling ready.

Alignment restrictions:

- a word access cannot target address `4n+1` or `4n+3`;
- a longword must be four-byte aligned;
- longword access to an 8-bit on-chip I/O space is invalid;
- external-space access in single-chip mode produces a bus error.

The first implementation should expose only byte, word and aligned-longword reads. Do not expose
generic writes in the host protocol.

## Expected bandwidth

A minimum aligned 32-bit random read needs approximately 18--22 clocks including command,
address, turnaround, ready and data. At the 10 MHz electrical maximum this is roughly
1.8--2.2 MB/s of theoretical payload before ready waits, bus arbitration, USB framing and host
overhead. At 1 MHz it is about 180--220 kB/s theoretical.

Practical examples before overhead:

| Capture | Payload |
|---|---:|
| 50 x 32-bit values at 100 Hz | 20 kB/s |
| 200 x 32-bit values at 100 Hz | 80 kB/s |
| 200 x 32-bit values at 200 Hz | 160 kB/s |

The Pico's USB full-speed interface will eventually limit a maximum-rate AUD stream, but it is
ample for the first several hundred parameters. Use aligned 32-bit reads and batch USB records.
Individual variables in one batch are not a globally atomic snapshot because the ECU can update
them between AUD reads.

## MCU / FPGA / SBC choices

| Platform | Verdict | Use |
|---|---|---|
| Existing RP2040 Pico | **Start here** | Cheapest proof; PIO handles AUD and USB carries selected parameters |
| RP2350B board | Good compact successor | More GPIO/headroom and security; still USB full-speed on common boards |
| Teensy 4.1 / i.MX RT1062 | Best simple high-speed MCU prototype | FlexIO-class deterministic I/O, USB high speed, Ethernet and SD |
| Small FPGA + RP2350/SBC | Best robust architecture | FPGA owns AUD timing/FIFO; MCU or Linux host handles storage/network/UI |
| Raspberry Pi 5 / Orange Pi 5 alone | Do not drive AUD directly | Linux GPIO timing is not deterministic; pair with Pico/FPGA |
| Existing XC7Z020 video board | Powerful but inconvenient | PL+ARM is ideal in theory, but the photographed board exposes no confirmed general-purpose PL I/O; reverse-engineering its BGA/HDMI routing is more work than a small dev board |

The sensible final architecture is:

```text
SH7055 AUD pins
    -> short flex/test-pad connection
    -> 5 V-safe data/control buffers beside the ECU
    -> PIO or FPGA transaction engine
    -> FIFO/ring buffer
    -> USB-HS or 100BASE-T host link
    -> laptop/logger/tuning application
```

Wireless, storage and a dashboard belong after the deterministic AUD engine. They should never
be allowed to control bus timing directly. An SBC is useful as the UI/storage/network layer, not
as the signal-level interface.

## Live tuning boundary

### What AUD writes can do immediately

AUD can write mapped RAM variables while the CPU runs. Many stock variables are regenerated by
periodic tasks, so changing an arbitrary working value may last only one task and may be unsafe.
Unrestricted access also reaches peripheral registers. A bad write can stop injection, alter timer
outputs, corrupt the stack, or crash engine control.

The first write-capable firmware must therefore have all of these controls:

- a compile-time read-only default;
- a physical `WRITE_ENABLE` jumper/key;
- an address and width allowlist in the PIO/FPGA host firmware;
- explicit rejection of peripheral, stack and unknown RAM regions;
- aligned 32-bit writes for float calibration values;
- request logging with address, old value, new value and monotonic sequence;
- CRC/version checking for any multi-value calibration block;
- no flash erase/program command while RPM is nonzero.

### Why stock maps cannot simply be overwritten

The maps used by the master tune live in flash, mostly around `0x76000--0x7EAC7`. Normal AUD
writes do not make those addresses persistent RAM.

SH7055 `RAMER` can overlap physical RAM `0xFFFF6000--0xFFFF6FFF` onto exactly one 4 KiB flash
erase block, but only one of EB0--EB7 (`0x0000--0x7FFF`). It cannot overlay the high calibration
pages used by this ROM. Worse, D2WD610H already uses that physical 4 KiB RAM; `0xFFFF6004` is a
known computed jump-table/buffer base and the existing RAM audit has not proven the block free.
Enabling RAMER would alias live ECU RAM and corrupt normal operation.

The stock `flash_ram_emulation_disable` function also explicitly writes `RAMER=0` during startup.
RAMER is therefore a useful SH7055 capability but **not a safe shortcut for this stock firmware**.

### Feasible live-calibration design

A later ECU patch should reserve a small, proven RAM area and redirect only selected calibration
consumers to RAM-backed descriptors/data. The external controller stores the working tune, loads
the shadow after each key-on, and applies only valid bounded changes. Start with the few tables
that matter most during commissioning rather than trying to mirror every flash table.

Possible implementation order:

1. Scalars: injector scale, global fuel multiplier, boost/pressure safety thresholds.
2. One small table at a time, with the axis left in flash and RAM holding only cell data.
3. VE and primary open-loop fueling tables.
4. Selected ignition surfaces only after RAM and update atomicity are solved.

For coherent multi-cell updates, either pause table publication at an ECU task boundary or write a
staging block and atomically switch a pointer/generation word after CRC validation. If enough RAM
for double buffering cannot be proven, keep live writes to individual aligned cells and never
change an axis and its data concurrently.

The lasting tune should still be built by the deterministic repository tooling and flashed with
the engine stopped. Live tuning is a development overlay, not a replacement for a recoverable,
checksummed flash image.

## Commissioning tests

1. Obtain clear top-down photographs of both D2WD610H ECU PCB sides and the full Denso case/PCB
   number.
2. With the ECU unpowered, continuity-map CPU pins 238 and 240--246 to factory pads. Confirm pins
   239/247 separately; never infer them from a similar Subaru ECU.
3. Validate buffer power sequencing with the CPU disconnected or the data buffer disabled.
4. Start AUD at 250 kHz or 500 kHz and read a constant flash longword repeatedly.
5. Read known RAM addresses with the engine stopped, then running:
   - RPM `0xFFFFB544`;
   - MAP `0xFFFFABC4`;
   - IAT `0xFFFFB3B8`;
   - throttle `0xFFFFB314`;
   - committed AVLS mode `0xFFFFCD86`.
6. Compare those values and scalings with K-line logging.
7. Sweep 0.5, 1, 2, 5 and 10 MHz while checking read errors, ready waits, ECU DTCs and task
   timing/jitter.
8. Do not enable writes until the read path has completed soak testing and the RAM allowlist is
   independently reviewed.

## Sources

- [Renesas SH-2E SH7055S F-ZTAT Hardware Manual](https://www.renesas.com/en/document/mah/sh-2e-sh7055s-hardware-manual), especially sections 19, 22.7, 24.2 and 26.3.12.
- [Renesas SH7055 On-Chip I/O Application Note](https://www.renesas.com/en/document/apn/sh7055-chip-io-volume-application-note), appendix A.1 for the HD74HC245 reference circuit and read/write timing.
- [Renesas SH7055MCM E10A Emulator User's Manual](https://www.renesas.com/en/document/mat/sh7055mcm-e10a-emulator-users-manual), for a commercial H-UDI/AUD implementation reference.
- [TI SN74LVC245A](https://www.ti.com/product/SN74LVC245A), 3.3 V bus transceiver with 5.5 V-tolerant inputs and partial-power-down support.
- [TI SN74AHCT125-Q1](https://www.ti.com/product/SN74AHCT125-Q1), automotive-qualified 5 V quad buffer with TTL-compatible inputs.
