#!/usr/bin/env python3
"""
Boost-control patch for Subaru EZ30R D2WD610H.

Proportional + feed-forward controller on the repurposed purge PWM output (ATU-II 0xFFFFF590):

    base   = BaseDuty[rpm]                 (feed-forward, ratio)
    target = TargetBoost[rpm]              (native pressure: mmHg absolute)
    err    = target - MAP(0xFFFFABC4)
    ratio  = clamp(base + Kp*err, 0, MaxRatio)
    if throttle <= MinThrottle: ratio = 0  (driver-demand gate)
    if MAP > Overboost: ratio = 0          (actuator fail-safe)
    -> stock output stage 0xE8C4

STATELESS by design — no persistent RAM. The integral term (WRX "Turbo Dynamics") is
intentionally OMITTED: an audit (patch/verify_regions.py) showed no RAM word can be *proven*
free on this ROM (the top-of-RAM candidates fall inside the cam-solenoid struct array via
computed addressing; the large unreferenced gaps are computed-access buffers / jump tables).
Rather than risk corrupting other subsystems, this controller is P-only. Adding I later requires
a rigorously-verified RAM scratch (or reclaiming purge RAM by NOP-ing the stock writes).

Hijack: repoint the tail-call pointer @0x3FD8C (evap_purge_duty_compute) to the stub. The
mechanism is verified against Ghidra. The stub is the SOLE runtime driver of the
solenoid (0xE8C4 has one caller; 0xFFFFF590 is otherwise written only by init).

Default calibrations are reduced from the 2005 EJ255 Legacy GT MT ROM A2WC510N and rescaled to
a 5 psi peak target. The matching MAP conversion (-414.0 offset, 514.2 multiplier) is installed
at 0x72810. Use the matching turbo MAP sensor, validate it against a reference gauge, bench-prove
the built-in hard fuel cut, and retain a mechanical boost fallback.

The canonical stock ROM is always read from the repository root and is never opened for
writing. The patcher refuses an output path that aliases it.

Usage:  python3 patch_boost.py [out.bin]
"""
import hashlib, struct, sys, os
from sh2_asm import Asm

HERE  = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.abspath(os.path.join(HERE, "..", "2005 BLE MT.bin"))
DEFAULT_OUT = os.path.join(HERE, "D2WD610H_boost.bin")
OUT = (os.path.abspath(sys.argv[1]) if __name__ == "__main__" and len(sys.argv) > 1
       else DEFAULT_OUT)
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"
if __name__ == "__main__" and len(sys.argv) > 2:
    raise SystemExit("usage: python3 patch_boost.py [out.bin]")

# --- fixed ROM anchors (verified against Ghidra) ---
HIJACK_LITERAL = 0x3FD8C
STOCK_OUTPUT   = 0x0000E8C4     # evap_purge_pwm_output_write (fr4 = ratio)
INTERP_2D      = 0x0000209C     # table2d_lookup_dispatch(r4=desc, fr4=in) -> fr0
RPM_ADDR       = 0xFFFFB544     # engine RPM (float)          [read only]
MAP_ADDR       = 0xFFFFABC4     # manifold pressure (float)   [read only]
THROTTLE_ADDR  = 0xFFFFB314     # processed throttle opening (float) [read only]
MAP_SCALING_ADDR = 0x00072810   # float32[2]: offset, multiplier (native mmHg units)
# overboost fuel-cut (reuses the rev limiter's fuel-cut path, verified):
REVLIMITER     = 0x00024B24     # rev limiter (sets fuel-cut flag 0xFFFFBF6C bit0x80 by RPM)
REVLIM_FNPTR   = 0x00011D3C     # periodic-dispatcher fn-ptr slot -> rev limiter (we repoint it)
FUELCUT_FLAG   = 0xFFFFBF6C     # fuel-cut status byte; bit0x80 feeds the fuel-cut aggregator (0x23FC0)

