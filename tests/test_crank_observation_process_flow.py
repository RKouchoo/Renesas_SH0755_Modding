#!/usr/bin/env python3
"""Connect retained crank observations to the shared cam/diagnostic queue.

Decoded positions, capture timestamps and callback delivery are explicit.
NativeD92C, DB50, queue publication and high-RPM6A6AC snapshot execute.
This is not a physical crank waveform or complete low-RPM monitor model.
"""
import _test_paths
from itertools import product
import unittest

from test_purge_monitor_shared_state_flow import PurgeMonitorMachine,SNAPSHOT_WRITES,ROOT,RAM
from test_avcs_event_process_flow import QUEUE_WRITES
from test_runtime_rom_checksum_execution import before_pump_scaling

HISTORY_WRITES={(RAM+a,4) for a in (*range(0xB038,0xB058,4),
    *range(0xB05C,0xB074,4),0xB074)} | {(RAM+a,1) for a in (
    0xB058,*range(0xB078,0xB080))}
STATUS_WRITES={(RAM+a,1) for a in (0xB080,0xB088,0xB089,0xB08A)}


class CrankObservationMachine(PurgeMonitorMachine):
    LOOKUPS=PurgeMonitorMachine.LOOKUPS | {0xD01C,0xC700,0x6170,0x6A6AC}

    def __init__(self,image,rpm=3000):
        super().__init__(image)
        for a,n in HISTORY_WRITES | STATUS_WRITES:
            self.write(a,0,n)
        for i,a in enumerate(range(0xB038,0xB058,4)):
            self.put_float(RAM+a,100+i)
        self.execute(0xD8EE,HISTORY_WRITES)
        self.put_float(RAM+0xB544,rpm)
        self.write(RAM+0xAC16,1,1)
        for a in range(0x94A0,0x96F8,4):
            self.write(RAM+a,0xA55A5AA5,4)
        for a,v in ((0x930A,1),(0x930B,0),(0x930C,1)):
            self.write(RAM+a,v,1)
        # Queue2 already active; its first record/delivery time is explicit.
        for a in range(self.STACK-128,self.STACK,4):
            self.write(a,0x5AA55AA5,4)
        self.protected={a:0xA55A0000+i for i,a in enumerate(
            (*self.wideband_outputs,self.lean_counter_ram,self.lean_state_ram))}
        for a,v in self.protected.items():
            self.write(a,v,4)

    def edge(self,channel,finish=False,timestamp=1000):
        absolute=12*channel+(9 if finish else 0)
        self.write(RAM+0xAC15,absolute%36,1)
        self.write(RAM+0xAC17,4*channel+(3 if finish else 0),1)
        self.write(RAM+0xF434,timestamp&0xFFFFFFFF,4)
        self.execute(0xDB50,STATUS_WRITES)
        head=self.read(RAM+0x930A,1)
        self.execute(0xD92C,HISTORY_WRITES | QUEUE_WRITES)
        for a,v in self.protected.items():
            assert self.read(a,4)==v,hex(a)
        return RAM+0x94A0+20*head

    def deliver(self,record):
        self.original_r[4]=record+4
        self.execute(self.read(record,4),SNAPSHOT_WRITES)


class CrankObservationProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock=(ROOT/'2005 BLE MT.bin').read_bytes()
        main=(ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2=(ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images={'main':main,'v2':v2,'captured':before_pump_scaling(v2)}
        for image in cls.images.values():
            for a,b in ((0xD8EE,0xDBF0),(0xD01C,0xD034),(0xFCD0,0xFCD8),
                         (0x11ED2,0x11ED8),(0x11F88,0x11F8C),
                         (0x6A6AC,0x6A6F6)):
                assert image[a:b]==stock[a:b],hex(a)

    def test_all_six_timestamp_pairs_publish_bounded_history_and_actual_queue_callback(self):
        for image,channel,start in product(self.images.values(),range(6),(1000,0xFFFFF000)):
            cpu=CrankObservationMachine(image)
            cpu.edge(channel,timestamp=start)
            self.assertEqual(cpu.read(RAM+0xB05C+4*channel,4),start)
            self.assertEqual(cpu.read(RAM+0xB078+channel,1),1)
            self.assertEqual(cpu.read(RAM+0x930C,1),1)
            record=cpu.edge(channel,True,start+20000)
            self.assertEqual(cpu.read(RAM+0xB074,4),20000)
            self.assertAlmostEqual(cpu.get_float(RAM+0xB038),3000,delta=.001)
            self.assertEqual(cpu.array(RAM+0xB03C,7),list(range(100,107)))
            self.assertEqual(cpu.read(RAM+0xB058,1),channel)
            self.assertEqual(cpu.read(record,4),0x11ED2)
            self.assertEqual(cpu.read(RAM+0x930C,1),2)
            cpu.deliver(record)
            self.assertEqual(cpu.read(RAM+0xD9AC,1),channel)
            self.assertEqual(cpu.get_float(RAM+0xD96C),3000)
            self.assertNotIn(0x6E338,cpu.entered)

    def test_unsynchronized_or_missing_initial_sample_does_not_publish_observation(self):
        for image,sync in product(self.images.values(),(0,1)):
            cpu=CrankObservationMachine(image)
            cpu.write(RAM+0xAC16,sync,1)
            for channel in range(6):
                cpu.edge(channel,True)
            self.assertEqual(cpu.read(RAM+0x930C,1),1)
            self.assertEqual(cpu.read(RAM+0xB058,1),0)

    def test_delayed_zero_payload_callback_observes_latest_global_channel_and_history(self):
        for image in self.images.values():
            cpu=CrankObservationMachine(image)
            records=[]
            for channel in range(3):
                cpu.edge(channel,timestamp=1000+channel*40000)
                records.append(cpu.edge(channel,True,21000+channel*40000))
            self.assertEqual(cpu.read(0xFCD2,2),0)  # Descriptor payload length.
            cpu.deliver(records[0])
            self.assertEqual(cpu.read(RAM+0xD9AC,1),2)
            self.assertEqual(cpu.read(RAM+0xD9B0,4),cpu.read(RAM+0xB038,4))
            # Native descriptor carries no per-edge history snapshot. This
            # conditional lag effect does not establish actual task backlog.

    def test_full_shared_queue_drops_callback_but_updates_global_history_without_alias(self):
        for image in self.images.values():
            cpu=CrankObservationMachine(image)
            cpu.write(RAM+0x930A,0,1)
            cpu.write(RAM+0x930C,30,1)
            before=cpu.read(RAM+0x94A0,20)
            cpu.edge(5,timestamp=1000)
            cpu.edge(5,True,21000)
            self.assertEqual(cpu.read(RAM+0x930C,1),30)
            self.assertEqual(cpu.read(RAM+0x94A0,20),before)
            self.assertEqual(cpu.read(RAM+0xB058,1),5)
            self.assertAlmostEqual(cpu.get_float(RAM+0xB038),3000,delta=.001)

    def test_native_edge_status_counter_checks_thirty_edge_window_and_saturates(self):
        for image in self.images.values():
            cpu=CrankObservationMachine(image)
            cpu.write(RAM+0xB088,1,1)
            for count,expected in ((28,2),(29,1),(30,2)):
                cpu.write(RAM+0xB089,count,1)
                cpu.write(RAM+0xAC15,0,1)
                cpu.execute(0xDB50,STATUS_WRITES)
                self.assertEqual(cpu.read(RAM+0xB080,1),expected)
                self.assertEqual(cpu.read(RAM+0xB089,1),0)
            cpu.write(RAM+0xAC15,1,1)
            cpu.write(RAM+0xB089,254,1)
            for _ in range(3):
                cpu.execute(0xDB50,STATUS_WRITES)
            self.assertEqual(cpu.read(RAM+0xB089,1),255)
            self.assertEqual(cpu.read(RAM+0xB08A,1),1)


if __name__=='__main__':
    unittest.main(verbosity=2)
