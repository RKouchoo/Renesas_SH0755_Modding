#!/usr/bin/env python3
"""Execute phase publication, activation capacity, IRQ dispatch and recovery.

The crank decoder's accepted phase edges and interrupt arrivals are explicit.
Native87F2, period publication, task activation, two-slot queues and kernel
entry/exit execute. Task5 consumes the actual phase and runs263EE; its other
engine work and real execution time remain outside this bounded fixture.
"""
import _test_paths
from itertools import product
import unittest

from test_cut_interrupt_execution import (InterruptMachine, KERNEL, KERNEL_WRITES,
    TASK5_RAM, TASK6_RAM, PAYLOAD_RETURN, SCHEDULER_WRITES, INHIBIT_WORD,
    safety, bits, ROOT)
from test_runtime_rom_checksum_execution import before_pump_scaling

RAM=0xFFFF0000
PHASE_WRITES={(RAM+a,4) for a in (0xAC00,0xAC04,0xAC08,0xAC1C,0xAC18,
    *range(0xAC50,0xAC60,4),0xAFEC,0xAFF0,0xAFF8,0xAFFC)} | {
    (RAM+a,1) for a in (0xAC17,0xAC60,0xAC61,0xAC44,0xAC45,
                       0xAFF4,0xAFF5,0xB000,0xB001,0xB00C,0xB00D)}
NATIVE={0x87F2,0x8BE6,0xCF58,0xCF7E,0xD0D0,0xD106,0xD156,0x82B6,0x8776}


class PhaseActivationMachine(InterruptMachine):
    def __init__(self,image,phase=0,rpm=3000):
        super().__init__(image)
        self.phase_burst=1
        self.delivered=[]
        self.publication_depths=[]
        self.write(RAM+0xAC17,(phase-1)%24,1)
        self.write(RAM+0xAC16,1,1)
        self.write(RAM+0xAC47,255,1)
        self.write(RAM+0xAC60,4,1)
        self.write(RAM+0xAC61,0,1)
        step=round(4_000_000*5/rpm)
        for a in (0xAC24,*range(0xAC50,0xAC60,4)):
            self.write(RAM+a,step,4)
        self.write(RAM+0xAC34,16000,4)
        for a in (0xAFEC,0xAFF0,0xAFF8,0xAFFC):
            self.write(RAM+a,0xA55A5AA5,4)
        for a in (0xAFF4,0xAFF5,0xB000,0xB001,0xB00C,0xB00D):
            self.write(RAM+a,0,1)
        # Error/debug hooks are native optional pointers, both disabled in ROM.
        assert self.read(0x4B14,4)==0

    def call_lookup(self,target):
        if target in NATIVE:
            self.entered.append(target)
            if target==0xD0D0:
                self.publication_depths.append(self.read(KERNEL+8,4))
            self.subroutine(target)
        else:
            super().call_lookup(target)

    def step(self,in_delay=False):
        pc,op=self.pc,self.read(self.pc,2)
        if op & 0xF00F==0x0006:  # MOV.L Rm,@(R0,Rn).
            n,m=(op>>8)&15,(op>>4)&15
            self.write((self.r[0]+self.r[n])&0xFFFFFFFF,self.r[m],4,record=True)
            self.pc+=2
            self.instructions+=1
            self.visited.add(pc)
        else:
            super().step(in_delay)

    def irq_body(self):
        saved_pr=self.pr
        for _ in range(self.phase_burst):
            self.pr=PAYLOAD_RETURN
            self.subroutine(0x87F2)
        self.pr=saved_pr
        self.poison_scratch()
        self.fpscr=0x40021
        self.pc=self.pr

    def task_payload(self):
        assert self.read(KERNEL+4,2)==5
        assert self.sr & 0xF0==0
        self.r[4]=0
        self.pr=PAYLOAD_RETURN
        self.subroutine(0xD106)
        phase=self.r[0]
        assert 0<=phase<24
        self.delivered.append(phase)
        self.task_runs.append((self.read(INHIBIT_WORD,2),
                               self.read(safety.FUEL_CUT_FLAG,1)))
        self.task_depths.append(self.irq_depth)
        outgoing_state=self.read(TASK6_RAM,1)
        assert outgoing_state in (4,12)
        self.r[4]=phase
        self.pr=PAYLOAD_RETURN
        self.subroutine(0x263EE)
        for i in range(15):
            self.r[i]=0xAA000000+i
        for i in range(16):
            self.fr[i]=bits(-800-i)
        self.fpul=0xCAFEBABE
        self.macl,self.mach,self.gbr=0x123,0x456,0xFFFF9990
        if outgoing_state==12:
            self.fpscr=0x40041
        self.t=not self.t
        self.pc=0x3F2C

    def event(self,level=2):
        self.pc=self.STOP
        self.instructions=0
        self.min_sp=self.STACK
        self.writes.clear()
        self.interrupt(level)
        allowed=PHASE_WRITES | KERNEL_WRITES | SCHEDULER_WRITES
        for a,n in self.writes:
            assert (a,n) in allowed or self.min_sp<=a<self.STACK,(hex(a),n)


class PhaseActivationProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock=(ROOT/'2005 BLE MT.bin').read_bytes()
        main=(ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2=(ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images={'main':main,'v2':v2,'captured':before_pump_scaling(v2)}
        for image in cls.images.values():
            for a,b in ((0x87F2,0x8910),(0x8BE6,0x8CE8),(0x82B6,0x82E0),
                        (0xCF58,0xCFA4),(0xD0D0,0xD18C),(0x33F4,0x357C),
                        (0x3930,0x3C94),(0x3DC8,0x3FE4),(0x49EC,0x4A0C),
                        (0x4ACC,0x4AFC),(0x4B10,0x4B50),(0xFA7C,0xFA94),
                        (0xFBC0,0xFBC8)):
                assert image[a:b]==stock[a:b],hex(a)

    def test_actual_phase_producer_preserves_context_and_dispatches_only_after_publication(self):
        for image,phase,rpm in product(self.images.values(),range(24),(2500,3000,3500,4144)):
            cpu=PhaseActivationMachine(image,phase,rpm)
            cpu.event()
            self.assertEqual(cpu.delivered,[phase])
            self.assertTrue(all(depth==1 for depth in cpu.publication_depths))
            self.assertEqual(cpu.read(TASK5_RAM+3,1),2)
            self.assertEqual(cpu.read(RAM+0xB00C,2),0)
            self.assertEqual(cpu.read(RAM+0xAC17,1),phase)
            self.assertAlmostEqual(cpu.get_float(RAM+0xAC00),rpm,delta=1)
            if phase%4==0:
                self.assertEqual(cpu.read(RAM+0xAFF8,4),phase//4)
                self.assertEqual(cpu.read(TASK6_RAM+3,1),0)
            else:
                self.assertEqual(cpu.read(TASK6_RAM+3,1),1)

    def test_two_pending_phases_are_consumed_in_order_and_third_is_counted_lost(self):
        for image,phase in product(self.images.values(),(1,22,23)):
            cpu=PhaseActivationMachine(image,phase)
            cpu.phase_burst=3
            cpu.event()
            self.assertEqual(cpu.delivered,[phase,(phase+1)%24])
            self.assertEqual(cpu.read(RAM+0xAC17,1),(phase+2)%24)
            self.assertEqual(cpu.read(RAM+0xB00C,1),1)
            self.assertEqual(cpu.read(TASK5_RAM+3,1),2)
            cpu.phase_burst=1
            cpu.event()
            self.assertEqual(cpu.delivered[-1],(phase+3)%24)
            self.assertEqual(cpu.read(RAM+0xB00C,1),1)

    def test_failed_activation_counter_saturates_and_never_overwrites_queued_phase(self):
        for image in self.images.values():
            cpu=PhaseActivationMachine(image,1)
            cpu.write(RAM+0xB00C,254,1)
            cpu.phase_burst=4
            cpu.event()
            self.assertEqual(cpu.delivered,[1,2])
            self.assertEqual(cpu.read(RAM+0xB00C,1),255)
            self.assertEqual(cpu.read(RAM+0xAFEC,8),0x0000000100000002)

    def test_running_task6_has_one_remaining_activation_and_drops_later_mapped_phases(self):
        for image in self.images.values():
            cpu=PhaseActivationMachine(image,0)
            for _ in range(24):
                cpu.event()
            self.assertEqual(cpu.delivered,list(range(24)))
            self.assertEqual(cpu.read(RAM+0xB00C,1),0)
            self.assertEqual(cpu.read(RAM+0xB00D,1),5)
            self.assertEqual(cpu.read(RAM+0xAFF8,4),0)
            self.assertEqual(cpu.read(RAM+0xAFFC,4),0xA55A5AA5)
            self.assertEqual(cpu.read(TASK6_RAM+3,1),0)

    def test_caller_interrupt_mask_defers_consumption_without_exposing_unpublished_slot(self):
        for image,mask in product(self.images.values(),(1,2,7,14)):
            cpu=PhaseActivationMachine(image,1)
            cpu.sr=mask<<4
            cpu.event(15)
            self.assertEqual(cpu.delivered,[])
            self.assertEqual(cpu.read(RAM+0xAFEC,4),1)
            self.assertEqual(cpu.read(TASK5_RAM+3,1),1)
            cpu.r[4],cpu.pr=0,cpu.STOP
            cpu.subroutine(0x3B08)
            self.assertEqual(cpu.delivered,[1])
            self.assertEqual(cpu.read(TASK5_RAM+3,1),2)
            self.assertEqual(cpu.sr & 0xF0,0)


if __name__=='__main__':
    unittest.main(verbosity=2)
