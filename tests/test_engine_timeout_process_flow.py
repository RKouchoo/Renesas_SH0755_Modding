#!/usr/bin/env python3
"""Execute signal timeout startup/poll/reset and its queued injector reset.

TSR10 comparison/capture flags and task delivery are explicit events. The
native code runs through initialization, timeout publication and queue-2
reset callback. Timer elapsed time, RTOS deadlines and physical crank signal
quality are not reconstructed from the loaded log.
"""
import _test_paths
from itertools import product
import unittest

from test_cam_selector_process_flow import CamSelectorMachine, ROOT, RAM
from test_avcs_event_process_flow import CAPTURE_WRITES, QUEUE_WRITES
from test_injector_device_process_flow import InjectorDeviceMachine, DEVICE_WRITES, HARDWARE
from test_runtime_rom_checksum_execution import before_pump_scaling

SIGNAL_WRITES = {(RAM+a, 4) for a in (0xAC00,0xAC04,0xAC08,0xAC10,0xAC2C,0xAC38,
                                     0xAC64,0xAC68,0xAC6C,0xAC70,0xAC74)} | {
    (RAM+a, 1) for a in (0xAC0C,0xAC14,0xAC15,0xAC16,0xAC20,0xAC21,0xAC22,
                         0xAC3C,0xAC3D,0xAC3E,0xAC40,0xAC41,0xAC42,0xAC43,
                         0xAC44,0xAC45,0xAC46,0xAC47,0xAC48,0xAC49,0xAC4A,
                         0xAC4E,0xAC4F,0xAC60)} | {(RAM+0xAC4C, 2)}
SIGNAL_IO_WRITES = {(RAM+a, n) for a,n in ((0xF42A,1),(0xF42E,2),
    (0xF6E4,1),(0xF6EA,2),(0xF6E0,1),(0xF6D4,4),(0xF4AB,1),
    (0xF482,2),(0xF6D8,1),(0xF6C4,1),(0xF6E8,2))}


class EngineTimeoutMachine(CamSelectorMachine):
    LOOKUPS = CamSelectorMachine.LOOKUPS | {
        0x82E0,0x8360,0x8764,0x8776,0x87CE,0x8A38,0x8AC0,0x8BAA,
        0x8CE8,0x83B0,0x8AD6,0xCFD4,0x8B2E,0x8B80,0x6521C,0x80F8,
    }

    def __init__(self, image):
        self.tsr_read = 0
        super().__init__(image)
        for a,n in SIGNAL_IO_WRITES:
            self.write(a, 0, n)
        self.execute(0x813C, SIGNAL_WRITES | SIGNAL_IO_WRITES)
        self.execute(0x8B2E, SIGNAL_WRITES | SIGNAL_IO_WRITES)
        self.write(RAM+0xAC15, 0, 1)
        self.put_float(RAM+0xAC00, 3000)
        self.write(RAM+0xAC04, 6667, 4)
        self.write(RAM+0xAC08, 26667, 4)
        self.write(RAM+0xAC21, 1, 1)

    def load(self, address, size):
        value = super().load(address, size)
        if address == RAM+0xF6E8 and size == 2:
            self.tsr_read = value & 15
        return value

    def write(self, address, value, size=4, record=False):
        if record and address == RAM+0xF6E8 and size == 2:
            # Manual11.2.26: flags clear after a read-of-one/write-of-zero;
            # writing ones does not invent a compare or capture event.
            value = self.read(address,2) & (value | (self.tsr_read ^ 15)) & 15
            self.tsr_read = 0
        super().write(address,value,size,record)

    def poll_timeout(self):
        self.execute(0x81C0, SIGNAL_WRITES | SIGNAL_IO_WRITES | QUEUE_WRITES)
        return self.read(RAM+0xAC0C, 1)


