# Fuel-learning airflow ranges and open-loop application

[Reference home](README.md) · [Process-flow audit](PATCH_PROCESS_FLOW.md) · [Tests](../../tests/test_fuel_learning_process_flow.py)

**The earlier claim that v2's 500 g/s boundary guarantees zero learned trim
in boost was incorrect.** The native ROM selects the trim region by airflow,
including when the pressure guard has forced open loop. Moving a boundary
does not erase retained values or stop their application.

## Actual native dependency

`216EA` reads SD airflow `B420` and uses `7616C/76170/76174` to select
`BCD3`. Stock/main boundaries are 5, 10 and 22 g/s; v2 uses 5, 10 and
500 g/s. Running v2 therefore selects region C at 100 g/s. There is no
branch here that substitutes region D because fueling is open loop.

The separate output `BCFE` permits learning only for **2 <= airflow < 52
g/s**, from unchanged `76168/76178`; stopped-state input `BCF1 == 1`
forces region A and clears that permission. Region selection and permission
to acquire a new value must not be conflated.

The bank descriptors `4B2EC/4B314` point to four protected float records
each, `81C0..81DF` and `81E0..81FF`. `20B28` calls the classifier,
qualification stages, bank learning updates and final publication. `21024`
can update the selected record through protected writer `49530`. Its
prerequisites include the separate `20F9C` gate, with **80 <= coolant < 94
C**, airflow permission and other stability/fault conditions.

`21350` still selects the stored record using `BCD3`, filters a significant
change, clamps it to `BCC0/BCC4`, and writes applied corrections
`BCB8/BCBC`. That publication is not cancelled merely because new learning
is ineligible. `1DD04` includes these corrections in bank fuel delivery,
after the primary-target/pressure-guard path. `B7DC`, exported as Final
Fueling Base, excludes these separate bank correction terms.

## Native execution evidence

Five test groups execute saved main, v2 and exact captured v2 instructions,
including lookup helpers and the whole `20B28` pair publisher:

- At 100 g/s, v2 selects C while airflow-learning permission is zero.
- With a valid stored C correction of +12.5% and D at zero, v2 applies
  +12.5% to the fixture's open-loop bank pulses. Stock/main select D at
  the same airflow. Other fuel terms are controlled inputs.
- Crossing 500 g/s selects D and filters the applied transition. An
  existing nonzero D record remains nonzero; the calibration does not
  lock it at zero.
- Starting with zero records and supplied qualifying feedback state,
  native learning acquires signed 0.1% steps. Those values survive the
  subsequent 100 g/s/open-loop transition.
- Every write is checked against the reviewed state/record extents,
  alongside the native calling-convention checks.

These are conditional software results, not recovered trims from the car.
The sustained September 12 bog at 77–85.25 seconds has logged coolant
66–67 C, below the native learning gate. It contains no `BCB8/BCBC` or
retained-record capture. A prior correction is unmeasured; this finding
does not establish a fuel-learning cause of the cut.

The inaccurate explanation and source comment are corrected. The 500 g/s
value, all calibration data, patch instructions and BINs are unchanged.
Changing or bypassing learning is not justified as a cut fix by this evidence.
