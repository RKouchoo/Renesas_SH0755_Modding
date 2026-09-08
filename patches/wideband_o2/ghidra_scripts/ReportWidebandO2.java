// Read-only report for the D2WD610H single-external-wideband O2 substitution trace.
// @category D2WD610H

import java.util.LinkedHashSet;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.symbol.Reference;

public class ReportWidebandO2 extends GhidraScript {
    private final Set<Address> consumerEntries = new LinkedHashSet<>();

    private void reportReferences(String addressText) {
        Address address = toAddr(addressText);
        println("References to " + address + ":");
        for (Reference reference : getReferencesTo(address)) {
            Address from = reference.getFromAddress();
            Function function = getFunctionContaining(from);
            if (function != null) {
                consumerEntries.add(function.getEntryPoint());
            }
            println(
                "  " + from + " " + reference.getReferenceType() + " in " +
                (function == null
                    ? "<no function>"
                    : function.getName() + " @" + function.getEntryPoint())
            );
        }
    }

    private void reportWrites(String addressText) {
        Function function = getFunctionAt(toAddr(addressText));
        if (function == null) {
            println("No function at " + addressText);
            return;
        }
        println("Direct writes from " + function.getName() + " @" + function.getEntryPoint() + ":");
        InstructionIterator instructions =
            currentProgram.getListing().getInstructions(function.getBody(), true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            for (Reference reference : instruction.getReferencesFrom()) {
                if (reference.getReferenceType().isWrite()) {
                    println(
                        "  " + instruction.getAddress() + " -> " +
                        reference.getToAddress() + " " + reference.getReferenceType()
                    );
                }
            }
        }
    }

    private void decompile(Address entry) {
        Function function = getFunctionAt(entry);
        if (function == null) {
            println("No function at " + entry);
            return;
        }
        DecompInterface decompiler = new DecompInterface();
        try {
            decompiler.openProgram(currentProgram);
            DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
            println("Decompile for " + function.getName() + " @" + function.getEntryPoint() + ":");
            if (result.decompileCompleted()) {
                println(result.getDecompiledFunction().getC());
            }
            else {
                println("  FAILED: " + result.getErrorMessage());
            }
        }
        finally {
            decompiler.dispose();
        }
    }

    private void decompile(String addressText) {
        decompile(toAddr(addressText));
    }

    @Override
    public void run() {
        String[] channels = {
            "ffffab06",
            "ffffab18", "ffffab00",
            "ffffae60", "ffffae64",
            "ffffae68", "ffffae6c",
            "ffffae70", "ffffae74",
            "ffffb4e8", "ffffb4ec",
            "ffffd268", "ffffd26c"
        };
        for (String channel : channels) {
            reportReferences(channel);
        }

        String[] keyFunctions = {
            "0000b690",
            "0000b8cc",
            "00018dac",
            "0001917a",
            "00064fd0",
            "0006500c",
            "00031790"
        };
        for (String address : keyFunctions) {
            reportWrites(address);
            decompile(address);
        }

        println("Decompiler pass over all direct channel consumers:");
        for (Address entry : consumerEntries) {
            decompile(entry);
        }
    }
}
