#!/usr/bin/env python3
"""Build an OFFLINE-ONLY SD fault-path experiment in memory.

HISTORICAL EXPERIMENT, NOT COMPATIBLE WITH THE CURRENT COMPONENT CONTRACT.
Its C85E/C861/C862 allocation overlaps native AVCS integrators; the old
rear-O2 ownership rationale was disproved on 2026-09-13. Keep this source only
as an explanation of the abandoned offline experiment. It is not part of a
current build or verification run. See AVCS_OCV_REPAIR_20260913.md.

This module is deliberately outside build_master_patch.py. It never writes a
BIN and is not a flash recommendation. It retains the current MAP transfer,
VE calibration, negative transient gains and load filter. Electrical bounds
come from the installed native classifier; this does not validate the sensor
below its published calibration endpoints.

Valid positive MAP below the first VE knot uses that knot for VE selection
and actual MAP for air mass. Invalid inputs/calculations latch a reason and
publish both native injector-cut interfaces, instead of synthetic 500 g/s.
The ordinary cut task is wrapped so its retained limiter cannot clear the SD
cut. Valid samples and zero RPM do not release the latch. The existing startup
zero initializer clears the reclaimed state; its call context is audited
separately before any proposal to integrate this experiment.
"""

import _analysis_paths  # Shared repository, artifact and interpreter paths.
from pathlib import Path
import hashlib
import struct

import build_master_patch as master
from sh2_asm import Asm
import patch_speed_density as sd
import patch_boost as boost
import fueling_safety_component as safety
import wideband_component as wideband

SOURCE = _analysis_paths.MASTER / 'candidates/D2WD610H_slight_dashpot_candidate.bin'
SOURCE_SHA = '2f80b8e5cb80361cdee170655bc26aa8ed8a41bcf4cd7f7249fe3f8c8eaa1f1c'
WRAPPER = 0x7EE00
PUBLISHER = 0x7F200
CUT_WRAPPER = 0x7F300
END = 0x7FAF8
ADC = 0xFFFFABC8  # Processed count paired with ABC4 by native converter 7A14.
ADC_LOW = 0x7B286
ADC_HIGH = 0x7B284
FAULT_COUNT = 0xFFFFC85E  # Saturating count of rejected nonzero-RPM calculations.
FAULT_REASON = 0xFFFFC861  # First reason, latched until state initialization.
FAULT_ADC = 0xFFFFC862  # Processed count at first rejection; FFFF if not acquired.
REASONS = {1: 'RPM or RPM bounds', 2: 'MAP electrical low',
           3: 'MAP electrical high', 4: 'MAP or MAP maximum',
           5: 'IAT or IAT bounds', 6: 'calibration/electrical bounds',
           7: 'VE result', 8: 'IAT density result', 9: 'air-mass product'}
STATE_WRITES = {(FAULT_COUNT, 2), (FAULT_REASON, 1), (FAULT_ADC, 2)}
CUT_WRITES = {(boost.FUELCUT_FLAG, 1), (boost.FUELCUT_INHIBIT_WORD, 2)}
AIR_WRITES = {(a, 4) for a in (sd.FINAL_MASS_AIRFLOW_ADDR,
    sd.SYNTHETIC_RAW_AIRFLOW_ADDR, sd.SYNTHETIC_FILTER_A_ADDR,
    sd.SYNTHETIC_FILTER_B_ADDR)}


