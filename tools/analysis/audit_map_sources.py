#!/usr/bin/env python3
"""Execute retained MAP processing and barometer selection with supplied state.

No ECU I/O or BIN writes. These are conditional native-code fixtures, not
recovered diagnostic flags from the September captures.
"""

import _analysis_paths  # Shared repository, artifact and interpreter paths.
import argparse
import hashlib
import json
from pathlib import Path
import struct

from audit_map_intercept import MapConversionMachine, KPA_PER_MMHG
from audit_fpu_usage import sd
import analyze_20260908_dashpot as dashpot
import build_master_patch as master

NATIVE_MAP = 0xFFFFABC4
LOGGED_MAP = 0xFFFFB2A0
BARO = 0xFFFFCFBC
STORED_BARO = 0xFFFF8E04
MAP_FLAGS = 0xFFFFD26C
BARO_FLAGS = 0xFFFFCFD0
MAP_WRITES = {(a, 4) for a in (0xFFFFB290, 0xFFFFB294, 0xFFFFB298,
    0xFFFFB29C, LOGGED_MAP, 0xFFFFB2A4, 0xFFFFB2AC, 0xFFFFB2B0, 0xFFFFB2B4)} | {(0xFFFFB2B8, 1)}
BARO_WRITES = {(STORED_BARO, 4), (STORED_BARO+4, 2),
    (STORED_BARO+6, 2), (0xFFFFCFC0, 4)}


class MapSourceMachine(MapConversionMachine):
    LOOKUPS = MapConversionMachine.LOOKUPS | {
        0x64FBC, 0x1D228, 0x2424, 0x24A0, 0x24B0, 0x24C0,
        0x49530, 0x3AF4, 0x3B08, 0x209C, 0x26E0, 0x27D0, 0x25F8, 0x28A4,
    }

    def __init__(self, image, native_kpa=15, load=.58, rpm=992,
                 map_flags=0, baro_flags=0, history_kpa=15, baro_mmhg=712):
        super().__init__(image)
        for a in range(0xFFFFB290, 0xFFFFB2B9):
            self.write(a, 0, 1)
        for a in (0xFFFFB290, 0xFFFFB2B0, 0xFFFFB2B4, 0xFFFFB2AC):
            self.put_float(a, history_kpa/KPA_PER_MMHG)
        self.put_float(NATIVE_MAP, native_kpa/KPA_PER_MMHG)
        self.put_float(0xFFFFB438, load)
        self.put_float(0xFFFFB544, rpm)
        self.put_float(BARO, baro_mmhg)
        self.put_float(STORED_BARO, baro_mmhg)
        self.put_float(0xFFFFCFC4, 0)
        self.write(MAP_FLAGS, map_flags, 1)
        self.write(BARO_FLAGS, baro_flags, 1)
        self.write(0xFFFFB748, 0, 1)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF0FF == 0xF01D:  # FLDS FRn,FPUL.
            self.fpul = self.fr[n]
        elif op & 0xF0FF == 0xF05D:  # FABS FRn.
            self.fr[n] &= 0x7FFFFFFF
        elif op & 0xFF00 == 0x8100:  # MOV.W R0,@(disp,Rm).
            self.write(self.r[m] + (op & 15)*2, self.r[0], 2, record=True)
        elif op & 0xF00F == 0x3000:  # CMP/EQ Rm,Rn.
            self.t = self.r[n] == self.r[m]
        elif op & 0xF00F == 0x6007:  # NOT Rm,Rn.
            self.r[n] = ~self.r[m] & 0xFFFFFFFF
        elif op & 0xF0FF == 0x4000:  # SHLL Rn.
            self.t = bool(self.r[n] & 0x80000000)
            self.r[n] = (self.r[n] << 1) & 0xFFFFFFFF
        elif op & 0xF00F == 0x6005:  # MOV.W @Rm+,Rn; sign extend.
            address = self.r[m]
            value = self.load(address, 2)
            self.r[n] = (value if value < 0x8000 else value-0x10000) & 0xFFFFFFFF
            if n != m:
                self.r[m] = (address+2) & 0xFFFFFFFF
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1
        assert self.instructions < self.INSTRUCTION_LIMIT

    def execute(self, entry, writes):
        self.trace.clear()
        self.invoke(entry, writes)
        assert len(self.trace) == self.instructions
        assert (self.mach, self.macl) == (0x12345678, 0x76543210)

    def process_map(self):
        self.execute(0x1496C, MAP_WRITES)
        return self.get_float(LOGGED_MAP)*KPA_PER_MMHG

    def barometer(self):
        self.execute(0x47DCC, BARO_WRITES)
        self.execute(0x47DB2, {(BARO, 4)})
        return self.get_float(BARO)


