// Report code sites containing constants used by Subaru's four-state fuel-pump
// command (0, 0x55, 0xAA, 0xFF) and the standard SSM parameter number 0x3B.
// This script is read-only and is intended to narrow the live D2WD610H audit.
// @category D2WD610H

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;

public class ReportFuelPumpCandidates extends GhidraScript {
    private boolean interesting(long value) {
        long byteValue = value & 0xff;
        return byteValue == 0x3b || byteValue == 0x55 || byteValue == 0xaa;
    }

    @Override
    public void run() throws Exception {
        FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
        while (functions.hasNext() && !monitor.isCancelled()) {
            Function function = functions.next();
            InstructionIterator instructions = currentProgram.getListing().getInstructions(
                function.getBody(), true
            );
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                if (!instruction.getMnemonicString().toLowerCase().startsWith("mov")) {
                    continue;
                }
                boolean matched = false;
                for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                    for (Object object : instruction.getOpObjects(operand)) {
                        if (object instanceof Scalar && interesting(((Scalar)object).getValue())) {
                            matched = true;
                        }
                    }
                }
                if (matched) {
                    println(
                        function.getEntryPoint() + " " + function.getName() + " | " +
                        instruction.getAddress() + " | " + instruction
                    );
                }
            }
        }
    }
}
