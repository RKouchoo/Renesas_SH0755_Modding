#!/usr/bin/env python3
"""Execute received CAN requests through native cut latches and phase patterns.

Mailbox bytes/arrival bits, battery, calculated torque and phase are explicit
fixtures. Native receive copies, retained checks, timeout/reset, ratio, pattern
lookups and final B744 publication execute. CAN bus traffic, physical torque
and real task timing are not reconstructed from the vehicle capture.
"""
import _test_paths
from itertools import product
import unittest

from test_dbw_arbitration_process_flow import DBWReceiveMachine
from test_wideband_fuel_guard_execution import INHIBIT_GETTERS
from test_runtime_rom_checksum_execution import before_pump_scaling

ROOT, RAM = _test_paths.ROOT, 0xFFFF0000
RX_WRITES = {(RAM+a, 1) for a in (0xB1FE, 0xB200, 0xB24C, 0xB24D, *range(0xB260,0xB27C),
                                  *range(0xB280,0xB286))} | {
    (RAM+a, 4) for a in (0xB250, 0xB254, 0xB258, 0xB25C)} | {
    (RAM+a, 2) for a in (0xB27C, 0xB27E, 0xE40E)}
MESSAGE_WRITES = {(RAM+a, 1) for a in (0xB1FE, 0xB200, 0xCC54, *range(0xCC5C,0xCC72),
                                       *range(0xCC78,0xCC85))} | {
    (RAM+a, 2) for a in (0xCC72,0xCC74,0xCC76,0x82B8,0xE40E)} | {
    (RAM+0xCC58,4)}
PATTERN_WRITES = {(RAM+a,1) for a in (0xCCB8,0xCCB9,0xCCBA,0xCCBB,
                                     0xCCC2,0xCCC3,0xCCC4)} | {
    (RAM+a,2) for a in (0xCCB0,0xCCB2,0xB744)} | {(RAM+0xCCAC,4)}
MODEL_WRITES = {(RAM+a,4) for a in (0xB82C,0xCA38,0xCA3C,0xC5DC,
    0xC5E4,0xC5E8,0xC5EC,0xC5F0,0xC5F4,0xC5F8,0xC5FC,0xC600,0xC608)} | {
    (RAM+a,1) for a in (0xCA49,0xC5E0,0xC604,0xC60C,0xC60D)}


