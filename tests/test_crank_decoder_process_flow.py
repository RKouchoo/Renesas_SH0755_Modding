#!/usr/bin/env python3
"""Execute primary/secondary capture decoding through accepted phase events.

Capture timestamps and a 36-position pattern with six missing positions are
explicit waveform fixtures, not measurements from the vehicle. Full native
8218/8248, decoder, period publication and sync-message enqueue execute.
CF58/CF7E acceptance is a recorded boundary already exercised with the native
kernel in test_phase_activation_process_flow. The hardware IRQ frame and
post-decoder DB50/D92C callbacks are covered separately.
"""
import _test_paths
from itertools import product
import unittest

from test_sync_transition_process_flow import (SyncEventMachine,QUEUE_WRITES,
    SOURCE_WRITES,SIGNAL_WRITES,SIGNAL_IO_WRITES,RAM,ROOT)
from test_runtime_rom_checksum_execution import before_pump_scaling

DECODER_WRITES=SIGNAL_WRITES | SIGNAL_IO_WRITES | SOURCE_WRITES | QUEUE_WRITES | {
    (RAM+a,4) for a in (0xAC18,0xAC1C,0xAC24,0xAC28,0xAC30,0xAC34,
                        *range(0xAC50,0xAC60,4))} | {
    (RAM+a,1) for a in (0xAC17,0xAC3F,0xAC61)}


class CrankDecoderMachine(SyncEventMachine):
    LOOKUPS=SyncEventMachine.LOOKUPS | {0x8428,0x84B2,0x86BE,0x8692,
        0x8910,0x89E0,0x87F2,0x8BE6,0x8298,0x82B6,0x8782,0x87B0,
        0x8A44,0x8A9E,0xD034,0x8104,0x8286}

    def __init__(self,image,mode=0):
        super().__init__(image)
        self.phases=[]
        self.mapped=[]
        self.decoder_reads=[]
        for a in (0xAC18,0xAC1C,0xAC24,0xAC28,0xAC30,0xAC34,
                  *range(0xAC50,0xAC60,4)):
            self.write(RAM+a,0,4)
        for a in (0xAC17,0xAC3F,0xAC61):
            self.write(RAM+a,0,1)
        self.execute(0x813C,DECODER_WRITES)
        self.write(RAM+0xAC20,mode,1)
        self.ticks=0

    def load(self,address,size):
        value=super().load(address,size)
        if 0xFA2C<=address<0xFA7C:
            self.decoder_reads.append((address,size))
        return value

    def call_lookup(self,target):
        if target in (0xCF58,0xCF7E):
            # Phase/task activation and delivery are separately native-tested.
            (self.phases if target==0xCF58 else self.mapped).append(self.r[4])
            self.poison_scratch()
        else:
            super().call_lookup(target)

    def step(self,in_delay=False):
        if self.pc in (0xCF58,0xCF7E):
            # 82B6 tail-jumps to CF7E rather than issuing a JSR.
            assert not in_delay
            self.call_lookup(self.pc)
            self.pc=self.pr
        else:
            super().step(in_delay)

    def primary(self,interval):
        self.ticks=(self.ticks+interval)&0xFFFFFFFF
        self.write(RAM+0xF434,self.ticks,4)
        self.write(RAM+0xF6D0,interval,4)
        self.execute(0x8218,DECODER_WRITES)

    def secondary(self):
        self.execute(0x8248,DECODER_WRITES)

    def waveform(self,revolutions=6,step=2000):
        teeth=[n for n in range(36) if n not in (7,8,10,11,31,32)]
        last=-1
        per_rev=[]
        for rev in range(revolutions):
            first=len(self.phases)
            for position in teeth:
                absolute=rev*36+position
                # Actual bank0 cam selectors are0/8/16 per720; a supplied
                # secondary capture precedes the coincident primary edge.
                if absolute%72 in (0,24,48):
                    self.secondary()
                self.primary((absolute-last)*step)
                last=absolute
            per_rev.append(self.phases[first:])
        return per_rev


class CrankDecoderProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock=(ROOT/'2005 BLE MT.bin').read_bytes()
        main=(ROOT/'master_patch/D2WD610H_master_patch.bin').read_bytes()
        v2=(ROOT/'master_patch_v2/D2WD610H_master_patch_v2.bin').read_bytes()
        cls.images={'main':main,'v2':v2,'captured':before_pump_scaling(v2)}
        for image in cls.images.values():
            for a,b in ((0x8218,0x8D06),(0xFA2C,0xFA94),(0x7281C,0x72834),
                         (0x7B248,0x7B260),(0x7B2AC,0x7B2B4),(0xFCD8,0xFCE0),
                         (0x19EF0,0x19F9C),(0x1A0BA,0x1A0EE),
                         (0x1A1C0,0x1A1D8),(0x8104,0x813C)):
                assert image[a:b]==stock[a:b],hex(a)

    def test_native_waveform_acquires_and_maintains_twenty_four_phases_in_both_modes(self):
        for image,mode,step in product(self.images.values(),(0,1),(1800,2000,2600)):
            cpu=CrankDecoderMachine(image,mode)
            revs=cpu.waveform(step=step)
            self.assertEqual(cpu.read(RAM+0xAC16,1),1)
            self.assertEqual(cpu.read(RAM+0xAC3C,1),1)
            self.assertEqual(sorted(revs[-2]+revs[-1]),list(range(24)),revs)
            self.assertEqual(cpu.read(RAM+0xAC0C,1),0)
            self.assertAlmostEqual(cpu.get_float(RAM+0xAC00),
                                   4_000_000*5/(3*step),delta=.001)
            self.assertTrue(all(0<=phase<24 for phase in cpu.phases))
            self.assertTrue(all(0<=phase<6 for phase in cpu.mapped))

    def test_decoder_rejects_invalid_position_before_indexing_transition_table_and_posts_sync_loss(self):
        for image,state in product(self.images.values(),(37,128,255)):
            cpu=CrankDecoderMachine(image)
            cpu.write(RAM+0xAC15,state,1)
            cpu.write(RAM+0xAC3C,1,1)
            cpu.write(RAM+0xAC16,1,1)
            head=cpu.read(RAM+0x9304,1)
            cpu.primary(2000)
            self.assertEqual(cpu.read(RAM+0xAC15,1),36)
            self.assertEqual(cpu.read(RAM+0xAC16,1),0)
            self.assertEqual(cpu.read(RAM+0x9310+20*head,4),0x69DE)
            self.assertEqual(cpu.read(RAM+0x9314+20*head,4),0)
            self.assertTrue(all(a<0xFA76 for a,n in cpu.decoder_reads))

    def test_gap_search_resets_after_five_plain_edges_and_bounds_its_adjustment_lookup(self):
        for image,gap_at in product(self.images.values(),range(1,6)):
            cpu=CrankDecoderMachine(image)
            cpu.write(RAM+0xAC15,4,1)
            cpu.write(RAM+0xAC3D,2,1)
            cpu.write(RAM+0xAC3E,0,1)
            cpu.write(RAM+0xAC2C,2000,4)
            for n in range(1,gap_at+1):
                cpu.primary(6000 if n==gap_at else 2000)
            adjustments=[a for a,n in cpu.decoder_reads if 0xFA76<=a<0xFA7C]
            self.assertEqual(adjustments,[0xFA76+gap_at])
            cpu=CrankDecoderMachine(image)
            cpu.write(RAM+0xAC15,4,1)
            cpu.write(RAM+0xAC3D,2,1)
            cpu.write(RAM+0xAC3E,0,1)
            cpu.write(RAM+0xAC2C,2000,4)
            for _ in range(5):cpu.primary(2000)
            self.assertEqual(cpu.read(RAM+0xAC15,1),36)
            self.assertEqual(cpu.read(RAM+0xAC3D,1),0)
            self.assertFalse(any(a>=0xFA76 for a,n in cpu.decoder_reads))

    def test_capture_inhibit_skips_decoder_while_secondary_latch_and_timeout_recovery_are_separate(self):
        for image in self.images.values():
            cpu=CrankDecoderMachine(image)
            cpu.write(RAM+0xAC22,1,1)
            before=cpu.read(RAM+0xAC15,1)
            cpu.secondary();cpu.primary(2000)
            self.assertEqual(cpu.read(RAM+0xAC15,1),before)
            self.assertEqual(cpu.read(RAM+0xAC44,1),0)
            self.assertEqual(cpu.phases,[])
            cpu.write(RAM+0xAC22,0,1)
            cpu.secondary()
            self.assertEqual(cpu.read(RAM+0xAC44,1),1)
            self.assertEqual(cpu.read(RAM+0xAC45,1),5)
            cpu.primary(2000)
            self.assertEqual(cpu.read(RAM+0xAC0C,1),0)
            self.assertEqual(cpu.read(RAM+0xAC45,1),4)

    def test_capture_inhibit_parent_uses_two_high_bits_and_resets_only_on_rising_request(self):
        for image,first,second in product(self.images.values(),(0x7F,0xFF),(0x7F,0xFF)):
            cpu=CrankDecoderMachine(image)
            cpu.write(RAM+0xAC16,1,1)
            cpu.write(RAM+0xAC3C,1,1)
            cpu.write(RAM+0xB525,first,1)
            cpu.write(RAM+0xB542,second,1)
            wanted=int(bool((first|second)&0x80))
            before=cpu.read(RAM+0x9306,1)
            allowed=DECODER_WRITES | {(RAM+0xB52B,1)}
            cpu.execute(0x1A0BA,allowed)
            self.assertEqual(cpu.read(RAM+0xB52B,1),wanted)
            self.assertEqual(cpu.read(RAM+0xAC22,1),wanted)
            self.assertEqual(cpu.read(RAM+0xAC16,1),1-wanted)
            self.assertEqual(cpu.read(RAM+0x9306,1),before+wanted)
            cpu.execute(0x1A0BA,allowed)
            self.assertEqual(cpu.read(RAM+0x9306,1),before+wanted)
            cpu.write(RAM+0xB525,0x7F,1)
            cpu.write(RAM+0xB542,0x7F,1)
            cpu.execute(0x1A0BA,allowed)
            self.assertEqual(cpu.read(RAM+0xAC22,1),0)

    def test_low_rpm_capture_inhibit_producer_clears_at_one_thousand_and_logged_speeds(self):
        for image,rpm,digital in product(self.images.values(),(1000,2500,2800,3000,3500,4144),(0,8)):
            cpu=CrankDecoderMachine(image)
            cpu.put_float(RAM+0xB544,rpm)
            cpu.write(RAM+0xB51E,digital,1)
            cpu.write(RAM+0xB524,255,1)
            cpu.write(RAM+0xB525,255,1)
            cpu.write(RAM+0xB527,0,1)
            cpu.execute(0x19EF0,{(RAM+a,1) for a in (0xB524,0xB525,0xB527)})
            self.assertEqual(cpu.read(RAM+0xB525,1),0x7F)
            self.assertEqual(cpu.read(RAM+0xB524,1),255)


if __name__=='__main__':
    unittest.main(verbosity=2)
