# Master-patch wiring notes

These notes cover the D2WD610H H6DO wiring traced in the 2005 Legacy/Liberty
service-manual set. Multiple market and body diagrams exist, so treat connector
numbers as continuity targets, not permission to splice by colour alone. With
the ECU and all devices unpowered, verify every terminal end-to-end on the
actual car before making a connection.

Service-manual references:

- [Engine electrical-system diagrams](https://subaruport.ru/leg4/leg4_sec3_11-1.pdf)
- [ECM input/output and connector diagrams](https://subaruport.ru/leg4/leg4_sec3_11-2.pdf)

## Former MAF connector B3

| B3 terminal | D2WD610H circuit | ECM terminal | Master-patch use |
|---:|---|---|---|
| 1 | Stock MAF power from the main relay | — | Do not use for the wideband or IAT; isolate. |
| 2 | Airflow signal ground | B136-31 | No wideband connection; insulate. Never connect controller black here. |
| 3 | Airflow signal | B136-23 | Wideband single-ended 0-5 V analog output/white. |
| 4 | Intake-air-temperature signal | B136-13 | Retain for a separate post-intercooler IAT sensor. |
| 5 | Sensor ground | B136-35 | Retain for the IAT sensor return. |

The airflow cable shield terminates at ECM B136-32; it is not a controller power
ground. The old MAF element is removed, but B3-4/B3-5 remain the live factory
IAT circuit. A replacement thermistor must have the stock transfer or its ECU
calibration must be changed before the speed-density result can be trusted.

## Seller-labelled AEM 50-4110 / 30-4110-style controller

The instruction sheet supplied with the purchased unit documents a four-wire,
single-ended controller and a selectable rear calibration switch. This is not
the differential AEM X-Series 30-0300 interface previously assumed by the
project. Use only P0 (AFR display) or P1 (lambda display); their 0-5 V output
tables are identical. P2 and P3 do not match this firmware calibration.

| Wire | Supplied function | Connection |
|---|---|---|
| Red | Gauge and sensor power | Separate switched 10-18 V supply through a 10 A fuse. Do not use B3-1. |
| Black | Gauge and sensor power ground | Clean power/engine ground sized for controller and heater current. Do not use B3-2 or another ECU sensor ground. |
| White | Single-ended 0-5 V analog output | B3-3 / ECM B136-23 only. |
| Blue | Serial output | Not used by this firmware. Insulate it unless its electrical standard is separately verified for an external logger. |

The white output is referenced to controller black, while the ECU measures
B136-23 relative to its own internal sensor-ground domain. Ground the controller
at a clean engine/ECU power-ground location, route white in the retained shielded
signal circuit, and keep it away from injectors, ignition wiring, the boost
solenoid, and exhaust heat. Never join black to B3-2: black also returns gauge
and LSU-heater current, whereas B3-2/B136-31 is a low-current sensor ground.

Before connecting the ECU, power the controller independently and measure
white relative to black. Then, with the controller connected, compare that
reading with B136-23 relative to B136-31 at key-on, warm idle, and with normal
electrical loads operating. Their difference is the installed ground offset and
directly changes the ECU's calculated lambda. The transfer used by firmware is:

```text
gasoline AFR = 2.0 * volts + 10.0
lambda       = (2.0 * volts + 10.0) / 14.64
             = 0.136612... * volts + 0.683060...
accepted     = 0.50 V through 4.50 V inclusive
```

The unit advertises a legitimate 0-5 V output. The narrower accepted window is
a conservative operating plausibility gate corresponding to 11-19 gasoline
AFR, not a controller-health flag. Outside it, firmware inhibits patched
closed-loop feedback and commands zero electronic boost duty. A disconnected,
warming, or failed controller may still produce an in-window voltage, so bench
record its cold, warmed-free-air, and unplugged-sensor outputs before relying on
it. This does not create a fully validated limp-home strategy.

Mount the supplied LSU 4.9-type sensor in the post-turbo downpipe as planned and
follow the supplied orientation, heat, condensation, and harness instructions. Because it is the
only feedback source for both banks, place it upstream of any point where
outside air can enter and account for exhaust transport delay during control
and log analysis.

## Omni Power MAP-SUP-3BR

The H6DO service diagram maps MAP connector E28 as:

| E28 terminal | D2WD610H circuit | ECM terminal |
|---:|---|---|
| 1 | Sensor ground | B136-35 |
| 2 | MAP signal | B136-22 |
| 3 | Sensor supply, nominal 5 V | ECU sensor supply |

The selected [MAP-SUP-3BR](https://www.prospeedracing.com.au/products/omni-power-3-bar-map-sensor-subaru-wrx-sti-97-00-wrx-08-14-lgt-04-09-toyota-supra-93-02-map-sup-3br)
is advertised in an OEM-style direct-fit housing, but its listed applications
do not explicitly include this EZ30R. Confirm connector keying and prove pin 1
ground, pin 3 regulated supply, and pin 2 signal on the vehicle before plugging
it in. Never infer the three terminals from physical order alone.

At key-on/engine-off, logged MAP must agree with a local barometric reference.
Then pressure-test the complete transfer against a regulated reference before
enabling any route into boost.

## Four stock oxygen sensors

Disconnect both original front A/F sensors and both rear narrowband sensors.
Seal and secure every unused connector so neither signal nor heater terminal
can contact ground, battery voltage, the exhaust, or another terminal. The
firmware removes their conversion/monitor tasks and 18 mapped DTC switches, but
does not force the four stock heater output drivers electrically off.

Do not connect the wideband to any original oxygen-sensor signal or heater wire.
Its only ECU connection for this patch is white to former-MAF signal B3-3.

## EVAP output used for the EBCS

The firmware proof identifies the purge PWM peripheral and its single runtime
owner, but the project has not established one universal harness terminal for
all wiring-diagram variants. Identify the original canister-purge solenoid
connector on this exact car by service diagram and continuity, then bench-scope
it before attaching the boost solenoid.

Zero commanded duty must produce minimum boost with the chosen valve plumbing.
For first pressure testing, bypass the solenoid and connect the 45 mm wastegate
directly to the pressure source. Verify the actual purge PWM frequency and the
solenoid's polarity/fail state before putting it in the boost-control path.
