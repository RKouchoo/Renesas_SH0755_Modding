// Print every Ghidra reference to an address and its containing function.
// Usage: -postScript ReportReferences.java 00006892
// @category D2WD610H

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ReportReferences extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("expected one target address");
        }
        Address target = toAddr(args[0]);
        ReferenceIterator references = currentProgram.getReferenceManager().getReferencesTo(target);
        while (references.hasNext()) {
            Reference reference = references.next();
            Function owner = getFunctionContaining(reference.getFromAddress());
            println(
                reference.getFromAddress() + " | " + reference.getReferenceType() +
                " | " + (owner == null ? "<no function>" :
                    owner.getEntryPoint() + " " + owner.getName())
            );
        }
    }
}