# --- free-space layout (all 0xFF-verified free; < 0x7FAF7) ---
BASE_DESC   = 0x7D790   # 1-axis desc: RPM -> base duty ratio (u8 % * 0.01)
RPM_AXIS    = 0x7D7A4   # float32[8]  (shared by base + target)
BASE_DATA   = 0x7D7C4   # u8[8]  duty %
TARGET_DESC = 0x7D7CC   # 1-axis desc: RPM -> target (float32, type 0)
TARGET_DATA = 0x7D7E0   # float32[8]  target native mmHg absolute
KP_ADDR     = 0x7D800   # float32
MAXR_ADDR   = 0x7D804   # float32
OVERB_ADDR  = 0x7D808   # float32
BOOST_ENABLE_ADDR = 0x7D80C # uint8: exact 1=patch; every other value=zero duty/stock rev limit
STUB_ADDR   = 0x7D810   # controller (4-aligned)
THROTTLE_GATE_ADDR = 0x7D8BC # float32: minimum throttle opening for boost duty
OVERB_FC_ADDR = 0x7D8C0 # float32: overboost FUEL-CUT MAP limit
REVWRAP_ADDR  = 0x7D8C4 # rev-limiter wrapper (adds overboost fuel cut; 4-aligned)
FREE_START, FREE_END = 0x7D790, 0x7FAF7

# ---------------- donor-derived defaults / tunables ----------------
# Donor: A2WC510N, 2005 USDM Legacy GT MT, EJ255, SH7058, 1 MiB.
# SHA-256: db8827673a2383ce0ee3182d2c33f81be39fd63c3545e77b3e6bf8476488008d
# The EZ30 MAP routine was rechecked in Ghidra and named
# map_sensor_voltage_to_pressure_process @0x7A14. It calculates:
#   MAP_native = sensor_voltage * MAP_SENSOR_MULTIPLIER + MAP_SENSOR_OFFSET
# Native pressure is mmHg absolute. 760 mmHg is the sea-level reference used by the 32BITBASE
# Subaru boost scalings; one psi is 51.71493257 mmHg. This controller does not yet apply the
# donor's atmospheric-pressure target compensation, so displayed psi is relative to 760 mmHg.
ATM_PRESSURE_NATIVE = 760.0
NATIVE_PER_PSI = 51.71493257
MAP_SENSOR_OFFSET = -414.0
MAP_SENSOR_MULTIPLIER = 514.199951171875
STOCK_MAP_SENSOR_OFFSET = -150.0
STOCK_MAP_SENSOR_MULTIPLIER = 250.0

RPM_BREAKS  = [1500.0, 2000.0, 2500.0, 3000.0, 3500.0, 4000.0, 5000.0, 6000.0]
# Full-demand A2WC510N Initial WGDC curve, reduced by the same 5 psi / 13.536 psi peak ratio.
# This is only a conservative starting curve: WGDC does not physically scale linearly with boost.
BASE_DUTY   = [   0,     0,     21,     19,     18,     17,     15,     14 ]
# Full-demand A2WC510N Target Boost A/B curve reduced so its peak is exactly 5 psi above 760 mmHg.
TARGET_BOOST_PSI = [1.482142857, 2.285714286, 5.0, 5.0, 5.0, 4.785714286, 4.357142857, 3.928571429]
TARGET_MAP = [ATM_PRESSURE_NATIVE + psi * NATIVE_PER_PSI for psi in TARGET_BOOST_PSI]
# A2WC510N TD Proportional is locally 0.5 duty percentage point per 10 native units:
# (0.005 ratio / 10 mmHg) = 0.0005 ratio/mmHg.
KP          = 0.0005
MAXRATIO    = 0.33     # conservative scalar cap near the donor's 5 psi-scaled peak max WGDC
OVERBOOST_PSI = 6.0
OVERBOOST   = ATM_PRESSURE_NATIVE + OVERBOOST_PSI * NATIVE_PER_PSI
MIN_THROTTLE = 30.0   # native throttle opening (~35.7% on the donor's x/.84 display scaling)
OVERBOOST_FUELCUT_PSI = 7.0
OVERBOOST_FUELCUT = ATM_PRESSURE_NATIVE + OVERBOOST_FUELCUT_PSI * NATIVE_PER_PSI
DUTY_SCALE  = 0.01     # base-map u8 % -> ratio

assert len(RPM_BREAKS) == len(BASE_DUTY) == len(TARGET_MAP) == 8
assert abs(max(TARGET_BOOST_PSI) - 5.0) < 1e-9
assert OVERBOOST_FUELCUT > OVERBOOST > max(TARGET_MAP)

# ---------------- builders ----------------
def be32(v): return struct.pack(">I", v & 0xFFFFFFFF)
def f32(x):  return struct.pack(">f", x)