class InjectorResetMachine(InjectorDeviceMachine):
    def step(self, in_delay=False):
        op=self.read(self.pc,2)
        if op & 0xF00F == 0x0005:  # MOV.W Rm,@(R0,Rn).
            n,m=(op>>8)&15,(op>>4)&15
            self.write((self.r[0]+self.r[n])&0xFFFFFFFF,self.r[m],2,record=True)
            self.pc+=2
            self.instructions+=1
        else:
            super().step(in_delay)

    def call_lookup(self, target):
        if target in (0xE3CA,0x11E80,0x8EDA,0x7E50):
            self.entered.append(target)
            return_pc,self.pc=self.pr,target
            while self.pc != return_pc:
                self.step()
        else:
            super().call_lookup(target)


class EngineTimeoutProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock=(ROOT/'2005 BLE MT.bin').read_bytes()
        main=(ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2=(ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images={'main':main,'v2':v2,'captured':before_pump_scaling(v2)}
        for image in cls.images.values():
            for a,b in ((0x80F8,0x8D06),(0x72820,0x72834),(0x69C4,0x69DE),
                         (0x6ADC,0x6AEC),(0xCFD4,0xCFEC),(0xFCA8,0xFCB0),
                         (0xFBD0,0xFBD4),(0x8EDA,0x8F08),(0x7E50,0x7EF4)):
                assert image[a:b]==stock[a:b],hex(a)

    def test_native_startup_sets_timeouts_and_programs_shared_capture_without_fabricating_status(self):
        for image in self.images.values():
            cpu=EngineTimeoutMachine(image)
            cpu.execute(0x813C,SIGNAL_WRITES | SIGNAL_IO_WRITES)
            self.assertEqual(cpu.read(RAM+0xAC0C,1),1)
            self.assertEqual(cpu.read(RAM+0xAC4C,4),0xFFFF0101)
            self.assertEqual(cpu.read(RAM+0xAC20,3),0)
            self.assertEqual(cpu.read(RAM+0xF6D4,4),0xFA000)
            self.assertEqual(cpu.read(RAM+0xF4AB,1)&7,5)
            self.assertEqual(cpu.read(RAM+0xF482,2)&1,1)
            self.assertEqual(cpu.read(RAM+0xF6E8,2),0)

    def test_current_cam_fault_selects_only_zero_or_one_and_secondary_timeout_does_not_stop_engine(self):
        for image,fault in product(self.images.values(),(0,0x80)):
            cpu=EngineTimeoutMachine(image)
            cpu.write(RAM+0xD270,fault,1)
            cpu.execute(0x1A202,{(RAM+0xB52C,1),(RAM+0xAC20,1)})
            self.assertEqual(cpu.read(RAM+0xAC20,1),int(bool(fault)))
            before=cpu.read(RAM+0x930C,1)
            for _ in range(12):
                self.assertEqual(cpu.poll_timeout(),0)
            self.assertEqual(cpu.read(RAM+0xAC4F,1),1)  # Installed72820==0.
            self.assertEqual(cpu.read(RAM+0x930C,1),before)
            self.assertEqual(cpu.get_float(RAM+0xAC00),3000)

    def test_primary_compare_timeout_resets_signal_state_once_and_queues_native_reset_callback(self):
        for image,mode in product(self.images.values(),(0,1)):
            cpu=EngineTimeoutMachine(image)
            cpu.write(RAM+0xAC20,mode,1)
            cpu.write(RAM+0xF6E8,15,2)  # Explicit simultaneous status flags.
            head=cpu.read(RAM+0x930A,1)
            self.assertEqual(cpu.poll_timeout(),1)
            self.assertEqual(cpu.read(RAM+0xF6E8,2),11)  # Arm helper clearsbit2only.
            self.assertEqual(cpu.get_float(RAM+0xAC00),0)
            self.assertEqual(cpu.read(RAM+0xAC04,4),0x7FFFFFFF)
            self.assertEqual(cpu.read(RAM+0xAC08,4),0x7FFFFFFF)
            self.assertEqual(cpu.read(RAM+0xAC15,1),36)
            record=RAM+0x94A0+20*head
            self.assertEqual(cpu.read(record,4),0x69C4)
            count=cpu.read(RAM+0x930C,1)
            cpu.poll_timeout()
            self.assertEqual(cpu.read(RAM+0x930C,1),count)
            cpu.execute(0x1A16E,{(RAM+0xB52C,1),(RAM+0xAC21,1)})
            self.assertEqual(cpu.read(RAM+0xB52C,1)&0xC0,0x80)
            self.assertEqual(cpu.read(RAM+0xAC21,1),0)
            cpu.execute(0x8B2E,SIGNAL_WRITES | SIGNAL_IO_WRITES)
            self.assertEqual(cpu.read(RAM+0xAC0C,1),0)
            self.assertEqual(cpu.read(RAM+0xF6E8,2),10)

    def test_queued_reset_cancels_all_pending_injectors_without_ending_active_hardware_pulses(self):
        writes=CAPTURE_WRITES | DEVICE_WRITES | {(RAM+0xABFC,1),(RAM+0xABF0,2),(RAM+0xABF8,4)}
        for image,active in product(self.images.values(),(False,True)):
            source=EngineTimeoutMachine(image)
            source.write(RAM+0xF6E8,1,2)
            head=source.read(RAM+0x930A,1)
            source.poll_timeout()
            target=InjectorResetMachine(image)
            for bank in (0,1):
                target.put_float(RAM+0xB0B0+4*bank,40)
            for channel in range(6):
                target.put_float(RAM+0xAC18,300 if active else 0)
                target.enqueue(channel,300,30000)
            if active:
                # Explicit hardware start-comparison delivery. Enqueue
                # programs a future edge and does not advance the timer.
                target.write(RAM+0xF666,0x3F,2)
            before=target.read(RAM+0xF666,2)
            target.invoke(source.read(RAM+0x94A0+20*head,4),writes)
            self.assertEqual(target.cancellations[-6:],list(range(6)))
            self.assertEqual(target.read(RAM+0xF666,2),before)
            self.assertEqual(before&0x3F,0x3F if active else 0)
            for h in HARDWARE:
                self.assertEqual(target.read(h+19,1),0)
            if active:
                for channel in range(6):
                    self.assertGreater(target.read(target.read(0xFA94+12*channel,4),2),0)
            self.assertEqual(target.get_float(RAM+0xB0B0),0)
            self.assertEqual(target.read(RAM+0xABF0,2),65535)

    def test_full_shared_cam_queue_drops_timeout_callback_but_keeps_immediate_signal_reset(self):
        for image in self.images.values():
            cpu=EngineTimeoutMachine(image)
            cpu.write(RAM+0x930A,0,1)
            cpu.write(RAM+0x930C,30,1)
            first=cpu.read(RAM+0x94A0,20)
            cpu.write(RAM+0xF6E8,1,2)
            self.assertEqual(cpu.poll_timeout(),1)
            self.assertEqual(cpu.get_float(RAM+0xAC00),0)
            self.assertEqual(cpu.read(RAM+0x930C,1),30)
            self.assertEqual(cpu.read(RAM+0x94A0,20),first)
            # The timeout latch suppresses another reset publication until
            # primary-event recovery. Freeing one slot alone is not a retry.
            cpu.write(RAM+0x930C,29,1)
            cpu.poll_timeout()
            self.assertEqual(cpu.read(RAM+0x930C,1),29)
            cpu.execute(0x8B2E,SIGNAL_WRITES | SIGNAL_IO_WRITES)
            cpu.write(RAM+0xF6E8,1,2)
            cpu.poll_timeout()
            self.assertEqual(cpu.read(RAM+0x930C,1),30)
            self.assertEqual(cpu.read(RAM+0x94A0,4),0x69C4)


if __name__=='__main__':
    unittest.main(verbosity=2)
