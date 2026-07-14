#!/usr/bin/env python3
"""
Phase 1 boost-control patch for Subaru EZ30R D2WD610H (SH7055).

Repurposes the EVAP purge PWM output (ATU-II reg 0xFFFFF590) as an open-loop
wastegate/boost solenoid driver, controlled by an RPM -> duty map.

Mechanism (see docs/boost_repurpose_notes.md, docs/patch_build_guide.md):
  evap_purge_duty_compute @0x3FC0A tail-calls the purge output stage via a pooled
  pointer at file offset 0x3FD8C (= 0x0000E8C4), passing the duty RATIO in fr4.
  We repoint that ONE 4-byte literal to a small stub placed in free space. The stub
  ignores the purge ratio, looks up boost duty from an RPM map using the ROM's own
  interpolator (table2d_lookup_dispatch @0x209C), and tail-calls the real output
  stage (0xE8C4) with our ratio in fr4. Net: the solenoid is driven by our map.

Everything lands in the 9 KB free space at 0x7D790 (0xFF-filled, verified).
Flash the output via EcuFlash/RomRaider (they recompute the subarudbw checksum on save).

Usage:  python3 patch_boost.py [stock.bin] [out.bin]
"""
import struct, sys, os

# ---------------------------------------------------------------- config
HERE        = os.path.dirname(os.path.abspath(__file__))
STOCK       = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "2005 BLE MT.bin")
OUT         = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "D2WD610H_boost_p1.bin")

# ROM anchors (file offsets; flash base = 0)
HIJACK_LITERAL = 0x3FD8C      # pooled ptr in evap_purge_duty_compute; stock = 0x0000E8C4
STOCK_OUTPUT   = 0x0000E8C4   # evap_purge_pwm_output_write (real output stage)
INTERP_2D      = 0x0000209C   # table2d_lookup_dispatch(r4=descriptor, fr4=input) -> fr0
RPM_ADDR       = 0xFFFFB544   # engine RPM (float) in RAM

# Free-space layout (must be 0xFF and inside 0x7D790..0x7FAF7)
DESC_ADDR      = 0x7D790      # 1-axis table descriptor (0x14 bytes)
AXIS_ADDR      = 0x7D7A4      # RPM breakpoints (float32[])
DATA_ADDR      = 0x7D7C4      # duty values (uint8[])
STUB_ADDR      = 0x7D7CC      # boost stub (4-byte aligned)
FREE_START, FREE_END = 0x7D790, 0x7FAF7

# --- the tunable map (placeholder; tune in RomRaider) ---
RPM_BREAKS = [1500.0, 2000.0, 2500.0, 3000.0, 3500.0, 4000.0, 5000.0, 6000.0]
DUTY_PCT   = [   0,      0,     12,     22,     28,     30,     28,     22   ]  # wastegate duty %
DUTY_SCALE = 0.01            # descriptor scale: u8 duty% * 0.01 -> ratio 0..1 (returned in fr0)

assert len(RPM_BREAKS) == len(DUTY_PCT)
assert all(0 <= d <= 100 for d in DUTY_PCT)

# ---------------------------------------------------------------- helpers
def be32(v):  return struct.pack(">I", v & 0xFFFFFFFF)
def be16(v):  return struct.pack(">H", v & 0xFFFF)
def bef32(x): return struct.pack(">f", x)

def build_descriptor():
    """1-axis descriptor: len@0 u16, type@2 u8, axisptr@4, dataptr@8, scale@0xC f32, offset@0x10 f32."""
    d  = be16(len(RPM_BREAKS))     # +0x00 axis length
    d += bytes([0x04, 0x00])       # +0x02 type = 4 (uint8), +0x03 pad
    d += be32(AXIS_ADDR)           # +0x04 axis ptr
    d += be32(DATA_ADDR)           # +0x08 data ptr
    d += bef32(DUTY_SCALE)         # +0x0C scale
    d += bef32(0.0)                # +0x10 offset
    assert len(d) == 0x14
    return d

def build_axis(): return b"".join(bef32(x) for x in RPM_BREAKS)
def build_data(): return bytes(DUTY_PCT)