def desc_1axis(type_byte, axis_addr, data_addr, scale, offset):
    d = struct.pack(">H", 8) + bytes([type_byte, 0]) + be32(axis_addr) + be32(data_addr) + f32(scale) + f32(offset)
    assert len(d) == 0x14
    return d

def build_stub():
    """Proportional + feed-forward. Entered via tail-call jmp (PR=grandparent).

       With BOOST_ENABLE_ADDR clear, force FR4 to zero before the stock output stage
       (the safe spring-pressure state for the required plumbing). With it set,
       replace FR4 with calculated boost duty. Reads only RAM + flash constants —
       NO RAM writes.
    """
    a = Asm(STUB_ADDR)
    a.movl_pool(1, BOOST_ENABLE_ADDR); a.movb_at(0, 1); a.cmp_eq_imm(0x01)
    a.bt('enabled')                                                # exact 01 -> boost controller
    a.fldi0(4)                                                     # disabled: fail closed at zero EBCS duty
    a.movl_pool(2, STOCK_OUTPUT); a.jmp(2); a.nop()
    a.label('enabled')
    a.stsl_pr()                                                    # [stack: PR]
    a.movl_pool(1, THROTTLE_ADDR); a.fmov_load(2, 1)               # fr2 = throttle opening
    a.movl_pool(1, THROTTLE_GATE_ADDR); a.fmov_load(3, 1)          # fr3 = minimum throttle
    a.fcmpgt(3, 2); a.bf('throttle_off')                           # require throttle > minimum
    a.movl_pool(1, RPM_ADDR); a.fmov_load(4, 1)                    # fr4 = RPM
    a.movl_pool(4, BASE_DESC); a.movl_pool(2, INTERP_2D); a.jsr(2); a.nop()  # fr0 = base ratio
    a.fpush(0)                                                     # [stack: PR, base]
    a.movl_pool(1, RPM_ADDR); a.fmov_load(4, 1)                    # fr4 = RPM
    a.movl_pool(4, TARGET_DESC); a.movl_pool(2, INTERP_2D); a.jsr(2); a.nop()  # fr0 = target
    a.movl_pool(1, MAP_ADDR); a.fmov_load(2, 1)                    # fr2 = MAP
    a.movl_pool(1, OVERB_ADDR); a.fmov_load(3, 1)                  # fr3 = overboost limit
    a.fcmpgt(3, 2); a.bf('no_ob')                                  # if MAP > limit:
    a.fldi0(4); a.fpop(0); a.bra('out'); a.nop()                   #   ratio=0, drop base, out
    a.label('no_ob')
    a.fsub(2, 0)                                                   # fr0 = target - MAP = error
    a.movl_pool(1, KP_ADDR); a.fmov_load(5, 1); a.fmul(5, 0)       # fr0 = Kp*error
    a.fpop(1); a.fadd(1, 0)                                        # fr0 = base + Kp*error
    a.fldi0(2); a.fcmpgt(0, 2); a.bf('rhi'); a.fldi0(0)            # clamp low: if ratio<0 -> 0
    a.label('rhi')
    a.movl_pool(1, MAXR_ADDR); a.fmov_load(2, 1)
    a.fcmpgt(2, 0); a.bf('rdone'); a.fmov(2, 0)                    # clamp high: if ratio>Max -> Max
    a.label('rdone')
    a.fmov(0, 4)                                                   # fr4 = ratio
    a.bra('out'); a.nop()
    a.label('throttle_off')
    a.fldi0(4)                                                     # fail closed: zero solenoid duty
    a.label('out')
    a.ldsl_pr()                                                    # restore PR [stack empty]
    a.movl_pool(2, STOCK_OUTPUT); a.jmp(2); a.nop()                # tail-call output stage
    return a.assemble()

