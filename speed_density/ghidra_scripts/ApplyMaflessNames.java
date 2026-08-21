// Apply the function boundaries/names found while completing the D2WD610H
// MAFless speed-density trace. Safe to run repeatedly on the stock program.
// @category D2WD610H

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class ApplyMaflessNames extends GhidraScript {
    private void createOrRename(String addressText, String name) throws Exception {
        Address address = toAddr(addressText);
        Function function = getFunctionAt(address);
        if (function == null) {
            disassemble(address);
            function = createFunction(address, name);
        }
        if (function == null) {
            throw new IllegalStateException(
                "Ghidra could not create function " + name + " at " + addressText
            );
        }
        if (!function.getName().equals(name)) {
            function.setName(name, SourceType.USER_DEFINED);
        }
        println(addressText + " -> " + function.getName());
    }

    @Override
    public void run() throws Exception {
        createOrRename("000066c6", "sensor_adc_processing_task");
        createOrRename("00006328", "sensor_processing_batch_task");
        createOrRename("000316a2", "mass_airflow_logger_high_byte_get");
        createOrRename("000316ba", "mass_airflow_logger_low_byte_get");
        createOrRename("00031790", "maf_sensor_raw_adc_logger_value_get");
        createOrRename("00061328", "maf_sensor_input_diagnostic_update");
        createOrRename("00061332", "maf_sensor_high_input_diagnostic_update");
        createOrRename("000613ac", "maf_sensor_low_input_diagnostic_update");
        createOrRename("000115ea", "diagnostic_task_list_dispatcher");
        createOrRename("000107ee", "periodic_airflow_sensor_task_dispatcher");
        createOrRename("000172a4", "maf_airflow_temperature_compensation_update");
        createOrRename("000024b0", "float_minimum_select");
        createOrRename("0001b800", "engine_load_from_mass_airflow_calculate");
        createOrRename("0002ffa8", "filtered_mass_airflow_consumer_2ffa8");
        createOrRename("0004f1fa", "filtered_mass_airflow_logger_convert");
        createOrRename("000673c6", "filtered_mass_airflow_consumer_673c6");
        createOrRename("0002212c", "filtered_mass_airflow_consumer_2212c");
        createOrRename("00021c50", "filtered_mass_airflow_consumer_21c50");
        createOrRename("00012f10", "compensated_engine_load_consumer_12f10");
        createOrRename("0003da30", "engine_load_dependent_update_3da30");
        createOrRename("0003ea94", "engine_load_dependent_update_3ea94");
        createOrRename("0003daa6", "engine_load_dependent_update_3daa6");
        createOrRename("0003e1c8", "engine_load_dependent_update_3e1c8");
        createOrRename("000289e0", "engine_load_dependent_update_289e0");
        createOrRename("000135c4", "engine_load_dependent_update_135c4");
        createOrRename("000498b0", "engine_load_dependent_update_498b0");
        createOrRename("00024cb0", "engine_load_dependent_update_24cb0");
        createOrRename("0003da60", "engine_load_dependent_update_3da60");
        createOrRename("0003eace", "engine_load_dependent_update_3eace");
        createOrRename("000353b0", "intake_avcs_target_by_avls_mode_update");
        createOrRename("0003fdbc", "avls_control_sequence_update");
        createOrRename("00040168", "avls_cam_mode_state_machine");
        createOrRename("000405b2", "avls_mode_commit_copy");
        createOrRename("000405cc", "avls_osv_actuation_gate");
        createOrRename("0003e20e", "engine_load_dependent_update_3e20e");
        createOrRename("00029024", "engine_load_dependent_update_29024");
        createOrRename("00022454", "primary_open_loop_fueling_target_update");
        createOrRename("0002046c", "engine_load_dependent_update_2046c");
        createOrRename("0001e0c8", "injector_flow_scaling_factor_update");
        createOrRename("0003def0", "engine_load_dependent_update_3def0");
        createOrRename("000666ec", "engine_load_and_delta_dependent_update_666ec");
        createOrRename("000672e4", "engine_load_dependent_update_672e4");
        createOrRename("0002fb50", "engine_load_dependent_update_2fb50");
        createOrRename("0003eb68", "knock_correction_advance_max_select");
        createOrRename("0001496c", "engine_load_dependent_update_1496c");
        createOrRename("0003e7dc", "engine_load_dependent_update_3e7dc");
        createOrRename("0003ebdc", "engine_load_dependent_update_3ebdc");
        createOrRename("0001e7e8", "engine_load_dependent_update_1e7e8");
        createOrRename("00046d74", "engine_load_dependent_update_46d74");
        createOrRename("000217b8", "engine_load_and_filtered_airflow_update_217b8");
        createOrRename("0001e5e8", "engine_load_dependent_update_1e5e8");
        createOrRename("0006bba2", "engine_load_dependent_update_6bba2");
        createOrRename("0006bfdc", "engine_load_dependent_update_6bfdc");
        createOrRename("00023238", "engine_load_delta_consumer_23238");
        createOrRename("0001af80", "filtered_engine_load_consumer_1af80");
        createOrRename("000177dc", "airflow_state_flag_counter_update");
        setEOLComment(
            toAddr("0000639c"),
            "MAFless speed-density component replaces this raw-MAF jsr with nop."
        );
        setEOLComment(
            toAddr("000066d8"),
            "MAFless speed-density component replaces this raw-MAF jsr with nop."
        );
        setEOLComment(
            toAddr("000107f8"),
            "MAFless speed-density component replaces the MAF limit/filter jsr with nop."
        );
        setPlateComment(
            toAddr("0003fdbc"),
            "AVLS request/state-machine, committed-mode copy, then OSV actuation. " +
            "Speed density reads committed mode 0xFFFFCD86 for dual-VE selection."
        );
        setPlateComment(
            toAddr("000405b2"),
            "Copies requested AVLS mode 0xFFFFCD87 to committed mode 0xFFFFCD86. " +
            "High-lift VE is selected only for committed value 3."
        );
        setPlateComment(
            toAddr("000405cc"),
            "Retained synchronized OSV gate. The merged SD calibration uses a " +
            "3000 RPM actuation minimum and predictable 3200/3000 hysteresis."
        );
        setEOLComment(
            toAddr("000114d2"),
            "Retained: filters final mass airflow B420 (speed-density output) into B424."
        );
        setEOLComment(
            toAddr("00011d20"),
            "Retained stock airflow/load task pointer (0x172A4). MAFless component " +
            "hooks its final-airflow helper at 0x1743C."
        );
        setEOLComment(
            toAddr("0001743c"),
            "MAFless component redirects final airflow calculation to 0x7E18C before B420 store."
        );
        setPlateComment(
            toAddr("000172a4"),
            "Retained airflow/load task. MAFless component disables raw-MAF producers and " +
            "redirects the final-airflow helper pointer at 0x1743C to 0x7E18C. " +
            "It stores final mass airflow in B420 as g/s, forms raw engine load B428 " +
            "as airflow_g_s * 60 / RPM, and conditions that into B438 in g/rev. " +
            "Thus the stock load normalization remains active on the speed-density result."
        );
    }
}
