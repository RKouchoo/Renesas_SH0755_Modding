#!/usr/bin/env python3
"""Execute native permission/inhibit parents around received torque requests.

Received status, digital inputs and fault summaries remain supplied boundaries.
The actual mode initializer, reason-byte builders, hysteresis, timing history,
and downstream CAN cut/throttle permission execute from all pinned images.
"""
import _test_paths
from itertools import product
import unittest

from test_received_cut_process_flow import ReceivedCutMachine, PATTERN_WRITES, RAM, ROOT
from test_runtime_rom_checksum_execution import before_pump_scaling

MODE_WRITES={(RAM+a,1) for a in (0xCA45,0xCA46,0xCA48,0xCA49,0xCA62,0xC5E0)}|{
    (RAM+0xCA60,2)}


class TorqueModeMachine(ReceivedCutMachine):
    LOOKUPS=ReceivedCutMachine.LOOKUPS|{0x3BB12,0x27456,0x146E0,0x3675E,
        0x3682C,0x36854,0x3687C,0x19CB8,0x651BA,0x2484,0x251C}

    def __init__(self,image):
        super().__init__(image)
        for a in (0xCA45,0xCA46,0xCA62,0xB748,0xC0E3,0xB51C,0xD26F):
            self.write(RAM+a,0,1)
        for a in (0xCA60,0xCCB4,0xCCB6):self.write(RAM+a,0,2)
        for a,v in ((0xB90D,1),(0xB90E,1),(0xCC4C,0x80),(0xB24D,0x80)):
            self.write(RAM+a,v,1)
        for a,v in ((0xB2A0,800),(0xBE48,0),(0xCCAC,0),(0xB3AC,67)):
            self.put_float(RAM+a,v)
        self.execute(0x36054,MODE_WRITES)

    def qualify(self):
        for entry in (0x36190,0x36370,0x36610,0x2ECCA):
            self.execute(entry,MODE_WRITES)
        return tuple(self.read(RAM+a,1) for a in (0xCA45,0xCA46,0xCA48,0xCA49))

    def pattern_history(self):
        writes={(RAM+0xCCBB,1),(RAM+0xCCB4,2),(RAM+0xCCB6,2)}
        for entry in (0x3D2E4,0x3D28E,0x3D322):self.execute(entry,writes)


class TorqueModeProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock=(ROOT/'2005 BLE MT.bin').read_bytes()
        main=(ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2=(ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images={'main':main,'v2':v2,'captured':before_pump_scaling(v2)}
        for image in cls.images.values():
            for a,b in ((0x36054,0x36904),(0x3D28E,0x3D3A2),
                         (0x72CD4,0x72CE0),(0x72D10,0x72D50)):
                assert image[a:b]==stock[a:b],hex(a)

    def test_warm_parent_releases_throttle_permission_but_keeps_cylinder_cut_inhibited(self):
        for image in self.images.values():
            cpu=TorqueModeMachine(image)
            self.assertEqual(cpu.read(RAM+0xCA48,1)&3,3)
            self.assertEqual(cpu.qualify()[:3],(0,0,0x0A))
            self.assertEqual(cpu.read(RAM+0xC5E0,1)&1,0)
            cpu.write(RAM+0xB24C,1,1)
            self.assertEqual(cpu.qualify()[:3],(0,0,0x0A))
            self.assertEqual(cpu.read(RAM+0xC5E0,1)&1,1)

    def test_each_mode_reason_inhibits_received_cut_and_healthy_state_releases(self):
        # Reason sources are native getter inputs, not their upstream causes.
        cases=((0xCC4C,0,0,1),(0xB748,0x80,0,2),(0xC0E3,0x40,0,4),
               (0xCA49,2,0,8),(0xB51C,8,0,0x10),(0xD26F,8,1,1),
               (0xB24D,0,1,2))
        for image,(address,value,byte,mask) in product(self.images.values(),cases):
            cpu=TorqueModeMachine(image)
            cpu.qualify()
            cpu.write(RAM+0xB24C,1,1)
            old=cpu.read(RAM+address,1)
            cpu.write(RAM+address,value,1)
            reasons=cpu.qualify()
            self.assertEqual(reasons[byte]&mask,mask)
            self.assertEqual(reasons[2]&3,3)
            self.assertEqual(cpu.read(RAM+0xC5E0,1)&1,0)
            cpu.execute(0x3CE58,PATTERN_WRITES)
            self.assertEqual(cpu.read(RAM+0xCCB8,1),12)
            cpu.write(RAM+address,old,1)
            # Digital falling-edge delay is a distinct native timed reason.
            for _ in range(380):cpu.qualify()
            self.assertEqual(cpu.read(RAM+0xCA48,1)&3,2)
            self.assertEqual(cpu.read(RAM+0xC5E0,1)&1,1)

    def test_warm_parent_blocks_aggressive_received_cut_across_loaded_inputs(self):
        for image,rpm,pressure,transient in product(self.images.values(),
                (2500,2800,3000,3500,4144),(75,800,1000,1800),(0,-.2,.2)):
            cpu=TorqueModeMachine(image)
            cpu.write(RAM+0xB24C,1,1)
            cpu.put_float(RAM+0xB250,0)
            cpu.put_float(RAM+0xB544,rpm)
            cpu.put_float(RAM+0xB2A0,pressure)
            cpu.put_float(RAM+0xBE48,transient)
            cpu.qualify()
            self.assertEqual(cpu.read(RAM+0xC5E0,1)&1,1)
            self.assertEqual(cpu.read(RAM+0xCA48,1)&0x0A,0x0A)
            for phase in range(6):self.assertEqual(cpu.pattern(phase),0)
            self.assertEqual(cpu.read(RAM+0xCCB8,1),12)

    def test_ratio_and_low_rpm_hysteresis_inhibit_only_the_received_pattern(self):
        for image in self.images.values():
            cpu=TorqueModeMachine(image)
            cpu.write(RAM+0xB24C,1,1)
            # Explicit cold calibration window; warm ECT independently blocks.
            cpu.put_float(RAM+0xB3AC,-39)
            for rpm,expected in ((1400,0),(1349,4),(1360,4),(1375,0)):
                cpu.put_float(RAM+0xB544,rpm)
                flags=cpu.qualify()[2]
                self.assertEqual(flags&4,expected)
                self.assertEqual(bool(flags&2),bool(expected))
            cpu.put_float(RAM+0xB544,3000)
            for ratio,expected in ((100,0x40),(99.4,0x40),(99,0)):
                cpu.put_float(RAM+0xCCAC,ratio)
                flags=cpu.qualify()[2]
                self.assertEqual(flags&0x40,expected)
                self.assertEqual(bool(flags&2),bool(expected))

    def test_native_coolant_window_and_hysteresis_bound_the_forced_cut_fixture(self):
        for image in self.images.values():
            cpu=TorqueModeMachine(image)
            cpu.write(RAM+0xB24C,1,1)
            for ect,mask in ((67,8),(-38,8),(-39,0),(-41,0x10),
                             (-40,0x10),(-39,0),(-37,8),(85,8)):
                cpu.put_float(RAM+0xB3AC,ect)
                flags=cpu.qualify()[2]
                self.assertEqual(flags&0x18,mask)
                self.assertEqual(bool(flags&2),bool(mask))
                cpu.execute(0x3CE58,PATTERN_WRITES)
                self.assertEqual(cpu.read(RAM+0xCCB8,1),12 if mask else 2)

    def test_native_falling_edge_blocks_reentry_for_1250_calls_and_counter_saturates(self):
        for image in self.images.values():
            cpu=TorqueModeMachine(image)
            cpu.put_float(RAM+0xB3AC,-39)
            cpu.write(RAM+0xB24C,1,1)
            cpu.qualify()
            cpu.execute(0x3CE58,PATTERN_WRITES)
            cpu.pattern_history()
            self.assertEqual(cpu.read(RAM+0xCCBB,1)&3,3)
            self.assertEqual(cpu.read(RAM+0xCCB4,2),0)
            cpu.write(RAM+0xCCBB,2,1)
            cpu.pattern_history()
            self.assertEqual(cpu.read(RAM+0xCCB4,2),1250)
            self.assertEqual(cpu.read(RAM+0xCCBB,1)&3,0)
            for remaining in range(1249,-1,-1):
                cpu.pattern_history()
                self.assertEqual(cpu.read(RAM+0xCCB4,2),remaining)
                cpu.qualify()
                self.assertEqual(bool(cpu.read(RAM+0xCA48,1)&2),remaining!=0)
                cpu.execute(0x3CE58,PATTERN_WRITES)
                self.assertEqual(cpu.read(RAM+0xCCB8,1),12 if remaining else 2)
            cpu.write(RAM+0xCCBB,3,1)
            cpu.write(RAM+0xCCB6,65535,2)
            cpu.pattern_history()
            self.assertEqual(cpu.read(RAM+0xCCB6,2),65535)
            self.assertEqual(cpu.read(RAM+0xCCB4,2),1250)


if __name__=='__main__':unittest.main(verbosity=2)
