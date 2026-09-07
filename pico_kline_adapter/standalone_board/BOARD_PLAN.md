# Standalone Pico K-line board plan

Status: architecture and schematic-entry plan only. This is **not yet a
build-approved schematic or an ECU-write-qualified adapter**.

For the lower-cost hand-wired development version using parts recovered from
the AD310, see [LM2903_PROTO.md](LM2903_PROTO.md). That circuit identifies U7
and gives exact component values and assembly tests; it is not the production
alternative to L9637D.

For the current all-Jaycar, through-hole circuit, see
[JAYCAR_FAST_KLINE.md](JAYCAR_FAST_KLINE.md). It deliberately favours a fast,
inexpensive BF469/LM393 signal path over the protection and fault containment
specified for the production architecture below.

## Goal

Replace the salvaged ANCEL AD310 electronics with a small purpose-built board
that:

- accepts a Raspberry Pi Pico as the USB/firmware module;
- connects only OBD battery, grounds, and Subaru K-line;
- presents the same raw USB CDC serial interface used by the current firmware;
- is electrically passive on K-line when the Pico/USB side is unpowered;
- supports logging, repeatable ROM reads, and eventually ECU writes; and
- uses hand-solderable parts and visible test points.

The first board should remain K-line only. J2534/OpenPort emulation, CAN, an
on-board display, and vehicle-powered standalone operation are separate future
projects.

## Recommended architecture

```text
 Mac/PC USB
     |
 Raspberry Pi Pico (USB CDC bridge)
     | 3V3       GP4/TX       GP5/RX
     |             |             ^
     +-------------+-------------+
                   |
             ST L9637D
          VCC=3V3, VS=protected VBAT
                   |
        protected bidirectional K-line
                   |
           OBD-II pin 7 / ECU

 OBD pin 16 --> transient-limited VS supply for L9637D only
 OBD pins 4/5 --> board ground --> Pico ground
```

The Pico remains USB-powered in revision A. OBD pin 16 does **not** power the
Pico, so there is no second 5 V source to back-feed into USB or Pico VBUS. It is
used only as the battery-referenced `VS` supply required by the K-line
transceiver.

## K-line transceiver

Use an `E-L9637D` in SO-8. ST lists it as an active automotive-grade ISO 9141
interface. Its relevant characteristics are:

- `VS` operating range 4.5--36 V, with 40 V transient rating;
- `VCC` operating range 3--7 V;
- TTL-compatible `TX`, with a guaranteed high threshold of 2.5 V;
- `RX` has an internal pull-up to `VCC`;
- K output current limiting and thermal shutdown; and
- K-line output is off when `TX` is open or the logic supply is absent.

Supplying `VCC` from Pico `3V3` therefore keeps both `TX` and `RX` in the RP2040
logic domain without the AD310 voltage divider. The L9637D data sheet describes
operation above 50 kbaud, but Subaru's 62,500-baud flashing phase must be
qualified on the assembled board before any ECU write.

Do not substitute the similar NXP `MC33290` in the production design: NXP marks
it archived/discontinued.

## Preliminary net list

| L9637D pin | Name | Revision-A connection |
|---:|---|---|
| 1 | RX | Through 1 kOhm series resistor to Pico `GP5` |
| 2 | LO | No connect; expose a small test pad only |
| 3 | VCC | Pico `3V3`, with 100 nF ceramic at the pin |
| 4 | TX | Through 1 kOhm series resistor from Pico `GP4` |
| 5 | GND | Board ground plane |
| 6 | K | OBD pin 7 through a zero-ohm configuration link; protection at connector |
| 7 | VS | Protected/filtered OBD pin 16 supply |
| 8 | LI | No connect; expose a small test pad only |

OBD connector nets:

| OBD-II pin | Signal | Board treatment |
|---:|---|---|
| 4 | Chassis ground | Separate zero-ohm link to board ground |
| 5 | Signal ground | Default-populated zero-ohm link to board ground |
| 7 | K-line | Direct to K-line protection, then L9637D pin 6 |
| 16 | Battery | Input protection, then L9637D `VS` only |

Use a locking four-way harness connector between the PCB and a replaceable OBD
cable rather than putting a bulky OBD plug directly on the PCB. Keep an
unpopulated 4-pin 2.54 mm bench header carrying the same four nets.

## Protection and support circuitry

The schematic should include footprints for all of the following:

1. A small replaceable or resettable input fuse from OBD pin 16.
2. A pulse-rated series element and automotive TVS on `VS`. Exact values must
   be selected from an ISO 7637-2/ISO 16750-2 transient calculation; the
   L9637D's 40 V transient limit must not be exceeded.
3. Reverse-current/polarity protection on `VS`, even though L9637D itself has
   limited reverse-battery protection.
4. An automotive single-line ESD suppressor adjacent to the K-line connector.
   `ESDLIN1524BJ` is a sensible schematic candidate because it is AEC-Q101,
   has +24 V stand-off for jump-start conditions, and targets automotive
   single-wire buses. It still needs verification against the K-line waveform.
5. `100 nF` ceramic decoupling directly at L9637D `VCC` and `VS`, plus a
   footprint for modest local bulk capacitance on `3V3`.
6. An optional, normally unpopulated `510 Ohm` K-to-`VS` pull-up footprint.
   The vehicle already pulls K-line high; fit this only if scope testing shows
   it is required. The L9637D application material uses 510 Ohm in its example.
7. One-kilohm series resistors on Pico `TX` and `RX` to limit accidental GPIO
   fault current without affecting these baud rates.

