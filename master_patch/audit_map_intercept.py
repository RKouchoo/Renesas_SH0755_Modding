#!/usr/bin/env python3
"""Execute the native MAP ADC conversion and inspect proposed offset shifts.

No physical pressure is inferred from the minimum observed in a log. Runs
7A14, 25CC, 257C and 7A56 from saved ROM bytes. Hardware ADC acquisition and
electrical sensor accuracy remain external; no BIN or calibration is written.
"""

import _analysis_paths  # Locate shared offline interpreters after repository cleanup.
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from audit_fpu_usage import NativeSDMachine, sd, sd_test
import analyze_20260908_recovery as recovery
import analyze_20260908_dashpot as dashpot
import build_master_patch as master
from test_primary_fueling_execution import number

RAW_ADC = 0xFFFFAB04
PROCESSED_ADC = 0xFFFFABC8
PRESSURE = 0xFFFFABC4
CONVERTER = 0x7A14
CLASSIFIER = 0x7A56
OFFSET = 0x72810
MULTIPLIER = 0x72814
ADC_ALPHA = 0x72818
KPA_PER_MMHG = 1/master.KPA_TO_MMHG
VOLTS_PER_COUNT = 5/65536
CONVERTER_WRITES = {(PROCESSED_ADC, 2), (PRESSURE, 4)}


class MapConversionMachine(NativeSDMachine):
    LOOKUPS = {0x25CC, 0x257C}

    def __init__(self, image):
        super().__init__(image, 1500, 315, 25, 1)
        self.write(PROCESSED_ADC, 65535, 2)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n = (op >> 8) & 15
        if op & 0xF0FF == 0xF03D:  # FTRC: valid finite in-range fixture only.
            value = number(self.fr[n])
            assert math.isfinite(value) and -(1 << 31) <= value < (1 << 31)
            self.fpul = math.trunc(value) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x005A:  # STS FPUL,Rn.
            self.r[n] = self.fpul
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def convert(self, raw):
        assert 0 <= raw <= 65535
        self.write(RAW_ADC, raw, 2)
        self.trace.clear()
        self.invoke(CONVERTER, CONVERTER_WRITES)
        assert self.read(PROCESSED_ADC, 2) == raw, 'Installed ADC alpha must pass the current count through'
        assert (self.mach, self.macl) == (0x12345678, 0x76543210)
        assert len(self.trace) == self.instructions
        return self.get_float(PRESSURE)

    def classify(self):
        self.trace.clear()
        self.invoke(CLASSIFIER, set())
        return self.r[0]


def summarize(image):
    offset, multiplier = struct.unpack_from('>2f', image, OFFSET)
    return dict(offset_mmhg=offset,multiplier_mmhg_per_v=multiplier,
        offset_kpa=offset*KPA_PER_MMHG,multiplier_kpa_per_v=multiplier*KPA_PER_MMHG)


