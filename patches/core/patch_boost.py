#!/usr/bin/env python3
"""
Spring-pressure overboost-safety component for Subaru EZ30R D2WD610H.

The former electronic actuator hook was misidentified: 0x3FC0A -> 0xE8C4
controls radiator-fan PWM, not CPC purge. This builder now leaves that stock
route intact and retires the actuator code as return-only reserved space.
No EBCS switch can reactivate it. Use direct wastegate-spring plumbing.

The independent hard MAP fuel-cut wrapper and donor MAP scaling remain.
Legacy actuator calibration bytes keep their addresses for layout stability
but are unreferenced and removed from supplied tuning definitions. Master
replaces donor MAP calibration with the selected Omni sensor transfer.

The canonical stock ROM is read-only; only a private copy is patched.
Usage: python3 patch_boost.py [out.bin]
"""
import hashlib, struct, sys, os
from sh2_asm import Asm

HERE  = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.abspath(os.path.join(HERE, "..", "..", "2005 BLE MT.bin"))
DEFAULT_OUT = os.path.join(HERE, "D2WD610H_boost.bin")
OUT = (os.path.abspath(sys.argv[1]) if __name__ == "__main__" and len(sys.argv) > 1
       else DEFAULT_OUT)
STOCK_SHA256 = "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee"
if __name__ == "__main__" and len(sys.argv) > 2:
    raise SystemExit("usage: python3 patch_boost.py [out.bin]")

# --- fixed ROM anchors (verified against Ghidra) ---
HIJACK_LITERAL = 0x3FD8C       # historical name; stock fan pointer is never replaced
STOCK_OUTPUT   = 0x0000E8C4     # radiator_fan_pwm_output_write; MUST remain stock
INTERP_2D      = 0x0000209C     # table2d_lookup_dispatch(r4=desc, fr4=in) -> fr0
RPM_ADDR       = 0xFFFFB544     # engine RPM (float)          [read only]
MAP_ADDR       = 0xFFFFABC4     # manifold pressure (float)   [read only]
THROTTLE_ADDR  = 0xFFFFB314     # processed throttle opening (float) [read only]
MAP_SCALING_ADDR = 0x00072810   # float32[2]: offset, multiplier (native mmHg units)
# overboost fuel-cut (reuses the rev limiter's fuel-cut path, verified):
REVLIMITER     = 0x00024B24     # rev limiter (sets fuel-cut flag 0xFFFFBF6C bit0x80 by RPM)
REVLIM_FNPTR   = 0x00011D3C     # periodic-dispatcher fn-ptr slot -> rev limiter (we repoint it)
FUELCUT_FLAG   = 0xFFFFBF6C     # fuel-cut status byte; bit0x80 feeds the fuel-cut aggregator (0x23FC0)
FUELCUT_INHIBIT_WORD = 0xFFFFB744  # native six-channel injector scheduler inhibit word

# --- free-space layout (all 0xFF-verified free; < 0x7FAF7) ---
# Actuator descriptors/data are inert legacy reservations, retained only for
# stable addresses. Only OVERBOOST_ENABLE_ADDR, OVERB_FC_ADDR, and REVWRAP_ADDR
# below belong to active boost-protection logic.
BASE_DESC   = 0x7D790   # retired RPM -> base duty descriptor (u8 % * 0.01)
RPM_AXIS    = 0x7D7A4   # float32[8]  (shared by base + target)
BASE_DATA   = 0x7D7C4   # u8[8]  duty %
TARGET_DESC = 0x7D7CC   # 1-axis desc: RPM -> target (float32, type 0)
TARGET_DATA = 0x7D7E0   # float32[8]  target native mmHg absolute
KP_ADDR     = 0x7D800   # float32
MAXR_ADDR   = 0x7D804   # float32
OVERB_ADDR  = 0x7D808   # float32
EBCS_ENABLE_ADDR = 0x7D80C # retired uint8; no value enables an actuator
OVERBOOST_ENABLE_ADDR = 0x7D80D # uint8: exact 1=added hard MAP fuel cut; default 1
STUB_ADDR   = 0x7D810   # retired controller allocation, now RTS/NOP and erased padding
THROTTLE_GATE_ADDR = 0x7D8BC # retired float32 throttle gate; not executed
OVERB_FC_ADDR = 0x7D8C0 # float32: overboost FUEL-CUT MAP limit
REVWRAP_ADDR  = 0x7D8C4 # rev-limiter wrapper (adds overboost fuel cut; 4-aligned)
FREE_START, FREE_END = 0x7D790, 0x7FAF7