def build_wrapper():
    a = Asm(WRAPPER)
    a.push(8).push(9).fpush(12).fpush(13).stsl_pr()
    a.mov_imm(-1, 8).mov_imm(1, 9)
    a.fcmpeq(15, 15).bt('rpm_not_nan')
    a.bra('fault').nop()
    a.label('rpm_not_nan').fldi0(3).fcmpeq(3, 15).bf('running')
    a.bra('zero').nop()
    a.label('running')

    # ABC8 and ABC4 are written by the sensor-processing task. Prevent task
    # switches between these reads; higher hardware IRQs remain enabled.
    # Unlock can dispatch a task and clobber scratch registers: snapshots live
    # in callee-saved registers and FR15 remains the caller's load-divisor RPM.
    a.movl_pool(3, boost.TASK_LOCK).jsr(3).mov_imm(0x10, 4)
    a.push(0)
    a.movl_pool(1, ADC).movw_at(8, 1).extu_w(8, 8)
    a.movl_pool(1, sd.MAP_ADDR).fmov_load(12, 1)
    a.movl_pool(1, sd.IAT_ADDR).fmov_load(13, 1)
    a.pop(4).movl_pool(3, boost.TASK_UNLOCK).jsr(3).nop()
    a.fmov(15, 5)
    sd.emit_float_register_range_gate(a, sd.RPM_MIN_ADDR, sd.RPM_MAX_ADDR, 5, 'bad_rpm')
    a.bra('electrical').nop()
    a.label('bad_rpm').bra('fault').nop()

    a.label('electrical').mov_imm(6, 9)
    a.movl_pool(1, ADC_LOW).movw_at(2, 1).extu_w(2, 2)
    a.movl_pool(1, ADC_HIGH).movw_at(3, 1).extu_w(3, 3)
    a.tst_reg(2, 2).bt('bad_electrical')
    a.cmp_hs(3, 2).bt('bad_electrical')  # low >= high is malformed.
    a.mov_imm(2, 9).cmp_hs(2, 8).bf('bad_electrical')
    a.mov_imm(3, 9).cmp_hs(3, 8).bt('bad_electrical')
    a.bra('pressure').nop()
    a.label('bad_electrical').bra('fault').nop()

    a.label('pressure').mov_imm(4, 9)
    sd.emit_positive_finite_value_gate(a, 12, 'bad_pressure')
    sd.emit_positive_calibration_gate(a, sd.MAP_MAX_ADDR, 2, 'bad_pressure')
    a.fcmpgt(2, 12).bt('bad_pressure')
    a.bra('temperature').nop()
    a.label('bad_pressure').bra('fault').nop()

    a.label('temperature').mov_imm(5, 9).fmov(13, 4)
    sd.emit_float_register_range_gate(a, sd.IAT_MIN_ADDR, sd.IAT_MAX_ADDR, 4, 'bad_temperature')
    a.bra('calibration').nop()
    a.label('bad_temperature').bra('fault').nop()

    a.label('calibration').mov_imm(6, 9)
    for address in (sd.GLOBAL_MULTIPLIER_ADDR, sd.DISPLACEMENT_ADDR,
                    sd.MAX_AIRFLOW_ADDR, sd.AIRFLOW_CONSTANT_ADDR,
                    sd.MAP_AXIS_ADDR):
        sd.emit_positive_calibration_gate(a, address, 2, 'bad_calibration')
    a.bra('select_ve').nop()
    a.label('bad_calibration').bra('fault').nop()

    a.label('select_ve')
    a.movl_pool(1, sd.AVLS_COMMITTED_MODE_ADDR).movb_at(0, 1)
    a.cmp_eq_imm(sd.AVLS_HIGH_MODE).bt('high_lift')
    a.movl_pool(4, sd.LOW_VE_DESC_ADDR).bra('lookup_ve').nop()
    a.label('high_lift').movl_pool(4, sd.HIGH_VE_DESC_ADDR)
    a.label('lookup_ve').fmov(12, 4).fmov(15, 5)
    a.movl_pool(1, sd.MAP_AXIS_ADDR).fmov_load(3, 1)
    a.fcmpgt(4, 3).bf('coordinate_valid')
    a.fmov(3, 4)  # Clamp only lookup coordinate. FR12 retains actual pressure.
    a.label('coordinate_valid')
    a.movl_pool(2, sd.TABLE_3D_LOOKUP).jsr(2).nop()
    a.mov_imm(7, 9)
    sd.emit_positive_finite_value_gate(a, 0, 'bad_ve')
    a.bra('ve_valid').nop()
    a.label('bad_ve').bra('fault').nop()
    a.label('ve_valid')
    a.fmul(12, 0).fmul(15, 0)
    for address in (sd.DISPLACEMENT_ADDR, sd.AIRFLOW_CONSTANT_ADDR, sd.GLOBAL_MULTIPLIER_ADDR):
        a.movl_pool(1, address).fmov_load(2, 1).fmul(2, 0)
    a.fpush(0).fmov(13, 4).movl_pool(4, sd.IAT_DESC_ADDR)
    a.movl_pool(2, sd.TABLE_2D_LOOKUP).jsr(2).nop()
    a.mov_imm(8, 9)
    sd.emit_positive_finite_value_gate(a, 0, 'drop_and_fault')
    a.fpop(1).fmul(1, 0).mov_imm(9, 9)
    sd.emit_positive_finite_value_gate(a, 0, 'fault')
    a.movl_pool(1, sd.MAX_AIRFLOW_ADDR).fmov_load(2, 1)
    a.fcmpgt(2, 0).bf('valid_result')
    a.fmov(2, 0)
    a.label('valid_result')
    a.movl_pool(1, FAULT_REASON).movb_at(0, 1).tst_reg(0, 0).bt('store')
    a.mov_imm(0, 9).bra('fault').nop()  # Hold cut, without counting a new fault.
    a.label('drop_and_fault').fpop(1)
    a.label('fault').mov_reg(9, 4).mov_reg(8, 5)
    a.movl_pool(2, PUBLISHER).jsr(2).nop()
    a.label('zero').fldi0(0)
    a.label('store')
    for address, _ in sorted(AIR_WRITES):
        a.movl_pool(1, address).fmov_store(0, 1)
    a.ldsl_pr().fpop(13).fpop(12).pop(9).pop(8).rts().nop()
    blob = a.assemble()
    assert WRAPPER + len(blob) <= PUBLISHER
    return blob, a.labels


