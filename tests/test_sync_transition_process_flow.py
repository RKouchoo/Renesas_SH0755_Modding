#!/usr/bin/env python3
"""Trace queued synchronization transitions into spark/fuel and adjacent RAM.

The synchronization decision and delivery time are explicit. Native8298
publishes a real queue-0 message; its callback69DE runs completely. This
does not synthesize crank-tooth waveforms or recover actual queue occupancy.
"""
import _test_paths
from itertools import product
import unittest

from test_engine_timeout_process_flow import (EngineTimeoutMachine, ROOT, RAM,
    SIGNAL_WRITES, SIGNAL_IO_WRITES)
from test_avcs_event_process_flow import QUEUE_WRITES as CAM_QUEUE_WRITES
from test_ignition_device_process_flow import IgnitionDeviceMachine, SCHEDULE_WRITES
from test_injector_device_process_flow import DEVICE_WRITES as INJECTOR_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling

QUEUE_WRITES={(RAM+a,1) for a in range(0x9304,0x9307)} | {
    (RAM+a,4) for a in range(0x9310,0x93D8,4)}
SOURCE_WRITES={(RAM+0xAC60,1),(RAM+0xAC10,4),(RAM+0xAC14,1)}
SIGNAL_WORK_WRITES={(RAM+a,4) for a in (
    0xAE08,0xAE00,0xAE04,0xAD9C,0xADD8,*range(0xADA4,0xADBC,4),
    *range(0xAE0C,0xAE24,4),*range(0xADE0,0xADF8,4))} | {
    (RAM+a,2) for a in (0xAE30,0xAE32)} | {
    (RAM+a,1) for a in (0xAE3C,0xAE3D,0xAE3E,0xAD94,*range(0xAE45,0xAE4B),
                        *range(0xB078,0xB07E),0xB080,0xB088,0xB081,
                        0xB08B,0xB08C,0xB08D)}
CALLBACK_WRITES=SIGNAL_WORK_WRITES | SCHEDULE_WRITES | INJECTOR_WRITES | {
    (RAM+a,1) for a in (0xB7D4,0xC0B5,0xC0B0,0xBFB4,0xBFB5,0xBFB6,0xBFB7)} | {
    (RAM+0xC290,2),(RAM+0xC0A8,2),(RAM+0xC0AC,4)}


class SyncEventMachine(EngineTimeoutMachine):
    LOOKUPS=EngineTimeoutMachine.LOOKUPS | {0x8BCA,0xCFEC}

    def __init__(self,image):
        super().__init__(image)
        for a in range(0x9310,0x93D8,4):
            self.write(RAM+a,0xA55A5AA5,4)
        for a,value in ((0x9304,1),(0x9305,0),(0x9306,1)):
            self.write(RAM+a,value,1)
        self.put_float(RAM+0xAC38,25)
        self.write(RAM+0xAC42,7,1)

    def publish(self,state):
        head=self.read(RAM+0x9304,1)
        self.original_r[4]=state
        self.execute(0x8298,SOURCE_WRITES | QUEUE_WRITES)
        return RAM+0x9310+20*head


class SyncTransitionMachine(IgnitionDeviceMachine):
    def __init__(self,image):
        super().__init__(image)
        for a,n in SIGNAL_WORK_WRITES:
            self.write(a,0xA5A5A5A5,n)
        for i in range(6):
            self.write(RAM+0xC68C+i,image[0x7B250+i],1)
        # Native A76C work ends before WB publications. Distinct sentinels
        # cover the entire current8-float output set plus moved lean slots.
        self.protected={a:0xA5A00000+i for i,a in enumerate((*self.wideband_outputs,
                       self.lean_counter_ram,self.lean_state_ram))}
        for a,value in self.protected.items():
            self.write(a,value,4)

    def call_lookup(self,target):
        if target in (0x9B58,0xD914,0xDB2E,0xA76C,0x11E84,0x29C08,
                      0x261EC,0x2684E,0x1D8AE,0x2A242,0x29C00,
                      0x26200,0x26846):
            self.entered.append(target)
            return_pc,self.pc=self.pr,target
            while self.pc!=return_pc:
                self.step()
        else:
            super().call_lookup(target)

    def deliver(self,source,record):
        for i in range(0,12,4):
            self.write(RAM+0xAF00+i,source.read(record+4+i,4),4)
        self.original_r[4]=RAM+0xAF00
        self.invoke(source.read(record,4),CALLBACK_WRITES)
        for a,value in self.protected.items():
            assert self.read(a,4)==value,hex(a)


class SyncTransitionProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock=(ROOT/'2005 BLE MT.bin').read_bytes()
        main=(ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2=(ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images={'main':main,'v2':v2,'captured':before_pump_scaling(v2)}
        for image in cls.images.values():
            for a,b in ((0x8298,0x82B6),(0x8BCA,0x8BE6),(0x69DE,0x6A06),
                         (0x11E84,0x11EBE),(0xA76C,0xA884),
                         (0x9B58,0x9B7C),(0xD914,0xD92C),(0xDB2E,0xDB50),
                         (0xFBD4,0xFBD8),(0xFCB0,0xFCB8),(0xFA0C,0xFA14)):
                assert image[a:b]==stock[a:b],hex(a)

    def test_real_sync_event_payload_updates_period_seed_only_for_acquisition(self):
        for image,state in product(self.images.values(),(0,1)):
            cpu=SyncEventMachine(image)
            old=cpu.read(RAM+0xAC10,4)
            record=cpu.publish(state)
            self.assertEqual(cpu.read(record,4),0x69DE)
            self.assertEqual(cpu.read(record+4,4),state)
            self.assertEqual(cpu.read(RAM+0x9306,1),2)
            if state:
                self.assertEqual(cpu.get_float(RAM+0xAC10),25)
                self.assertEqual(cpu.read(RAM+0xAC14,1),6)
            else:
                self.assertEqual(cpu.read(RAM+0xAC10,4),old)

    def test_acquisition_rearms_spark_fuel_and_auxiliary_mode_without_overwriting_patch_ram(self):
        for image,cam_fault in product(self.images.values(),(0,0x20)):
            source=SyncEventMachine(image);record=source.publish(1)
            cpu=SyncTransitionMachine(image)
            cpu.write(RAM+0xB52C,cam_fault,1)
            cpu.write(RAM+0xC28D,0,1)
            cpu.write(RAM+0xC0B5,0,1)
            cpu.deliver(source,record)
            self.assertEqual(cpu.read(RAM+0xB7D4,1),1)
            self.assertEqual(cpu.read(RAM+0xC28D,1),1)
            self.assertEqual(cpu.read(RAM+0xC0B5,1),1)
            self.assertEqual(cpu.read(RAM+0xBFB6,1),255)
            self.assertEqual(cpu.read(RAM+0xC290,2),0 if cam_fault else 0xFC0)
            self.assertEqual(cpu.read(RAM+0xAE45,6),int.from_bytes(image[0x7B250:0x7B256],'big'))

    def test_loss_cancels_both_scheduler_requests_and_resets_event_counters_without_patch_alias(self):
        for image in self.images.values():
            source=SyncEventMachine(image);record=source.publish(0)
            cpu=SyncTransitionMachine(image)
            cpu.write(RAM+0xC0A8,10,2)
            cpu.write(RAM+0xC0AC,20,4)
            cpu.write(RAM+0xC0B0,1,1)
            for a in (0xBFB4,0xBFB5,0xBFB6,0xBFB7):
                cpu.write(RAM+a,0xA5,1)
            cpu.deliver(source,record)
            self.assertEqual(cpu.read(RAM+0xC0A8,2),0)
            self.assertEqual(cpu.read(RAM+0xC0AC,4),0)
            self.assertEqual(cpu.read(RAM+0xC0B0,1),0)
            self.assertEqual(cpu.read(RAM+0xBFB4,4),0)
            self.assertEqual(cpu.cancellations[-6:],list(range(6)))
            # 296F0 copies alternating hardware IDs from 4C69C. 29C08
            # visits both bytes in each half-record, not the logical IDs.
            self.assertEqual([call[1] for call in cpu.coil_calls if call[0]==0x99B4][-12:],
                             [1,0,0,1,3,2,2,3,4,5,5,4])
            self.assertEqual(cpu.read(RAM+0xB078,6),0)
            self.assertEqual(cpu.read(RAM+0xAE3C,3),0xFF0000)

    def test_full_sync_queue_preserves_memory_but_sender_does_not_retry_event(self):
        for image in self.images.values():
            cpu=SyncEventMachine(image)
            cpu.write(RAM+0x9304,0,1)
            cpu.write(RAM+0x9306,10,1)
            before=cpu.read(RAM+0x9310,20)
            cpu.publish(1)
            self.assertEqual(cpu.read(RAM+0x9306,1),10)
            self.assertEqual(cpu.read(RAM+0x9310,20),before)
            self.assertEqual(cpu.get_float(RAM+0xAC10),25)

    def test_timeout_while_synchronized_posts_loss_before_separate_injector_reset(self):
        for image in self.images.values():
            source=SyncEventMachine(image)
            source.write(RAM+0xAC3C,1,1)
            source.write(RAM+0xAC16,1,1)
            source.write(RAM+0xF6E8,1,2)
            head=source.read(RAM+0x9304,1)
            cam_head=source.read(RAM+0x930A,1)
            source.execute(0x81C0,SIGNAL_WRITES | SIGNAL_IO_WRITES |
                           SOURCE_WRITES | QUEUE_WRITES | CAM_QUEUE_WRITES)
            record=RAM+0x9310+20*head
            self.assertEqual(source.read(RAM+0xAC16,1),0)
            self.assertEqual(source.read(record,4),0x69DE)
            self.assertEqual(source.read(record+4,4),0)
            self.assertEqual(source.read(RAM+0x94A0+20*cam_head,4),0x69C4)
            cpu=SyncTransitionMachine(image)
            cpu.deliver(source,record)
            self.assertEqual(cpu.cancellations[-6:],list(range(6)))


if __name__=='__main__':
    unittest.main(verbosity=2)