class ReceivedCutMachine(DBWReceiveMachine):
    LOOKUPS = DBWReceiveMachine.LOOKUPS | {0x1C5D4, *INHIBIT_GETTERS,
        0x146A6, 0x257C, 0x368B2, 0x146D2, 0x3D4CE, 0x2130, 0x20F8,
        0x2458, 0x24B0, 0x3C652, 0x3C4C6, 0x2714, 0x2808, 0x2878, 0x368C6}

    def __init__(self,image):
        super().__init__(image)
        for a in range(0xB24C,0xB286): self.write(RAM+a,0,1)
        self.write(RAM+0xCC54,0,1)
        for a in range(0xCC58,0xCC85): self.write(RAM+a,0,1)
        for a in range(0xCCAC,0xCCC5): self.write(RAM+a,0,1)
        for a in (0xB27C,0xB27E,0xCC72,0xCC74,0xCC76,0x82B8):
            self.write(RAM+a,0x00FF,2)
        for a in (0xB528,0xB529,0xCA48,0xCA49): self.write(RAM+a,0,1)
        self.put_float(RAM+0xCA38,100)
        for a in (0xC5E4,0xC5E8,0xC5EC,0xC5F0,0xC5F4,0xC5F8,0xC5FC,0xC600,0xC608):
            self.put_float(RAM+a,0)
        for a in (0xC604,0xC60C,0xC60D):self.write(RAM+a,0,1)
        self.put_float(RAM+0xB3B8,36)
        self.write(RAM+0xCC7A,1,1)
        self.execute(0x146A6,RX_WRITES)
        self.write(RAM+0xB52C,0x80,1)
        self.execute(0x3CD80,PATTERN_WRITES)
        self.write(RAM+0xB52C,0,1)
        for descriptor in (0x4AF5C,0x4AF74,0x4B034,0x4AFD4,0x4B064):
            source=self.read(descriptor+12,4)
            for i in range(8):self.write(source+i,0,1)

    def step(self,in_delay=False):
        pc,op=self.pc,self.read(self.pc,2)
        n,m=(op>>8)&15,(op>>4)&15
        if op == 0x0019:  # DIV0U; SR M/Q are bits 9/8, T is separate here.
            self.sr &= ~0x300
            self.t = False
        elif op & 0xF0FF == 0x4024:  # ROTCL Rn.
            value = self.r[n]
            self.r[n] = ((value << 1) | int(self.t)) & 0xFFFFFFFF
            self.t = bool(value & 0x80000000)
        elif op & 0xF00F == 0x3004:  # DIV1 Rm,Rn, one native division step.
            # Renesas SH-1/SH-2/SH-DSP Software Manual, 6.1.19, pp162-163:
            # https://www.renesas.com/en/document/mah/sh-1sh-2sh-dsp-software-manual
            old_q, flag_m = bool(self.sr & 0x100), bool(self.sr & 0x200)
            sign = bool(self.r[n] & 0x80000000)
            value = ((self.r[n] << 1) | int(self.t)) & 0xFFFFFFFF
            self.r[n] = value
            if old_q == flag_m:
                self.r[n] = (value-self.r[m]) & 0xFFFFFFFF
                carry = self.r[n] > value
            else:
                self.r[n] = (value+self.r[m]) & 0xFFFFFFFF
                carry = self.r[n] < value
            flag_q = carry ^ sign ^ flag_m
            self.sr = (self.sr & ~0x100) | (int(flag_q) << 8)
            self.t = flag_q == flag_m
        elif op & 0xF00F == 0x0004:  # MOV.B Rm,@(R0,Rn).
            self.write((self.r[0]+self.r[n])&0xFFFFFFFF,self.r[m],1,record=True)
        elif op & 0xF0FF == 0x4009:  # SHLR2, T unchanged.
            self.r[n] >>= 2
        else:return super().step(in_delay)
        self.trace.append((pc,op));self.pc+=2;self.instructions+=1

    def supply(self,descriptor,payload):
        assert len(payload)==8
        source=self.read(descriptor+12,4)
        for i,v in enumerate(payload):self.write(source+i,v,1)
        self.write(RAM+0xE40E,self.read(RAM+0xE40E,2)|self.read(descriptor+6,2),2)

    def pattern(self,phase=0):
        self.write(RAM+0xB528,phase,1)
        self.execute(0x3CE0A,PATTERN_WRITES)
        self.execute(0x3CE58,PATTERN_WRITES)
        self.execute(0x3D33E,PATTERN_WRITES)
        self.execute(0x3D050,PATTERN_WRITES)
        return self.read(RAM+0xB744,2)

    def requests(self,a=None,b=None):
        if a is not None:self.supply(0x4AFD4,a)
        if b is not None:self.supply(0x4B064,b)
        self.execute(0x3BEE4,MESSAGE_WRITES)
        self.execute(0x3C388,{(RAM+0xCC71,1)})
        self.execute(0x472E4,{(RAM+0xCFA0,1),(RAM+0xB744,2)})
        return self.read(RAM+0xB744,2)

    def duration_model(self,rpm,load,request):
        for a,v in ((0xB544,rpm),(0xB438,load),(0xB250,request)):
            self.put_float(RAM+a,v)
        # 110C8..110E4 is the actual periodic pointer order for this branch.
        for entry in (0x1E0C8,0x365C0,0x36610,0x2EEAE,0x2EE88,0x2EE6C,0x2ED76,
                      0x2ED38,0x2ED14,0x2ECC0,0x2ECCA):
            self.execute(entry,MODEL_WRITES)
        return tuple(self.get_float(RAM+a) for a in (0xCA38,0xC5F8,0xC5DC))


class ReceivedCutProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock=(ROOT/'2005 BLE MT.bin').read_bytes()
        main=(ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2=(ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images={'main':main,'v2':v2,'captured':before_pump_scaling(v2)}
        for image in cls.images.values():
            for a,b in ((0x14374,0x147A0),(0x3CD80,0x3D52C),(0x3BEE4,0x3C550),
                         (0x4AF5C,0x4AF8C),(0x4AFD4,0x4AFEC),(0x4B034,0x4B04C),
                         (0x4B064,0x4B07C),(0x77468,0x774B8),(0x4C6B4,0x4C72C),
                         (0x764D8,0x764F0),(0x72D68,0x72D6C)):
                assert image[a:b]==stock[a:b],hex(a)
            for a,b in ((0x1E0C8,0x1E0FC),(0x365C0,0x366EC),
                         (0x2ECC0,0x2EEF4),(0x110C8,0x110E8),
                         (0x60720,0x60748),(0x60860,0x6087C),
                         (0x79918,0x79934),(0x2714,0x2836)):
                assert image[a:b]==stock[a:b],hex(a)

    def test_no_received_permission_keeps_all_twelve_pattern_slots_enabled(self):
        for image,torque in product(self.images.values(),(0,1,50,100,400)):
            cpu=ReceivedCutMachine(image)
            cpu.put_float(RAM+0xCA38,torque)
            cpu.put_float(RAM+0xB250,0)
            for phase in range(24):
                self.assertEqual(cpu.pattern(phase),0)
                self.assertEqual(cpu.read(RAM+0xCCB8,1),12)
                self.assertEqual(cpu.read(RAM+0xCCB2,2),0xFFF)

    def test_received_ratio_reaches_five_cylinder_cut_and_releases_at_update_boundary(self):
        for image in self.images.values():
            cpu=ReceivedCutMachine(image)
            cpu.write(RAM+0xB24C,1,1)
            cpu.put_float(RAM+0xB250,0)
            # Native minimum is 2 enabled slots out of 12, pattern 0x300.
            self.assertEqual([cpu.pattern(phase) for phase in range(24)],
                             [0]*5+[0x1F]*19)
            self.assertEqual(cpu.read(RAM+0xCCB8,1),2)
            self.assertEqual(cpu.read(RAM+0xCCB2,2),0x300)
            cpu.write(RAM+0xB24C,0,1)
            # Permission clears immediately, published bits wait for count 6.
            self.assertEqual([cpu.pattern(phase) for phase in range(12)],
                             [0x1F]*5+[0]*7)
            self.assertEqual(cpu.read(RAM+0xCCB8,1),12)

    def test_native_can_parent_copies_permission_and_timeout_resets_it(self):
        for image in self.images.values():
            cpu=ReceivedCutMachine(image)
            # ID501: byte3 scales request, byte4 is permission, byte5 sequence.
            payload=[0,0,0,0,1,1,0,0]
            cpu.supply(0x4AF5C,payload)
            cpu.execute(0x14374,RX_WRITES)
            self.assertEqual(cpu.read(RAM+0xB24C,1),1)
            self.assertEqual(cpu.get_float(RAM+0xB250),0)
            self.assertEqual([cpu.pattern(i) for i in range(6)], [0]*5+[0x1F])
            for _ in range(63):cpu.execute(0x14374,RX_WRITES)
            self.assertEqual(cpu.read(RAM+0xB24C,1),0)
            self.assertEqual([cpu.pattern(i) for i in range(6)], [0x1F]*5+[0])
            self.assertEqual(cpu.get_float(RAM+0xB250),408)

    def test_combined_cut_needs_both_received_requests_and_two_qualifying_messages(self):
        for image in self.images.values():
            cpu=ReceivedCutMachine(image)
            a=[0,0,0,0,0,0,0x20,0]
            b=[1,0,0,0,0,0,0,0]
            self.assertEqual(cpu.requests(a,b),0)
            self.assertEqual(cpu.requests(a,b),0xFFFF)
            self.assertEqual(cpu.read(RAM+0xCC71,1)&0x38,0x38)
            self.assertEqual(cpu.requests([0]*8,b),0)
            self.assertEqual(cpu.read(RAM+0xCC71,1)&8,0)
            for _ in range(3):self.assertEqual(cpu.requests(a,[0]*8),0)

    def test_missing_messages_and_low_battery_reset_hold_latches_until_fresh_clear(self):
        for image in self.images.values():
            cpu=ReceivedCutMachine(image)
            a=[0,0,0,0,0,0,0x20,0];b=[1,0,0,0,0,0,0,0]
            cpu.requests(a,b);self.assertEqual(cpu.requests(a,b),0xFFFF)
            for _ in range(10):self.assertEqual(cpu.requests(),0xFFFF)
            cpu.put_float(RAM+0xABB4,5)
            # 3C4C6 resets received values/counters, but preserves CC71/08/10.
            self.assertEqual(cpu.requests(),0xFFFF)
            cpu.put_float(RAM+0xABB4,13.5)
            self.assertEqual(cpu.requests([0]*8,[0]*8),0)

    def test_startup_battery_window_expires_without_creating_or_releasing_a_latch(self):
        for image in self.images.values():
            cpu=ReceivedCutMachine(image)
            cpu.execute(0x3C494,MESSAGE_WRITES)
            self.assertEqual(cpu.read(RAM+0xCC7A,1),44)
            self.assertEqual(cpu.read(RAM+0xCC71,1)&0x38,0)
            cpu.put_float(RAM+0xABB4,7.99)
            cpu.execute(0x3C366,{(RAM+0xCC7A,1)})
            self.assertEqual(cpu.read(RAM+0xCC7A,1),44)
            cpu.put_float(RAM+0xABB4,8)
            for remaining in range(43,-1,-1):
                cpu.execute(0x3C366,{(RAM+0xCC7A,1)})
                self.assertEqual(cpu.read(RAM+0xCC7A,1),remaining)
            a=[0,0,0,0,0,0,0x20,0];b=[1,0,0,0,0,0,0,0]
            for _ in range(4):self.assertEqual(cpu.requests(a,b),0)
            # An existing pair is retained after the window closes.
            cpu.write(RAM+0xCC7A,1,1)
            cpu.requests(a,b);self.assertEqual(cpu.requests(a,b),0xFFFF)
            cpu.execute(0x3C366,{(RAM+0xCC7A,1)})
            self.assertEqual(cpu.read(RAM+0xCC7A,1),0)
            self.assertEqual(cpu.requests(a,b),0xFFFF)
            self.assertEqual(cpu.requests([0]*8,[0]*8),0)

    def test_ratio_thresholds_and_native_rotation_keep_request_bounded(self):
        for image in self.images.values():
            for ratio,slots in ((0,2),(1,2),(1.5,4),(2,4),(10,6),(25,6),
                                (40,8),(50,8),(60,10),(75,10),(90,12),(100,12)):
                cpu=ReceivedCutMachine(image)
                cpu.write(RAM+0xB24C,1,1)
                cpu.put_float(RAM+0xB250,ratio)
                for phase in range(24):cpu.pattern(phase)
                self.assertEqual(cpu.read(RAM+0xCCB8,1),slots)
                self.assertEqual(cpu.read(RAM+0xCCB2,2).bit_count(),slots)
            for rotation in range(24):
                cpu=ReceivedCutMachine(image)
                cpu.original_r[4]=0xA53
                cpu.original_r[5]=rotation
                cpu.execute(0x3D4CE,set())
                shift=rotation%12
                expected=((0xA53>>shift)|(0xA53<<(12-shift)))&0xFFF
                self.assertEqual(cpu.r[0]&0xFFFF,expected)

    def test_injector_scalar_model_alias_does_not_enable_received_permission(self):
        stock=(ROOT/'2005 BLE MT.bin').read_bytes()
        for image in self.images.values():
            scalar_control=bytearray(image)
            scalar_control[0x76014:0x76018]=stock[0x76014:0x76018]
            for rpm,load,request in product((2500,2800,3000,3500,4144),
                                             (.7,1.975,2.5),(0,80,200,408)):
                cpu=ReceivedCutMachine(image)
                control=ReceivedCutMachine(bytes(scalar_control))
                actual=cpu.duration_model(rpm,load,request)
                original=control.duration_model(rpm,load,request)
                self.assertLessEqual(actual[0],original[0])
                self.assertGreaterEqual(actual[1],original[1])
                self.assertEqual(cpu.read(RAM+0xB24C,1),0)
                self.assertEqual(cpu.read(RAM+0xC5E0,1)&1,0)
                self.assertEqual(cpu.pattern(),0)
                control.pattern()
                self.assertGreaterEqual(cpu.get_float(RAM+0xCCAC),
                                        control.get_float(RAM+0xCCAC))
                self.assertEqual(cpu.read(RAM+0xCCB8,1),12)

    def test_received_drop_resets_throttle_correction_and_rising_request_releases(self):
        for image in self.images.values():
            cpu=ReceivedCutMachine(image)
            cpu.write(RAM+0xB24C,1,1)
            cpu.duration_model(2800,1.975,200)
            self.assertEqual(cpu.read(RAM+0xC604,1),0)
            cpu.duration_model(2800,1.975,180)
            self.assertEqual(cpu.read(RAM+0xC604,1),1)
            self.assertEqual(cpu.get_float(RAM+0xC5EC),0)
            self.assertEqual(cpu.get_float(RAM+0xC5F0),0)
            cpu.duration_model(2800,2.5,180)
            self.assertEqual(cpu.read(RAM+0xC604,1),1)
            cpu.duration_model(2800,2.5,181)
            self.assertEqual(cpu.read(RAM+0xC604,1),0)
            self.assertEqual(cpu.read(RAM+0xC5E0,1)&1,1)

    def test_received_throttle_permission_needs_can_bit_and_clear_native_inhibit(self):
        for image,permission,inhibit in product(self.images.values(),(0,1),(0,1)):
            cpu=ReceivedCutMachine(image)
            cpu.write(RAM+0xB24C,permission,1)
            cpu.write(RAM+0xCA48,inhibit,1)
            cpu.duration_model(2800,1.975,80)
            self.assertEqual(cpu.read(RAM+0xCA49,1)&1,permission and not inhibit)
            self.assertEqual(cpu.read(RAM+0xC5E0,1)&1,permission and not inhibit)

    def test_periodic_edge_aligns_phase_pattern_and_slow_summary_retains_release_history(self):
        slow_writes=PATTERN_WRITES|{(RAM+0xCCC0,2)}
        for image,start in product(self.images.values(),range(24)):
            cpu=ReceivedCutMachine(image)
            cpu.write(RAM+0xB24C,1,1)
            cpu.put_float(RAM+0xB250,0)
            cpu.execute(0x3CE0A,PATTERN_WRITES)
            cpu.execute(0x3CE58,PATTERN_WRITES)
            cpu.execute(0x3D33E,PATTERN_WRITES)
            cpu.execute(0x3D48C,PATTERN_WRITES)
            for phase in range(start,start+12):
                cpu.write(RAM+0xB528,phase%24,1)
                cpu.execute(0x3D050,PATTERN_WRITES)
                self.assertEqual(cpu.read(RAM+0xCCB2,2).bit_count(),2)
                self.assertEqual(cpu.read(RAM+0xB744,2).bit_count(),5)
            cpu.execute(0x3D3A2,slow_writes)
            cpu.write(RAM+0xB24C,0,1)
            for phase in range(6):cpu.pattern(phase)
            self.assertEqual(cpu.read(RAM+0xB744,2),0)
            for count in range(1,252):
                cpu.execute(0x3D3A2,slow_writes)
                self.assertEqual(cpu.read(RAM+0xCCC0,2),count)
                self.assertEqual(bool(cpu.read(RAM+0xCCBB,1)&4),count<=250)
                self.assertEqual(cpu.read(RAM+0xB744,2),0)


if __name__=='__main__':unittest.main(verbosity=2)
