#!/usr/bin/env python3
"""
Phase 2 (closed-loop, WRX-style) boost-control patch for Subaru EZ30R D2WD610H.

Extends Phase 1: instead of a plain RPM->duty map, the injected stub runs a PI boost
controller on the repurposed purge PWM output (ATU-II 0xFFFFF590):

    base   = BaseDuty[rpm]            (feed-forward, ratio)
    target = TargetBoost[rpm]         (MAP units)
    error  = target - MAP(0xFFFFABC4)
    I      = clamp(I + error*Ki, -Ilim, +Ilim)     (integrator in free RAM 0xFFFFBFF0)
    ratio  = clamp(base + error*Kp + I, 0, MaxRatio)
    if MAP > Overboost: ratio = 0, I = 0           (anti-windup fail-safe)
    -> output ratio via the stock output stage (0xE8C4)

Hijack: repoint the pooled tail-call pointer @0x3FD8C (in evap_purge_duty_compute) to the
stub. Same mechanism as Phase 1, verified against Ghidra.

*** HARDWARE PREREQUISITE ***  MAP feedback (0xFFFFABC4) MUST read real boost: fit the EJ255
(turbo) MAP sensor and rescale table 0x72810 FIRST. Do NOT run closed loop on the stock ~1-bar
sensor. Default gains ship at 0 (behaves as feed-forward = Phase 1) so a first flash is safe;
raise Kp/Ki during commissioning. Keep an independent overboost FUEL cut as the real fail-safe.

Usage:  python3 patch_boost_p2.py [stock.bin] [out.bin]
"""
import struct, sys, os
from sh2_asm import Asm

HERE  = os.path.dirname(os.path.abspath(__file__))
STOCK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "2005 BLE MT.bin")
OUT   = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "D2WD610H_boost_p2.bin")

# --- fixed ROM anchors (verified against Ghidra) ---
HIJACK_LITERAL = 0x3FD8C
STOCK_OUTPUT   = 0x0000E8C4     # evap_purge_pwm_output_write (fr4 = ratio)
INTERP_2D      = 0x0000209C     # table2d_lookup_dispatch(r4=desc, fr4=in) -> fr0
RPM_ADDR       = 0xFFFFB544     # engine RPM (float)
MAP_ADDR       = 0xFFFFABC4     # manifold pressure (float, engineering units)
INTEG_ADDR     = 0xFFFFBFF0     # PI integrator state (free RAM, float)
FLAG_ADDR      = 0xFFFFBFF8     # init-flag (free RAM, u32)
INIT_MAGIC     = 0xB005D0FF

# --- free-space layout (all 0xFF-verified; < 0x7FAF7) ---
BASE_DESC   = 0x7D790   # 1-axis desc: RPM -> base duty ratio (u8 % * 0.01)
RPM_AXIS    = 0x7D7A4   # float32[8]  (shared by base + target)
BASE_DATA   = 0x7D7C4   # u8[8]  duty %
TARGET_DESC = 0x7D7CC   # 1-axis desc: RPM -> target (float32, type 0)
TARGET_DATA = 0x7D7E0   # float32[8]  target MAP units
KP_ADDR     = 0x7D800   # float32
KI_ADDR     = 0x7D804   # float32
ILIM_ADDR   = 0x7D808   # float32
MAXR_ADDR   = 0x7D80C   # float32
OVERB_ADDR  = 0x7D810   # float32
STUB_ADDR   = 0x7D814   # PI controller (4-aligned)
FREE_START, FREE_END = 0x7D790, 0x7FAF7

# ---------------- tunables (edit here or in RomRaider) ----------------
RPM_BREAKS  = [1500.0, 2000.0, 2500.0, 3000.0, 3500.0, 4000.0, 5000.0, 6000.0]
BASE_DUTY   = [   0,     0,     12,     22,     28,     30,     28,     22 ]   # wastegate duty %
TARGET_MAP  = [ 100.0, 105.0, 140.0, 165.0, 175.0, 175.0, 170.0, 160.0 ]      # MAP units (match sensor!)
KP          = 0.0      # ratio per MAP-unit  (0 = feed-forward only; raise to commission)
KI          = 0.0      # ratio per MAP-unit per cycle (raise AFTER Kp, watch for windup)
ILIM        = 0.25     # |integrator| clamp (ratio)
MAXRATIO    = 0.85     # max commanded duty ratio
OVERBOOST   = 250.0    # MAP units -> ratio forced to 0 (calibrate to your sensor!)
DUTY_SCALE  = 0.01     # base-map u8 % -> ratio

