#!/usr/bin/env python3
"""Minimal SH-2E (SH7055) big-endian disassembler for D2WD610H patch work.

Covers the instruction subset seen in this ROM. Flash base = file offset 0.
Not exhaustive; unknown opcodes render as `.word 0xXXXX`. Enough to read control
flow, literal-pool loads, and FP ops around the patch sites.

Usage:  python3 sh2_disasm.py <bin> <start_hex> <end_hex>
"""
import struct, sys

def load(path):
    with open(path, "rb") as f:
        return f.read()

def s8(v):  return v - 256 if v >= 128 else v
def s12(v): return v - 0x1000 if v >= 0x800 else v

def dis_one(rom, o):
    """Return (text, is_pcrel_target_or_None)."""
    w = struct.unpack_from(">H", rom, o)[0]
    n = (w >> 8) & 0xF; m = (w >> 4) & 0xF; d = w & 0xF; d8 = w & 0xFF; hi = w >> 12; lo = w & 0xF
    if w == 0x0009: return "nop", None
    if w == 0x000b: return "rts", None
    if w == 0x0028: return "clrmac", None
    if w == 0x0019: return "div0u", None
    if hi == 0x6:
        t = {0x0:"mov.b @r%d,r%d",0x1:"mov.w @r%d,r%d",0x2:"mov.l @r%d,r%d",0x3:"mov r%d,r%d",
             0x4:"mov.b @r%d+,r%d",0x5:"mov.w @r%d+,r%d",0x6:"mov.l @r%d+,r%d",0x7:"not r%d,r%d",
             0x8:"swap.b r%d,r%d",0x9:"swap.w r%d,r%d",0xa:"negc r%d,r%d",0xb:"neg r%d,r%d",
             0xc:"extu.b r%d,r%d",0xd:"extu.w r%d,r%d",0xe:"exts.b r%d,r%d",0xf:"exts.w r%d,r%d"}
        return (t[lo] % (m, n)) if lo in t else (".word 0x%04x" % w), None
    if hi == 0xe: return "mov #%d,r%d" % (s8(d8), n), None
    if hi == 0x9:  # mov.w @(disp,pc),Rn
        tgt = o + 4 + (d8 * 2); val = struct.unpack_from(">H", rom, tgt)[0]
        return "mov.w @(pc,0x%x=%#x),r%d  ; =0x%04x" % (d8*2, tgt, n, val), None
    if hi == 0xd:  # mov.l @(disp,pc),Rn
        tgt = (o & ~3) + 4 + (d8 * 4); val = struct.unpack_from(">I", rom, tgt)[0]
        return "mov.l @(pc,0x%x=%#x),r%d  ; =0x%08x" % (d8*4, tgt, n, val), val
    if hi == 0xa: t = o + 4 + s12(w & 0xFFF)*2; return "bra 0x%06x" % t, None
    if hi == 0xb: t = o + 4 + s12(w & 0xFFF)*2; return "bsr 0x%06x" % t, None
    if hi == 0x8:
        b = (w >> 8) & 0xF
        if b == 0x0: return "mov.b r0,@(0x%x,r%d)" % (d, m), None
        if b == 0x1: return "mov.w r0,@(0x%x,r%d)" % (d*2, m), None
        if b == 0x4: return "mov.b @(0x%x,r%d),r0" % (d, m), None
        if b == 0x5: return "mov.w @(0x%x,r%d),r0" % (d*2, m), None
        if b == 0x8: return "cmp/eq #%d,r0" % s8(d8), None
        if b == 0x9: return "bt 0x%06x" % (o + 4 + s8(d8)*2), None
        if b == 0xb: return "bf 0x%06x" % (o + 4 + s8(d8)*2), None
        if b == 0xd: return "bt/s 0x%06x" % (o + 4 + s8(d8)*2), None
        if b == 0xf: return "bf/s 0x%06x" % (o + 4 + s8(d8)*2), None
    if hi == 0x4:
        b = w & 0xFF
        t = {0x0b:"jsr @r%d",0x2b:"jmp @r%d",0x0e:"ldc r%d,sr",0x1e:"ldc r%d,gbr",0x2e:"ldc r%d,vbr",
             0x0a:"lds r%d,mach",0x1a:"lds r%d,macl",0x2a:"lds r%d,pr",0x22:"sts.l pr,@-r%d",
             0x26:"lds.l @r%d+,pr",0x00:"shll r%d",0x01:"shlr r%d",0x08:"shll2 r%d",0x09:"shlr2 r%d",
             0x18:"shll8 r%d",0x19:"shlr8 r%d",0x28:"shll16 r%d",0x29:"shlr16 r%d",0x20:"shal r%d",
             0x21:"shar r%d",0x24:"rotcl r%d",0x25:"rotcr r%d",0x04:"rotl r%d",0x05:"rotr r%d",
             0x10:"dt r%d",0x11:"cmp/pz r%d",0x15:"cmp/pl r%d",0x2d:"lds r%d,fpul",0x5a:"lds r%d,fpscr",
             0x0f:"mac.w @r%d+,@r%d+",0x06:"lds.l @r%d+,mach",0x56:"lds.l @r%d+,fpul"}
        if b in t: return (t[b] % n), None
        return ".word 0x%04x" % w, None
    if hi == 0x2:
        t = {0x0:"mov.b r%d,@r%d",0x1:"mov.w r%d,@r%d",0x2:"mov.l r%d,@r%d",0x4:"mov.b r%d,@-r%d",
             0x5:"mov.w r%d,@-r%d",0x6:"mov.l r%d,@-r%d",0x7:"div0s r%d,r%d",0x8:"tst r%d,r%d",
             0x9:"and r%d,r%d",0xa:"xor r%d,r%d",0xb:"or r%d,r%d",0xc:"cmp/str r%d,r%d",
             0xd:"xtrct r%d,r%d",0xe:"mulu.w r%d,r%d",0xf:"muls.w r%d,r%d"}
        return (t.get(lo, ".word 0x%04x") % ((m, n) if lo in t else ())), None
    if hi == 0x3:
        t = {0x0:"cmp/eq r%d,r%d",0x2:"cmp/hs r%d,r%d",0x3:"cmp/ge r%d,r%d",0x4:"div1 r%d,r%d",
             0x5:"dmulu.l r%d,r%d",0x6:"cmp/hi r%d,r%d",0x7:"cmp/gt r%d,r%d",0x8:"sub r%d,r%d",
             0xa:"subc r%d,r%d",0xb:"subv r%d,r%d",0xc:"add r%d,r%d",0xd:"dmuls.l r%d,r%d",
             0xe:"addc r%d,r%d",0xf:"addv r%d,r%d"}
        return (t.get(lo, ".word 0x%04x") % ((m, n) if lo in t else ())), None
    if hi == 0x7: return "add #%d,r%d" % (s8(d8), n), None
    if hi == 0x5: return "mov.l @(0x%x,r%d),r%d" % (d*4, m, n), None
    if hi == 0x1: return "mov.l r%d,@(0x%x,r%d)" % (m, d*4, n), None
    if hi == 0xc:
        b = (w >> 8) & 0xF
        t = {0x8:"tst #%d,r0",0x9:"and #%d,r0",0xa:"xor #%d,r0",0xb:"or #%d,r0",
             0x0:"mov.b r0,@(0x%x,gbr)",0x4:"mov.b @(0x%x,gbr),r0",0x7:"mova @(pc,0x%x),r0"}
        if b in (0x8,0x9,0xa,0xb): return t[b] % d8, None
        if b == 0x7: return "mova @(pc,0x%x=%#x),r0" % (d8*4, (o&~3)+4+d8*4), None
        return ".word 0x%04x" % w, None
    if hi == 0xf:
        t = {0x0:"fadd fr%d,fr%d",0x1:"fsub fr%d,fr%d",0x2:"fmul fr%d,fr%d",0x3:"fdiv fr%d,fr%d",
             0x4:"fcmp/eq fr%d,fr%d",0x5:"fcmp/gt fr%d,fr%d",0x6:"fmov.s @(r0,r%d),fr%d",
             0x7:"fmov.s fr%d,@(r0,r%d)",0x8:"fmov.s @r%d,fr%d",0x9:"fmov.s @r%d+,fr%d",
             0xa:"fmov.s fr%d,@r%d",0xb:"fmov.s fr%d,@-r%d",0xc:"fmov fr%d,fr%d",0xe:"fmac fr0,fr%d,fr%d"}
        if lo == 0xd:  # single-operand FP by n-field
            sub = (w >> 4) & 0xF
            st = {0x0:"fsts fpul,fr%d",0x1:"flds fr%d,fpul",0x2:"float fpul,fr%d",0x3:"ftrc fr%d,fpul",
                  0x4:"fneg fr%d",0x5:"fabs fr%d",0x6:"fsqrt fr%d",0x8:"fldi0 fr%d",0x9:"fldi1 fr%d",
                  0xa:"fcnvsd",0xb:"fcnvds"}
            return (st.get(sub, ".word 0x%04x") % (n if sub in st else ())), None
        return (t.get(lo, ".word 0x%04x") % ((m, n) if lo in t else ())), None
    return ".word 0x%04x" % w, None

def disasm(rom, start, end):
    o = start
    while o < end:
        txt, _ = dis_one(rom, o)
        print("%06x: %04x  %s" % (o, struct.unpack_from(">H", rom, o)[0], txt))
        o += 2

if __name__ == "__main__":
    rom = load(sys.argv[1])
    disasm(rom, int(sys.argv[2], 16), int(sys.argv[3], 16))
