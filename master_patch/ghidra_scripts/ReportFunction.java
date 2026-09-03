// Print instructions and decompiler output for one function name or address.
// Usage: -postScript ReportFunction.java fuel_pump_duty_logger_value_get
// @category D2WD610H

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

public class ReportFunction extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("expected one function name or address");
        }
        Function function = getGlobalFunctions(args[0]).stream().findFirst().orElse(null);
        if (function == null) {
            Address address = toAddr(args[0]);
            function = getFunctionAt(address);
        }
        if (function == null) {
            throw new IllegalArgumentException("function not found: " + args[0]);
        }

        println("FUNCTION " + function.getEntryPoint() + " " + function.getName());
        InstructionIterator instructions = currentProgram.getListing().getInstructions(
            function.getBody(), true
        );
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            println(instruction.getAddress() + " | " + instruction);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
        if (!result.decompileCompleted()) {
            throw new IllegalStateException(result.getErrorMessage());
        }
        println(result.getDecompiledFunction().getC());
        decompiler.dispose();
    }
}