def analyze():
    source = Path(__file__).resolve().parent/'candidates/D2WD610H_slight_dashpot_candidate.bin'
    image = source.read_bytes()
    assert hashlib.sha256(image).hexdigest() == dashpot.SECOND_SHA
    stock = master.STOCK.read_bytes()
    assert hashlib.sha256(stock).hexdigest() == master.STOCK_SHA256
    for start,end in ((0x7A14,0x7AB0),(0x257C,0x258C),(0x25CC,0x25F8)):
        assert image[start:end] == stock[start:end], hex(start)
    assert struct.unpack_from('>H',image,ADC_ALPHA)[0] == 256
    assert struct.unpack_from('>f',image,0x25F4)[0] == 1/256
    assert struct.unpack_from('>f',image,0x7A94)[0] == VOLTS_PER_COUNT
    assert image[sd.WRAPPER_ADDR:sd.WRAPPER_ADDR+len(sd.build_wrapper())] == sd.build_wrapper()

    cpu = MapConversionMachine(image)
    previous, minimum_step, maximum_step = None, math.inf, -math.inf
    first, last, low_voltage_max = None, None, None
    for raw in range(65536):
        value = cpu.convert(raw)*KPA_PER_MMHG
        assert math.isfinite(value)
        if previous is not None:
            step = value-previous
            assert step > 0, ('Clamped or non-increasing conversion', raw, previous, value)
            minimum_step, maximum_step = min(minimum_step,step),max(maximum_step,step)
        first = value if raw == 0 else first
        last, previous = value,value
        if raw*VOLTS_PER_COUNT <= .5:
            low_voltage_max = value
    print('PASS: all 65,536 ADC codes strictly increase; no pressure floor',flush=True)

    cases = []
    for voltage in (0,.1,.2,.25,.3,.32,.35,.4,.45,.5,.6,.65794,1.0,4.75):
        raw = round(voltage/VOLTS_PER_COUNT)
        pressure = cpu.convert(raw)
        classification = cpu.classify()
        sd_cpu = NativeSDMachine(image,1500,pressure,25,1)
        airflow = sd_test.Machine.run(sd_cpu)
        cases.append(dict(requested_volts=voltage,raw_adc=raw,
            represented_volts=raw*VOLTS_PER_COUNT,pressure_kpa=pressure*KPA_PER_MMHG,
            native_electrical_class=classification,
            conditional_1500rpm_airflow=airflow,
            fixed_sd_fallback=bool(sd_cpu.reads[sd.FAILSAFE_AIRFLOW_ADDR])))

    # A negative control demonstrates sensitivity of this decoder to a changed
    # coefficient. These shifts implement the user's stated hypothetical
    # 33.77 -> 20/15 kPa targets, not measured sensor calibration pairs.
    shifts = []
    original_offset = struct.unpack_from('>f',image,OFFSET)[0]
    formula = summarize(image)
    reference_volts = (33.77-formula['offset_kpa'])/formula['multiplier_kpa_per_v']
    for shift in (0,-5,20-33.77,15-33.77):
        variant = bytearray(image)
        struct.pack_into('>f',variant,OFFSET,original_offset+shift/KPA_PER_MMHG)
        assert all(a == b for i,(a,b) in enumerate(zip(image,variant)) if not OFFSET <= i < OFFSET+4)
        alt = MapConversionMachine(variant)
        points = []
        for voltage in (0,.3,.5,reference_volts):
            raw = round(voltage/VOLTS_PER_COUNT)
            pressure = alt.convert(raw)
            native = NativeSDMachine(variant,1500,pressure,25,1)
            flow = sd_test.Machine.run(native)
            points.append(dict(volts=voltage,pressure_kpa=pressure*KPA_PER_MMHG,
                conditional_airflow=flow,fixed_sd_fallback=bool(native.reads[sd.FAILSAFE_AIRFLOW_ADDR])))
        shifts.append(dict(hypothetical_offset_shift_kpa=shift,formula=summarize(variant),points=points))

    first_dashpot,_ = dashpot.historical_images()
    captures=[]
    for label,name,digest,count in dashpot.CAPTURES:
        rows=dashpot.read_capture(name,digest,count)
        exact=[{k:r[k] for k in ('time','rpm','map','load','throttle','pulse')} for r in rows if r['map']==33.77]
        captures.append(dict(label=label,file=name,log_sha256=digest,
            image_sha256=dashpot.FIRST_SHA,
            min_map_sample=min(rows,key=lambda r:r['map']),
            min_running_load_sample=min((r for r in rows if r['rpm']>500),key=lambda r:r['load']),
            samples_at_33_77_kpa=exact))
    for candidate in (first_dashpot,recovery.CANDIDATE.read_bytes()):
        assert candidate[OFFSET:ADC_ALPHA+2] == image[OFFSET:ADC_ALPHA+2]
        assert candidate[CONVERTER:0x7AB0] == image[CONVERTER:0x7AB0]
    _, recovery_rows = recovery.read_capture()
    # Logged E51/B2A0 is distinct from the converter's ABC4 output. These
    # samples cannot identify true pressure or calibrate the sensor transfer.
    assert source.read_bytes()==image
    return dict(status='READ-ONLY NATIVE SWEEP; this script changes no calibration, BIN or logger.',
        captured_map_source='E51 is FFFFB2A0 processed/fallback MAP, not the converter/SD input at FFFFABC4. Capture minima are not measured ADC-conversion limits.',
        image=str(source),image_sha256=dashpot.SECOND_SHA,
        equation=formula,native_converter=hex(CONVERTER),offset_address=hex(OFFSET),
        multiplier_address=hex(MULTIPLIER),pressure_output_address=hex(PRESSURE),
        sweep=dict(adc_codes=65536,strictly_increasing=True,kpa_at_zero=first,kpa_at_full_scale=last,
            min_step_kpa=minimum_step,max_step_kpa=maximum_step,
            maximum_kpa_for_adc_volts_at_or_below_0_5=low_voltage_max),
        voltage_cases=cases,offset_sensitivity=shifts,
        voltage_for_pressure_kpa={str(p):(p-formula['offset_kpa'])/formula['multiplier_kpa_per_v']
                                 for p in (10,12,15,20,33.77)},
        unchanged_filter=struct.unpack_from('>f',image,sd.LOAD_FILTER_ALPHA_ADDR)[0],
        unchanged_slow_negative_gain=struct.unpack_from('>f',image,0x76030)[0],
        unchanged_first_negative_rpm_multiplier=struct.unpack_from('>H',image,0x76E7E)[0]/2048,
        capture_checks=captures,recovery_minimum=min(recovery_rows,key=lambda r:r['map']),
        limitations=['ADC counts are supplied; hardware voltage/reference/ground, installed sensor identity and true pressure are unmeasured.',
            'Electrical range classification is a separate native routine; diagnostic consequences beyond that classification are not executed.',
            'SD uses fixed 1500 RPM/25 C/low-lift fixtures here; no downstream load/transient or engine response is predicted.',
            '0 V can be executed mathematically but is not a valid physical sensor calibration reference for running the engine.',
            'Offset variants are in-memory negative controls derived from hypothetical pressure targets, not recommended calibration values.',
            'Native arithmetic is modeled with valid finite FTRC operands; FPSCR exceptions, hardware ADC timing and IRQ interleaving are not simulated.'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.suffix.lower() != '.json':
        parser.error('Only a JSON report may be written')
    report=analyze()
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(args.output)
