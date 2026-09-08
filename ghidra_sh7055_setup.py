# Ghidra setup for Subaru EZ30R D2WD610H (SH7055SF, 512 KiB, big-endian SH-2E)
# PyGhidra version — run from Script Manager (or `pyghidra` CLI) on Ghidra 11.3+/12.x
# ECU ID 3C5A387116  |  reset PC 0x000009E0  SP 0xFFFFDFA0
#
# Import the RAW 512KB image as SuperH4:BE:32:default, base 0x0, THEN run this,
# THEN Analysis > Auto Analyze.
#
# @category Subaru.EZ30R
# @runtime PyGhidra

from ghidra.program.model.symbol import SourceType

# --- PyGhidra: pull script state explicitly instead of relying on injected globals ---
# When run from the Script Manager these are provided; this makes the intent explicit
# and keeps the script portable if run headless via pyghidra.
try:
    currentProgram  # noqa: F821  (provided by Script Manager)
except NameError:
    import pyghidra
    raise RuntimeError("Run this from Ghidra's Script Manager with a program open.")

prog       = currentProgram          # noqa: F821
flat       = None
try:
    from ghidra.app.flatapi import FlatProgramAPI
    flat = FlatProgramAPI(prog)
except Exception:
    pass

FLASH_END = 0x0007FFFF
# Renesas SH-2E SH7055S Hardware Manual, section 23.1: 32 KiB.
# SuperH4 is an analysis-language approximation, not the processor identity.
RAM_START = 0xFFFF6000
RAM_END   = 0xFFFFDFFF
IO_START  = 0xFFFFE400
IO_END    = 0xFFFFFFFF
RESET_PC  = 0x000009E0
INIT_SP   = 0xFFFFDFA0

def space():
    return prog.getAddressFactory().getDefaultAddressSpace()

def addr(x):
    return space().getAddress(x)

def make_uninit(name, start, end, volatile=False):
    mem = prog.getMemory()
    overlapping = [block for block in mem.getBlocks()
                   if block.getStart().compareTo(addr(end)) <= 0
                   and block.getEnd().compareTo(addr(start)) >= 0]
    if overlapping:
        if (len(overlapping) == 1 and overlapping[0].getStart() == addr(start)
                and overlapping[0].getEnd() == addr(end)):
            print("exact block 0x%X-0x%X exists, preserving %s" % (start, end, name))
            return
        # Do not silently accept the old FFFF0000-FFFFBFFF block, or delete
        # it and lose the user's analysis. Existing projects need a deliberate
        # memory-block migration; the current MCP server cannot perform one.
        raise RuntimeError(
            "Incorrect/overlapping %s geometry; expected 0x%X-0x%X. "
            "Existing analysis was preserved. See docs/reference/GHIDRA.md."
            % (name, start, end))
    blk = mem.createUninitializedBlock(name, addr(start), end - start + 1, False)
    blk.setRead(True); blk.setWrite(True); blk.setExecute(False); blk.setVolatile(volatile)
    print("created %-4s 0x%X-0x%X" % (name, start, end))

def label(a, name):
    prog.getSymbolTable().createLabel(addr(a), name, SourceType.USER_DEFINED)
    print("label %-18s @ 0x%X" % (name, a))

def run():
    # 1) RAM + peripheral blocks (IO marked volatile)
    make_uninit("RAM", RAM_START, RAM_END, volatile=False)
    make_uninit("IO",  IO_START,  IO_END,  volatile=True)

    # 2) reset entry + initial SP, then disassemble the entry
    label(RESET_PC, "reset_entry")
    label(INIT_SP,  "initial_SP")
    if flat is not None:
        flat.disassemble(addr(RESET_PC))
        print("disassembled reset_entry @ 0x%X" % RESET_PC)

    # 3) CALID / ECU-ID / free-space markers
    label(0x0007BDDD, "CALID_D2WD610H")
    label(0x0007BDA8, "ECUID_3C5A387116")
    label(0x00002000, "internalid_D2WD610H")
    label(0x0007D790, "STOCK_ERASED_PATCH_WINDOW_START")

    print("SH7055 setup complete. Now run Analysis > Auto Analyze.")

run()