assert len(RPM_BREAKS) == len(BASE_DUTY) == len(TARGET_MAP) == 8

# ---------------- builders ----------------
def be32(v): return struct.pack(">I", v & 0xFFFFFFFF)
def be16(v): return struct.pack(">H", v & 0xFFFF)
def f32(x):  return struct.pack(">f", x)

def desc_1axis(type_byte, axis_addr, data_addr, scale, offset):
    d = be16(8) + bytes([type_byte, 0]) + be32(axis_addr) + be32(data_addr) + f32(scale) + f32(offset)
    assert len(d) == 0x14
    return d

def build_stub():
    a = Asm(STUB_ADDR)
    # --- init integrator on first run (RAM may be garbage at boot) ---
    a.stsl_pr()                                   # [stack: PR(grandparent)]
    a.movl_pool(1, FLAG_ADDR); a.movl_at(0, 1)    # r0 = *flag
    a.movl_pool(2, INIT_MAGIC); a.cmp_eq(2, 0)    # T = (*flag == MAGIC)
    a.bt('inited')
    a.movl_pool(3, INTEG_ADDR); a.fldi0(1); a.fmov_store(1, 3)  # *integ = 0
    a.movl_store(2, 1)                            # *flag = MAGIC
    a.label('inited')
    # --- base duty (ratio) ---
    a.movl_pool(1, RPM_ADDR); a.fmov_load(4, 1)
    a.movl_pool(4, BASE_DESC); a.movl_pool(2, INTERP_2D); a.jsr(2); a.nop()  # fr0 = base
    a.fpush(0)                                    # [stack: PR, base]
    # --- target ---
    a.movl_pool(1, RPM_ADDR); a.fmov_load(4, 1)
    a.movl_pool(4, TARGET_DESC); a.movl_pool(2, INTERP_2D); a.jsr(2); a.nop()  # fr0 = target
    # no more calls -> fr0..fr7 free
    a.movl_pool(1, MAP_ADDR); a.fmov_load(2, 1)   # fr2 = MAP
    # --- overboost fail-safe ---
    a.movl_pool(1, OVERB_ADDR); a.fmov_load(3, 1) # fr3 = limit
    a.fcmpgt(3, 2)                                # T = MAP > limit
    a.bf('no_ob')
    a.fldi0(4)                                    # ratio = 0
    a.movl_pool(3, INTEG_ADDR); a.fmov_store(4, 3)# integ = 0 (anti-windup)
    a.fpop(0)                                     # discard base -> [stack: PR]
    a.bra('out'); a.nop()
    a.label('no_ob')
    a.fsub(2, 0)                                  # fr0 = target - MAP = error
    # --- integrator: I = clamp(I + error*Ki, -Ilim, +Ilim) ---
    a.movl_pool(3, INTEG_ADDR); a.fmov_load(1, 3) # fr1 = I
    a.movl_pool(1, KI_ADDR); a.fmov_load(5, 1)    # fr5 = Ki
    a.fmov(0, 6)                                  # fr6 = error (for P)
    a.fmul(5, 0); a.fadd(0, 1)                    # fr1 = I + error*Ki
    a.movl_pool(1, ILIM_ADDR); a.fmov_load(7, 1)  # fr7 = +Ilim
    a.fcmpgt(7, 1); a.bf('ilo'); a.fmov(7, 1)     # if I>+Ilim: I=+Ilim
    a.label('ilo')
    a.fneg(7)                                     # fr7 = -Ilim
    a.fcmpgt(1, 7); a.bf('idone'); a.fmov(7, 1)   # if I<-Ilim: I=-Ilim
    a.label('idone')
    a.movl_pool(3, INTEG_ADDR); a.fmov_store(1, 3)# *integ = I
    # --- ratio = clamp(base + error*Kp + I, 0, MaxRatio) ---
    a.movl_pool(1, KP_ADDR); a.fmov_load(5, 1)    # fr5 = Kp
    a.fmul(6, 5)                                  # fr5 = Kp*error
    a.fpop(0)                                     # fr0 = base -> [stack: PR]
    a.fadd(5, 0); a.fadd(1, 0)                    # fr0 = base + P + I
    a.fldi0(2); a.fcmpgt(0, 2); a.bf('rhi'); a.fldi0(0)   # if ratio<0: 0
    a.label('rhi')
    a.movl_pool(1, MAXR_ADDR); a.fmov_load(2, 1)
    a.fcmpgt(2, 0); a.bf('rdone'); a.fmov(2, 0)   # if ratio>Max: Max
    a.label('rdone')
    a.fmov(0, 4)                                  # fr4 = ratio
    a.label('out')
    a.ldsl_pr()                                   # restore grandparent PR -> [stack empty]
    a.movl_pool(2, STOCK_OUTPUT); a.jmp(2); a.nop()  # tail-call output stage
    return a.assemble()

