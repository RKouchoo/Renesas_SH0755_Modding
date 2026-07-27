// Read-only report for D2WD610H MAF diagnostic references.
// @category D2WD610H

import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.symbol.Reference;

public class ReportMafDiagnostics extends GhidraScript {
    private void report(String addressText) {
        Address address = toAddr(addressText);
        println("References to " + addressText + ":");
        for (Reference reference : getReferencesTo(address)) {
            Address from = reference.getFromAddress();
            Function function = getFunctionContaining(from);
            println(
                "  " + from + " " + reference.getReferenceType() + " in " +
                (function == null ? "<no function>" : function.getName() + " @" + function.getEntryPoint())
            );
        }
    }

    private void dump(String addressText) {
        Function function = getFunctionAt(toAddr(addressText));
        if (function == null) {
            println("No function at " + addressText);
            return;
        }
        println("Instructions for " + function.getName() + " @" + function.getEntryPoint() + ":");
        InstructionIterator instructions =
            currentProgram.getListing().getInstructions(function.getBody(), true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            println("  " + instruction.getAddress() + "  " + instruction);
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
                        "  " + instruction.getAddress() + " -> " + reference.getToAddress() +
                        " " + reference.getReferenceType()
                    );
                }
            }
        }
    }

    private void decompile(String addressText) {
        Function function = getFunctionAt(toAddr(addressText));
        if (function == null) {
            println("No function at " + addressText);
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

    @Override
    public void run() {
        report("00007c30");
        report("00007c52");
        report("00017726");
        report("000177be");
        report("00061328");
        report("0007266c");
        report("ffffab06");
        report("ffffabe4");
        report("ffffb414");
        report("ffffb418");
        report("ffffb41c");
        report("ffffb420");
        report("ffffb424");
        report("ffffb428");
        report("ffffb42c");
        report("ffffb430");
        report("ffffb434");
        report("ffffb438");
        report("ffffb43c");
        report("ffffb440");
        report("ffffb444");
        report("ffffb448");
        report("ffffb44c");
        report("ffffb450");
        report("ffffb458");
        report("ffffb45c");
        dump("00007c52");
        dump("00017726");
        dump("000177be");
        dump("00061328");
        dump("00061332");
        dump("000613ac");
        dump("0007266c");
        dump("000115ea");
        dump("000107ee");
        reportWrites("000172a4");
        reportWrites("00017726");
        reportWrites("000177be");
        decompile("000172a4");
        decompile("00017726");
        decompile("000177be");
        String[] auxiliaryConsumers = {
            "00012f10", "000135c4", "0001496c", "000177dc", "0001af80",
            "0001e0c8", "0001e5e8", "0001e7e8", "0002046c", "000217b8",
            "00021c50", "0002212c", "00022454", "00023238", "00024cb0",
            "000289e0", "00029024", "0002fb50", "0002ffa8", "000353b0",
            "0003da30", "0003da60", "0003daa6", "0003def0", "0003e1c8",
            "0003e20e", "0003e7dc", "0003ea94", "0003eace", "0003eb68",
            "0003ebdc", "00046d74", "000498b0", "0004f1fa", "000666ec",
            "000672e4", "000673c6", "0006bba2", "0006bfdc"
        };
        for (String address : auxiliaryConsumers) {
            decompile(address);
        }
    }
}
