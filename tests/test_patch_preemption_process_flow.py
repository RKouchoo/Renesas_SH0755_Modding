#!/usr/bin/env python3
"""Resume emitted FPU patches through native phase-task IRQ/context handling.

Every reached non-delay instruction address in each selected path receives
one explicit IRQ. The actual kernel and phase queue run; task5 consumes its
phase and executes263EE. Other task5 work, physical timing and CPU pipeline
latency are not simulated. A final-value check does not prove atomic multi-
field publication to every possible native consumer.
"""
import _test_paths
from itertools import product
import unittest

from test_phase_activation_process_flow import (PhaseActivationMachine,
    PHASE_WRITES,KERNEL_WRITES,SCHEDULER_WRITES,RAM,ROOT,bits)
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_wideband_fuel_guard_execution import signed,wideband
from audit_fpu_usage import NativeSDMachine,sd

AIR_WRITES={(RAM+a,4) for a in (0xB420,0xB448,0xB458,0xB45C)}
IRQ_WRITES=PHASE_WRITES | KERNEL_WRITES | SCHEDULER_WRITES


class PatchPreemptionMachine(PhaseActivationMachine):
    def __init__(self,image,rpm=3300,pressure=810,iat=37,mode=3):
        # An accepted IRQ edge needs a finite positive period fixture even
        # when the interrupted SD caller still holds its prior zero RPM.
        super().__init__(image,phase=1,rpm=rpm if rpm>0 else 3000)
        self.sites=set()
        self.original_fr[15]=bits(rpm)
        self.put_float(sd.MAP_ADDR,pressure)
        self.put_float(sd.IAT_ADDR,iat)
        self.write(sd.AVLS_COMMITTED_MODE_ADDR,mode,1)

    def call_lookup(self,target):
        if target in NativeSDMachine.LOOKUPS:
            self.entered.append(target)
            self.subroutine(target)
        else:
            super().call_lookup(target)

    def step(self,in_delay=False):
        pc,op=self.pc,self.read(self.pc,2)
        if not in_delay and not self.irq_depth:
            self.sites.add(pc)
        n,m=(op>>8)&15,(op>>4)&15
        if op & 0xF0FF==0x4009:  # SHLR2, T unchanged.
            self.r[n]>>=2
        elif op & 0xF00F==0x200F:  # MULS.W, signed low halfwords -> MACL.
            self.macl=(signed(self.r[n]&65535,16)*signed(self.r[m]&65535,16))&0xFFFFFFFF
        else:
            return super().step(in_delay)
        self.pc+=2
        self.instructions+=1
        self.visited.add(pc)
        if pc==self.inject_at and not self.irq_depth and not in_delay:
            self.inject_at=None
            self.interrupt(self.inject_level)

    def run_sd(self,site=None):
        self.inject_at=site
        self.invoke(sd.WRAPPER_ADDR,AIR_WRITES | IRQ_WRITES)
        assert self.inject_at is None
        return tuple(self.read(a,4) for a,_ in sorted(AIR_WRITES))

    def run_wb(self,raw,site=None):
        self.write(wideband.RAW_WIDEBAND_ADC,raw,2)
        self.inject_at=site
        self.invoke(0xB690,{(a,4) for a in self.wideband_outputs} | IRQ_WRITES)
        assert self.inject_at is None
        return tuple(self.read(a,4) for a in self.wideband_outputs)


class PatchPreemptionProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main=(ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2=(ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images={'main':main,'v2':v2,'captured':before_pump_scaling(v2)}

    def test_sd_interior_both_lift_modes_resume_bit_identically_at_every_reached_instruction_address(self):
        for image,mode in product(self.images.values(),(1,3)):
            baseline=PatchPreemptionMachine(image,mode=mode)
            expected=baseline.run_sd()
            self.assertIn(0x2150,baseline.entered)
            for site in sorted(baseline.sites):
                cpu=PatchPreemptionMachine(image,mode=mode)
                self.assertEqual(cpu.run_sd(site),expected,(mode,hex(site)))
                self.assertEqual(cpu.delivered,[1])
                self.assertEqual(len(cpu.injections),1)
                self.assertEqual(cpu.fpscr,0x40001)
                self.assertEqual(cpu.macl,0xA55A5AA5)
                self.assertEqual(cpu.mach,0xAADD1122)

    def test_sd_clamped_invalid_and_stopped_exits_resume_with_original_result_and_mask(self):
        for image,rpm,pressure,iat in product(self.images.values(),(0,3000),(78.62,810,float('nan')),(37,)):
            baseline=PatchPreemptionMachine(image,rpm,pressure,iat)
            expected=baseline.run_sd()
            for site in sorted(baseline.sites):
                cpu=PatchPreemptionMachine(image,rpm,pressure,iat)
                self.assertEqual(cpu.run_sd(site),expected,(rpm,pressure,hex(site)))
                self.assertEqual(cpu.delivered,[1])
                self.assertEqual(cpu.sr & 0xF0,0)

    def test_wideband_valid_and_invalid_publications_resume_at_every_reached_instruction_address(self):
        for image,raw in product(self.images.values(),(0,16000,50000,65535)):
            baseline=PatchPreemptionMachine(image)
            expected=baseline.run_wb(raw)
            for site in sorted(baseline.sites):
                cpu=PatchPreemptionMachine(image)
                self.assertEqual(cpu.run_wb(raw,site),expected,(raw,hex(site)))
                self.assertEqual(cpu.delivered,[1])
                self.assertEqual(cpu.fpscr,0x40001)


if __name__=='__main__':
    unittest.main(verbosity=2)