# ---------------- donor provenance and active MAP/hard-cut defaults ----------------
# Donor: A2WC510N, 2005 USDM Legacy GT MT, EJ255, SH7058, 1 MiB.
# SHA-256: db8827673a2383ce0ee3182d2c33f81be39fd63c3545e77b3e6bf8476488008d
# The EZ30 MAP routine was rechecked in Ghidra and named
# map_sensor_voltage_to_pressure_process @0x7A14. It calculates:
#   MAP_native = sensor_voltage * MAP_SENSOR_MULTIPLIER + MAP_SENSOR_OFFSET
# Native pressure is mmHg absolute. 760 mmHg is the sea-level reference used by the 32BITBASE
# Subaru pressure scalings; one psi is 51.71493257 mmHg. The active hard cut
# uses an absolute MAP threshold, displayed relative to 760 mmHg.
ATM_PRESSURE_NATIVE = 760.0
NATIVE_PER_PSI = 51.71493257
MAP_SENSOR_OFFSET = -414.0
MAP_SENSOR_MULTIPLIER = 514.199951171875
STOCK_MAP_SENSOR_OFFSET = -150.0
STOCK_MAP_SENSOR_MULTIPLIER = 250.0

RPM_BREAKS  = [1500.0, 2000.0, 2500.0, 3000.0, 3500.0, 4000.0, 5000.0, 6000.0]
# Full-demand A2WC510N Initial WGDC curve, reduced by the same 5 psi / 13.536 psi peak ratio.
# Retained only as inert donor-provenance data; there is no WGDC controller.
BASE_DUTY   = [   0,     0,     21,     19,     18,     17,     15,     14 ]
# Full-demand A2WC510N Target Boost A/B curve reduced so its peak is exactly 5 psi above 760 mmHg.
TARGET_BOOST_PSI = [1.482142857, 2.285714286, 5.0, 5.0, 5.0, 4.785714286, 4.357142857, 3.928571429]
TARGET_MAP = [ATM_PRESSURE_NATIVE + psi * NATIVE_PER_PSI for psi in TARGET_BOOST_PSI]
# A2WC510N TD Proportional is locally 0.5 duty percentage point per 10 native units:
# (0.005 ratio / 10 mmHg) = 0.0005 ratio/mmHg.
KP          = 0.0005
MAXRATIO    = 0.33     # inert legacy scalar derived from the donor max-WGDC curve
OVERBOOST_PSI = 6.0
OVERBOOST   = ATM_PRESSURE_NATIVE + OVERBOOST_PSI * NATIVE_PER_PSI
MIN_THROTTLE = 30.0   # inert legacy throttle gate
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
    """Retired actuator allocation: return without touching hardware or state.

    The original output was radiator-fan PWM, not CPC. Never reinstall that
    hook. Preserve the 172-byte reservation so unrelated calibrations do not
    move, but erase all former controller instructions and output literals.
    """
    return bytes.fromhex("000b0009") + b"\xff" * (THROTTLE_GATE_ADDR - STUB_ADDR - 4)

def emit_added_fuel_cut(a):
    """Publish both native cut interfaces after the retained limiter ran.

    Stock 24B24 builds B744 via 1C5D4 before returning. Setting BF6C afterward
    alone leaves the injector scheduler's word stale. The stock global-cut
    branch at 1C662/1C90A publishes 0xFFFF; use that same value here. The next
    retained limiter invocation rebuilds the ordinary per-cylinder word.
    """
    a.movl_pool(1, FUELCUT_FLAG).movb_at(0, 1).or_imm(0x80).movb_store(0, 1)
    a.movl_pool(1, FUELCUT_INHIBIT_WORD).mov_imm(-1, 0).movw_store(0, 1)


TASK_LOCK = 0x00003AF4
TASK_UNLOCK = 0x00003B08


def emit_cut_update_begin(a, prior):
    """Use the native minimum-IMASK-1 critical section around the whole update.

    Higher hardware interrupt levels remain enabled. Native task activation
    defers dispatch while IMASK is nonzero; 3B08 restores the incoming mask
    and dispatches a pending task when unlocking to zero. Save its mask return
    in the prior routine's delay slot, before that routine can clobber R0.
    """
    a.stsl_pr()
    a.movl_pool(3, TASK_LOCK).jsr(3).mov_imm(0x10, 4)
    a.movl_pool(2, prior).jsr(2).push(0)


def emit_cut_update_end(a):
    """Restore the original mask and caller PR, including nested guard calls."""
    a.pop(4).movl_pool(3, TASK_UNLOCK).jmp(3).ldsl_pr()