def build_fuelcut_wrapper():
    """Rev-limiter wrapper: run the stock rev limiter, then set the fuel-cut flag on overboost.
       Entered void (PR = dispatcher). Runs in the rev-limiter's task slot, so the fuel-cut
       aggregator (0x23FC0) picks up the flag the same/next cycle. No RAM state."""
    a = Asm(REVWRAP_ADDR)
    a.stsl_pr()                                                    # save dispatcher PR
    a.movl_pool(2, REVLIMITER); a.jsr(2); a.nop()                  # call stock rev limiter
    a.movl_pool(1, BOOST_ENABLE_ADDR); a.movb_at(0, 1); a.cmp_eq_imm(0x01)
    a.bf('skip')                                                   # anything but 01: stock rev limiter only
    a.movl_pool(1, MAP_ADDR); a.fmov_load(2, 1)                    # fr2 = MAP
    a.movl_pool(1, OVERB_FC_ADDR); a.fmov_load(3, 1)               # fr3 = fuel-cut limit
    a.fcmpgt(3, 2); a.bf('skip')                                   # if MAP > limit:
    a.movl_pool(1, FUELCUT_FLAG)                                   #   flag |= 0x80  (force fuel cut)
    a.movb_at(0, 1); a.or_imm(0x80); a.movb_store(0, 1)
    a.label('skip')
    a.ldsl_pr(); a.rts(); a.nop()                                  # return to dispatcher
    return a.assemble()

# ---------------- apply ----------------
def build_blobs():
    return [
        ("base_desc",   BASE_DESC,   desc_1axis(0x04, RPM_AXIS, BASE_DATA, DUTY_SCALE, 0.0)),
        ("rpm_axis",    RPM_AXIS,    b"".join(f32(x) for x in RPM_BREAKS)),
        ("base_data",   BASE_DATA,   bytes(BASE_DUTY)),
        ("target_desc", TARGET_DESC, desc_1axis(0x00, RPM_AXIS, TARGET_DATA, 1.0, 0.0)),
        ("target_data", TARGET_DATA, b"".join(f32(x) for x in TARGET_MAP)),
        ("gains",       KP_ADDR,     f32(KP)+f32(MAXRATIO)+f32(OVERBOOST)),
        ("enable",      BOOST_ENABLE_ADDR, b"\x01"),
        ("stub",        STUB_ADDR,   build_stub()),
        ("throttle_gate",THROTTLE_GATE_ADDR, f32(MIN_THROTTLE)),
        ("overb_fc",    OVERB_FC_ADDR, f32(OVERBOOST_FUELCUT)),
        ("fuelcut_wrap",REVWRAP_ADDR,  build_fuelcut_wrapper()),
    ]


def apply_to_rom(rom):
    """Apply only the boost changes to a mutable stock-derived ROM image.

    This function is shared by the standalone and combined builders.  Every
    touched byte retains the same stock/free-space guard used by the original
    standalone patcher.
    """
    if len(rom) != 0x80000:
        raise SystemExit("REFUSING: expected a 512 KB stock-derived image, got %d bytes"
                         % len(rom))
    for addr in (BASE_DESC, RPM_AXIS, TARGET_DESC, STUB_ADDR, KP_ADDR):
        assert addr % 4 == 0

    blobs = build_blobs()
    map_scaling = f32(MAP_SENSOR_OFFSET) + f32(MAP_SENSOR_MULTIPLIER)
    stock_map_scaling = f32(STOCK_MAP_SENSOR_OFFSET) + f32(STOCK_MAP_SENSOR_MULTIPLIER)
    if rom[MAP_SCALING_ADDR:MAP_SCALING_ADDR+len(stock_map_scaling)] != stock_map_scaling:
        raise SystemExit("REFUSING: stock MAP scaling @0x%X is not {%g, %g}"
                         % (MAP_SCALING_ADDR, STOCK_MAP_SENSOR_OFFSET, STOCK_MAP_SENSOR_MULTIPLIER))
    previous_end = FREE_START
    for name, addr, data in sorted(blobs, key=lambda item: item[1]):
        assert FREE_START <= addr and addr + len(data) - 1 <= FREE_END, "%s overflows free space" % name
        if addr < previous_end:
            raise SystemExit("layout error: %s @0x%X overlaps the preceding allocation" % (name, addr))
        if any(b != 0xFF for b in rom[addr:addr+len(data)]):
            raise SystemExit("REFUSING: %s @0x%X..0x%X not 0xFF-free" % (name, addr, addr+len(data)-1))
        previous_end = addr + len(data)
    # two hijacks: output tail-call (boost) + rev-limiter fn-ptr (overboost fuel cut)
    cur = struct.unpack_from(">I", rom, HIJACK_LITERAL)[0]
    if cur != STOCK_OUTPUT:
        raise SystemExit("REFUSING: output hijack @0x%X = 0x%08X (expected 0x%08X)" % (HIJACK_LITERAL, cur, STOCK_OUTPUT))
    cur2 = struct.unpack_from(">I", rom, REVLIM_FNPTR)[0]
    if cur2 != REVLIMITER:
        raise SystemExit("REFUSING: rev-limiter fn-ptr @0x%X = 0x%08X (expected 0x%08X)" % (REVLIM_FNPTR, cur2, REVLIMITER))

    for name, addr, data in blobs:
        rom[addr:addr+len(data)] = data
    rom[MAP_SCALING_ADDR:MAP_SCALING_ADDR+len(map_scaling)] = map_scaling
    rom[HIJACK_LITERAL:HIJACK_LITERAL+4] = be32(STUB_ADDR)
    rom[REVLIM_FNPTR:REVLIM_FNPTR+4]     = be32(REVWRAP_ADDR)
    return blobs


