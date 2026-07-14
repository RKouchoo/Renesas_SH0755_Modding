#!/usr/bin/env python3
"""Minimal two-pass SH-2E (SH7055) big-endian assembler for D2WD610H patch stubs.

Supports the instruction subset the boost stubs need, plus labels (for branches) and
an auto-placed, deduped 32-bit literal pool (for mov.l @(disp,pc),Rn loads).

Delay slots are NOT auto-filled: jsr/jmp/bra are delayed — put the delay-slot instruction
(usually nop()) immediately after. bt/bf are NON-delayed (no delay slot).

Encodings verified against this ROM's own code and patch/sh2_disasm.py.
"""
import struct

class Asm:
    def __init__(self, base):
        self.base = base
        self.items = []          # ('w',word) | ('pool',reg,val) | ('br',kind,label) | ('label',name)
        self.labels = {}

    # --- structural ---
    def label(self, name): self.items.append(('label', name)); return self
    def _w(self, word):    self.items.append(('w', word & 0xFFFF)); return self

    # --- moves / loads ---
    def movl_pool(self, rn, val): self.items.append(('pool', rn, val & 0xFFFFFFFF)); return self  # mov.l @(disp,pc),Rn
    def mov_reg(self, rm, rn):    return self._w(0x6003 | rn<<8 | rm<<4)   # mov Rm,Rn
    def movl_at(self, rn, rm):    return self._w(0x6002 | rn<<8 | rm<<4)   # mov.l @Rm,Rn
    def movl_store(self, rm, rn): return self._w(0x2002 | rn<<8 | rm<<4)   # mov.l Rm,@Rn
    def movb_at(self, rn, rm):    return self._w(0x6000 | rn<<8 | rm<<4)   # mov.b @Rm,Rn (sign-ext)
    def movb_store(self, rm, rn): return self._w(0x2000 | rn<<8 | rm<<4)   # mov.b Rm,@Rn (low byte)
    def or_imm(self, imm):        return self._w(0xCB00 | (imm & 0xFF))    # or #imm,r0
    def cmp_eq(self, rm, rn):     return self._w(0x3000 | rn<<8 | rm<<4)   # cmp/eq Rm,Rn (T=Rn==Rm)

    # --- FP moves ---
    def fmov_load(self, frn, rn):  return self._w(0xF008 | frn<<8 | rn<<4) # fmov.s @Rn,FRn
    def fmov_store(self, frm, rn): return self._w(0xF00A | rn<<8 | frm<<4) # fmov.s FRm,@Rn
    def fpush(self, frm):          return self._w(0xF00B | 15<<8 | frm<<4) # fmov.s FRm,@-r15
    def fpop(self, frn):           return self._w(0xF009 | frn<<8 | 15<<4) # fmov.s @r15+,FRn
    def fmov(self, frm, frn):      return self._w(0xF00C | frn<<8 | frm<<4)# fmov FRm,FRn
    def fldi0(self, frn):          return self._w(0xF08D | frn<<8)         # fldi0 FRn
    def fneg(self, frn):           return self._w(0xF04D | frn<<8)         # fneg FRn

    # --- FP arith / compare (T = FRn > FRm for fcmpgt) ---
    def fadd(self, frm, frn):  return self._w(0xF000 | frn<<8 | frm<<4)
    def fsub(self, frm, frn):  return self._w(0xF001 | frn<<8 | frm<<4)
    def fmul(self, frm, frn):  return self._w(0xF002 | frn<<8 | frm<<4)
    def fdiv(self, frm, frn):  return self._w(0xF003 | frn<<8 | frm<<4)
    def fcmpgt(self, frm, frn):return self._w(0xF005 | frn<<8 | frm<<4)    # T = FRn > FRm

    # --- control flow ---
    def stsl_pr(self):  return self._w(0x4F22)   # sts.l pr,@-r15
    def ldsl_pr(self):  return self._w(0x4F26)   # lds.l @r15+,pr
    def jsr(self, rn):  return self._w(0x400B | rn<<8)   # jsr @Rn   (delayed)
    def jmp(self, rn):  return self._w(0x402B | rn<<8)   # jmp @Rn   (delayed)
    def rts(self):      return self._w(0x000B)           # rts       (delayed)
    def nop(self):      return self._w(0x0009)
    def bt(self, label):  self.items.append(('br','bt',label));  return self   # non-delayed
    def bf(self, label):  self.items.append(('br','bf',label));  return self   # non-delayed
    def bra(self, label): self.items.append(('br','bra',label)); return self   # delayed

    # --- assemble ---
    def assemble(self):
        # pass 1: assign addresses to instrs + labels
        addr = self.base
        for it in self.items:
            if it[0] == 'label': self.labels[it[1]] = addr
            else: addr += 2
        code_end = addr
        pool_start = (code_end + 3) & ~3
        # assign deduped pool slots (insertion order)
        slot = {}
        pa = pool_start
        for it in self.items:
            if it[0] == 'pool' and it[2] not in slot:
                slot[it[2]] = pa; pa += 4
        # pass 2: emit
        out = bytearray(); addr = self.base
        for it in self.items:
            if it[0] == 'label': continue
            if it[0] == 'w':
                out += struct.pack('>H', it[1]); addr += 2
            elif it[0] == 'pool':
                _, rn, val = it
                disp = (slot[val] - ((addr & ~3) + 4)) // 4
                assert 0 <= disp <= 255, "pool disp out of range at 0x%X" % addr
                out += struct.pack('>H', 0xD000 | rn<<8 | disp); addr += 2
            elif it[0] == 'br':
                _, kind, lab = it
                t = self.labels[lab]
                if kind in ('bt','bf'):
                    d = (t - (addr+4)) // 2
                    assert -128 <= d <= 127, "%s disp out of range" % kind
                    op = {'bt':0x8900,'bf':0x8B00}[kind]
                    out += struct.pack('>H', op | (d & 0xFF))
                else:  # bra
                    d = (t - (addr+4)) // 2
                    assert -2048 <= d <= 2047
                    out += struct.pack('>H', 0xA000 | (d & 0xFFF))
                addr += 2
        # pad to pool alignment, then emit pool
        while (self.base + len(out)) < pool_start:
            out += struct.pack('>H', 0x0009)
        for val in slot:
            out += struct.pack('>I', val)
        return bytes(out)


def _selftest_phase1():
    """Reproduce the verified Phase-1 stub byte-for-byte to validate the assembler."""
    RPM, DESC, INTERP, OUTPUT = 0xFFFFB544, 0x0007D790, 0x0000209C, 0x0000E8C4
    a = Asm(0x7D7CC)
    a.stsl_pr()
    a.movl_pool(1, RPM);   a.fmov_load(4, 1)
    a.movl_pool(4, DESC)
    a.movl_pool(2, INTERP); a.jsr(2); a.nop()
    a.fmov(0, 4)
    a.ldsl_pr()
    a.movl_pool(2, OUTPUT); a.jmp(2); a.nop()
    got = a.assemble()
    want = bytes.fromhex("4f22d105f418d405d205420b0009f40c4f26d204422b0009"
                         "ffffb5440007d7900000209c0000e8c4")
    assert got == want, "SELFTEST FAIL:\n got=%s\nwant=%s" % (got.hex(), want.hex())
    print("sh2_asm selftest OK (reproduces verified Phase-1 stub, %d bytes)" % len(got))

if __name__ == "__main__":
    _selftest_phase1()