def build_stub():
    """SH-2E stub. Entered via tail-call jmp (PR = grandparent, fr4 = purge ratio, ignored).
       Layout (STUB 4-aligned): 0x18 bytes code + 0x10 bytes literal pool."""
    code = b""
    code += be16(0x4F22)   # +00 sts.l pr,@-r15         ; save grandparent PR
    code += be16(0xD105)   # +02 mov.l @(pc,0x14),r1    ; r1 = RPM_ADDR   (lit0 @ +0x18)
    code += be16(0xF418)   # +04 fmov.s @r1,fr4         ; fr4 = RPM
    code += be16(0xD405)   # +06 mov.l @(pc,0x14),r4    ; r4 = DESC_ADDR  (lit1 @ +0x1C)
    code += be16(0xD205)   # +08 mov.l @(pc,0x14),r2    ; r2 = INTERP_2D  (lit2 @ +0x20)
    code += be16(0x420B)   # +0A jsr @r2                ; interp -> fr0 = duty ratio
    code += be16(0x0009)   # +0C nop                    ; (delay slot)
    code += be16(0xF40C)   # +0E fmov fr0,fr4           ; fr4 = ratio (arg to output stage)
    code += be16(0x4F26)   # +10 lds.l @r15+,pr         ; restore grandparent PR
    code += be16(0xD204)   # +12 mov.l @(pc,0x10),r2    ; r2 = STOCK_OUTPUT (lit3 @ +0x24)
    code += be16(0x422B)   # +14 jmp @r2                ; tail-call 0xE8C4 (rts -> grandparent)
    code += be16(0x0009)   # +16 nop                    ; (delay slot)
    assert len(code) == 0x18
    pool  = be32(RPM_ADDR) + be32(DESC_ADDR) + be32(INTERP_2D) + be32(STOCK_OUTPUT)
    return code + pool     # 0x28 bytes

# ---------------------------------------------------------------- apply
def main():
    with open(STOCK, "rb") as f:
        rom = bytearray(f.read())
    assert len(rom) == 0x80000, "expected 512 KB image, got %d" % len(rom)
    assert STUB_ADDR % 4 == 0 and DESC_ADDR % 4 == 0 and AXIS_ADDR % 4 == 0

    blobs = [("descriptor", DESC_ADDR, build_descriptor()),
             ("rpm_axis",   AXIS_ADDR, build_axis()),
             ("duty_data",  DATA_ADDR, build_data()),
             ("stub",       STUB_ADDR, build_stub())]

    # safety: every target byte must currently be free (0xFF) and inside the free region
    for name, addr, data in blobs:
        assert FREE_START <= addr and addr + len(data) - 1 <= FREE_END, "%s outside free space" % name
        if any(b != 0xFF for b in rom[addr:addr+len(data)]):
            raise SystemExit("REFUSING: %s target 0x%X..0x%X is not 0xFF-free" % (name, addr, addr+len(data)-1))

    # sanity: hijack literal must currently be the stock output pointer
    cur = struct.unpack_from(">I", rom, HIJACK_LITERAL)[0]
    if cur != STOCK_OUTPUT:
        raise SystemExit("REFUSING: hijack literal @0x%X is 0x%08X, expected 0x%08X (already patched or wrong bin?)"
                         % (HIJACK_LITERAL, cur, STOCK_OUTPUT))

    # write blobs
    for name, addr, data in blobs:
        rom[addr:addr+len(data)] = data
    # repoint the tail-call literal to the stub
    rom[HIJACK_LITERAL:HIJACK_LITERAL+4] = be32(STUB_ADDR)

    with open(OUT, "wb") as f:
        f.write(rom)

    # report
    print("Phase 1 boost patch written: %s" % OUT)
    print("  hijack  @0x%05X : 0x%08X -> 0x%08X (evap output ptr -> boost stub)"
          % (HIJACK_LITERAL, STOCK_OUTPUT, STUB_ADDR))
    for name, addr, data in blobs:
        print("  %-10s @0x%05X : %d bytes" % (name, addr, len(data)))
    print("  RPM breaks : %s" % RPM_BREAKS)
    print("  duty %%     : %s" % DUTY_PCT)
    print("\nFlash via EcuFlash/RomRaider (recomputes subarudbw checksum on save).")

if __name__ == "__main__":
    main()
