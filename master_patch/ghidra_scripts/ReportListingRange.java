// Print instructions and function ownership across an address range.
// Usage: -postScript ReportListingRange.java 00006840 000068c0
// @category D2WD610H

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

public class ReportListingRange extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: ReportListingRange.java START END");
        }

        Address start = toAddr(args[0]);
        Address end = toAddr(args[1]);
        AddressSet range = new AddressSet(start, end);
        InstructionIterator instructions = currentProgram.getListing().getInstructions(range, true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            Function owner = getFunctionContaining(instruction.getAddress());
            println(instruction.getAddress() + " | " + instruction + " | "
                    + (owner == null ? "<no function>" : owner.getName()));
        }
    }
}