# ---------------- apply ----------------
def main():
    with open(STOCK, "rb") as f:
        rom = bytearray(f.read())
    assert len(rom) == 0x80000
    for addr in (BASE_DESC, RPM_AXIS, TARGET_DESC, STUB_ADDR, KP_ADDR):
        assert addr % 4 == 0

    blobs = [
        ("base_desc",   BASE_DESC,   desc_1axis(0x04, RPM_AXIS, BASE_DATA, DUTY_SCALE, 0.0)),
        ("rpm_axis",    RPM_AXIS,    b"".join(f32(x) for x in RPM_BREAKS)),
        ("base_data",   BASE_DATA,   bytes(BASE_DUTY)),
        ("target_desc", TARGET_DESC, desc_1axis(0x00, RPM_AXIS, TARGET_DATA, 1.0, 0.0)),
        ("target_data", TARGET_DATA, b"".join(f32(x) for x in TARGET_MAP)),
        ("gains",       KP_ADDR,     f32(KP)+f32(KI)+f32(ILIM)+f32(MAXRATIO)+f32(OVERBOOST)),
        ("stub",        STUB_ADDR,   build_stub()),
    ]
    for name, addr, data in blobs:
        assert FREE_START <= addr and addr + len(data) - 1 <= FREE_END, "%s overflows free space" % name
        if any(b != 0xFF for b in rom[addr:addr+len(data)]):
            raise SystemExit("REFUSING: %s @0x%X..0x%X not 0xFF-free" % (name, addr, addr+len(data)-1))
    cur = struct.unpack_from(">I", rom, HIJACK_LITERAL)[0]
    if cur != STOCK_OUTPUT:
        raise SystemExit("REFUSING: hijack literal @0x%X = 0x%08X (expected 0x%08X)" % (HIJACK_LITERAL, cur, STOCK_OUTPUT))

    for name, addr, data in blobs:
        rom[addr:addr+len(data)] = data
    rom[HIJACK_LITERAL:HIJACK_LITERAL+4] = be32(STUB_ADDR)

    with open(OUT, "wb") as f:
        f.write(rom)

    print("Phase 2 closed-loop boost patch written: %s" % OUT)
    print("  hijack @0x%05X : 0x%08X -> 0x%08X" % (HIJACK_LITERAL, STOCK_OUTPUT, STUB_ADDR))
    for name, addr, data in blobs:
        print("  %-11s @0x%05X : %d bytes" % (name, addr, len(data)))
    print("  RPM    : %s" % RPM_BREAKS)
    print("  base %% : %s" % BASE_DUTY)
    print("  target : %s (MAP units)" % TARGET_MAP)
    print("  Kp=%g Ki=%g Ilim=%g MaxRatio=%g Overboost=%g" % (KP, KI, ILIM, MAXRATIO, OVERBOOST))
    print("  integrator @0x%08X  init-flag @0x%08X" % (INTEG_ADDR, FLAG_ADDR))
    print("\n*** Fit EJ255 MAP sensor + rescale 0x72810 BEFORE raising Kp/Ki. ***")
    print("Flash via EcuFlash/RomRaider (recomputes subarudbw checksum on save).")

if __name__ == "__main__":
    main()
