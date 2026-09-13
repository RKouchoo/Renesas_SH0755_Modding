#!/usr/bin/env python3
"""Execute native ADC scan -> retained A/F measurement -> WB publication.

ADC completion and external triggers are explicit hardware events. Result
registers use the documented left-aligned 10-bit format. This models channel
selection and completed-scan handoff, not conversion time, IRQ latency or
analog sensor behavior. No image or ECU writes occur.
"""
import _test_paths
import unittest

from test_iat_process_flow import IATProcessMachine
from test_runtime_rom_checksum_execution import before_pump_scaling
from test_wideband_fuel_guard_execution import WIDEBAND_OUTPUTS

ROOT, RAM = _test_paths.ROOT, 0xFFFF0000
CONTROLS = (0xF818, 0xF838, 0xF858)
CONTROL_WRITES = {(RAM+a, 1) for a in
                  (*CONTROLS, 0xF819, 0xF839, 0xF859, 0xF76E, 0xF72E)}
SCAN_WRITES = CONTROL_WRITES | {(RAM+a, 2) for a in range(0xAB00, 0xAB40, 2)} | {
    (RAM+a, 1) for a in (*range(0xAAFC, 0xAAFF), *range(0xAB40, 0xAB4E))}
AFE_WRITES = CONTROL_WRITES | {(RAM+a, 2) for a in (
    0xAE84, 0xAE86, 0xAE88, 0xAE8A, 0xAEC0, 0xAEC2, 0xAEC4, 0xAEC6,
    0xF64C, 0xF64E, 0xF65E, 0xF450, 0xF452, 0xF622)} | {
    (RAM+a, 1) for a in (0xAECC, 0xAECD, 0xAECE, 0xAECF, 0xAEC8,
                        0xAEC9, 0xAED0, 0xAB43)}
WB_WRITES = {(a, 4) for a in WIDEBAND_OUTPUTS} | {(RAM+0xAED0, 1)}


class ADCHandoffMachine(IATProcessMachine):
    LOOKUPS = IATProcessMachine.LOOKUPS | {
        0x6FF2, 0x70A8, 0x7138, 0x71D8, 0x723E, 0x7320, 0x6FBE, 0x6FBA,
        0xBAE0, 0x7372, 0xBBF0, 0xBCB4, 0xD744, 0x2088, 0x2098, 0xB690,
    }

    def __init__(self, image):
        self.auto_complete = False
        self.analog = [(i+1)*1024 for i in range(32)]
        self.analog[3] = 16384
        super().__init__(image)
        for a in range(0xAAFC, 0xAB4E):
            self.write(RAM+a, 0, 1)
        for a in range(0xAE84, 0xAED1):
            self.write(RAM+a, 0, 1)
        for a in (0xAE78, 0xAE7C):
            self.put_float(RAM+a, 16384)
        for a in CONTROLS:
            self.write(RAM+a, 0, 1)
            self.write(RAM+a+1, 15, 1)
        for a in (0xF76E, 0xF72E):
            self.write(RAM+a, 255, 1)
        for a in (0xF64C, 0xF64E, 0xF65E, 0xF450, 0xF452, 0xF622):
            self.write(RAM+a, 0, 2)
        self.write(RAM+0xF440, 1000, 2)
        # Native startup polls completion; use immediate completion only for
        # this explicit initialization boundary, then require supplied events.
        self.auto_complete = True
        self.execute(0x6CE4, SCAN_WRITES)
        self.auto_complete = False

    def write(self, address, value, size=4, record=False):
        if record and address-RAM in CONTROLS:
            assert size == 1
            # Reconfiguration must stop conversion first. ADF cannot be set
            # by CPU writes, and is cleared by the native read/zero sequence.
            assert not self.read(address+1, 1) & 32, hex(self.pc)
            value = (value & 127) | (value & self.read(address, 1) & 128)
        if record and address-1-RAM in CONTROLS:
            assert size == 1 and value & 15 == 15
        super().write(address, value, size, record)
        if (record and self.auto_complete and address-1-RAM in CONTROLS
                and value & 32):
            self.complete(CONTROLS.index(address-1-RAM))

    def complete(self, module, external=False):
        """Supply one completed hardware conversion; no elapsed-time claim."""
        control = RAM+CONTROLS[module]
        mode, cr = self.read(control, 1), self.read(control+1, 1)
        if external:
            assert cr & 128 and not cr & 32
        else:
            assert cr & 32
        selection, scan = mode & (7 if module == 2 else 15), (mode >> 4) & 3
        base = (0, 12, 24)[module]
        if scan == 0:
            selected = [selection]
        else:
            groups = [selection & ~3] if scan == 1 else list(range(0, scan*4, 4))
            selected = [g+i for g in groups for i in range((selection & 3)+1)]
        for channel in selected:
            value = self.analog[base+channel]
            assert 0 <= value <= 65472 and value & 63 == 0
            self.write(RAM+0xF800+module*32+channel*2, value, 2)
        self.write(control, mode | 128, 1)
        self.write(control+1, cr & ~32, 1)

    def step(self, in_delay=False):
        pc, op = self.pc, self.read(self.pc, 2)
        n, m = (op >> 8) & 15, (op >> 4) & 15
        if op & 0xF00F == 0x0005:  # MOV.W Rm,@(R0,Rn).
            self.write((self.r[n]+self.r[0]) & 0xFFFFFFFF, self.r[m], 2, record=True)
        elif op & 0xF000 == 0x1000:  # MOV.L Rm,@(disp,Rn).
            self.write(self.r[n]+(op & 15)*4, self.r[m], 4, record=True)
        elif op & 0xF00F == 0x6002:  # MOV.L @Rm,Rn.
            self.r[n] = self.load(self.r[m], 4)
        else:
            return super().step(in_delay)
        self.trace.append((pc, op))
        self.pc += 2
        self.instructions += 1

    def collect_and_start(self):
        self.execute(0x6EAC, SCAN_WRITES)

    def finish_normal_scans(self):
        for module in range(3):
            if self.read(RAM+CONTROLS[module]+1, 1) & 32:
                self.complete(module)
        if self.read(RAM+0xF838, 1) & 64:
            self.execute(0x5F64, AFE_WRITES)

    def finish_front_measurement(self):
        self.complete(0, external=True)
        self.complete(1, external=True)
        self.execute(0x5F64, AFE_WRITES)


class ADCHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = (ROOT/'2005 BLE MT.bin').read_bytes()
        cls.images = [(ROOT/p).read_bytes() for p in (
            'master_patch/D2WD610H_master_patch.bin',
            'master_patch_v2/D2WD610H_master_patch_v2.bin')]
        cls.images.append(before_pump_scaling(cls.images[1]))
        for image in cls.images:
            for a, b in ((0x6CE4, 0x740C), (0xBAE0, 0xBD08),
                         (0x740C, 0x74BA), (0x7536, 0x7550),
                         (0xD744, 0xD77C), (0x5F64, 0x5F70),
                         (0x6006, 0x6008), (0x602C, 0x6030),
                         (0x727B0, 0x727B8), (0x727CE, 0x727D6)):
                assert image[a:b] == stock[a:b], hex(a)

    def test_startup_maps_all_32_hardware_channels_to_distinct_ram_words(self):
        for image in self.images:
            cpu = ADCHandoffMachine(image)
            self.assertEqual([cpu.read(RAM+0xAB00+2*i, 2) for i in range(32)], cpu.analog)
            self.assertEqual(cpu.read(RAM+0xAB06, 2), cpu.analog[3])
            self.assertEqual(cpu.read(RAM+0xAB04, 2), cpu.analog[2])
            self.assertEqual(cpu.read(RAM+0xAB1A, 2), cpu.analog[13])
            self.assertEqual(cpu.read(RAM+0xAB3A, 2), cpu.analog[29])

    def test_scan_widths_copy_only_the_selected_module_zero_prefix(self):
        for image in self.images:
            for count in (0, 1, 4, 8, 12):
                cpu = ADCHandoffMachine(image)
                for i in range(12):
                    cpu.write(RAM+0xAB00+2*i, 0xAAAA, 2)
                cpu.write(RAM+0xAB47, count, 1)
                cpu.execute(0x6FF2, SCAN_WRITES)
                self.assertEqual([cpu.read(RAM+0xAB00+2*i, 2) for i in range(12)],
                                 cpu.analog[:count]+[0xAAAA]*(12-count))

    def test_repeated_scan_handoff_preserves_wb_channel_and_resumes_after_both_banks(self):
        for image in self.images:
            cpu = ADCHandoffMachine(image)
            banks = []
            previous = cpu.analog[3]
            for cycle in range(1, 130):
                cpu.collect_and_start()
                self.assertEqual(cpu.read(RAM+0xAB06, 2), previous)
                cpu.execute(0xB62A, {(a, 4) for a in cpu.wideband_outputs} | {(RAM+0xAED0, 1)})
                expected = (10+2*previous*5/65536)/14.64
                # Constants are independently checked by the WB guard suite.
                self.assertAlmostEqual(cpu.get_float(RAM+0xAE60), expected, delta=.000002)
                cpu.analog[3] = 16384+cycle*64
                previous = cpu.analog[3]
                cpu.finish_normal_scans()
                if cpu.read(RAM+0xAB43, 1):
                    bank = cpu.read(RAM+0xAECE, 1)
                    banks.append(bank)
                    self.assertEqual(cpu.read(RAM+0xF818, 1) & 127, 11-bank)
                    self.assertEqual(cpu.read(RAM+0xF838, 1) & 127, 0x4B-bank)
                    saved = cpu.read(RAM+0xAB06, 2)
                    cpu.analog[10+1-bank] ^= 0x4000
                    cpu.analog[22+1-bank] ^= 0x4000
                    cpu.finish_front_measurement()
                    self.assertEqual(cpu.read(RAM+0xAB06, 2), saved)
                    self.assertEqual(cpu.read(RAM+0xAB43, 1), 0)
                    self.assertEqual(cpu.read(RAM+0xAED0, 1), 0)
                    self.assertEqual(cpu.read(RAM+0xAEC4+2*bank, 2), cpu.analog[11-bank])
                    self.assertEqual(cpu.read(RAM+0xAEC0+2*bank, 2), cpu.analog[23-bank])
            self.assertEqual(banks, [1, 0])

    def test_missing_front_completion_is_abandoned_by_next_normal_scan(self):
        for image in self.images:
            cpu = ADCHandoffMachine(image)
            cpu.write(RAM+0xAB40, 63, 1)
            cpu.write(RAM+0xAB42, 3, 1)
            cpu.collect_and_start()
            cpu.finish_normal_scans()
            self.assertEqual(cpu.read(RAM+0xAB43, 1), 1)
            # No external trigger/second ADI1. The next normal task explicitly
            # cancels pending special ownership and starts normal conversion.
            cpu.collect_and_start()
            self.assertEqual(cpu.read(RAM+0xAB43, 1), 0)
            self.assertEqual(cpu.read(RAM+0xF818, 1) & 127, 0x13)
            self.assertEqual(cpu.read(RAM+0xF838, 1) & 127, 0x10)
            cpu.analog[3] = 40000
            cpu.finish_normal_scans()
            cpu.collect_and_start()
            self.assertEqual(cpu.read(RAM+0xAB06, 2), 40000)

    def test_retained_impedance_changes_only_the_assigned_excitation_timer_channels(self):
        for image in self.images:
            for impedance, flag, expected in (
                    (16384, 1, (44, 25, 1029, 1004)),
                    (1000, 0, (25, 14, 1004, 1029)),
                    (1100, 0, (44, 25, 1029, 1004)),
                    (1100, 1, (25, 14, 1004, 1029))):
                cpu = ADCHandoffMachine(image)
                for channel in range(6):
                    cpu.write(RAM+0xF640+2*channel, 100+channel, 2)
                    cpu.write(RAM+0xF444+2*channel, 200+channel, 2)
                cpu.write(RAM+0xF666, 0xA55A, 2)
                cpu.write(RAM+0xAECF, 1, 1)  # Next native selection is bank0.
                cpu.write(RAM+0xAECC, flag, 1)
                cpu.put_float(RAM+0xAE78, impedance)
                cpu.execute(0xBAE0, AFE_WRITES)
                self.assertEqual(tuple(cpu.read(RAM+a, 2) for a in
                                       (0xF64C, 0xF64E, 0xF450, 0xF452)), expected)
                self.assertEqual(cpu.read(RAM+0xF65E, 2), 1)
                self.assertEqual(cpu.read(RAM+0xF622, 2), 1024)
                self.assertEqual(cpu.read(RAM+0xF440, 2), 1000)
                self.assertEqual(cpu.read(RAM+0xF666, 2), 0xA55A)
                self.assertEqual([cpu.read(RAM+0xF640+2*i, 2) for i in range(6)],
                                 list(range(100, 106)))
                self.assertEqual([cpu.read(RAM+0xF444+2*i, 2) for i in range(6)],
                                 list(range(200, 206)))

    def test_one_off_module_two_sample_restores_scan_mode_and_leaves_wb_results_alone(self):
        for image in self.images:
            for pending, completed in ((False, False), (False, True), (True, False)):
                cpu = ADCHandoffMachine(image)
                cpu.write(RAM+0xF858, 0x2B | (128 if completed else 0), 1)
                cpu.write(RAM+0xF859, 15 | (32 if pending else 0), 1)
                saved_wb = cpu.read(RAM+0xAB06, 2)
                saved_hardware = cpu.read(RAM+0xF806, 2)
                cpu.auto_complete = True
                cpu.execute(0x740C, CONTROL_WRITES)
                cpu.auto_complete = False
                self.assertEqual(cpu.r[0] & 65535, cpu.analog[24])
                self.assertEqual(cpu.read(RAM+0xF858, 1) & 127, 0x2B)
                # A previously running scan is restarted and completed by the
                # explicit immediate-completion fixture. A prior idle scan
                # keeps its original completion status.
                self.assertEqual(bool(cpu.read(RAM+0xF858, 1) & 128), pending or completed)
                self.assertEqual(cpu.read(RAM+0xAB06, 2), saved_wb)
                self.assertEqual(cpu.read(RAM+0xF806, 2), saved_hardware)


if __name__ == '__main__':
    unittest.main(verbosity=2)
