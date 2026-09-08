# K-line adapter test — 2026-09-07

## Current result after fitting the pull-up

The sections below this summary preserve the day's diagnostic chronology.
Earlier statements that the pull-up was not installed or that no ECU bytes
were received describe the pre-pull-up state and are superseded by this
result. They are not the current commissioning status.

The user installed two 470 Ohm resistors in series, 940 Ohm total, from raw
OBD pin 16 to K_INT/BF469 collector. Communication then worked with the same
version 1.1.2 Pico firmware. The user-reported installation and successful
traffic support the missing tester-side bus bias as the cause of the
remaining no-communication fault. No new physical voltage measurements were
made; digital GPIO reports and serial traffic are not substitute voltmeter
readings. Current hardware remains the standalone Jaycar LM393/BF469 board,
not the old AD310 circuit implied by the USB product name.

### Native macOS FastECU read and independent CRC checks

One complete 524,288-byte read was saved as
`/Users/regan/Dev/read_image_2026-09-07_20h22m17s.bin`.

- SHA-256:
  `f3efa36f8e3bef4e1eaa68544d0c1bc0578c6dbc53e7a13f87e08f8dcba01e6d`.
- Stored and calculated Subaru image checksum both equal `0xC96A0526`.
- Four recorded sets of all 16 ECU flash-block CRCs independently match
  this saved read, using FastECU's custom CRC32 polynomial `0x5AA5A55A`
  with initial and final XOR `0xFFFFFFFF`, not ordinary ZIP/zlib CRC32.
- The blocks are eight 4 KiB blocks over `0x00000..0x07FFF`, one 32 KiB
  block over `0x08000..0x0FFFF`, and seven 64 KiB blocks over
  `0x10000..0x7FFFF`. They are not sixteen equal-size blocks.

The source capture is
`/Users/regan/.config/FastECU/0.1.0-beta.5/syslogs/log_fastecu_2026-09-07_20h16m32s.txt`.
The four CRC sets precede the saved read; they were compared with it offline.
FastECU's original `IMG CRC` comparison reported a difference in block 15
because the image loaded for the attempted test write differed from the ECU.
The independently computed saved-read CRC for that block is `0xFDF541B3`,
matching the ECU replies in all four sets. This does not establish that two
separate full reads were captured; only one full read is recorded.

### Native macOS RomRaider connection

Checksum-valid ECU identity and RPM responses were obtained. RomRaider's
`Expected: 80. Actual: 00` failure occurred with a request registering 89 byte
addresses, above the 84-address SSM request limit. Hidden/retained selections
across Data and Dashboard contributed; selecting only RPM in one view did
not clear the other registered values. The saved
[RPM-only test profile](romraider_rpm_only_profile.xml) clears the other views,
and the user confirmed that it connects and works in native macOS RomRaider.
The full idle diagnostic profile is not thereby validated; request size must
be reduced or split before using that complete selection. A VM is not needed
to fix this demonstrated profile failure.

September 8 follow-up: the generic 84-address protocol limit above is not
the target ECU's receive limit. Native routine `32CA4` accepts at most
**43 byte addresses**. Separate idle/after-start profiles now each fit this
limit. A second fault in RomRaider's queued channel selection was repaired
locally. After restarting the application, the 12:36 capture contains all
22 idle channels in 1,786 complete rows, with valid full-size ECU responses.
This validates the core profile on the existing adapter; the after-start
profile is checked offline only. See the
[logger connection audit](../master_patch/LOGGER_CONNECTION_AUDIT.md).

### Earlier flash test failure — superseded by the 21:17 pass below

The existing 350 nm flash-driver kernel responds to `FLASH_DISABLE` (`0x21`)
with the valid negative-response frame `BE EF 00 03 7F 21 06 56`. This is a
kernel-side flash initialization failure, not missing K-line echo or the
RomRaider profile issue. The trace stops before erase/programming. The
replacement SH7055 180 nm RAM kernel was built, checked offline and installed
under a separate profile. The later 21:17 attempt below successfully exercised
that replacement in the ECU. Actual erase/programming remains untested. See
[FastECU kernel work](fastecu/README.md) for build/review details.