def analyze():
    path = _analysis_paths.MASTER / 'candidates/D2WD610H_slight_dashpot_candidate.bin'
    image = path.read_bytes()
    assert hashlib.sha256(image).hexdigest() == dashpot.SECOND_SHA
    stock = master.STOCK.read_bytes()
    assert hashlib.sha256(stock).hexdigest() == master.STOCK_SHA256
    ranges = ((0x1496C, 0x14B74), (0x47D6A, 0x48118), (0x64FBC, 0x64FD0),
              (0x1D228, 0x1D23C), (0x49530, 0x49576), (0x2424, 0x2450))
    for a,b in ranges:
        assert image[a:b] == stock[a:b], hex(a)
    first, second = dashpot.historical_images()
    assert second == image
    for a,b in ranges:
        assert first[a:b] == image[a:b], hex(a)
    assert image[0x737D9] == 0
    # Shared D26F getter survives, but SD's local load-task call is bypassed.
    assert int.from_bytes(image[0x173FC:0x17400], 'big') == 0x27088
    assert image[0x27088:0x2708C] == bytes.fromhex('000be000')
    assert first[0x173FC:0x17400] == image[0x173FC:0x17400]
    assert abs(struct.unpack_from('>f', image, 0x73834)[0]-.00264) < 1e-9

    map_cases = []
    for pressure in (10, 12, 15, 20, 33.77, 95, 150):
        for flags in (0, 0x10, 0xEF, 0xFF):
            cpu = MapSourceMachine(image, native_kpa=pressure, map_flags=flags,
                                   history_kpa=pressure)
            cpu.process_map()
            # Allow the fallback's two-point average to settle without changing
            # the supplied engine load. Normal histories remain at true MAP.
            published = cpu.process_map()
            expected = ((.58+.0851)/.00264*KPA_PER_MMHG if flags & 0x10 else pressure)
            assert abs(published-expected) < 4e-5, (pressure, flags, published, expected)
            assert abs(cpu.get_float(NATIVE_MAP)*KPA_PER_MMHG-pressure) < 2e-5
            map_cases.append(dict(native_kpa=pressure, diagnostic_flags=flags,
                supplied_load=.58, processed_kpa=published))

    # A real high-to-low input step and prior extrema exercise the normal
    # delta selector independently from load-derived diagnostic substitution.
    steps = []
    for flag in (0, 0x10):
        cpu = MapSourceMachine(image, native_kpa=15, history_kpa=95, map_flags=flag)
        rows = [cpu.process_map() for _ in range(4)]
        assert abs(rows[-1]-(15 if flag == 0 else (.58+.0851)/.00264*KPA_PER_MMHG)) < 4e-5
        steps.append(dict(map_diagnostic_flags=flag, native_step_kpa=[95,15], processed_updates_kpa=rows))

    baro_cases = []
    for pressure in (10, 15, 33.77, 95, 150):
        for diagnostic, flags, expected in ((0,0,712), (0,0x20,714.5),
                (0,0x80,max(570,min(770,pressure/KPA_PER_MMHG))), (0x10,0x80,760)):
            cpu = MapSourceMachine(image, native_kpa=pressure,
                                   map_flags=diagnostic, baro_flags=flags)
            actual = cpu.barometer()
            assert abs(actual-expected) < .0002
            assert abs(cpu.get_float(NATIVE_MAP)*KPA_PER_MMHG-pressure) < 2e-5
            baro_cases.append(dict(native_kpa=pressure, diagnostic_flags=diagnostic,
                baro_flags=flags, selected_baro_mmhg=actual))

    # Running learning uses native table interpolation, not a supplied alpha.
    cpu = MapSourceMachine(image, native_kpa=15, baro_flags=0x40)
    cpu.put_float(LOGGED_MAP, 680)
    cpu.put_float(0xFFFFCFC4, 20)
    before = cpu.get_float(STORED_BARO)
    actual = cpu.barometer()
    assert 700 <= actual <= before
    learning = dict(previous_baro_mmhg=before, supplied_processed_map_mmhg=680,
        pressure_loss_mmhg=20, alpha=cpu.get_float(0xFFFFCFC0), selected_baro_mmhg=actual)

    # Fault descriptors: current-status bank with byte index doubled by ROM.
    diagnostic_sources=[]
    for descriptor, dtc in ((0x5C5C0,'P0068'),(0x5C50C,'P0107'),(0x5C520,'P0108')):
        record=(descriptor-0x5BDF0)//20
        assert descriptor == 0x5BDF0+record*20
        diagnostic_sources.append(dict(dtc=dtc, descriptor=hex(descriptor),
            current_status_address=hex(0xFFFF8E58+2*image[descriptor+1]),
            mask=image[descriptor+2], enable_address=hex(0x5BD54+record),
            enable_value=image[0x5BD54+record]))
    assert image[sd.WRAPPER_ADDR:sd.WRAPPER_ADDR+len(sd.build_wrapper())] == sd.build_wrapper()
    assert path.read_bytes() == image
    return dict(status='Conditional native fixtures; no ECU I/O, firmware or calibration changes.',
        image_sha256=dashpot.SECOND_SHA, native_map=hex(NATIVE_MAP),
        matching_captured_image_sha256=dashpot.FIRST_SHA,
        airflow_load_fallback_local_getter_bypassed=True,
        captured_E51_map=hex(LOGGED_MAP), baro=hex(BARO), map_cases=map_cases,
        normal_and_fallback_step=steps, baro_cases=baro_cases, running_learning=learning,
        map_fallback_diagnostic_sources=diagnostic_sources,
        unchanged_load_filter=struct.unpack_from('>f',image,sd.LOAD_FILTER_ALPHA_ADDR)[0],
        unchanged_slow_negative_gain=struct.unpack_from('>f',image,0x76030)[0],
        limitations=['Native MAP, prior histories and diagnostic flags are supplied fixtures; the captures do not record ABC4 or D26C/D26F/CFD0.',
            'The estimator is executed for supplied flags; its full learning eligibility and diagnostic-status update chain are statically traced, not dynamically replayed.',
            'No sensor calibration, engine response, CPU deadlines, or logger sample atomicity is established.'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    if args.output.suffix.lower() != '.json':
        parser.error('Only a JSON report may be written')
    report=analyze()
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(f"PASS: {len(report['map_cases'])} MAP cases; {len(report['baro_cases'])} baro cases; native steps and learning")
    print(args.output)
