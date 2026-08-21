// Reapply the stock-function names and comments established while auditing
// D2WD610H master_patch. Safe to run repeatedly on the canonical stock program.
// @category D2WD610H

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SourceType;

public class ApplyMasterNames extends GhidraScript {
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

    private void createOrRenameData(String addressText, String name) throws Exception {
        Address address = toAddr(addressText);
        Symbol symbol = getSymbolAt(address);
        if (symbol == null) {
            createLabel(address, name, true);
        } else if (!symbol.getName().equals(name)) {
            symbol.setName(name, SourceType.USER_DEFINED);
        }
        println(addressText + " -> " + getSymbolAt(address).getName());
    }

    @Override
    public void run() throws Exception {
        createOrRename("00001884", "diagnostic_request_download_handle");
        createOrRename("00002458", "float_divide_guarded");
        createOrRename("000024b0", "float_minimum_select");
        createOrRename("000024c0", "float_clamp");
        createOrRename("000024fc", "float_difference_exceeds_tolerance");
        createOrRename("000078ac", "analog_sensor_abac_range_classify");
        createOrRename("000079b4", "analog_sensor_abbc_range_classify");
        createOrRename("00007a14", "map_sensor_voltage_to_pressure_process");
        createOrRename("00007a56", "map_sensor_raw_adc_range_classify");
        createOrRename("000098cc", "injector_battery_voltage_latency_lookup");
        createOrRename("00010a28", "engine_control_periodic_task_dispatch");
        createOrRename("0000a9a8", "injector_control_lookup_sequence_a9a8");
        createOrRename("0000b690", "front_af_sensor_pair_signal_process");
        createOrRename("0000f474", "engine_oil_temperature_sensor_process");
        createOrRename("00013330", "runtime_status_b6c0_bit7_is_set");
        createOrRename("000172a4", "maf_airflow_temperature_compensation_update");
        createOrRename(
            "00017984", "airflow_load_and_vehicle_speed_processing_sequence_update"
        );
        createOrRename("000179ee", "airflow_load_filter_state_initialize");
        createOrRename(
            "00017a24", "airflow_load_filter_state_requires_initialization"
        );
        createOrRename("00017b2a", "airflow_bank_charge_update");
        createOrRename("000180c6", "engine_load_from_airflow_calculate");
        createOrRename("000181ea", "engine_load_limit_update");
        createOrRename("000182ac", "engine_load_compensation_update");
        createOrRename("00018438", "vehicle_speed_conditioning_status_flags_update");
        createOrRename(
            "000184cc", "vehicle_speed_conditioning_coefficient_set_a_update"
        );
        createOrRename(
            "0001873c", "vehicle_speed_conditioning_coefficient_set_b_update"
        );
        createOrRename("000188f4", "vehicle_speed_conditioned_source_update");
        createOrRename("00018a68", "vehicle_speed_conditioned_filter_update");
        createOrRename("00018aea", "vehicle_speed_conditioned_snapshot_copy");
        createOrRename("00018dac", "front_af_sensor_lambda_condition_filter");
        createOrRename(
            "000192a8", "front_af_sensor_pump_current_pair_offset_clamp_update"
        );
        createOrRename("0001d228", "runtime_status_b748_bit7_is_set");
        createOrRename("0001e0c8", "injector_flow_scaling_factor_update");
        createOrRename("0001ee74", "closed_loop_fuel_control_bank_update");
        createOrRename("00022454", "primary_open_loop_fueling_target_update");
        createOrRename("00022756", "cl_ol_transition_delay_update");
        createOrRename("00022948", "cl_ol_delay_condition_and_counter_update");
        createOrRename("00022aae", "cl_ol_transition_state_update");
        createOrRename("00022ac2", "cl_ol_transition_state_initialize");
        createOrRename("0002331e", "fueling_state_flag_clear_on_condition");
        createOrRename("00023fc0", "fuel_cut_flag_aggregate");
        createOrRename("00024b24", "rev_limiter_fuel_cut");
        createOrRename("000279cc", "ign_final_timing_per_cylinder_update");
        createOrRename("00027088", "constant_zero_return");
        createOrRename("00028354", "ign_avcs_tracking_blend_factor_update");
        createOrRename("00028418", "ign_base_timing_map_blend");
        createOrRename("000284b8", "ign_base_timing_select");
        createOrRename("0003253c", "engine_oil_temperature_logger_convert");
        createOrRename(
            "00033964", "rear_o2_sensor_response_integrator_initialize"
        );
        createOrRename("00033970", "rear_o2_sensor_response_integrator_update");
        createOrRename("00034be4", "rear_o2_sensor_response_ratio_update");
        createOrRename("000353b0", "intake_avcs_target_by_avls_mode_update");
        createOrRename("00035750", "intake_avcs_tracking_control_update");
        createOrRename(
            "0003d7e4", "ign_per_cylinder_correction_enable_latch_update"
        );
        createOrRename("0003d824", "ign_per_cylinder_correction_array_update");
        createOrRename("0003d8e2", "ign_per_cylinder_correction_state_clear");
        createOrRename(
            "0003d916", "ign_per_cylinder_correction_state_any_active"
        );
        createOrRename("0003d95a", "ign_per_cylinder_correction_initialize");
        createOrRename("0003d980", "ign_per_cylinder_correction_array_clear");
        createOrRename("0003eb68", "knock_correction_advance_max_select");
        createOrRename("0003fdbc", "avls_control_sequence_update");
        createOrRename("0003ffda", "avls_threshold_curve_selector_state_update");
        createOrRename(
            "000400ee", "avls_curve_selector_oil_temp_band_latches_update"
        );
        createOrRename("00040168", "avls_cam_mode_state_machine");
        createOrRename("000405b2", "avls_mode_commit_copy");
        createOrRename("000405cc", "avls_osv_actuation_gate");
        createOrRename("00047000", "engine_oil_temperature_fallback_select");
        createOrRename("00047db2", "atmospheric_pressure_source_select_update");
        createOrRename("00064fd0", "front_af_sensor_bank1_inhibit_check");
        createOrRename("0006500c", "front_af_sensor_bank2_inhibit_check");
        createOrRename("0006504c", "runtime_status_d26d_bit5_get");
        createOrRenameData("ffffcfbc", "atmospheric_pressure_native");

        setPlateComment(
            toAddr("00022454"),
            "Primary open-loop fueling target lookup. Uses RPM 0xFFFFB544 and " +
            "conditioned load 0xFFFFB438 with descriptors 0x5FA9C/0x5FAB8, then " +
            "publishes the target through 0xFFFFBE20/BE24/BE00. State byte " +
            "0xFFFFBE38 bit 0x80 is set when closed-loop is permitted and cleared " +
            "for open-loop enrichment. Master pressure safety calls this stock " +
            "routine first and may only clear that bit afterward. Task pointer " +
            "slot is 0x11D78."
        );
        setPlateComment(
            toAddr("00022948"),
            "CL/OL delay condition and counter update. Reads native atmospheric " +
            "pressure at 0xFFFFCFBC for descriptor 0x5F8FC (axis 0x772D4, data " +
            "0x772DC), confirming the signal's mmHg-absolute barometric role."
        );
        setPlateComment(
            toAddr("00047db2"),
            "Selects the live atmospheric-pressure source from 0xFFFF8E04 or " +
            "0xFFFFB3A8 and publishes native mmHg absolute at 0xFFFFCFBC."
        );
        setPlateComment(
            toAddr("00024b24"),
            "Stock RPM limiter sets fuel-cut status 0xFFFFBF6C bit 0x80. The " +
            "periodic task pointer at 0x11D3C is the verified composition point " +
            "for hard-overboost and latched-lean cuts."
        );
        setPlateComment(
            toAddr("000279cc"),
            "Produces the six final per-cylinder ignition angles at " +
            "0xFFFFC0EC..0xFFFFC100. Master task slot 0x11E30 calls the " +
            "default-OFF rotational-idle wrapper, which runs this complete stock " +
            "task first and can only apply bounded retard afterward."
        );
        setPlateComment(
            toAddr("00033964"),
            "Initialization-only task writes float 1.0 to rear-O2 integrator " +
            "RAM 0xFFFFC85C and 0xFFFFC860. Master fueling safety repoints its " +
            "task slot at 0x1055C to an explicit zero initializer before " +
            "reclaiming those words as lean-cut counter/state."
        );
        setPlateComment(
            toAddr("00023fc0"),
            "Aggregates the stock fuel-cut flags, including 0xFFFFBF6C bit 0x80, " +
            "into the downstream injector-cut decision."
        );

        setPlateComment(
            toAddr("00027088"),
            "Canonical D2WD610H is exactly rts; mov #0,r0. The B/E base-timing " +
            "selector requires this callback to return 1, so the B/E path is " +
            "unreachable in stock."
        );
        setPlateComment(
            toAddr("00028354"),
            "Builds timing interpolation factor k at 0xFFFFC17C from intake " +
            "AVCS tracking: k = clamp((actual left + actual right at C8C8/C8CC) / " +
            "(commanded left + commanded right at C974/C978), 0, 1). A near-zero " +
            "commanded sum yields 0; verified status paths can force 1."
        );
        setPlateComment(
            toAddr("00028418"),
            "Looks up the six legacy base maps. For each selectable cam path, " +
            "timing = AVCS-tracking-ratio-1.0 endpoint * k + ratio-0.0 endpoint " +
            "* (1-k), using k at 0xFFFFC17C. This is not an IAM blend."
        );
        setPlateComment(
            toAddr("000284b8"),
            "Default/normal cam selects the A/D blend. AVLS high cam selects " +
            "C/F when cam mode 3 and debounced status bit 0x40 are active. B/E " +
            "requires constant_zero_return @0x27088 to return 1 and is therefore " +
            "dormant in canonical stock."
        );
        setPlateComment(
            toAddr("0003eb68"),
            "Selects KCA Max A in normal cam and KCA Max B in the verified AVLS " +
            "high-cam state."
        );
        setPlateComment(
            toAddr("000353b0"),
            "Selects AVCS descriptor 0x60C34 / data 0x7C5B0 when committed AVLS " +
            "cam mode 0xFFFFCD86 is 1 (low lift), or descriptor 0x60C50 / data " +
            "0x7C764 when mode is 3 (high lift). Publishes the common target at " +
            "0xFFFFC984. Both maps use genuine conditioned engine load 0xFFFFB438 " +
            "in g/rev and RPM 0xFFFFB544. Legacy A/B identify AVLS modes, not " +
            "cylinder banks."
        );
        setPlateComment(
            toAddr("00035750"),
            "Downstream intake AVCS tracking/control update using per-bank measured " +
            "and conditioned target state. The legacy A/B target maps selected " +
            "upstream are AVLS operating modes, not bank identities."
        );
        setPlateComment(
            toAddr("0003ffda"),
            "Updates AVLS threshold-curve selector 0xFFFFCD9C from conditioned " +
            "engine-oil temperature 0xFFFFCF94. Subject to runtime, delay, and " +
            "fault gates: state 1 is cold/fallback, state 2 is the normal " +
            "15..115 C band, and state 3 is the hot >=115 C band."
        );
        setPlateComment(
            toAddr("000400ee"),
            "Updates two hysteretic engine-oil-temperature latches in 0xFFFFCD9E " +
            "from 0xFFFFCF94: bit 0 sets at 15 C and clears below 13 C; bit 1 " +
            "sets at 115 C and clears below 113 C."
        );
        setPlateComment(
            toAddr("00040168"),
            "AVLS lift-mode state machine. Selector state 2 uses RPM-versus-" +
            "vehicle-speed descriptor 0x60F58; state 3 uses 0x60F64. The " +
            "compared 0xFFFFB46C signal is conditioned vehicle speed in km/h, " +
            "not engine load. Low lift requests high at curve + 10 km/h; high " +
            "lift releases below the raw curve. State 1 uses fixed 15 km/h " +
            "thresholds. Stock hard-RPM override is 4000/3800 RPM."
        );
        setPlateComment(
            toAddr("0003fdbc"),
            "Runs the AVLS selector, state machine, committed-mode copy, and " +
            "OSV actuation sequence. Master dual VE deliberately reads the " +
            "post-decision committed byte 0xFFFFCD86 rather than requested " +
            "mode 0xFFFFCD87."
        );
        setPlateComment(
            toAddr("000405b2"),
            "Copies requested AVLS mode 0xFFFFCD87 into committed mode " +
            "0xFFFFCD86 before the retained OSV actuation sequence. The dual-VE " +
            "airflow wrapper selects high-lift VE only when this committed byte is 3."
        );
        setPlateComment(
            toAddr("000405cc"),
            "Retained OSV actuation gate. Uses the minimum-RPM calibration at " +
            "0x7D4AC and synchronized state/phase checks before commanding all " +
            "three high-lift actuators."
        );
        setPlateComment(
            toAddr("0000f474"),
            "Processes raw ADC 0xFFFFAB12 through descriptor 0x60950 (voltage " +
            "axis 0x7B748, temperature data 0x7B7C4) and publishes engine-oil " +
            "temperature in degrees C at 0xFFFFB124. The table spans -40..150 C; " +
            "P0197/P0198 identify this CALID's channel."
        );
        setPlateComment(
            toAddr("00047000"),
            "Validates engine-oil temperature 0xFFFFB124 and publishes the AVLS-" +
            "facing value at 0xFFFFCF94. Fault/startup paths substitute the stock " +
            "70.0 C fallback at 0x73B88/0x73B8C."
        );
        setPlateComment(
            toAddr("000172a4"),
            "Final mass airflow is written to 0xFFFFB420 in g/s. The retained " +
            "stock path forms raw engine load 0xFFFFB428 as airflow_g_s * 60 / " +
            "RPM, then conditions it into 0xFFFFB438 in g/rev. Master speed " +
            "density replaces the final-airflow helper only, preserving this " +
            "native load normalization."
        );
        setPlateComment(
            toAddr("00017984"),
            "Runs the stock airflow/load pipeline and, separately, vehicle-speed " +
            "conditioning. The final chain publishes B4C0, B4C8, then AVLS speed " +
            "snapshot B46C. Speed density changes upstream airflow, not this speed " +
            "chain."
        );
        setPlateComment(
            toAddr("000188f4"),
            "Conditions vehicle speed 0xFFFFB538 in native km/h, caps it at " +
            "100.0, and publishes 0xFFFFB4C0. No engine-load conversion occurs."
        );
        setPlateComment(
            toAddr("00018a68"),
            "Filters conditioned vehicle speed 0xFFFFB4C0 into 0xFFFFB4C8; " +
            "units remain km/h."
        );
        setPlateComment(
            toAddr("00018aea"),
            "Copies filtered vehicle speed 0xFFFFB4C8 to AVLS compare signal " +
            "0xFFFFB46C; units remain km/h."
        );
        setPlateComment(
            toAddr("00007a14"),
            "Converts MAP sensor volts with float offset/multiplier at 0x72810 " +
            "and publishes native mmHg absolute at 0xFFFFABC4."
        );
        setPlateComment(
            toAddr("00007a56"),
            "Classifies raw MAP ADC 0xFFFFABC8 against high/low thresholds at " +
            "0x7B284/0x7B286."
        );
        setPlateComment(
            toAddr("000098cc"),
            "Looks up injector battery-voltage latency through descriptor 0x608D8 " +
            "(axis 0x7B304, data 0x7B318)."
        );
        setPlateComment(
            toAddr("0001e0c8"),
            "Consumes injector flow scaling at ROM 0x76014 in the fueling path."
        );
        setPlateComment(
            toAddr("0000b690"),
            "Master patch replaces this producer with former-MAF ADC wideband " +
            "conversion, publishing one synthetic lambda/readiness value to both " +
            "stock front-bank paths."
        );
        setPlateComment(
            toAddr("00018dac"),
            "Retained downstream condition/filter. Master patch feeds its AE60/AE64 " +
            "inputs from the single external wideband."
        );
        setPlateComment(
            toAddr("0001ee74"),
            "Retained per-bank closed-loop fuel consumer. In master_patch both banks " +
            "receive the same external-wideband lambda source."
        );
        setPlateComment(
            toAddr("0006504c"),
            "Reads RAM status byte 0xFFFFD26D bit 0x20 and returns 2 when set, " +
            "otherwise 0."
        );
    }
}