### 21:02 retest: generic profile still selected

`log_fastecu_2026-09-07_21h01m21s.txt` starts with profile ID 14,
Forester XT / `sub_ecu_denso_sh7055_04`. The ROM opened without a matching
definition and retained this selection; no dedicated-profile selection is
recorded. At 21:02:01 the operation explicitly names the generic
`ssmk_kline_sh7055.bin`, which uploads and reports its old `v1.00` identity.
It again rejects test-mode initialization with `7F 21 06`, before any erase.
This is not a live test of the new 180nm kernel. Source inspection confirms
the Test Write button does not itself force generic mode in this case.

Use the toolbar **Select protocol** button after loading/selecting the ROM,
choose `sub_ecu_denso_sh7055_04_d2wd610h_180`, and confirm the selection. With
this failed test stopped and no actual erase/write attempted, allow the ECU
to power down before restarting ignition to remove the old running RAM kernel.
Retry only Test Write and verify the exact dedicated filename and runtime ID.

### 21:17 retest: dedicated 180nm Test Write PASS

Source: `log_fastecu_2026-09-07_21h14m56s.txt`. Earlier attempts at 21:16:38
and 21:16:46 correctly rejected reuse of the still-running generic kernel.
The subsequent 21:17:01 attempt uploaded the dedicated image and received
`FastECU SH7055 180nm D2WD610H K-Line v1.01` at 21:17:13.059.

Test-mode initialization (`21`) received a valid positive reply
`BE EF 00 01 61 0F` at 21:17:16.784. The differing 64 KiB block at `00070000`
completed RAM-buffer transfer and CRC validation. Final Test Write PASS:
21:17:44.672. All ECU block CRCs were unchanged before/after; block 15 remained
ECU `FDF541B3` versus target `BA57B368`, as expected for a non-programming test.

The inherited `(EE) Flash mode succesfully set` line is mislabeled severity,
not an error response. Likewise "Erasing ... erased" describes an erase
request that the reviewed kernel's test-mode protection turns into a no-op.
Do not infer an actual flash erase from those host strings. Actual flash
programming and a post-write full read-back are still outstanding.

### Existing master target versus the saved ECU read

The read-only command `python3 -B master_patch/verify_master_patch.py` passes
the deterministic in-memory build comparison, layout/hook/executable checks,
calibration policies, definitions/logger checks and stock/SRF provenance.
It does not write a rebuilt image. The existing target is 524,288 bytes:

- File: `master_patch/D2WD610H_master_patch.bin`.
- SHA-256:
  `7d81124d372fff0c79df6a58b2b26563d2bb71ed85431c5416bbd5ba6fbf3198`.
- Stored and calculated Subaru checksum: `0xBBC99ED4`.
- Root stock SHA-256 remains
  `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee`;
  the base copy and extracted original SRF payload remain byte-identical.

Exactly 224 bytes differ from the saved ECU read, entirely within these
calibration fields. Ranges below encompass complete affected float cells,
including bytes within those cells that did not change.

| Field | Float/data range | Changed bytes |
|---|---|---:|
| IAT voltage axis, all 30 floats | `0x72960..0x729D7` | 100 |
| Low-lift VE, 800 RPM | `0x7E720..0x7E747` | 30 |
| Low-lift VE, 1200 RPM | `0x7E754..0x7E77B` | 30 |
| Low-lift VE, 1600 RPM | `0x7E788..0x7E7AF` | 30 |
| Low-lift VE, 2000 RPM | `0x7E7BC..0x7E7E3` | 30 |
| Subaru checksum | `0x7FB88..0x7FB8B` | 4 |

Every other byte is identical, including executable code, hooks, high-lift
VE, ignition timing, injectors, boost and safety settings. The IAT change
replaces a curve assuming a 2.49 kOhm ECU pull-up with one assuming 1.00 kOhm;
the installed pull-up has not been validated by this audit. Each affected VE
row changes ten MAP columns, 150 through 1050 mmHg absolute. The ECU table
matches the original seed; the target adds 0.675..6.75% at 800/2000 RPM and
2.7..27% at 1200/1600 RPM, with unchanged high-lift data. These are provisional
calibration changes. Structural/checksum success does not certify safe engine
operation, correct installed sensor scaling or a validated flashing path.

