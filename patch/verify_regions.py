#!/usr/bin/env python3
"""Verify the boost patch's free-flash and scratch-RAM assumptions against the stock ROM.

- Finds ALL *direct* RAM references (mov.w / mov.l PC-relative literals) — catches literal
  accesses but NOT computed base+index accesses (e.g. struct arrays).
- Adds KNOWN computed-access regions by hand (the cam solenoid struct array) and the
  state+stack region, so the "free RAM" answer is conservative.
- Checks the free-flash window for any inbound pointer / non-0xFF data.

Usage:  python3 verify_regions.py [stock.bin]
"""
import struct, sys, os

HERE  = os.path.dirname(os.path.abspath(__file__))
BIN   = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "2005 BLE MT.bin")
rom   = open(BIN, "rb").read()
N     = len(rom)

# ---- 1. direct RAM references via PC-relative loads ----
ram_refs = {}   # addr -> count
def add(a): ram_refs[a] = ram_refs.get(a, 0) + 1

for o in range(0, N-1, 2):
    w = struct.unpack_from(">H", rom, o)[0]
    hi = w >> 12
    if hi == 0x9:      # mov.w @(disp,pc),Rn  -> 16-bit literal (sign-extended)
        tgt = o + 4 + (w & 0xFF)*2
        if tgt+2 <= N:
            v = struct.unpack_from(">H", rom, tgt)[0]
            if v >= 0x8000:
                a = 0xFFFF0000 | v
                if 0xFFFF0000 <= a <= 0xFFFFDFFF: add(a)
    elif hi == 0xD:    # mov.l @(disp,pc),Rn  -> 32-bit literal
        tgt = (o & ~3) + 4 + (w & 0xFF)*4
        if tgt+4 <= N:
            v = struct.unpack_from(">I", rom, tgt)[0]
            if 0xFFFF0000 <= v <= 0xFFFFDFFF: add(v)

def near(addr, lo=0x40, hi=0x40):
    """direct refs within [addr-lo, addr+hi]"""
    return sorted(a for a in ram_refs if addr-lo <= a <= addr+hi)

# ---- 2. known COMPUTED-access regions (not visible as per-field literals) ----
SOL_BASE, SOL_STRIDE, SOL_N = 0xFFFFBFB8, 0x28, 6
SOL_END = SOL_BASE + SOL_STRIDE*SOL_N            # exclusive
computed = [("cam solenoid struct array", SOL_BASE, SOL_END),
            ("state + stack (>=0xC000)",  0xFFFFC000, 0xFFFFE000)]

def in_computed(a):
    return [n for (n, lo, hi) in computed if lo <= a < hi]

print("=== RAM scratch check ===")
print("total distinct direct RAM refs: %d" % len(ram_refs))
print("cam solenoid struct array: 0x%08X .. 0x%08X (base ref'd %d times as 0x%X)"
      % (SOL_BASE, SOL_END-1, ram_refs.get(SOL_BASE,0), SOL_BASE & 0xFFFF))
for a in (0xFFFFBFF0, 0xFFFFBFF8):
    print("  candidate 0x%08X: direct-refs=%d  computed-region=%s  nearest-direct=%s"
          % (a, ram_refs.get(a,0), in_computed(a) or "none",
             [hex(x) for x in near(a)] or "none within 0x40"))

# ---- 3. recommend genuinely free RAM: a wide quiet gap below the solenoid array ----
print("\n=== searching for a clean 8-byte scratch region (below 0x%X) ===" % SOL_BASE)
refs = sorted(a for a in ram_refs if 0xFFFF1000 <= a < SOL_BASE)
best = None
for i in range(len(refs)-1):
    gap = refs[i+1] - refs[i]
    if gap >= 0x80:                       # >=128 bytes clear
        mid = (refs[i] + refs[i+1]) // 2 & ~7
        best = (refs[i], refs[i+1], gap, mid)
# show a few large gaps
gaps = sorted(((refs[i+1]-refs[i], refs[i], refs[i+1]) for i in range(len(refs)-1)), reverse=True)[:6]
for g, lo, hi in gaps:
    print("  gap 0x%03X bytes: 0x%08X .. 0x%08X  (midpoint 0x%08X)" % (g, lo, hi, (lo+hi)//2 & ~7))

# ---- 4. free-flash window check ----
print("\n=== free-flash check (0x7D790 window) ===")
FS, FE = 0x7D790, 0x7FAF7
# last non-0xFF before FS
last = FS-1
while last > 0 and rom[last] == 0xFF: last -= 1
print("last non-0xFF byte before 0x%05X is at 0x%05X (%d bytes of 0xFF lead-in)" % (FS, last, FS-1-last))
# inbound 32-bit pointers into the free window (stock)
ptrs = []
for o in range(0, N-3):
    v = struct.unpack_from(">I", rom, o)[0]
    if FS <= v <= FE: ptrs.append((o, v))
print("32-bit values in the ROM pointing INTO 0x%05X..0x%05X : %d" % (FS, FE, len(ptrs)))
for o, v in ptrs[:8]:
    print("   at file 0x%05X -> 0x%05X" % (o, v))
# contiguous 0xFF run from FS
run = 0
while FS+run < N and rom[FS+run] == 0xFF: run += 1
print("contiguous 0xFF from 0x%05X: %d bytes (ends 0x%05X)" % (FS, run, FS+run-1))
