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
| 1 | Stock MAF power from the main relay | — | Do not use for the AEM or IAT; isolate. |
| 2 | Airflow signal ground | B136-31 | AEM analog negative/brown only. |
| 3 | Airflow signal | B136-23 | AEM analog positive/white. |
| 4 | Intake-air-temperature signal | B136-13 | Retain for a separate post-intercooler IAT sensor. |
| 5 | Sensor ground | B136-35 | Retain for the IAT sensor return. |

The airflow cable shield terminates at ECM B136-32; it is not an AEM power
ground. The old MAF element is removed, but B3-4/B3-5 remain the live factory
IAT circuit. A replacement thermistor must have the stock transfer or its ECU
calibration must be changed before the speed-density result can be trusted.

## AEM X-Series 30-0300

The [AEM instruction manual](https://documents.aemelectronics.com/techlibrary_30-0300.pdf)
defines Connector A as follows:

| AEM terminal | Wire | Connection |
|---:|---|---|
| 1 | Red | Separate switched 12 V supply through a 5 A fuse. |
| 2 | Black | Proper controller power/engine ground. |
| 9 | White | 0-5 V analog positive to B3-3 / ECM B136-23. |
| 10 | Brown | 0-5 V analog negative to B3-2 / ECM B136-31. |

The AEM output is differential. The stock MAF ADC is single-ended, so the AEM
brown analog-negative wire goes to the former MAF signal ground. Do not use
B3-2 to power the controller and do not join AEM red to B3-1. Keep the white
and brown signal pair routed together, away from injectors, ignition wiring,
the boost solenoid, and exhaust heat.

Before connecting the ECU, power the controller independently and measure
white relative to brown. Then verify the voltage at B136-23 relative to B136-31
with the controller connected; a ground offset here directly changes commanded
fuel. The AEM transfer used by the firmware is:

```text
lambda = 0.1621 * volts + 0.4990
valid  = 0.50 V through 4.50 V inclusive
```

Below 0.50 V is treated as not ready and above 4.50 V as an error. Either state
inhibits the patched closed-loop feedback and commands zero electronic boost
duty. It does not create a fully validated limp-home strategy.

Mount the Bosch LSU 4.9 in the post-turbo downpipe as planned and follow AEM's
orientation, heat, condensation, and harness instructions. Because it is the
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

Do not connect the AEM to any original oxygen-sensor signal or heater wire. Its
only ECU signal connection for this patch is the former MAF signal pair.

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