def main():
    if os.path.realpath(OUT) == os.path.realpath(STOCK):
        raise SystemExit("REFUSING: output path aliases the canonical stock ROM: %s" % STOCK)
    if os.path.exists(OUT) and os.path.samefile(OUT, STOCK):
        raise SystemExit("REFUSING: output file is the canonical stock ROM (or a hard link to it)")

    with open(STOCK, "rb") as f:
        stock_bytes = f.read()
    stock_hash = hashlib.sha256(stock_bytes).hexdigest()
    if stock_hash != STOCK_SHA256:
        raise SystemExit("REFUSING: canonical stock ROM hash is %s (expected %s)"
                         % (stock_hash, STOCK_SHA256))
    rom = bytearray(stock_bytes)  # patch a private copy; never modify STOCK in place
    blobs = apply_to_rom(rom)

    with open(OUT, "wb") as f:
        f.write(rom)

    # Guard the Ghidra source image even if this script is edited later.
    with open(STOCK, "rb") as f:
        if f.read() != stock_bytes:
            raise RuntimeError("canonical stock ROM changed during patch build")

    print("Boost-control patch written: %s" % OUT)
    print("  stock source     : %s (unchanged, SHA-256 %s)" % (STOCK, stock_hash))
    print("  output hijack   @0x%05X : 0x%08X -> 0x%08X" % (HIJACK_LITERAL, STOCK_OUTPUT, STUB_ADDR))
    print("  revlimiter hook @0x%05X : 0x%08X -> 0x%08X" % (REVLIM_FNPTR, REVLIMITER, REVWRAP_ADDR))
    print("  MAP scaling     @0x%05X : {%g, %g} -> {%g, %.7g}"
          % (MAP_SCALING_ADDR, STOCK_MAP_SENSOR_OFFSET, STOCK_MAP_SENSOR_MULTIPLIER,
             MAP_SENSOR_OFFSET, MAP_SENSOR_MULTIPLIER))
    for name, addr, data in blobs:
        print("  %-11s @0x%05X : %d bytes" % (name, addr, len(data)))
    print("  RPM    : %s" % RPM_BREAKS)
    print("  base %% : %s" % BASE_DUTY)
    print("  target : %s (psi relative to 760 mmHg; native=%s)" % (TARGET_BOOST_PSI, TARGET_MAP))
    print("  Kp=%g ratio/mmHg MaxRatio=%g MinThrottle=%g Overboost(duty)=%gpsi Overboost(fuelcut)=%gpsi"
          % (KP, MAXRATIO, MIN_THROTTLE, OVERBOOST_PSI, OVERBOOST_FUELCUT_PSI))
    print("  runtime switch  @0x%05X : ON (01); RomRaider OFF forces zero EBCS duty + stock rev limiter"
          % BOOST_ENABLE_ADDR)
    print("  switch caveat   : OFF does not restore the stock MAP-sensor scaling at 0x%05X" % MAP_SCALING_ADDR)
    print("  fuel cut reuses rev-limiter path: sets 0xFFFFBF6C bit0x80 (via 0x23FC0 aggregator)")
    print("\n*** Fit the A2WC510N-compatible EJ255 MAP sensor and validate 0xFFFFABC4 against a gauge. ***")
    print("Flash via EcuFlash/RomRaider (recomputes subarudbw checksum on save).")

if __name__ == "__main__":
    main()
