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
        createOrRename("00005d0e", "hardware_register_value_initialize_5d0e");
        createOrRename("00002458", "float_divide_guarded");
        createOrRename("000024b0", "float_minimum_select");
        createOrRename("000024c0", "float_clamp");
        createOrRename("000024fc", "float_difference_exceeds_tolerance");
        // Correct an earlier mid-function entry at 0x6892. The real wrapper
        // starts with its PR save and function-pointer load at 0x688E.
        Function misplacedPeriodicWrapper = getFunctionAt(toAddr("00006892"));
        if (misplacedPeriodicWrapper != null) {
            currentProgram.getFunctionManager().removeFunction(toAddr("00006892"));
        }
        createOrRename("0000684c", "engine_control_periodic_wrapper");
        createOrRename("0000688e", "diagnostic_monitor_periodic_wrapper");
        createOrRename("000078ac", "analog_sensor_abac_range_classify");
        createOrRename("00007d08", "analog_signal_scaled_accumulator_update_7d08");
        createOrRename("000079b4", "analog_sensor_abbc_range_classify");
        createOrRename("00007a14", "map_sensor_voltage_to_pressure_process");
        createOrRename("00007a56", "map_sensor_raw_adc_range_classify");
        createOrRename("0000938c", "actuator_schedule_countdown_update");
        createOrRename("000093d4", "actuator_schedule_event_commit");
        createOrRename("000098cc", "injector_battery_voltage_latency_lookup");
        createOrRename("00010a28", "engine_control_periodic_task_dispatch");
        createOrRename(
            "00011914", "fueling_compensation_periodic_dispatch_11914"
        );
        createOrRename(
            "00011f9c", "diagnostic_condition_sequence_update_11f9c"
        );
        createOrRename(
            "000123f6", "diagnostic_enable_runtime_latch_update_123f6"
        );
        createOrRename("0000a9a8", "injector_control_lookup_sequence_a9a8");
        createOrRename("0000b690", "front_af_sensor_pair_signal_process");
        createOrRename("0000deaa", "fuel_pump_pwm_output_write");
        createOrRename("0000f474", "engine_oil_temperature_sensor_process");
        createOrRename("0000f5f6", "hardware_register_word_initialize_f5f6");
        createOrRename(
            "0000f710", "hardware_register_guarded_initialize_f710"
        );
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
        createOrRename("00018fdc", "front_af_sensor_closed_loop_status_pair_update");
        createOrRename(
            "000192a8", "front_af_sensor_pump_current_pair_offset_clamp_update"
        );
        createOrRename("0001a838", "engine_run_counter_update");
        createOrRename("0001be8e", "fuel_trim_state_initialize");
        createOrRename("0001cc34", "cranking_fuel_state_periodic_update");
        createOrRename("0001cfee", "cranking_fuel_state_initialize");
        createOrRename(
            "0001d200", "cranking_clear_flood_throttle_hysteresis_update"
        );
        createOrRename("0001dd04", "final_fueling_multiplier_compose");
        createOrRename("0001d228", "runtime_status_b748_bit7_is_set");
        createOrRename("0001e0c8", "injector_flow_scaling_factor_update");
        createOrRename("0001e142", "after_start_enrichment_group_a_initialize");
        createOrRename("0001e1b0", "after_start_enrichment_group_a_decay_update");
        createOrRename("0001e41c", "after_start_enrichment_group_b_initialize");
        createOrRename("0001e47a", "after_start_enrichment_group_b_decay_update");
        createOrRename(
            "0001e5e8", "after_start_fueling_compensation_b868_update"
        );
        createOrRename(
            "0001e7e8", "after_start_fueling_compensation_b874_update"
        );
        createOrRename("0001ee74", "closed_loop_fuel_control_bank_update");
        createOrRename("0001f0d8", "closed_loop_feedback_bank_state_update");
        createOrRename("0001f1dc", "closed_loop_short_term_correction_publish");
        createOrRename("0001fb16", "closed_loop_lambda_delay_coefficients_update");
        createOrRename("0001fcd4", "closed_loop_lambda_delay_filter_update");
        createOrRename("00020326", "closed_loop_bank_feedback_correction_update");
        createOrRename("000205fa", "closed_loop_feedback_bank_counter_update");
        createOrRename(
            "000207ac", "closed_loop_feedback_entry_compensation_update"
        );
        createOrRename(
            "00020e5e", "long_term_fuel_trim_learning_condition_update"
        );
        createOrRename("0002104e", "closed_loop_bank_trim_state_update");
        createOrRename(
            "00021ac0", "airflow_range_threshold_compensation_update"
        );
        createOrRename("00021b1c", "airflow_range_delay_latch_update");
        createOrRename("00022454", "primary_open_loop_fueling_target_update");
        createOrRename("00022756", "cl_ol_transition_delay_update");
        createOrRename("00022948", "cl_ol_delay_condition_and_counter_update");
        createOrRename("00022aae", "cl_ol_transition_state_update");
        createOrRename("00022ac2", "cl_ol_transition_state_initialize");
        createOrRename("00022b38", "after_start_enrichment_group_c_initialize");
        createOrRename("00022b7e", "after_start_enrichment_group_c_decay_update");
        createOrRename(
            "00022ce4", "after_start_enrichment_group_c_residual_decay_update"
        );
        createOrRename("00022e00", "after_start_enrichment_group_d_initialize");
        createOrRename("00022e0e", "after_start_enrichment_group_d_update");
        createOrRename("0002331e", "fueling_state_flag_clear_on_condition");
        createOrRename("00023fc0", "fuel_cut_flag_aggregate");
        createOrRename("00024b24", "rev_limiter_fuel_cut");
        createOrRename("000279cc", "ign_final_timing_per_cylinder_update");
        createOrRename("00029794", "ignition_event_schedule_update_29794");
        createOrRename(
            "00029aa8", "ignition_event_schedule_reinitialize_29aa8"
        );
        createOrRename("00029c62", "ignition_cycle_position_delta_wrap");
        createOrRename("00029ca8", "ignition_cycle_position_wrap");
        createOrRename("00029f72", "ignition_event_output_window_clear");
        createOrRename(
            "0002a0a6", "ignition_schedule_position_threshold_check"
        );
        createOrRename("00027088", "constant_zero_return");
        createOrRename("00028354", "ign_avcs_tracking_blend_factor_update");
        createOrRename("00028418", "ign_base_timing_map_blend");
        createOrRename("000284b8", "ign_base_timing_select");
        createOrRename("0002a50c", "fuel_pump_control_initialize");
        createOrRename("0002a53a", "fuel_pump_pwm_command_output_update");
        createOrRename("0002a614", "fuel_pump_control_state_update");
        createOrRename("0002a7a6", "fuel_pump_control_mode_gate_update");
        createOrRename("0002a910", "fuel_pump_control_mode_select");
        createOrRename(
            "0002ad6c", "vehicle_speed_dependent_filter_update_2ad6c"
        );
        createOrRename("0003191c", "fuel_pump_duty_logger_value_get");
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
        createOrRename("0003f5f0", "radiator_fan_state_timeout_update");
        createOrRename("0003f650", "radiator_fan_control_state_update");
        createOrRename("0003fd38", "evap_purge_condition_counter_update");
        createOrRename("0003fdbc", "avls_control_sequence_update");
        createOrRename("0003ffda", "avls_threshold_curve_selector_state_update");
        createOrRename(
            "000400ee", "avls_curve_selector_oil_temp_band_latches_update"
        );
        createOrRename("00040168", "avls_cam_mode_state_machine");
        createOrRename("000405b2", "avls_mode_commit_copy");
        createOrRename("000405cc", "avls_osv_actuation_gate");
        createOrRename(
            "0004178c", "diagnostic_counter_event_state_update_4178c"
        );
        createOrRename("00041de4", "diagnostic_mode_sequence_update_41de4");
        createOrRename("00042a80", "diagnostic_state_initialize_42a80");
        createOrRename(
            "00045350", "diagnostic_condition_snapshot_update_45350"
        );
        createOrRename("00047000", "engine_oil_temperature_fallback_select");
        createOrRename("00047db2", "atmospheric_pressure_source_select_update");
        createOrRename(
            "000490ca", "diagnostic_monitor_counter_update_490ca"
        );
        createOrRename("00064fd0", "front_af_sensor_bank1_inhibit_check");
        createOrRename("0006500c", "front_af_sensor_bank2_inhibit_check");
        createOrRename("0006504c", "runtime_status_d26d_bit5_get");
        createOrRename("00067bf8", "diagnostic_threshold_pair_update_67bf8");
        createOrRename(
            "0006b6fc", "diagnostic_monitor_state_latch_update_6b6fc"
        );
        createOrRename(
            "0006e338", "diagnostic_monitor_enable_state_update_6e338"
        );
        createOrRename(
            "00071836", "diagnostic_monitor_11_condition_counter_update"
        );
        createOrRenameData("0002a5fc", "fuel_pump_high_speed_command_percent");
        createOrRenameData("0002a60c", "fuel_pump_medium_speed_command_percent");
        createOrRenameData("0002a610", "fuel_pump_low_speed_command_percent");
        createOrRenameData("ffffc298", "fuel_pump_duty_percent");
        createOrRenameData("ffffcfbc", "atmospheric_pressure_native");

        setPlateComment(
            toAddr("0002a53a"),
            "Selects the stock discrete fuel-pump commands from mode bits at " +
            "0xFFFFC2AC: 0, low 33.3% at 0x2A610, medium 66.7% at 0x2A60C, " +
            "or high 100.0% at 0x2A5FC. Publishes the selected percent at " +
            "0xFFFFC298, divides it by 100, and tail-calls the ATU PWM writer " +
            "at 0xDEAA. The low and medium literals are exposed by the master " +
            "RomRaider definition for a stationary diagnostic; the shared " +
            "100% high-mode/normalization literal remains fixed."
        );
        setPlateComment(
            toAddr("0001a838"),
            "Updates the saturating engine-run counter at 0xFFFFB688 and the " +
            "adjacent runtime counter at 0xFFFFB68A. Both reset while " +
            "runtime_status_b748_bit7_is_set is true. This task is reached by " +
            "the main engine-control periodic dispatch; timer conversions in " +
            "the audit use its derived 10 ms cadence."
        );
        setPlateComment(
            toAddr("0002a614"),
            "Fuel-pump mode state machine. It reads engine-run counter " +
            "0xFFFFB688 and directly compares it with big-endian u16 " +
            "calibration 0x794DA = 0x0EA6 (3750 periodic calls, approximately " +
            "37.5 s at the derived 10 ms cadence). Its other 31/63/94-count " +
            "tests are private mode counters, not additional 30-second clocks."
        );
        setPlateComment(
            toAddr("0001e1b0"),
            "After-start enrichment group A decay. Reads engine-run counter " +
            "0xFFFFB688, applies coolant-dependent delay/decay calibrations, " +
            "and publishes the additive state at 0xFFFFB834 consumed by final " +
            "fueling."
        );
        setPlateComment(
            toAddr("0001e47a"),
            "After-start enrichment group B decay. Reads engine-run counter " +
            "0xFFFFB688, applies coolant-dependent delay/decay calibrations, " +
            "and publishes the additive state at 0xFFFFB854 consumed by final " +
            "fueling."
        );
        setPlateComment(
            toAddr("00022ce4"),
            "Residual decay for after-start enrichment group C. Reads " +
            "0xFFFFB688 and uses calibration 0x75E8E = 5000 periodic calls " +
            "(approximately 50 s at the derived 10 ms cadence) while updating " +
            "0xFFFFBE44. Group output 0xFFFFBE40 is consumed by final fueling."
        );
        setPlateComment(
            toAddr("0001f0d8"),
            "Closed-loop feedback bank-state update. Counter 0xFFFFBC98 is " +
            "bounded by calibration 0x75E5E = 31 scheduler calls. This is an " +
            "independent readiness/sample counter, not engine-run seconds; the " +
            "captured event remained CL/OL status 7 (open loop)."
        );
        setPlateComment(
            toAddr("0003191c"),
            "Standard SSM byte address 0x3B dispatches here through pointer " +
            "table slot 0x4B7E8. Reads the selected fuel-pump percent from " +
            "0xFFFFC298 and scales it for P47 Fuel Pump Duty."
        );

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
            toAddr("0001fb16"),
            "Builds the stock 21-element per-bank closed-loop lambda response/delay " +
            "coefficient vector. Master patch supplies both banks from one post-turbo " +
            "AEM signal; these stock pre-turbo response calibrations remain unchanged."
        );
        setPlateComment(
            toAddr("0001fcd4"),
            "Applies the stock 21-sample lambda history/delay model using conditioned " +
            "feedback B4E8/B4EC and targets B8F4/B8F8. Moving feedback post-turbo adds " +
            "uncalibrated transport delay."
        );
        setPlateComment(
            toAddr("00020326"),
            "Updates each bank's closed-loop feedback correction. In master_patch both " +
            "instances receive the same post-turbo AEM measurement."
        );
        setPlateComment(
            toAddr("0001dd04"),
            "Composes final fueling using short-term corrections B8D4/B8D8 and learned " +
            "trims BCB8/BCBC among other factors; learned trims can affect open loop."
        );
        setPlateComment(
            toAddr("0006504c"),
            "Reads RAM status byte 0xFFFFD26D bit 0x20 and returns 2 when set, " +
            "otherwise 0."
        );
    }
}
