# Jaycar fast K-line point-to-point wiring guide

2026-09-07 diagnostic exception: a temporary 940 Ohm pull-up test adds two
470 Ohm resistors in series from raw OBD16 to K_INT/BF469 collector. This
additional resistor branch is not drawn in the revision-A SVG. Follow the
[temporary test instructions](JAYCAR_FAST_KLINE.md#temporary-k-line-pull-up-test)
for that test; the original R4 reference branch stays fitted. No successful
test result has yet been recorded.

This is the build guide for the all-Jaycar discrete K-line interface. The
drawing is one continuous, deliberately spread-out circuit: there are no
duplicated net terminals between separate sections. Each resistor box contains
its value and colour-band names. The junction list underneath is a second check
of every connection.

![Point-to-point K-line wiring diagram](JAYCAR_FAST_KLINE_WIRING.svg)

The electrical design remains documented in
[JAYCAR_FAST_KLINE.md](JAYCAR_FAST_KLINE.md). If this guide and the electrical
schematic ever disagree, stop rather than guessing.

## Before placing parts

- Put the LM393 notch upward. Pin 1 is then at the upper left and numbering runs
  anticlockwise.
- View the BF469 as shown in its data sheet: body face visible, leads downward.
  Left-to-right it is pin 1 emitter, pin 2 collector, pin 3 base. The mounting
  tab is also the collector.
- The stripe on the BAT46 is its cathode. The stripe goes to `K_INT`/BF469 pin
  2, not to the base.
- The HP9570 board has groups of five holes and long power rails already joined
  by copper. Check every intended pad with continuity mode. Do not assume
  adjacent holes are isolated.
- Use an 8-pin socket for the LM393 and leave the IC out until the unpowered
  continuity checks pass.

## Junction-by-junction list

Each bullet below describes one electrical junction. Everything named in a
single bullet must be connected together.

1. **Ground:** Pico physical pin 8 (`GND`), OBD pin 5, LM393 pins 3 and 4,
   BF469 pin 1, one end each of R3/R5/R9, one side of C1, and all three
   external LED cathodes/short legs. Leave OBD pin 4 disconnected initially.
2. **USB 5 V:** Pico physical pin 40 (`VBUS`), LM393 pin 8, and the other side
   of C1. C1 must sit beside LM393 pins 8 and 4.
3. **K-line entrance:** OBD pin 7 to one end of R1 (`22 Ohm`).
4. **K_INT:** the other end of R1, BF469 pin 2/collector, one end of R2
   (`47 kOhm`), and the striped end of the BAT46.
5. **K_SENSE:** the other end of R2, LM393 pin 5, one end of R3 (`4.7 kOhm`),
   and one end of R7 (`470 kOhm`).
6. **VREF:** OBD pin 16 through R4 (`100 kOhm`) to a junction containing
   LM393 pins 2 and 6 plus one end of R5 (`4.7 kOhm`). OBD pin 16 connects to
   nothing else.
7. **K_RX:** LM393 pin 7, Pico physical pin 7 (`GP5`), one end of R6
   (`4.7 kOhm`), and the other end of R7.
8. **3.3 V pull-up:** Pico physical pin 36 (`3V3 OUT`) to the other end of R6.
9. **TX/base:** Pico physical pin 6 (`GP4`) through R8 (`470 Ohm`) to a
   junction containing BF469 pin 3/base, one end of R9 (`10 kOhm`), and the
   unstriped end of the BAT46.
10. **Unused output:** LM393 pin 1 is not connected.
11. **TX LED:** Pico physical pin 32 (`GP27`) through R10 (`1 kOhm`) to the
    LED anode/long leg. Its cathode/short leg joins ground.
12. **RX LED:** Pico physical pin 31 (`GP26`) through R11 (`1 kOhm`) to the
    LED anode/long leg. Its cathode/short leg joins ground.
13. **Status/error LED:** Pico physical pin 4 (`GP2`) through R12 (`1 kOhm`)
    to the LED anode/long leg. Its cathode/short leg joins ground. This LED
    mirrors the Pico's onboard LED.

All three external LEDs are optional. A 10 kOhm series resistor is safe in any
of these positions but makes the corresponding LED very dim.

Resistors and the 100 nF ceramic capacitor are not polarized.

## Resistor colours

- R1, 22 Ohm, 5% carbon film: red, red, black, gold.
- R2, 47 kOhm, 1% metal film: yellow, violet, black, red, brown.
- R3/R5/R6, 4.7 kOhm, 1% metal film: yellow, violet, black, brown, brown.
- R4, 100 kOhm, 1% metal film: brown, black, black, orange, brown.
- R7, 470 kOhm, 1% metal film: yellow, violet, black, orange, brown.
- R8, 470 Ohm, 1% metal film: yellow, violet, black, black, brown.
- R9, 10 kOhm, 1% metal film: brown, black, black, red, brown.
- R10/R11/R12, 1 kOhm, 1% metal film: brown, black, black, brown, brown.

R1 has four bands because the specified Jaycar `RR2534` is a 5% carbon-film
part. The other specified Jaycar resistors are five-band 1% metal-film parts.
Measure every resistor before soldering even when its colours appear correct.

## Unpowered checks

Do these with USB and OBD both disconnected and the LM393 removed from its
socket:

1. Confirm every ground point is below 1 Ohm to Pico pin 8.
2. Confirm Pico `VBUS`, Pico `3V3`, `K_INT`, `K_SENSE`, and `VREF` are not
   shorted to ground.
3. Confirm OBD pin 7 to `K_INT` is approximately 22 Ohm.
4. Confirm OBD pin 16 reaches `VREF` only through approximately 100 kOhm.
5. Confirm the BF469 metal tab has continuity to pin 2 and no continuity to
   pins 1 or 3.
6. Confirm the BAT46 striped end reaches BF469 pin 2 and its unstriped end
   reaches BF469 pin 3.
7. Check adjacent LM393 socket pins are not accidentally joined by the
   protoboard copper.

## First power-up

1. Leave OBD disconnected. Insert the LM393, connect Pico USB, and confirm
   approximately 5 V between LM393 pins 8 and 4.
2. Confirm LM393 pin 7 and Pico GP5 never exceed 3.3 V.
3. Disconnect USB before attaching the OBD cable.
4. Attach OBD pins 5, 7 and 16 with ignition off. Reconnect USB, then turn the
   ignition on.
5. Before sending data, confirm OBD pin 7 remains approximately 11--14.5 V.
   A low K-line at idle means the circuit is miswired; switch it off.

Do not attempt an ECU write until read-only identity, loopback and two
byte-identical full-ROM reads have passed.