def build_fuelcut_wrapper():
    """Rev-limiter wrapper: run the stock rev limiter, then set the fuel-cut flag on overboost.
       Entered void (PR = dispatcher). Runs in the rev-limiter's task slot, so the fuel-cut
       aggregator sees the flag and the scheduler sees the inhibit word before
       this task returns. The native scheduler lock prevents a higher-priority
       injector task seeing the retained limiter's temporary clear. No new RAM state."""
    a = Asm(REVWRAP_ADDR)
    emit_cut_update_begin(a, REVLIMITER)
    a.movl_pool(1, OVERBOOST_ENABLE_ADDR); a.movb_at(0, 1); a.cmp_eq_imm(0x01)
    a.bf('skip')                                                   # anything but 01: stock rev limiter only
    a.movl_pool(1, MAP_ADDR); a.fmov_load(2, 1)                    # fr2 = MAP
    a.movl_pool(1, OVERB_FC_ADDR); a.fmov_load(3, 1)               # fr3 = fuel-cut limit
    a.fcmpgt(3, 2); a.bf('skip')                                   # if MAP > limit:
    emit_added_fuel_cut(a)
    a.label('skip')
    emit_cut_update_end(a)
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
        ("ebcs_enable", EBCS_ENABLE_ADDR, b"\x00"),
        ("overboost_enable", OVERBOOST_ENABLE_ADDR, b"\x01"),
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
    # Pin the native all-channel cut value, destination and downstream reader
    # before publishing the same word from either added cut path.
    for address, expected in (
        (0x1C662, "d40aa1500009"), (0x1C68C, "0000ffff"),
        (0x1C908, "93082341"), (0x1C91C, "b744"),
        (0x26DFC, "9377000b6031"), (0x26EEE, "b744"),
    ):
        data = bytes.fromhex(expected)
        if rom[address:address + len(data)] != data:
            raise SystemExit("REFUSING: native injector-inhibit contract changed @0x%X" % address)
    lock_contract = bytes.fromhex(
        "95050002205934068b02000b440e00f0000b0009"
        "24488b07d5045656846188018902d603462b440e000b440e"
        "ffff72b000003f84"
    )
    if rom[TASK_LOCK:TASK_LOCK + len(lock_contract)] != lock_contract:
        raise SystemExit("REFUSING: native scheduler-lock contract changed @0x3AF4")
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
    # Preserve the fan output; only install the independent overboost fuel cut.
    cur = struct.unpack_from(">I", rom, HIJACK_LITERAL)[0]
    if cur != STOCK_OUTPUT:
        raise SystemExit("REFUSING: output hijack @0x%X = 0x%08X (expected 0x%08X)" % (HIJACK_LITERAL, cur, STOCK_OUTPUT))
    cur2 = struct.unpack_from(">I", rom, REVLIM_FNPTR)[0]
    if cur2 != REVLIMITER:
        raise SystemExit("REFUSING: rev-limiter fn-ptr @0x%X = 0x%08X (expected 0x%08X)" % (REVLIM_FNPTR, cur2, REVLIMITER))

    for name, addr, data in blobs:
        rom[addr:addr+len(data)] = data
    rom[MAP_SCALING_ADDR:MAP_SCALING_ADDR+len(map_scaling)] = map_scaling
    assert rom[HIJACK_LITERAL:HIJACK_LITERAL+4] == be32(STOCK_OUTPUT)
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

    print("Spring-pressure overboost-safety patch written: %s" % OUT)
    print("  stock source     : %s (unchanged, SHA-256 %s)" % (STOCK, stock_hash))
    print("  fan output      @0x%05X : stock 0x%08X PRESERVED" % (HIJACK_LITERAL, STOCK_OUTPUT))
    print("  revlimiter hook @0x%05X : 0x%08X -> 0x%08X" % (REVLIM_FNPTR, REVLIMITER, REVWRAP_ADDR))
    print("  MAP scaling     @0x%05X : {%g, %g} -> {%g, %.7g}"
          % (MAP_SCALING_ADDR, STOCK_MAP_SENSOR_OFFSET, STOCK_MAP_SENSOR_MULTIPLIER,
             MAP_SENSOR_OFFSET, MAP_SENSOR_MULTIPLIER))
    for name, addr, data in blobs:
        print("  %-11s @0x%05X : %d bytes" % (name, addr, len(data)))
    print("  retired data     : donor RPM/WGDC/target/gain tables remain inert at legacy addresses")
    print("  hard fuel cut    : %g psi relative to 760 mmHg" % OVERBOOST_FUELCUT_PSI)
    print("  retired EBCS byte@0x%05X : inert; no electronic actuator code installed"
          % EBCS_ENABLE_ADDR)
    print("  overboost switch@0x%05X : ON (01); exact 01 permits the added hard MAP cut"
          % OVERBOOST_ENABLE_ADDR)
    print("  MAP calibration  : remains donor-scaled regardless of the hard-cut switch")
    print("  fuel cut reuses rev-limiter path: sets 0xFFFFBF6C bit0x80 (via 0x23FC0 aggregator)")
    print("\n*** Fit the A2WC510N-compatible EJ255 MAP sensor and validate 0xFFFFABC4 against a gauge. ***")
    print("This standalone output has no checksum repair; the master builder repairs the Subaru checksum.")

if __name__ == "__main__":
    main()