def build_publisher():
    a = Asm(PUBLISHER)
    a.push(8).push(9).stsl_pr().mov_reg(4, 8).mov_reg(5, 9)
    a.movl_pool(3, boost.TASK_LOCK).jsr(3).mov_imm(0x10, 4)
    a.push(0).tst_reg(8, 8).bt('publish')
    a.movl_pool(1, FAULT_COUNT).movw_at(0, 1).extu_w(0, 0)
    a.movl_pool(2, 0xFFFF).cmp_hs(2, 0).bt('counted')
    a.add_imm(1, 0).movw_store(0, 1)
    a.label('counted')
    a.movl_pool(1, FAULT_REASON).movb_at(0, 1).tst_reg(0, 0).bf('publish')
    a.movb_store(8, 1).movl_pool(1, FAULT_ADC).movw_store(9, 1)
    a.label('publish')
    boost.emit_added_fuel_cut(a)
    a.pop(4).movl_pool(3, boost.TASK_UNLOCK).jsr(3).nop()
    a.ldsl_pr().pop(9).pop(8).rts().nop()
    blob = a.assemble()
    assert PUBLISHER + len(blob) <= CUT_WRAPPER
    return blob, a.labels


def build_cut_wrapper():
    a = Asm(CUT_WRAPPER)
    boost.emit_cut_update_begin(a, safety.LEAN_CUT_WRAPPER_ADDR)
    a.movl_pool(1, FAULT_REASON).movb_at(0, 1).tst_reg(0, 0).bt('done')
    boost.emit_added_fuel_cut(a)
    a.label('done')
    boost.emit_cut_update_end(a)
    blob = a.assemble()
    assert CUT_WRAPPER + len(blob) <= END
    return blob, a.labels


def build_experiment(source=None):
    """Return bytes for an in-memory experiment; no file-write interface."""
    source = SOURCE.read_bytes() if source is None else bytes(source)
    assert hashlib.sha256(source).hexdigest() == SOURCE_SHA
    assert source[sd.WRAPPER_ADDR:sd.WRAPPER_ADDR+len(sd.build_wrapper())] == sd.build_wrapper()
    assert source[safety.LEAN_CUT_WRAPPER_ADDR:safety.LEAN_CUT_WRAPPER_ADDR+len(safety.build_lean_cut_wrapper())] == safety.build_lean_cut_wrapper()
    assert source[safety.LEAN_STATE_INITIALIZE_ADDR:safety.LEAN_STATE_INITIALIZE_ADDR+len(safety.build_lean_state_initialize())] == safety.build_lean_state_initialize()
    assert struct.unpack_from('>I', source, safety.LEAN_STATE_INIT_TASK_PTR)[0] == safety.LEAN_STATE_INITIALIZE_ADDR
    # Historical defect: these five AVCS tasks were incorrectly removed.
    for address in (0x11488, 0x1148C, 0x11490, 0x11494, 0x114A0):
        assert struct.unpack_from('>I', source, address)[0] == wideband.NOOP_TASK
    assert struct.unpack_from('>HH', source, ADC_HIGH) == (0xFBF5, 0x0F5C)
    assert source[0x72818:0x7281A] == b'\x01\x00'
    for descriptor in (sd.LOW_VE_DESC_ADDR, sd.HIGH_VE_DESC_ADDR):
        assert struct.unpack_from('>I', source, descriptor+4)[0] == sd.MAP_AXIS_ADDR
    image = bytearray(source)
    blobs = {}
    for name, address, builder in (('airflow', WRAPPER, build_wrapper),
            ('fault_publication', PUBLISHER, build_publisher),
            ('cut_composition', CUT_WRAPPER, build_cut_wrapper)):
        blob, labels = builder()
        assert all(v == 255 for v in source[address:address+len(blob)])
        image[address:address+len(blob)] = blob
        blobs[name] = dict(address=address, length=len(blob), labels=labels)
    for address, expected, target in ((sd.FINAL_AIRFLOW_HELPER_PTR, sd.WRAPPER_ADDR, WRAPPER),
            (safety.LEAN_CUT_TASK_PTR, safety.LEAN_CUT_WRAPPER_ADDR, CUT_WRAPPER)):
        assert struct.unpack_from('>I', source, address)[0] == expected
        struct.pack_into('>I', image, address, target)
    # Deliberately leave the checksum unchanged: these bytes are a test fixture,
    # never a flash artifact. Only the bounded hook/code ranges may differ.
    allowed = {a for item in blobs.values() for a in range(item['address'], item['address']+item['length'])}
    allowed |= set(range(sd.FINAL_AIRFLOW_HELPER_PTR, sd.FINAL_AIRFLOW_HELPER_PTR+4))
    allowed |= set(range(safety.LEAN_CUT_TASK_PTR, safety.LEAN_CUT_TASK_PTR+4))
    assert all(a in allowed for a, (old, new) in enumerate(zip(source, image)) if old != new)
    return bytes(image), blobs


if __name__ == '__main__':
    image, blobs = build_experiment()
    print('OFFLINE ONLY: built in memory; no BIN written; checksum intentionally not updated.')
    for name, item in blobs.items():
        print(f"{name}: {item['address']:05X}, {item['length']} bytes")
