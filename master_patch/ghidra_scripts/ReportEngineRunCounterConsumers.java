// Find D2WD functions that read the engine-run counter at 0xFFFFB688 and
// report ROM u16 values in the roughly 20-50 second range that are loaded by
// those functions. These are candidates only: a function can load unrelated
// calibrations, so confirm data flow from the counter to the comparison before
// treating any emitted value as a timer threshold.
// Usage: -postScript ReportEngineRunCounterConsumers.java
// @category D2WD610H

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

import java.util.LinkedHashSet;
import java.util.Set;

public class ReportEngineRunCounterConsumers extends GhidraScript {
    @Override
    public void run() throws Exception {
        println(
            "Candidate constants only; manually verify that each comparison " +
            "actually consumes 0xFFFFB688."
        );
        Memory memory = currentProgram.getMemory();
        Set<Function> consumers = new LinkedHashSet<>();
        ReferenceIterator counterReferences = currentProgram.getReferenceManager()
            .getReferencesTo(toAddr("ffffb688"));
        while (counterReferences.hasNext()) {
            Function function = getFunctionContaining(
                counterReferences.next().getFromAddress());
            if (function != null) {
                consumers.add(function);
            }
        }

        Set<String> emitted = new LinkedHashSet<>();
        for (Function function : consumers) {
            InstructionIterator instructions = currentProgram.getListing()
                .getInstructions(function.getBody(), true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                for (Reference reference : instruction.getReferencesFrom()) {
                    Address pool = reference.getToAddress();
                    long poolOffset = pool.getOffset();
                    if (poolOffset < 0 || poolOffset > 0x7fffc ||
                        !memory.contains(pool)) {
                        continue;
                    }
                    long pointer = memory.getInt(pool) & 0xffffffffL;
                    if (pointer < 0x50000 || pointer > 0x7fffe) {
                        continue;
                    }
                    Address calibration = toAddr(pointer);
                    int raw = memory.getShort(calibration) & 0xffff;
                    if (raw < 2000 || raw > 5000) {
                        continue;
                    }
                    String line = function.getName() + "@" + function.getEntryPoint()
                        + " | instruction=" + instruction.getAddress()
                        + " | pool=" + pool + " | calibration=" + calibration
                        + " | candidate_raw=" + raw + " | if_10ms="
                        + String.format("%.2fs", raw / 100.0);
                    if (emitted.add(line)) {
                        println(line);
                    }
                }
            }
        }
    }
}