## Historical diagnostic chronology — before the pull-up

### Live result before the startup fix

The Mac detected the Pico CDC device at `/dev/cu.usbmodem3101`, USB VID/PID
`2e8a:000a`, serial `E46340134F22472C`. Its product name still says
`Pico AD310 K-Line`; the current hardware design is the Jaycar LM393/BF469
circuit. No ECU flash writes were performed.

FastECU's 18:36:59–18:37:13 AEST read attempt opened the call-out serial port
at 4800 baud, changed to 62500 for a kernel-ID request, and returned to 4800
for SSM identification. Neither request produced the expected local echo or
an ECU reply. Selecting the macOS call-out endpoint did not resolve this fault.

A separate Python standard-library POSIX serial test opened the same port
exclusively, configured raw 4800 8N1 with no flow control or terminal echo, and
sent only `80 10 F0 01 BF 40` (the same SSM identification request used by
FastECU). Three attempts, with three-second receive windows, each accepted
all six transmit bytes and returned zero received bytes.

Two further three-attempt batches, first with explicit DTR/RTS and break
release and then with a 25 ms break followed by release, also returned zero
bytes. These host operations do not prove that the firmware received a USB
break callback. The serial port was released after each batch.

The user observed TX activity when sending and occasional RX LED flashes.
TX activity confirms that host bytes reached the firmware's UART transmit
path. Occasional RX activity alone does not establish valid echo or ECU
responses. The host did not receive a complete byte during these captures.

### Confirmed firmware defect and correction

Version 1.1.0 initialized GP4 in this order:

1. `gpio_set_outover(GP4, GPIO_OVERRIDE_INVERT)`.
2. `gpio_set_function(GP4, GPIO_FUNC_UART)`.

The actual Pico SDK 2.3.0 implementation in
`src/rp2_common/hardware_gpio/gpio.c` explicitly clears all GPIO overrides in
`gpio_set_function()`. The earlier release's disassembly also confirmed the
two calls in this order. This leaves normal UART polarity after cold startup:
idle-high GP4 turns on the external NPN and can hold K-line low.

Version 1.1.1 replaces those two calls with one atomic masked update of
GPIO4 CTRL, applying FUNCSEL=UART and OUTOVER=INVERT together. GP4 begins as
a pulled-down SIO input and switches directly to inverted UART output. There
is no intervening uninverted UART output and no subsequent function selection
on GP4 that could clear the inversion. The initialized CTRL value is `0x102`.

Validation:

- Pico SDK 2.3.0 / Arm GCC build passed with the project's warnings-as-errors.
- The compiled startup sequence was inspected: the CTRL update applies
  `0x102` with the combined field mask, using the RP2040 atomic XOR alias.
- `picotool info` identifies the resulting UF2 as version `1.1.1`, RP2040.
- Tested 1.1.1 UF2 SHA-256:
  `8d645346b5b91bf1a728b5032c63707254f051f040538154f968c26ea595665f`.
- Previous 1.1.0 UF2 SHA-256:
  `ded65e8cffdc921d1914019c4dd713c125f3ee7af5409a84ab03940f896821f3`.

### Installation and post-fix retest

Version 1.1.1 was copied successfully to the `RPI-RP2` BOOTSEL volume on
2026-09-07. The volume disappeared and the Pico re-enumerated as
`/dev/cu.usbmodem3101` with the same USB serial number `E46340134F22472C`.
The copied artifact had the 1.1.1 SHA-256 recorded above. This confirms upload
and reboot, not an independent flash read-back or ECU communication test.

At 18:47:34 AEST, after the user confirmed the car was ready, three more
exclusive raw-serial SSM identity requests were sent at 4800 8N1, with DTR/RTS
asserted and no break request. Each write accepted all six request bytes.
Each three-second receive window returned zero bytes: no local echo and no
checksum-valid ECU response. The port was released after the test.