Do not finalize the `VS` TVS, series limiter, or fuse solely from this document.
Vehicle load-dump energy is materially greater than connector ESD, and the
three components must be selected as one protection network.

## Pico connections

| Pico signal | Connection |
|---|---|
| `GP4 / UART1 TX` | L9637D `TX` through 1 kOhm |
| `GP5 / UART1 RX` | L9637D `RX` through 1 kOhm |
| `3V3 OUT` | L9637D `VCC` only |
| `GND` | Board/OBD ground |
| `GP1` | Unused on the standalone board |
| `RUN`, `SWCLK`, `SWDIO` | Labeled test pads |

Use the official Pico castellated-module footprint, with the USB connector at
the PCB edge and its underside connector/test-pad keep-outs respected.

## Firmware changes for this board

The existing AD310 firmware cannot be used unchanged because its output is
inverted for Q5 and it drives `GP1` to reset the scanner MCU. Add a second build
target with hardware configuration separated from transport logic:

```c
#define KLINE_TX_INVERTED 0
#define HAS_TARGET_RESET  0
```

For L9637D, normal UART polarity is correct: UART idle/high makes `TX` high and
leaves K-line recessive; a UART start-bit/low pulls K-line dominant. Preserve:

- the raw USB CDC interface and stable serial number;
- 4,800, 9,600, 15,625 and 62,500 baud support;
- local echo;
- timed and indefinite USB break handling;
- the one-second RP2040 watchdog; and
- safe behavior on USB detach, suspend, and firmware reset.

At power-up the RP2040 TX pin is high impedance. L9637D's internal TX pull-up
must keep K-line off until firmware assigns the UART. Confirm this on the scope
rather than relying only on the data sheet.

## Physical design

- Two-layer PCB is sufficient; target approximately 60 x 30 mm.
- Prefer 0805 passives, SO-8 L9637D, and other hand-solderable packages.
- Put the vehicle connector, fuse, TVS, and K-line ESD device at one end.
- Put the Pico USB connector at the opposite board edge.
- Keep the unprotected connector traces short and outside the protected logic
  area.
- Give transient suppressors a short, direct return to the OBD-ground entry;
  do not route their surge current through Pico ground traces.
- Provide labeled test points for `VBAT_RAW`, `VS_PROTECTED`, `K`, `TX`, `RX`,
  `3V3`, and `GND`.
- Add separate `USB`, `K-RX`, and `K-TX` indicators only if their loads cannot
  alter the bus or timing. Firmware-driven LEDs are preferable to loading K.
- Use mounting holes and an insulating enclosure; no exposed board should be
  loose in the driver's footwell.

## Build stages and acceptance gates

### Stage 1: schematic review

- Complete ERC with no unexplained power or unconnected-pin warnings.
- Verify every SO-8 pin against the ST top-view pinout.
- Calculate the full OBD pin-16 protection network for cold crank, jump start,
  reverse battery, and load dump.
- Confirm that no path can feed OBD battery voltage into Pico GPIO, `3V3`,
  `VSYS`, or USB VBUS.

### Stage 2: unpowered and USB-only tests

- Check for shorts between K, battery, USB VBUS, `3V3`, and ground.
- With USB only, require `VCC = 3.3 V`, `TX = high`, and no voltage driven onto
  the disconnected K-line harness.
- Reset and reflash the Pico repeatedly while watching L9637D `TX`.

### Stage 3: current-limited bench K-line

- Apply 12--14 V to `VS` from a current-limited supply.
- Use a representative external K-line pull-up/load.
- Scope `TX`, K, and `RX` during loopback at 4,800, 15,625, and 62,500 baud.
- Require correct idle state, local echo, clean thresholds, and no truncated
  bits at 62,500 baud.
- Test USB unplug, Pico reset, firmware watchdog reset, and host suspend. Every
  case must release K-line high.

### Stage 4: read-only vehicle test

- Connect with ignition off, then power USB, then enable ignition.
- Confirm K-line idle voltage before opening software.
- Read ECU identity using SSM and run a stationary RomRaider log.
- Verify error-free extended logging before attempting ROM access.

### Stage 5: flashing qualification

- Make at least two complete FastECU ROM reads and require byte-identical
  outputs.
- Compare a stock read against the project's canonical stock-ROM hash where
  applicable.
- Pass FastECU test-write/voltage checks.
- Repeat while gently moving both cables to expose connector faults.
- Only then consider a real write, with a charged battery and the laptop not
  dependent on a mains-powered ground path.

## Future revisions

After revision A is proven:

- integrate RP2040, flash, clock, USB-C, ESD, and SWD directly on the PCB;
- add an automotive-protected vehicle-power option with deliberate USB power
  OR-ing, rather than simply connecting OBD power to Pico VBUS;
- consider galvanic USB isolation if mains-ground loops become a real issue;
- add CAN only as a separately verified interface with a CAN controller and an
  automotive transceiver; RP2040 does not contain a native CAN controller; and
- retain the revision-A K-line-only layout as the simpler known-good flashing
  tool.

## Primary references

- [ST L9637 product page](https://www.st.com/en/automotive-analog-and-power/l9637.html)
- [ST L9637 data sheet](https://www.st.com/resource/en/datasheet/l9637.pdf)
- [Raspberry Pi: Hardware design with RP2040](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf)
- [ST ESDLIN1524BJ product page](https://www.st.com/en/protections-and-emi-filters/esdlin1524bj.html)
- [TI automotive battery-input protection reference design](https://www.ti.com/tool/TIDA-01167)
- [NXP MC33290 archived product page](https://www.nxp.com/products/MC33290)
