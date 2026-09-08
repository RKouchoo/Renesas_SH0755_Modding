# September 8 — throttle-link packet and received fault status

Seven new offline execution groups cover the forty-byte transmit builder,
diagnostic prerequisites, receive validator and received-status filter. No
direct use of repurposed MAF ADC, synthetic airflow/load or wideband outputs
was found in the outgoing message with request and diagnostic inputs fixed.
Received faults can still select the retained final-throttle override. The
engine capture contains neither the frames nor those fault states, so their
actual contribution to the near-stall remains unknown.

Both BINs, the raw capture and logger are unchanged. The repeat rev test
remains withdrawn; this pass establishes no new flash or demonstrated repair.

## Frame path and transport boundary

`30328` constructs twenty big-endian words at C714..C73B. `302B4` submits
them through `C0A4`; startup `30274` uses `C1BA`. The interrupt worker
`BECE`, reached through `542A`, handles the queued transmit buffer at AED6
and received buffers at AF26/AF4E. `306CA` checks AED4, copies twenty words
through `C176` into C73C and invokes validator `30718`.

F00B/F00D accesses identify SCI1 transmit/receive data registers: SCI1 has
base FFFFF008, TDR offset 3 and RDR offset 5 in the
[Renesas SH7055 application note](https://www.renesas.com/en/document/apn/sh7055-chip-io-volume-application-note),
printed page 156. A companion throttle-control endpoint is inferred from
the data; its physical identity, firmware and hardware timing are not
established or simulated. No serial device was opened. Frame counts are
not assigned a duration without tracing/measuring their cadence.

## Transmitted data

| Offset | Source / conversion |
|---|---|
| 00 | Header A55A |
| 02, 04 | Final absolute request C2B4 / 0.030517578125; second word duplicates first |
| 06 | Signed C2BC / 0.030517578125 |
| 08 | Filtered battery B410 / 0.00030517578125 |
| 0A, 0C | 80F0, 80F8 / 0.030517578125 |
| 0E | Raw pedal ADC AB08 |
| 10..16 | C70A/C70C/C70E/C710 words; producers and physical meanings unresolved |
| 18 | Local diagnostic aggregate C712 |
| 19 | Ignition and other retained digital/mode flags |
| 1A..1C | Diagnostic prerequisite bytes C6FE/C6FF/C700 |
| 1D | Further digital/mode flags |
| 1E | 8080 / 0.030517578125 |
| 20 | Driver-request component C2C8 / 0.030517578125 |
| 22 | Pedal offset 8110 / 0.00390625 |
| 24 | RPM B544 / 0.1953125 |
| 26 | Sum of the first nineteen words modulo 65536 |

Native `254C` rounds and saturates unsigned scalar fields to 0..65535;
offset 6 separately truncates and saturates to signed 16-bit. B410 is not
MAF voltage: native `17268` filters battery ABB4 through `2424` using 7395C.
Meanings of other learned/service values are not inferred from scaling alone.

`301EE` sets C712 to 3 when any of five raw diagnostic getters returns 1,
otherwise zero: 8150 bit 0, 81AC bit 0, 81A8 byte == 1, 814C byte == 1,
and the 81A0 field selected through `4244`. `2FFE4` uses
`4711E -> 56E64 -> 56F0C` prerequisite callbacks. Selectors 55..73 are
callback-list selectors, **not DTC descriptor indices**. With 75E02=0,
the used lists return unavailable when a listed diagnostic is active.

The clear-state traversal executes every applicable callback through its
sentinel. Its complete RAM read set is 8134/8138/813C/814C/8150/8194/
81A0/81A8/81AC, received C6F7..C6FD, mode CAAA and the three output bytes
being modified. Unmanaged bits remain intact: with CAAA=1, initial
FF/FF/FF becomes 0C/08/F8. An imposed 8150 bit 0 changes that to CD/08/FC
and sets C712=3. Isolated pedal-pair fault 8134/1 sets C700/4.

The raw diagnostic producers remain partly traced boundaries. Assembly shows:

- `62E50`/814C uses header/checksum errors, AED4 receive state and `30250`.
- `681E4`/81A8 uses AED5 transport status and B72C enable state.
- `654F0`/8150 compares C2B4 with ABD4 through RPM gates and tolerances.
  `7AF0` converts raw AB1A/AB1C into ABD4/ABD8, distinct from AB06 and
  the pedal pair AB08/AB0A.
- `68984`/81AC evaluates D33C..D344 counters. Their `68856` producer
  compares D34C with received C6D8 and uses the prior signed difference;
  D34C's upstream producer is unresolved here.
- `67FCE`/81A0 calls `312CA/F5FE/F6C0`; its physical diagnosis remains
  unresolved.

Thus fixed-input packet independence does not exclude a fault caused by
changed engine behavior, unresolved input producers, stale communication
or an actual throttle-tracking problem. No protection was bypassed.

## Accepted frames and final override

`30718` requires header 5AA5 and the nineteen-word checksum before `30790`.
Mismatch sets C6CD for the header and C6CC for the checksum. Invalid frames
leave decoded values and status history unchanged. Valid decode sets
C6CE=1; the validator itself does not clear an earlier acknowledgment.

Offsets 12..18 feed C6F7..C6FD through `30A2A`, with prior accepted bytes
at C768..C76E. A bit that differs from the previous accepted bit retains
its old output; agreement accepts it. Two matching accepted frames apply a
new state. Invalid frames do not reset this history. Agreement is per bit,
not whole byte. With CAAA=0, a separate adjustment clears C6FD bit 2 and
sets bit 3. Tests fixture the ordinary service selector to zero.

Native `64874` propagates the seven previously traced received fault bits
into D274/40. For normal request 6, fault request 1.5 and learned offset 2,
two fault frames produce final requests 8 then 3.5; two clear frames produce
3.5 then 8. All seven sources run through validator, decoder, aggregator
and final selector. These are imposed faults, not vehicle-log findings.

## Verification

`test_throttle_link_execution.py` passes seven groups on candidate and master:
layout/scaling/checksum; fixed-request sensor independence with positive
controls; native prerequisite/aggregate behavior; exact callback read set;
random per-bit histories; invalid frames; and fault selection/release.
Relevant code/calibration spans are stock-identical. ABI, allowed writes and
bounded execution checks remain active. The longest clear-state prerequisite
fixture takes 3662 interpreted instructions, with an 8000 bound. Ancestor
interpreters now honor their existing configurable bound; defaults remain
2000. Instruction counts are not measured execution times.

Four earlier idle-request/override assertions queried the read counter with
`(address, size)` although its keys are addresses. Corrected address checks
pass all thirteen affected groups; independent changed-input checks remain.
This is a test correction, not a firmware repair. The full master verifier
and seven candidate-integrity groups pass. DBW/dashpot follow-up is recorded
in [the idle-air audit](IDLE_AIR_RECOVERY_AUDIT.md#dbw-tables-and-dashpot-follow-up).
