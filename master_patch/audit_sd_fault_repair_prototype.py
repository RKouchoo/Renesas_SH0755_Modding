#!/usr/bin/env python3
"""Run offline SD repair tests and write a JSON audit, never a BIN."""

import _analysis_paths  # Locate shared offline interpreters after repository cleanup.
import argparse
import hashlib
from io import StringIO
import json
from pathlib import Path
import unittest

import prototype_sd_fault_repair as p
from test_sd_fault_repair_prototype import RepairTests, FaultMachine
from audit_fpu_usage import NativeSDMachine
from audit_map_intercept import KPA_PER_MMHG
from test_load_conditioning_execution import LoadConditioningMachine


def analyze():
    source = p.SOURCE.read_bytes()
    image, blobs = p.build_experiment(source)
    test_output = StringIO()
    result = unittest.TextTestRunner(stream=test_output).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RepairTests))
    if not result.wasSuccessful():
        raise AssertionError(test_output.getvalue())

    converter = FaultMachine(image)
    gap, below_ve = [], []
    for raw in range(converter.read(p.ADC_LOW, 2), 65536):
        pressure = converter.convert(raw)
        if pressure >= converter.get_float(p.sd.MAP_AXIS_ADDR):
            break
        below_ve.append(raw)
        if pressure < converter.get_float(p.sd.MAP_MIN_ADDR):
            gap.append(raw)
    cases = []
    for raw in (3931, 3932, 4194, 4506, 4507, 4588, 5243, 5898, 6554, 7864, 16000):
        cpu = FaultMachine(image)
        pressure = cpu.convert(raw)
        classification = cpu.classify()
        new_flow = cpu.calculate()
        old = NativeSDMachine(source, 1500, pressure, 25, 1)
        old.invoke(p.sd.WRAPPER_ADDR, p.AIR_WRITES)
        cases.append(dict(adc_count=raw, volts=raw*5/65536,
            converted_map_kpa=pressure*KPA_PER_MMHG,
            native_electrical_classification=classification,
            old_airflow_g_s=old.get_float(p.sd.FINAL_MASS_AIRFLOW_ADDR),
            prototype_airflow_g_s=new_flow,
            old_fixed_fallback=bool(old.reads[p.sd.FAILSAFE_AIRFLOW_ADDR]),
            prototype_fault_reason=cpu.read(p.FAULT_REASON, 1),
            prototype_inhibit_word=cpu.read(p.boost.FUELCUT_INHIBIT_WORD, 2),
            old_native_instruction_count=old.instructions,
            prototype_native_instruction_count=cpu.instructions))

    # Same supplied source trajectory through each SD version, then retained
    # load/transient instructions with normal flags. One transient update per
    # load call is a test schedule, not reconstruction of an ECU capture.
    steady = FaultMachine(image)
    steady.convert(7864)
    steady_flow = steady.calculate()
    histories = []
    for name, firmware in (('current', source), ('prototype', image)):
        cpu = LoadConditioningMachine(firmware, load=steady_flow*60/1500,
                                      rpm=1500, coolant=45)
        sd_cpu = FaultMachine(image)
        rows = []
        for call in range(1, 101):
            raw = 3932 if call == 1 else 7864
            pressure = sd_cpu.convert(raw)
            if name == 'prototype':
                flow = sd_cpu.calculate()
            else:
                native = NativeSDMachine(source, 1500, pressure, 25, 1)
                native.invoke(p.sd.WRAPPER_ADDR, p.AIR_WRITES)
                flow = native.get_float(p.sd.FINAL_MASS_AIRFLOW_ADDR)
            load = cpu.condition(flow, 1500, coolant=45)
            transient = cpu.transient()
            rows.append(dict(call=call, adc=raw, airflow_g_s=flow,
                raw_load=cpu.get_float(p.sd.RAW_ENGINE_LOAD_ADDR),
                conditioned_load=load, B874=transient))
        histories.append(dict(version=name, initial_load=steady_flow*60/1500,
            first_ten_updates=rows[:10], last_update=rows[-1],
            maximum_conditioned_load=max(r['conditioned_load'] for r in rows),
            B874_range=[min(r['B874'] for r in rows), max(r['B874'] for r in rows)]))

    assert p.SOURCE.read_bytes() == source
    return dict(status='Offline prototype only; not integrated, no BIN written, no ECU I/O.',
        source_sha256=hashlib.sha256(source).hexdigest(),
        fixture_sha256=hashlib.sha256(image).hexdigest(),
        fixture_checksum='Intentionally unchanged from source; not a flash artifact.',
        native_execution_test_groups=result.testsRun,
        below_first_ve_knot=dict(first_adc=below_ve[0], last_adc=below_ve[-1],
            all_codes_tested=len(below_ve)),
        electrically_accepted_but_old_sd_rejected=dict(first_adc=gap[0],
            last_adc=gap[-1], count=len(gap)),
        fixture_inputs=dict(rpm=1500, iat_c=25, committed_avls=1),
        boundary_cases=cases, conditional_load_transient_history=histories,
        code=blobs, new_ram=dict(rejected_call_count=hex(p.FAULT_COUNT),
            first_reason=hex(p.FAULT_REASON), first_processed_adc=hex(p.FAULT_ADC)),
        fault_reasons=p.REASONS,
        reset='Only existing global state initialization, reached by task 17 / 6328 -> FEF4 -> 1055C -> 7EBA0; valid inputs, lean reset and stopped RPM do not clear SD state.',
        unchanged=['MAP slope/offset', 'ADC electrical thresholds', 'VE surfaces',
                   'slow-negative gain/RPM table', '0.06 load filter', 'all saved BINs and logger XML'],
        limitations=[
            'These are supplied inputs, not replay of recorded ABC4/ADC; no vehicle event is attributed to this path.',
            'The existing approximately 0.30 V diagnostic classifier is not a validated physical lower sensor endpoint. Immediate latched injector inhibition differs from the stock debounced DTC response.',
            'Reset dispatch is statically traced; whole hardware startup, watchdog and task reactivation are not emulated.',
            'Native SD lookups run; retained load/transient table interpolation is mathematical. Engine, fuel pressure, exhaust delay and combustion are absent.',
            'IRQs use native frames/dispatch with explicit scripted activation. Hardware delivery, arbitrary IRQ schedules, FP exception flags and real execution deadlines are not validated.',
            'Production integration, logger/profile allocation, fault response suitability and full integrated verification remain before considering any flash artifact.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.suffix.lower() != '.json':
        parser.error('Only a JSON audit may be written')
    report = analyze()
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(f"PASS: {report['native_execution_test_groups']} native execution test groups")
    print(json.dumps(report['electrically_accepted_but_old_sd_rejected']))
    print(args.output)