The startup defect is corrected in the uploaded firmware, but the unchanged
live result proves it was not sufficient to restore communication. The next
diagnostic is idle voltage measurement at GP4, GP5, and OBD pin 7 before
attempting further serial traffic. A physical-layer fault has not yet been
isolated, and the remaining issue must not be attributed to either FastECU
or the wiring without further evidence.

### Idle electrical checks

For the current Jaycar circuit, GP4 is Pico physical pin 6 and GP5 is physical
pin 7. GP5 connects directly to LM393 pin 7; the old AD310 two-resistor receive
divider is not part of this circuit. At powered idle, relative to common
ground, expect GP4 near 0 V, GP5/LM393 pin 7 near 3.3 V, LM393 pin 8 near 5 V,
and OBD pin 7 near battery voltage. Valid local echo should reproduce the
six transmitted bytes before the ECU reply.

Full ROM reads and flashing remain unvalidated.

### Meter-free diagnostic firmware prepared

With voltage measurements unavailable, version 1.1.2 adds read-only status
reporting over USB endpoint zero. It exposes GPIO4/GPIO5 digital levels,
GPIO control registers, actual baud, queue counts, UART error flags and byte
counters. No diagnostic text is inserted into the serial data stream, and
the status request does not send anything to the ECU.

The native Mac libusb library successfully read the connected 1.1.1 Pico's
standard USB device descriptor without claiming an interface or detaching the
CDC driver. Version 1.1.2 then built with warnings-as-errors, and the resulting
ELF contains the strong diagnostic callback and KLD1/version constants.
Its UF2 identifies as version 1.1.2 with SHA-256
`f04d6d916b6c4ecddfa73489b07ebda79c2cc53a3d66caea63f8558cfed8c65f`.
The reader's offline packet validation tests passed. A subsequent read while
the Pico was in BOOTSEL correctly reported that no matching CDC device was
present. Version 1.1.2 was then copied to the BOOTSEL volume and successfully
re-enumerated. Three live status reads decoded the reported version as 1.1.2,
TX GPIO CTRL `0x102`, RX GPIO CTRL `0x2`, requested baud 4800 and actual baud
4799 (the SDK divisor result, approximately 0.021% low). USB was mounted and
ready, with no active break or pending line coding.

The initial snapshots reported GP4 low and GP5 low. The UART had counted one
receive byte and one error event, with RSR bits `0x5` (framing plus break).
USB queued bytes were zero; a startup byte received before USB mount can be
discarded by the normal bridge. No host or UART transmit bytes had occurred.
These samples were taken immediately after BOOTSEL upload, before confirmation
that OBD had been reconnected. They validate diagnostic reporting and corrected
TX startup, but do not yet establish the powered vehicle's RX idle state.
See [DIAGNOSTICS.md](DIAGNOSTICS.md).

### Powered-car diagnostic result

After the user confirmed OBD reconnected and ignition on, the 1.1.2 status
report still sampled GP4 low and GP5 low at idle. USB was mounted/ready,
DTR/RTS asserted after serial open, and neither break nor pending baud changes
were active. GPIO CTRL values remained TX `0x102` and RX `0x2`.

One normal six-byte SSM identity request produced these counter changes:

| Counter | Increase |
|---|---:|
| Host bytes received by Pico | 6 |
| Bytes written to UART TX | 6 |
| Bytes decoded by UART RX | 0 |
| Bytes queued for USB return | 0 |
| Error events during this request | 0 |

The only RX byte/error was the prior startup event; the Mac received no serial
data. Software queues were empty after the request. This locates the observed
failure before successful UART reception, rather than an RX byte being lost
while forwarding it from the Pico to the Mac.

A second identity request was sampled with 25 read-only GPIO status snapshots
over approximately 36 ms. GP4 sampled high six times during transmission and
returned low; GP5 sampled low in all 25 snapshots. UART TX increased by six
again, UART RX by zero, and the host received no data. These sparse digital
samples establish that the Pico TX pad is switching; they do not establish
the voltage or waveform at the external K-line node.

The user confirmed that R2's nominal 47 kOhm was replaced by two 100 kOhm
resistors in parallel, giving nominal 50 kOhm. This is a suitable substitution;
a mistaken series combination is not the reported configuration. Actual
connections and component values have not been measured. The next visual check
is the direct LM393 pin-7-to-GP5 connection and its 4.7-kOhm pull-up to Pico
3.3 V. GP5 being low does not by itself isolate comparator wiring, missing
pull-up, ground, K-line supply, or transistor faults.

