// Reapply the stock-function names/comments established while auditing the
// committed-AVLS-state dual-VE component. Safe to run on canonical D2WD610H.
// @category D2WD610H

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class ApplyAvlsVeNames extends GhidraScript {
    private void createOrRename(String addressText, String name) throws Exception {
        Address address = toAddr(addressText);
        Function function = getFunctionAt(address);
        if (function == null) {
            disassemble(address);
            function = createFunction(address, name);
        }
        if (function == null) {
            throw new IllegalStateException("Cannot create " + name + " at " + addressText);
        }
        if (!function.getName().equals(name)) {
            function.setName(name, SourceType.USER_DEFINED);
        }
        println(addressText + " -> " + function.getName());
    }

    @Override
    public void run() throws Exception {
        createOrRename("000024b0", "float_minimum_select");
        createOrRename("000172a4", "maf_airflow_temperature_compensation_update");
        createOrRename("000353b0", "intake_avcs_target_by_avls_mode_update");
        createOrRename("0003fdbc", "avls_control_sequence_update");
        createOrRename("00040168", "avls_cam_mode_state_machine");
        createOrRename("000405b2", "avls_mode_commit_copy");
        createOrRename("000405cc", "avls_osv_actuation_gate");

        setPlateComment(
            toAddr("0003fdbc"),
            "AVLS sequence: selector/state-machine request, committed-mode copy, " +
            "then OSV actuation. Dual VE reads committed mode 0xFFFFCD86."
        );
        setPlateComment(
            toAddr("000405b2"),
            "Copies requested AVLS mode 0xFFFFCD87 to committed mode 0xFFFFCD86. " +
            "The patch selects high-lift VE only for committed value 3."
        );
        setPlateComment(
            toAddr("000405cc"),
            "Retained synchronized OSV actuation gate. Calibration 0x7D4AC is " +
            "kept at 3000 RPM for the predictable 3200/3000 policy."
        );
        setPlateComment(
            toAddr("000172a4"),
            "The final-airflow helper pointer at 0x1743C is redirected to the " +
            "dual-VE wrapper. Stock B420 g/s and B428/B438 g/rev processing remains."
        );
    }
}
