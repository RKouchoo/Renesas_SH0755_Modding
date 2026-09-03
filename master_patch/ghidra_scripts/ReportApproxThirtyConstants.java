// Report code references to ROM constants near 30 in common scalar encodings.
// This is a candidate finder: every hit still requires decompiler/context review.
// Usage: -postScript ReportApproxThirtyConstants.java
// @category D2WD610H

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

import java.util.HashSet;
import java.util.Set;

public class ReportApproxThirtyConstants extends GhidraScript {
    private final Set<String> emitted = new HashSet<>();

    private void report(Address valueAddress, String encoding, String value) {
        ReferenceIterator references =
            currentProgram.getReferenceManager().getReferencesTo(valueAddress);
        while (references.hasNext()) {
            Reference reference = references.next();
            Address from = reference.getFromAddress();
            Function owner = getFunctionContaining(from);
            if (owner == null) {
                continue;
            }
            String line = valueAddress + " | " + encoding + "=" + value + " | "
                    + from + " | " + reference.getReferenceType() + " | "
                    + owner.getName() + "@" + owner.getEntryPoint();
            if (emitted.add(line)) {
                println(line);
            }
        }
    }

    @Override
    public void run() throws Exception {
        Memory memory = currentProgram.getMemory();
        for (long offset = 0; offset < 0x80000; offset++) {
            Address address = toAddr(offset);
            if (!memory.contains(address)) {
                continue;
            }

            int u8 = memory.getByte(address) & 0xff;
            if (u8 >= 29 && u8 <= 32) {
                report(address, "u8", Integer.toString(u8));
            }

            if (offset <= 0x7fffe) {
                int u16 = memory.getShort(address) & 0xffff;
                if (u16 >= 29 && u16 <= 32) {
                    report(address, "u16be", Integer.toString(u16));
                }
            }

            if (offset <= 0x7fffc) {
                long u32 = memory.getInt(address) & 0xffffffffL;
                if (u32 >= 29 && u32 <= 32) {
                    report(address, "u32be", Long.toString(u32));
                }
                float f32 = Float.intBitsToFloat((int)u32);
                if (f32 == 29.0f || f32 == 30.0f ||
                    f32 == 31.0f || f32 == 32.0f) {
                    report(address, "f32be", Float.toString(f32));
                }
            }
        }
    }
}