### User-reported wiring checks after the low-RX result

With voltage measurements unavailable, the user traced the following
connections. These reports match the intended netlist; they are not
continuity, voltage, component-value, or solder-joint measurements:

- R2 is two 100-kOhm resistors in parallel (nominal 50 kOhm).
- LM393 pin 7 connects to GP5 and a resistor to Pico 3.3 V. Its connection to
  the 50-kOhm sense junction is through the 470-kOhm feedback resistor, not a
  direct wire.
- LM393 pin 5 connects to the 50-kOhm sense junction.
- LM393 pins 6 and 2 share the 100-kOhm / 4.7-kOhm reference junction fed from
  OBD pin 16.
- LM393 pin 4 connects to ground; pin 8 connects to VBUS and the bypass
  capacitor to ground.
- The BAT46 stripe connects to the BF469 middle leg/collector; the unstriped
  end connects to BF469 pin 3/base.

The remaining fault is not identified by these reports. Clear board photos
can help check resistor bands, component orientation and visible solder
bridges while electrical measurements are unavailable. The actual vehicle
K-line idle voltage, comparator input voltages, and output pull-up continuity
remain unverified.

### Photo inspection and K-line bias review

Reviewed the user-supplied component-side photo
`D1CD2932-B834-4A32-90C8-0994B05A1261_1_102_o.jpeg` and underside photo
`EA865099-F8FC-466C-8453-44205C39675E_1_102_o.jpeg`. Inspection crops were made
only in `/tmp`; original photos were unchanged.

The large series resistor's visible bands are consistent with 22 Ohm, and two
resistors are visibly mounted in parallel as reported for R2. A close crop of
the Pico header supports blue on GP4/TX and green on GP5/RX, with their far
ends routing toward the transistor and comparator respectively. An initial
possible-swap impression from the full photo was not sustained by the crop;
there is no photographic basis to recommend swapping those wires. The exact
joint edges and some component markings are obscured. Neither a specific
short/open connection nor a burnt component was positively identified.

The circuit's lack of a tester-side K-line pull-up remains a design concern.
The earlier approximately 11 V reading was obtained during AD310 work and
does not establish idle voltage with the standalone interface alone. ST's
[L9637 datasheet, Figure 4 and functional description](https://www.st.com/resource/en/datasheet/l9637.pdf)
shows a tester pull-up and discusses external K-to-supply pull-up resistance.
This is reference evidence for bus biasing, not validation of our discrete
circuit or identification of the Subaru's actual internal pull-up.

Illustrative DC calculation with the reported 50-kOhm R2, 4.7-kOhm R3,
470-kOhm R7, 12 V supply, and comparator output initially low:

- If the vehicle supplied a 100-kOhm pull-up, the receive divider would load
  K-line to approximately 4.24 V. Sense voltage would be 0.361 V versus the
  0.539 V reference, leaving RX low despite otherwise correct connections.
- A 1-kOhm tester pull-up in the same idealized model gives approximately
  11.78 V at K and 1.003 V at the sense input, above the reference.

The 100-kOhm vehicle pull-up is an example, not a measured ECU property.
The model excludes faults, leakage, dynamics, and other bus nodes. A controlled
pull-up test is being considered; availability of a spare 1-kOhm resistor rated
at least 0.5 W was requested. No pull-up has yet been fitted or tested, and
neither a design fault nor a wiring fault is conclusively isolated.

The user subsequently confirmed spare original-BOM resistors are available.
The proposed test now uses two 470 Ohm resistors in series (940 Ohm total),
each rated at least 0.5 W, from raw OBD16 to K_INT/BF469 collector. This avoids
assuming a separate 1-kOhm part was bought. The exact temporary configuration
and comparison procedure are recorded in
[standalone_board/JAYCAR_FAST_KLINE.md](standalone_board/JAYCAR_FAST_KLINE.md).
The resistor chain has not yet been confirmed fitted or tested.
