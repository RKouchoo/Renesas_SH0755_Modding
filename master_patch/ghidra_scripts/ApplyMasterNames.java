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
        setPlateComment(
            toAddr("000193d0"),
            "Corrected September 13: PE14/15 from AAE6 publish to B51C/20,10 and " +
            "B51E/04,02 with the same polarity. B51A/04 and B51B/02 instead invert " +
            "serial input channel 2 bit 2 (AAEC), after two-sample debounce. " +
            "19C90 reads that separate serial request for retained-bank path 4892C. " +
            "The earlier inverse-AVLS-switch claim was incorrect."
        );
        // September 13 retained reset input and SSM command separation.
        createOrRename("0000766c", "serial_input_mux_read_channel");
        createOrRename("00019c90", "serial_input2_bit2_low_get");
        createOrRename("00048830", "retained_bank_shutdown_request_rearm");
        createOrRename("0004892c", "retained_bank_serial_request_invalidate");
        createOrRename("0004898c", "retained_bank_serial_request_latch_initialize");
        createOrRename("000313f2", "retained_bank_request_word_set_4055");
        createOrRename("00032fec", "ssm_standard_command_decode");
        createOrRename("0003322c", "ssm_standard_response_chunk_dispatch");
        createOrRename("00033668", "ssm_standard_read_byte_or_parameter");
        createOrRename("000336e6", "ssm_standard_write_byte_or_parameter");
        createOrRename("00032bb4", "ssm_receive_byte_or_transmit_echo");
        createOrRename("00032b24", "ssm_timer_and_initial_transmit_service");
        createOrRename("00032de8", "ssm_transmit_echo_advance_and_repeat");
        // September 13 retained knock records, learning and mode handoffs.
        createOrRename("00029570", "ignition_retained_records_validate");
        createOrRename("0003d9e8", "knock_grid_records_validate");
        createOrRename("0003e9fc", "iam_retained_records_initialize");
        createOrRename("0003ec6c", "iam_learning_reset_eligibility_update");
        createOrRename("0003ecb6", "iam_first_qualified_entry_reset");
        createOrRename("0003ed6c", "iam_rough_learning_event_update");
        createOrRename("0003f020", "iam_avcs_fault_recovery_update");
        createOrRename("0003dc9c", "knock_fine_selected_record_learn");
        createOrRename("0003dfd6", "knock_clean_event_counter_update");
        createOrRename("0003ef74", "knock_fine_to_rough_mode_reentry");
        createOrRename("0003e7dc", "knock_load_stability_filter_update");
        createOrRename("0003e45c", "knock_learning_inhibit_update");
        createOrRename("0003e760", "knock_feedback_entry_edge_update");
        createOrRename("0003e20e", "knock_feedback_retard_update");
        createOrRename("0003e83c", "knock_learning_transition_timers_update");
        createOrRename("0003e80a", "knock_feedback_clean_event_timer_update");
        createOrRename("0003e72e", "knock_permission_activity_timer_update");
        createOrRename("0003e1b0", "knock_feedback_history_initialize");
        createOrRename("0000a8f0", "knock_phase_window_dispatch");
        createOrRename("0000aa50", "knock_sample_threshold_and_event_update");
        createOrRename("0000add8", "knock_window_timer_arm");
        createOrRename("0000aeec", "knock_window_close_and_next_gain_select");
        createOrRename("0000a7ea", "knock_window_an24_capture");
        createOrRename("00017914", "knock_sample_event_publish");
        createOrRename("00017942", "knock_sample_event_reset");
        createOrRename("00007748", "knock_sci0_command_publish");
        createOrRename("000077aa", "sci0_framed_byte_transfer");
        createOrRename("00005cd8", "knock_window_completion_callback");
        createOrRename("00028c38", "timing_retard_c1bc_update");
        createOrRename("0002e8cc", "idle_timing_retard_air_compensation_update");
        createOrRename("0002b570", "idle_base_air_compensation_sum_update");
        createOrRename("0002b432", "idle_total_air_request_update");
        createOrRename("0002b408", "idle_air_to_throttle_request_update");
        createOrRename("0006bb30", "monitor_timing_temperature_gain_update");
        createOrRename("00028a82", "idle_speed_timing_c1a8_update");
        createOrRename("0002c760", "idle_air_feedback_permission_update");
        createOrRename("0002ce50", "idle_pressure_demand_update");
        createOrRename("0002cf9c", "idle_pressure_error_terms_update");
        createOrRename("0002d0ac", "idle_air_feedback_output_and_history_update");
        createOrRename("0002d1fc", "idle_air_feedback_headroom_limits_update");
        // September 13 native inhibit producers and release paths.
        createOrRename("00024c34", "digital_input_loss_injector_cut_update");
        createOrRename("00024cb0", "stationary_speed_plausibility_update");
        createOrRename("00024e0c", "stationary_timed_rpm_injector_cut_update");
        createOrRename("0002513c", "vehicle_speed_injector_cut_pattern_update");
        createOrRename("0004551c", "low_lift_high_rpm_injector_cut_update");
        createOrRename("00025ac0", "received_torque_cut_pattern_demand_update");
        // September 13 received requests, phase patterns and torque model.
        createOrRename("00014374", "can_powertrain_torque_request_receive");
        createOrRename("0003bee4", "can_startup_cut_request_receive");
        createOrRename("0003ce0a", "received_torque_cut_ratio_update");
        createOrRename("0003ce58", "received_torque_enabled_slots_update");
        createOrRename("0003d050", "received_torque_cut_phase_publish");
        createOrRename("0003d3a2", "received_torque_cut_release_history_update");
        createOrRename("0002ee6c", "received_torque_model_error_update");
        createOrRename("0003d48c", "received_torque_cut_alignment_edge_update");
        createOrRename("00036190", "received_torque_common_inhibit_reasons_update");
        createOrRename("00036370", "received_torque_cylinder_cut_inhibit_update");
        createOrRename("0003d28e", "received_torque_cut_reentry_delay_update");
        // September 13 capture decoder and shared observation queue.
        createOrRename("00008218", "crank_primary_capture_process");
        createOrRename("00008248", "crank_secondary_capture_process");
        createOrRename("00008428", "crank_capture_decode_and_phase_publish");
        createOrRename("000084b2", "crank_capture_pattern_state_update");
        createOrRename("0001a0ba", "engine_capture_inhibit_request_publish");
        createOrRename("0000d92c", "crank_interval_observation_publish");
        createOrRename("0000db50", "crank_edge_window_status_update");
        // September 13 native phase activation and period publication.
        createOrRename("000087f2", "crank_phase_publish_and_activate");
        createOrRename("00008be6", "crank_phase_period_and_rpm_publish");
        createOrRename("0000cf58", "crank_phase_task5_activate_and_queue");
        createOrRename("0000cf7e", "crank_phase_task6_activate_and_queue");
        // September 13 synchronization and adjacent computed RAM.
        createOrRename("00008298", "engine_sync_transition_publish");
        createOrRename("00029c08", "ignition_all_schedule_requests_cancel");
        createOrRename("0000a76c", "knock_sample_history_initialize");
        // September 13 actual cam selectors and engine timeout dependencies.
        createOrRename("0002fddc", "sensor_interface_calibration_refresh");
        createOrRename("000081c0", "engine_signal_timeout_periodic_poll");
        // No live MCP function exists at813C; this is for later reapplication.
        createOrRename("0000813c", "engine_signal_state_initialize");
        createOrRename("00008eda", "injector_all_pending_requests_cancel");
        // September 13 queued fault history and bounded snapshot records.
        createOrRename("00053da8", "diagnostic_class0_history_promote");
        createOrRename("00054d60", "diagnostic_snapshot_select");
        createOrRename("00055064", "diagnostic_snapshot_capture_sources");
        createOrRename("00055518", "diagnostic_snapshot_clear");
        setEOLComment(toAddr("0005bda8"),
            "P0111 ID54 enable is00 in stock and both patches. Descriptor " +
            "5C480 exists but native reporters return early;511F8 clears " +
            "its bit04 while preserving enabled P0112/P0113 bits01/02.");
        // September 13 retained diagnostic mode and reset dispatch.
        createOrRename("00051124", "diagnostic_mode_process_dispatch");
        createOrRename("000567b4", "diagnostic_mode_select_and_publish");
        createOrRename("00051378", "diagnostic_mode_startup_initialize");
        createOrRename("0005690e", "diagnostic_mode_inhibit_publish");
        // September 13 cam edge producers, fault qualification and recovery.
        createOrRename("00069318", "cam_sensor_diagnostic_slow_dispatch");
        createOrRename("00069394", "cam_sensor_edge_count_fault_update");
        createOrRename("00069442", "cam_sensor_missing_edge_fault_update");
        createOrRename("000694c2", "cam_sensor_fault_report_or_recover");
        createOrRename("0000e314", "cam_edge_latch_read_and_clear");
        createOrRename("0000e6b0", "cam_bank0_capture_interrupt_publish");
        createOrRename("0000e6da", "cam_bank1_capture_interrupt_publish");
        // September 13 native diagnostic readiness and temperature history.
        createOrRename("0005116e", "diagnostic_readiness_publish_all");
        createOrRename("000565be", "diagnostic_basic_readiness_update");
        createOrRename("000565f8", "diagnostic_battery_readiness_update");
        createOrRename("0001ae04", "minimum_temperature_history_update");
        // September 13 shutdown state, callback accounting and queued record.
        createOrRename("000310d8", "ignition_off_shutdown_state_update");
        createOrRename("00030fd4", "shutdown_state_initialize");
        createOrRename("0004eec4", "shutdown_diagnostic_counter_update");
        // September 13 AVLS diagnostics, shared timers and digital inputs.
        createOrRename("00069ca8", "avls_electrical_diagnostic_dispatch");
        createOrRename("000705fa", "avls_switch_performance_diagnostic_dispatch");
        createOrRename("00070608", "avls_switch_monitor_qualify");
        createOrRename("000706de", "avls_switch_response_counter_update");
        createOrRename("00070852", "avls_switch_fault_report_or_recover");
        createOrRename("0000f0c0", "avls_pwm_periodic_buffer_write");
        createOrRename("0000f12a", "avls_pwm_transition_restart");
        createOrRename("0000f39c", "avls_osv_current_adc_convert");
        createOrRename("00006bb4", "digital_inputs_two_sample_debounce");
        createOrRename("000193d0", "runtime_digital_switch_flags_publish");
        // September 13 cam performance monitor and healthy recovery.
        createOrRename("0007198c", "avcs_cam_performance_diagnostic_dispatch");
        createOrRename("000719a8", "avcs_cam_performance_monitor_qualify");
        createOrRename("00071ade", "avcs_cam_performance_failure_update");
        createOrRename("00071d2c", "avcs_cam_performance_healthy_update");
        // September 13 native ignition device trace, applied through MCP.
        createOrRename("000296f0", "ignition_schedule_records_initialize");
        createOrRename("00009bcc", "ignition_coil_devices_poll");
        createOrRename("0000997a", "ignition_coil_angle_enqueue");
        createOrRename("000099b4", "ignition_coil_pending_cancel");
        createOrRename("000099e0", "ignition_coil_pending_state");
        createOrRename("00009fec", "ignition_dwell_counts_update");
        createOrRename("00009d3a", "ignition_coil_angle_service");
        createOrRename("00009f9c", "ignition_coil_timer_prepare");
        createOrRename("0002a214", "ignition_auxiliary_mask_update");
        createOrRename("0002a262", "ignition_effective_inhibit_mask");
        createOrRename("00029e14", "ignition_inhibit_transition_update");
        createOrRename("00029aa8", "ignition_schedule_phase_resynchronize");
        // September 9 central review, applied live through MCP and read back.
        createOrRename("0000b536", "protected_float_pair_zero_initialize");
        createOrRename("0000251c", "u16_add_saturating");
        createOrRename("0000254c", "float_scale_offset_to_u16_round_clamp");
        createOrRename("00049530", "protected_float_record_write");
        createOrRename("00016ca4", "coolant_protected_records_initialize");
        createOrRename("00016b04", "engine_coolant_temperature_condition_update");
        createOrRenameData("0004b1cc", "closed_loop_bank_a_delay_descriptor");
        setEOLComment(toAddr("0001ef0a"),
            "4B1CC is the 20-byte bank-A feedback descriptor, paired with " +
            "4B1E0; not an SSM table. Standard SSM handlers begin at 4B6FC.");
        setEOLComment(toAddr("00014fc2"),
            "737DC is u16 debounce limit 3, compared with B2FC. This is " +
            "a call-count threshold, not a throttle-angle float.");
        setEOLComment(toAddr("00024b36"),
            "Rev limiter is hysteretic: BF6D/80 uses 7644C/76450 and " +
            "BF6D/40 uses 76454/76458. State holds between thresholds. " +
            "Stock primary pair is 7000/6970 RPM; main/v2 use 6800/6770.");
        setEOLComment(toAddr("0004677c"),
            "46864 is a ROM literal containing helper address 251C. " +
            "Word literal 4684E resolves to RAM FFFFCF7B.");
        setPlateComment(toAddr("00033830"),
            "Auxiliary duty C858 publisher. Startup descriptor 609EC uses " +
            "B3B0, axis 7BDFC and Q15 u16 data 7BE0C. Not a fan case-7 " +
            "table; physical actuator identity remains unresolved.");
        // September 8 final-throttle override producer trace; no ROM edits.
        createOrRename("0000c5c8", "accelerator_pedal_adc_pair_update");
        createOrRename("00019c04", "ignition_switch_is_on");
        createOrRename("0002efb8", "throttle_ignition_off_counter_update");
        createOrRename("0002f03c", "throttle_stopped_engine_override_update");
        createOrRename("0002f684", "throttle_ignition_off_override_update");
        createOrRename("00061a08", "pedal_pair_agreement_monitor");
        setPlateComment(toAddr("0000c5c8"),
            "Pedal ADC pair AB08/AB0A -> AF80/AF84. Native 180C6 subtracts " +
            "8110/8118 into B464/B468 before percent normalization. Earlier " +
            "cylinder_airflow_pair_update identification was incorrect. AB06 " +
            "is a separate channel repurposed by the wideband patch.");
        setPlateComment(toAddr("0002f03c"),
            "C618 bit 0 override requires C638 low-RPM qualifier: set below " +
            "200 RPM, clear at 300 or above. Both activation routes share this " +
            "gate. Native execution tests include an initially active override.");
        setPlateComment(toAddr("0002f684"),
            "C640 bit 0 requires ignition OFF (19C04 == 0), C614 < 375 and " +
            "other retained qualifiers. 19C04 is native SSM-62 bit 3. C614 " +
            "resets while ignition is on; this is a shutdown window, not an " +
            "after-start timer. No vehicle switch state is inferred.");
        setEOLComment(toAddr("00064b8e"),
            "r13 now holds 8134 bit 0 (pedal-pair monitor), replacing the " +
            "earlier C6FB/8 getter. Its 64D44 use feeds D273/10 -> D274/40.");
        // September 8 downstream cut audit: these six crank-phase channels
        // are injector scheduling, not the previously labelled cam bank.
        createOrRename("0001c5d4", "injector_fuel_cut_inhibit_word_build");
        createOrRename("00026dfc", "injector_inhibit_word_read");
        createOrRename("000263ee", "injector_phase_scheduler");
        createOrRename("000268e8", "injector_channel_pulse_output_gate");
        createOrRename("00026aec", "injector_schedule_inhibit_transition_update");
        createOrRename("00026958", "injector_output_activity_mark");
        createOrRename("00026990", "injector_phase_distance_wrap_720");
        createOrRename("00026f8c", "injector_pulse_width_log_update");
        createOrRename("00003af4", "kernel_raise_interrupt_mask");
        createOrRename("00003b08", "kernel_restore_mask_and_dispatch");
        setPlateComment(toAddr("0001c5d4"),
            "Builds B744: native global cuts publish FFFF, otherwise six channel " +
            "fault bits. Called at the end of stock 24B24 before added master " +
            "cuts. Both added wrappers must publish B744 as well as BF6C bit80; " +
            "BF1C aggregation alone is insufficient. Both complete updates now " +
            "use 3AF4(0x10)/3B08 so higher-priority injector task 5 cannot see " +
            "the temporary clear. See INJECTOR_SCHEDULER_EXECUTION_AUDIT.md.");
        setPlateComment(toAddr("000268e8"),
            "Reads B744 via 26DFC, tests the channel mask from 4B64C, and " +
            "returns before output handoffs when inhibited. Instruction-tested " +
            "for all 64 six-channel masks. Hardware delivery is not emulated.");
        // September 8 retained-system audit: the old boost output was FAN,
        // not CPC purge. Keep these identities reproducible on stock.
        createOrRename("00014dcc", "throttle_position_sensor_process");
        createOrRename("00015192", "runtime_b2bc_bit1_is_set");
        createOrRename("00019c68", "runtime_b51c_bit7_is_set");
        createOrRename("00027de8", "ign_idle_timing_blend_factor_update");
        createOrRename("00027f3e", "ign_idle_timing_target_update");
        createOrRename("00028166", "ign_base_and_idle_timing_update");
        createOrRename("0001baf0", "canister_purge_airflow_and_duty_mode_dispatch");
        createOrRename("0002300a", "purge_fuel_compensation_periodic_update");
        createOrRename("00051194", "diagnostic_descriptor_enabled_return_one");
        createOrRename("000057da", "canister_purge_pwm_compare_interrupt_service");
        createOrRename("00028958", "ignition_c1a0_adjustment_update");
        createOrRename("00029024", "ignition_retard_c1c8_update");
        createOrRename("00029128", "ignition_retard_c1d0_update");
        createOrRename("0002931a", "ignition_retard_c1e0_update");
        createOrRename("0004ac6e", "post_ignition_periodic_state_update_4ac6e");
        createOrRename("00007ab0", "analog_pair_abcc_abd0_voltage_process");
        createOrRename("0002379c", "fueling_correction_beb8_bec0_initialize");
        createOrRename("00023864", "fueling_correction_beb8_bec0_update");
        createOrRename("00045258", "fueling_correction_cefc_cf00_update");
        createOrRename("000452b8", "fueling_correction_cefc_cf00_reciprocal_compute");
        createOrRename("00049b20", "fueling_correction_d114_d118_update");
        createOrRename("00033b92", "intake_avcs_operating_state_flags_update");
        createOrRename("00033ea0", "intake_avcs_runtime_temperature_permission_update");
        createOrRename("00033ffc", "intake_avcs_rpm_oil_temperature_gate_update");
        createOrRename("0003bb26", "runtime_cc4c_bit6_is_set");
        createOrRename("00022fe8", "purge_fuel_compensation_filter_initialize");
        createOrRename("0001bc16", "purge_airflow_from_pulsed_duty_update");
        createOrRename("0001bc90", "purge_airflow_from_fixed_duty_update");
        createOrRename("0001bcae", "purge_airflow_from_zero_duty_update");
        createOrRename("0001bcca", "purge_airflow_target_and_duty_update");
        createOrRename("0001bc0a", "purge_airflow_and_duty_clear");
        createOrRename("0001bd34", "purge_duty_diagnostic_ramp_update");
        createOrRename("0001b800", "purge_airflow_limit_and_correction_update");
        createOrRename("0001b15e", "purge_operating_condition_flags_update");
        createOrRename("00023300", "hot_iat_fuel_compensation_initialize");
        createOrRename("0002333c", "hot_iat_fuel_compensation_update");
        createOrRename("0002354c", "hot_iat_fuel_compensation_table_update");
        createOrRename("000236d4", "hot_iat_fuel_compensation_blend_update");
        createOrRename("000235d6", "hot_iat_fuel_compensation_enable_hysteresis_update");
        createOrRename("00023482", "hot_iat_fuel_compensation_temperature_filter_update");
        createOrRename("0003fc0a", "radiator_fan_duty_compute");
        createOrRename("0003f9e4", "radiator_fan_operating_state_update");
        createOrRename("0003fd38", "radiator_fan_condition_counter_update");
        createOrRename("0000e8c4", "radiator_fan_pwm_output_write");
        createOrRename("00046748", "radiator_fan_coolant_response_monitor");
        createOrRename("0000b182", "canister_purge_pwm_duty_request_write");
        createOrRename("0002bd5c", "idle_target_c460_with_fan_duty_limits_update");
        createOrRename("0002e0e0", "idle_compensation_c540_with_fan_duty_update");
        createOrRename("0001bfbc", "purge_status_b705_bit6_is_set");
        createOrRename("00023054", "purge_bank_fuel_subtraction_publish");
        createOrRename("000231d6", "airflow_compensation_mass_flow_filter_update");
        createOrRename("00046fe8", "diagnostic_override_inactive_return_zero");
        createOrRename("00031878", "ssm_radiator_fan_command_percent_read");
        createOrRename("000318e8", "ssm_canister_purge_duty_ratio_read");
        setPlateComment(
            toAddr("0003fc0a"),
            "Radiator fan request CD54, exported by SSM 0x2F / P92. Coolant " +
            "tables 609C4/609D8 corroborate identity. Earlier purge label was " +
            "wrong: pre-repair master images redirected 3FD8C and overrode " +
            "this fan command even with EBCS OFF. September 8 repair preserves " +
            "stock 3FD8C=E8C4 and retires both injected actuator allocations."
        );
        setPlateComment(
            toAddr("0000e8c4"),
            "Radiator fan PWM writer: F590 = AB84 minus scaled ratio. Physical " +
            "fan fail-safe behavior unverified. Actual CPC request writer is B182."
        );
        setPlateComment(
            toAddr("00027de8"),
            "Idle/base timing blend C134 uses RPM, speed and debounced throttle " +
            "idle flag B2BC bit1, not load directly. Stationary recognized idle " +
            "selects0 (idle target), off-idle1 from either endpoint; intermediate " +
            "blends move0.008 per call. A/D table lookups alone " +
            "do not establish actual idle ignition retard."
        );
        setPlateComment(
            toAddr("00027f3e"),
            "Idle target C138. Stationary maps7828F/78298 flat15.15625deg over " +
            "400..2000RPM; load compensation782AC approximately0.039deg. " +
            "Not final spark timing after downstream corrections."
        );
        setPlateComment(
            toAddr("00028166"),
            "Combines idleC138 and baseC150 using C134 into C130. 281AA is " +
            "inside this function, not a separate function entry. Idle code " +
            "and calibration unchanged by September8 fan/purge repair."
        );
        setPlateComment(
            toAddr("0001baf0"),
            "Actual CPC dispatcher, not fan. September8 master replaces first " +
            "40bytes: B6D4 duty, B6D8 modeled flow and B720 mode zero; tail-call " +
            "unchanged B182 with FR4=0. Canonical stock remains unpatched."
        );
        setPlateComment(
            toAddr("00023054"),
            "Both-bank purge fuel-subtraction publisher. September8 master " +
            "replaces8bytes with unconditional zero store to caller R4 " +
            "(BE60/BE64). Ordinary stock72C purge gate does not prove a " +
            "cold lean-out cause."
        );
        createOrRename(
            "000009f4", "bus_state_controller_and_ram_emulation_initialize"
        );
        createOrRename(
            "00000a1e", "bus_and_port_registers_initialize_a1e"
        );
        createOrRename("00001b4a", "port_registers_initialize_1b4a");
        createOrRename("00001884", "diagnostic_request_download_handle");
        createOrRename("00005d0e", "hardware_register_value_initialize_5d0e");
        createOrRename("0000209c", "table2d_lookup_dispatch");
        createOrRename("00002150", "table3d_lookup_dispatch");
        createOrRename("00002424", "float_first_order_filter_with_snap");
        createOrRename("00002458", "float_divide_guarded");
        createOrRename("000024b0", "float_minimum_select");
        createOrRename("000024c0", "float_clamp");
        createOrRename("000024fc", "float_difference_exceeds_tolerance");
        createOrRename("0000257c", "u16_scale_offset_to_float");
        createOrRename("0000258c", "float_scale_offset_to_u8_round_clamp");
        createOrRename("000025cc", "integer_signal_first_order_filter_q8");
        createOrRename("000025f8", "interp_2axis_float32");
        createOrRename("000026e0", "axis_index_search_float");
        createOrRename("000027d0", "axis_pair_index_search");
        createOrRename("000027f0", "interp_1axis_float32");
        createOrRename(
            "0000505e", "hardware_register_byte_initialize_505e"
        );
        createOrRename("00005076", "no_operation_return_5076");
        createOrRename("0000507a", "no_operation_return_507a");
        createOrRename("0000507e", "no_operation_return_507e");
        createOrRename("00005082", "port_registers_initialize_5082");
        createOrRename("000050c6", "no_operation_return_50c6");
        createOrRename("000050ca", "port_registers_initialize_50ca");
        createOrRename("0000529c", "flash_ram_emulation_disable");
        createOrRename("000052a4", "flash_ram_emulation_disable_thunk");
        createOrRename(
            "000052a8", "aud_system_control_and_module_standby_initialize"
        );
        createOrRename(
            "000052da", "ram_enable_and_fpu_stop_dispatch"
        );
        // Correct an earlier mid-function entry at 0x6892. The real wrapper
        // starts with its PR save and function-pointer load at 0x688E.
        Function misplacedPeriodicWrapper = getFunctionAt(toAddr("00006892"));
        if (misplacedPeriodicWrapper != null) {
            currentProgram.getFunctionManager().removeFunction(toAddr("00006892"));
        }
        createOrRename("0000684c", "engine_control_periodic_wrapper");
        createOrRename("0000688e", "diagnostic_monitor_periodic_wrapper");
        createOrRename("000066c6", "sensor_adc_processing_task");
        createOrRename("00006eac", "adc_scan_results_collect_and_schedule");
        createOrRename("00006ff2", "adc_module_0_scan_results_copy");
        createOrRename("000078ac", "analog_sensor_abac_range_classify");
        createOrRename("00007d08", "analog_signal_scaled_accumulator_update_7d08");
        createOrRename("000079b4", "analog_sensor_abbc_range_classify");
        createOrRename("00007a14", "map_sensor_voltage_to_pressure_process");
        createOrRename("00007a56", "map_sensor_raw_adc_range_classify");
        createOrRename("00008ac0", "engine_signal_timeout_latches_initialize");
        createOrRename("00008ad6", "engine_signal_timeout_latch_update");
        createOrRename("00008b2e", "engine_signal_primary_event_timeout_clear");
        createOrRename("00008b80", "engine_signal_secondary_event_timeout_clear");
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
        createOrRename("0000a9a8", "knock_reference_and_window_parameters_update");
        createOrRename("0000b690", "front_af_sensor_pair_signal_process");
        createOrRename("0000d24c", "periodic_status_counter_service_d24c");
        createOrRename("0000deaa", "fuel_pump_pwm_output_write");
        createOrRename("0000f474", "engine_oil_temperature_sensor_process");
        createOrRename("0000f5f6", "retained_bank_header_invalidate");
        createOrRename(
            "0000f710", "retained_bank_validate_or_begin_reset"
        );
        createOrRename("0000fd5c", "retained_bank_validate_all_subsystems");
        createOrRename("00010690", "retained_bank_cold_initialize_all_subsystems");
        createOrRename("00030a84", "retained_bank_invalid_link_status_publish");
        createOrRename("00004c7c", "startup_stack_relocate_with_saved_pointer");
        createOrRename("00004c82", "startup_stack_restore_saved_pointer");
        createOrRename("0000f950", "startup_ram_pattern_write_readback_test");
        createOrRename("00013330", "runtime_status_b19c_bit7_is_set");
        createOrRename("00016acc", "atmospheric_pressure_sensor_value_condition");
        createOrRename("000172a4", "maf_airflow_temperature_compensation_update");
        createOrRename("0001785c", "airflow_state_coolant_initialization");
        createOrRename("00011ad0", "periodic_engine_control_task_dispatcher");
        createOrRename(
            "00017984", "accelerator_pedal_processing_sequence_update"
        );
        createOrRename("000179ee", "pedal_offset_records_initialize");
        createOrRename(
            "00017a24", "pedal_offset_records_require_initialization"
        );
        createOrRename("00017b2a", "pedal_pair_filter_delta_update");
        createOrRename("000180c6", "accelerator_pedal_pair_normalize");
        createOrRename("000181ea", "accelerator_pedal_pair_select");
        createOrRename("000182ac", "accelerator_pedal_compensation_update");
        createOrRename("00018438", "pedal_conditioning_status_flags_update");
        createOrRename(
            "000184cc", "pedal_conditioning_coefficient_set_a_update"
        );
        createOrRename(
            "0001873c", "pedal_conditioning_coefficient_set_b_update"
        );
        createOrRename("000188f4", "pedal_conditioned_source_update");
        createOrRename("00018a68", "pedal_conditioned_filter_update");
        createOrRename("00018aea", "pedal_conditioned_snapshot_copy");
        createOrRename("00018dac", "front_af_sensor_lambda_condition_filter");
        createOrRename("00018fdc", "front_af_sensor_closed_loop_status_pair_update");
        createOrRename(
            "000192a8", "front_af_sensor_pump_current_pair_scale_update"
        );
        createOrRename("0001add8", "runtime_status_b6b8_bit7_is_set");
        createOrRename("0001a838", "engine_run_counter_update");
        createOrRename("00019f9c", "crank_event_state_publish_and_clear_b52c_bit7");
        createOrRename("0001a0ee", "engine_runtime_b52c_bit6_warmup_gate_update");
        createOrRename("0001a16e", "engine_runtime_b52c_bit7_update_from_ac0c");
        createOrRename("0001a202", "engine_runtime_b52c_bit5_diagnostic_gate_update");
        createOrRename("0001be8e", "purge_operating_state_initialize");
        createOrRename("0001cc34", "cranking_fuel_state_periodic_update");
        createOrRename("0001cfee", "cranking_fuel_state_initialize");
        createOrRename(
            "0001d200", "cranking_clear_flood_throttle_hysteresis_update"
        );
        createOrRename("0001dd04", "final_fueling_multiplier_compose");
        createOrRename("0001d228", "runtime_status_b748_bit7_is_set");
        createOrRename("0001e0c8", "injector_flow_scaling_factor_update");
        createOrRename("00011958", "crank_synchronous_engine_output_task");
        createOrRename("00026208", "crank_output_mode_update_gate");
        createOrRename("00026256", "crank_output_mode_select");
        createOrRename("00026f8c", "injector_scheduled_pulse_width_channels_publish");
        createOrRename("0001e142", "after_start_enrichment_group_a_initialize");
        createOrRename("0001e1b0", "after_start_enrichment_group_a_decay_update");
        createOrRename("0001e41c", "after_start_enrichment_group_b_initialize");
        createOrRename("0001e47a", "after_start_enrichment_group_b_decay_update");
        createOrRename(
            "0001e5e8", "after_start_fueling_compensation_b868_update"
        );
        createOrRename(
            "0001e7e8", "transient_load_fuel_compensation_update"
        );
        createOrRename("0001e9e4", "transient_load_fuel_delta_terms_update");
        createOrRename("0001ead4", "transient_load_fuel_startup_gain_update");
        createOrRename("0001ec62", "transient_load_fuel_history_update");
        createOrRename("0001ca38", "injector_crank_running_duration_select");
        createOrRename("0001ee74", "closed_loop_fuel_control_bank_update");
        createOrRename("0001f0d8", "closed_loop_feedback_bank_state_update");
        createOrRename("0001f1dc", "closed_loop_correction_and_history_initialize");
        createOrRename("000216ea", "fuel_trim_airflow_region_classify");
        createOrRename("000217b8", "legacy_o2_voltage_loop_sequence_update");
        createOrRename("000230e8", "purge_fuel_compensation_ratio_update");
        createOrRename("0004963a", "protected_float_record_validate_and_repair");
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
            "0002ad6c", "throttle_request_filter_update_2ad6c"
        );
        createOrRename("0003191c", "fuel_pump_duty_logger_value_get");
        createOrRename("000312e0", "atmospheric_pressure_sample_trigger_state_get");
        createOrRename("000317ec", "atmospheric_pressure_logger_value_get");
        createOrRename("0003253c", "engine_oil_temperature_logger_convert");
        createOrRename(
            "00033964", "avcs_ocv_current_integrator_initialize"
        );
        createOrRename("00033970", "avcs_ocv_current_integrator_update");
        createOrRename("00033aac", "avcs_ocv_current_filter_error_update");
        createOrRename("00033b12", "avcs_ocv_current_reference_update");
        createOrRename("00034be4", "avcs_ocv_duty_feedback_output");
        createOrRename("0000df00", "avcs_ocv_duty_set");
        createOrRename("0000dfb4", "avcs_ocv_bank_current_select");
        createOrRename("0000e0d0", "avcs_ocv_pair_current_adc_convert");
        createOrRename("0000e290", "avcs_ocv_pwm_buffer_write");
        createOrRename("00069568", "avcs_ocv_circuit_diagnostic_dispatch");
        createOrRename("0000e468", "avcs_cam_capture_convert_and_queue");
        createOrRename("00034208", "avcs_cam_capture_filter_update");
        createOrRename("00034304", "avcs_cam_actual_angle_update");
        createOrRename("0003438e", "avcs_cam_target_error_update");
        createOrRename("00034880", "avcs_rest_learning_convergence_update");
        createOrRename("00034920", "avcs_learned_permission_update");
        createOrRename("0003df56", "knock_grid_avcs_fallback_reset");
        createOrRename("000078ac", "iat_filtered_adc_electrical_status");
        createOrRename("000685d2", "iat_high_voltage_diagnostic_update");
        createOrRename("0006864c", "iat_low_voltage_diagnostic_update");
        createOrRename("000353b0", "intake_avcs_target_by_avls_mode_update");
        createOrRename("00035750", "intake_avcs_tracking_control_update");
        createOrRename(
            "0003d7e4", "ign_per_cylinder_correction_enable_latch_update"
        );
        createOrRename("0003d824", "ign_per_cylinder_correction_array_update");
        createOrRename("0003d8e2", "ign_per_cylinder_correction_state_clear");
        createOrRename(
            "0003d916", "ign_correction_records_any_invalid"
        );
        createOrRename("0003d95a", "ign_per_cylinder_correction_initialize");
        createOrRename("0003d980", "ign_per_cylinder_correction_array_clear");
        createOrRename("0003eb68", "knock_correction_advance_max_select");
        createOrRename("0003f5f0", "ignition_switch_off_spark_inhibit_update");
        createOrRename("0003f650", "radiator_fan_control_state_update");
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
        createOrRename("00047d6a", "atmospheric_pressure_estimate_initialize");
        createOrRename("00047d74", "atmospheric_pressure_estimate_status_check");
        createOrRename("00047db2", "atmospheric_pressure_source_select_update");
        createOrRename("00047dcc", "atmospheric_pressure_estimate_update");
        createOrRename("00047ea6", "atmospheric_pressure_map_sample_gate_update");
        createOrRename("00047f84", "atmospheric_pressure_running_update_gate");
        createOrRename(
            "000490ca", "diagnostic_monitor_counter_update_490ca"
        );
        createOrRename("00064fd0", "front_af_sensor_bank1_inhibit_check");
        createOrRename("00064fbc", "atmospheric_pressure_estimate_fallback_status_get");
        createOrRename("0006500c", "front_af_sensor_bank2_inhibit_check");
        createOrRename("0006504c", "runtime_status_d26d_bit5_get");
        createOrRename("00065168", "airflow_load_fallback_status_get");
        createOrRename("00063174", "diagnostic_fallback_status_flags_update");
        createOrRename("000374f0", "airflow_rpm_diagnostic_monitor_update");
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
        createOrRenameData("ffff8e04", "atmospheric_pressure_stored_estimate");

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
            "Stock/master selector byte0x737D9=0 selects the MAP-derived stored " +
            "estimate0xFFFF8E04 and publishes it to0xFFFFCFBC. A nonzero " +
            "selector uses the conditioned sensor channel0xFFFFB3A8. The " +
            "selected value is not an independent physical barometer reading."
        );
        setPlateComment(
            toAddr("00047dcc"),
            "Updates stored barometric estimate0xFFFF8E04. Fallback status2 " +
            "selects760; CFD0 bit80 samples native MAP ABC4; bit40 learns from " +
            "processed MAP B2A0 plus pressure-loss compensation CFC4; bit20 " +
            "adds2.5. Otherwise holds the previous estimate. Output clamps to " +
            "570..770 mmHg. Exact running-learning behavior on the modified " +
            "engine remains unvalidated."
        );
        setPlateComment(
            toAddr("000317ec"),
            "P24 handler via SSM slot0x4B788. Selector0x737D9=0 reads stored " +
            "baro estimate8E04; nonzero uses raw sensor state ABE8. Divides " +
            "native mmHg by7.50063467 and rounds/clamps to a kPa byte. The " +
            "logger displays720 mmHg for returned byte96 via x*7.5."
        );
        setPlateComment(
            toAddr("00024b24"),
            "Stock RPM limiter sets fuel-cut status 0xFFFFBF6C bit 0x80. The " +
            "periodic task pointer at 0x11D3C is the verified composition point " +
            "for hard-overboost and latched-lean cuts. Its B744 rebuild can " +
            "temporarily clear a continuing added cut. Both wrappers now hold " +
            "the native scheduler lock through their complete decision."
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
            "Native AVCS OCV current integrators C85C/C860 initialize to float 1.0. " +
            "The 2026-09-13 repaired master task1055C ->7EBA0 calls this initializer " +
            "and separately zeros lean state AE9C/AEA0. Earlier rear-O2 labels " +
            "and reclamation of C85C/C860 were incorrect."
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
            "pedal descriptor 0x60F58; state 3 uses 0x60F64. The compared " +
            "0xFFFFB46C signal is conditioned accelerator pedal percent, proven " +
            "by P30 dispatch 4B7A0->3184E. Low lift requests high at curve + " +
            "10 percentage points; high lift releases below the raw curve. " +
            "State 1 uses fixed 15-percent " +
            "thresholds. Stock hard-RPM override is 4000/3800 RPM."
        );
        setPlateComment(
            toAddr("0003fdbc"),
            "Runs the AVLS selector, state machine, committed-mode copy, and " +
            "conditional mode reset via40682. OSV gate405CC runs in11958. Dual VE reads the " +
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
            "native load normalization. Hardened SD at7E18C uses caller FR15 " +
            "RPM saved172CE, also used by load divisor17550. MAP/IAT are " +
            "captured once into saved FR12/13 and restored on all exits. " +
            "No interrupt masking or new static RAM. B428->B42C uses alpha0.06; " +
            "later normal B438 gains are1. Compensation descriptor 0x5EB6C " +
            "currently yields 1.0 everywhere. ECT-override timer threshold " +
            "u16@0x737FA is zero; the other override gate is B748 bit7. This " +
            "path does not establish a 30-second load reduction. Master now " +
            "redirects only local fallback literal173FC to27088 constantzero; " +
            "global diagnostic and cranking/timeout paths remain intact."
        );
        setPlateComment(
            toAddr("00026f8c"),
            "Publishes existing scheduled cylinder pulse counts as microseconds " +
            "(counts * 0.25) at C0B8 onward and latency at C0D8; forms latency-" +
            "inclusive outputs C0D0/C0D4. E60 excludes latency, P21 includes it. " +
            "Does not itself calculate per-cylinder fuel compensation. Previously " +
            "named injector_per_cylinder_base_pulse_width_update."
        );
        setPlateComment(
            toAddr("00017984"),
            "Runs paired accelerator-pedal learning and conditioning. The " +
            "pedal chain publishes B4C0, B4C8, then B46C used by P30, AVLS and " +
            "the idle-air pedal-release qualification. Earlier vehicle-speed " +
            "names were incorrect; see IDLE_AIR_RECOVERY_AUDIT.md."
        );
        setPlateComment(
            toAddr("000188f4"),
            "Conditions accelerator-pedal B470 with a 100-percent upper bound " +
            "into B4C0. Vehicle speed B538 is a gate input, not the quantity " +
            "copied to the output: final min call18A20 takes B470 in its delay " +
            "slot. P30 getter3184E confirms final B46C is pedal percent."
        );
        setPlateComment(
            toAddr("00018a68"),
            "Conditions pedal B4C0 into B4C8 with retained release shaping; " +
            "units remain accelerator-pedal percent."
        );
        setPlateComment(
            toAddr("00018aea"),
            "Copies conditioned pedal B4C8 to B46C in percent. P30 SSM " +
            "address29 selects4B7A0->3184E and divides B46C by100/255. " +
            "B46C also feeds AVLS and18B14 pedal-release flags B484."
        );
        setPlateComment(
            toAddr("00018b14"),
            "Pedal-release qualifier: near-zero B46C sets B483 bit2; B4CC " +
            "counts to u16@73802=3 before B484 bit7. Pedal opening clears " +
            "qualification. Native coverage in test_idle_air_execution.py."
        );
        setPlateComment(
            toAddr("0002c760"),
            "Idle-air feedback eligibility has separate pedal, switch, " +
            "startup and fault gates. B484 qualifies C510 against38 calls; " +
            "C4D9 bit3 permits feedback. C4D6 is a cycling update counter. " +
            "B2BC ignition-idle does not establish air-feedback permission. " +
            "Native fixtures do not prove the recorded near-stall cause."
        );
        setPlateComment(
            toAddr("00007a14"),
            "Live MAP: AB04 -> Q8 filter 25CC with stock/master 72818=256, " +
            "so the new ADC sample passes directly -> ABC8 -> volts using " +
            "5/65536 -> offset 72810 + multiplier 72814 -> mmHg absolute ABC4. " +
            "SD reads ABC4, not atmospheric estimate 8E04/CFBC. Converter adds " +
            "no smoothing lag; acquisition/task latency remains unmeasured."
        );
        setPlateComment(
            toAddr("000025cc"),
            "Integer filter: new + trunc((1 - coefficient/256)*(previous-new)). " +
            "Constant25F4=1/256. MAP coefficient72818=256 passes new sample exactly."
        );
        setPlateComment(
            toAddr("00002424"),
            "fr4=new,fr5=previous,fr6=alpha,fr7=snap epsilon. Returns " +
            "new+(1-alpha)*(previous-new), snapping for nonfinite previous " +
            "or near target. B428->B42C uses73968=0.06; normal later B438 " +
            "gains73974..73980=1; B440 gain73984=0.5."
        );
        setPlateComment(
            toAddr("00065168"),
            "Returns2 iff D26F bit40 set, else0. Producer63174 reads status " +
            "for P0102/P0103/P0101 through descriptors5BE2C/5BE40/5C5FC. " +
            "Master switch bytes5BD57/58=0; P0101 switch5BDBB already0 stock. " +
            "Stock: if2, airflow task replaces B438 with " +
            "max(B2A0*0.00264-0.0851,0). Hardened master bypasses only its " +
            "local173FC call via27088; this shared helper is unchanged."
        );
        setPlateComment(
            toAddr("0000257c"),
            "Returns float(unsigned u16 r4)*fr4 + fr5 in fr0. MAP converter " +
            "uses fr4=5/65536 and fr5=0 for ADC-count to volts conversion."
        );
        setPlateComment(
            toAddr("00006eac"),
            "Collects ADC scan result images, then selects/starts next scans. " +
            "Normal module0 scan sizes4/8/12 all include MAP channel2. " +
            "Caller66C6 then converts MAP at7A14. Absolute task interval and " +
            "end-to-end sensor latency are not established by this trace."
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
            "inputs from the single external wideband. Stock computes " +
            "1+(lambda-1)*K(CFBC) using descriptor 5EA2C and Q15 data 73E08. " +
            "The retained-sensor repair sets all four coefficients to unity; " +
            "readiness, fallback and filter code remain unchanged."
        );
        setPlateComment(
            toAddr("00007ab0"),
            "Converts ADC AB22/AB0E to voltage ABCC/ABD0 using 5/65536. " +
            "SSM 16/17 and 1A/1B handlers identify these as legacy front-O2 " +
            "voltage channels. Separate from master external-wideband ADC AB06. " +
            "Conversion remains active; do not claim all raw-voltage consumers " +
            "were removed by the principal O2 conversion/monitor bypasses."
        );
        setPlateComment(
            toAddr("00049b20"),
            "Auxiliary per-bank fuel adders D114/D118 depend on legacy O2 " +
            "voltages ABCC/ABD0 <0.3 V and conditioned lambda B4E8/B4EC >=1.05, " +
            "plus D110/B90C/BDF8/BE48 gates. Stock chooses 0 or one of two " +
            "0.25 constants at 76384/76388. Master zeros both constants, leaving " +
            "this consumer unchanged. Not a demonstrated cold lean-out cause."
        );
        setPlateComment(
            toAddr("00020564"),
            "Legacy-voltage bank offsets B900/B904 via structures 4B2CC/4B2DC " +
            "and 4B27C/4B28C. Gates BCAB!=1, B90C==0, BB64/BB66>0; " +
            "BC64/BC68 below lookup 5F2E8 selects -0.04 at 760F0, otherwise " +
            "zero at 760F4. Master zeros 760F0; active flags remain stock. " +
            "Offsets feed lambda targets and CEFC/CF00 reciprocal correction."
        );
        setPlateComment(
            toAddr("000202b8"),
            "Bank lambda-target composer. Stock includes BD04/BD08 voltage-loop " +
            "trim (21F0C), including stored 8200/8208 baseline when inactive. " +
            "Master substitutes FLDI0 FR4 at 202CC (BRA delay slot) and 202D0 " +
            "to exclude only this input. Other terms, clamps and main external-" +
            "lambda feedback remain; see RETAINED_ROUTINE_AUDIT.md."
        );
        setPlateComment(
            toAddr("0001ee74"),
            "Retained per-bank closed-loop fuel consumer. In master_patch both banks " +
            "receive the same external-wideband lambda source."
        );
        setPlateComment(
            toAddr("00024bc6"),
            "Separate stock reset writer of BF6C bit80 and BF6D bits80/40. " +
            "Runs only when 1A256 returns 1 (B52C bit7 set). Instruction tests " +
            "verify all 256 flag bytes remain unchanged on its running path. " +
            "Do not remove this reset on the assumption it unconditionally " +
            "overwrites the master lean/overboost cut."
        );
        setPlateComment(
            toAddr("00022aae"),
            "Startup call 1008A through pointer 1024C sets BE38 bit80 and " +
            "initializes CL/OL state. Existing update-style function name " +
            "must not be read as evidence of a periodic permission override."
        );
        setPlateComment(
            toAddr("00022ac2"),
            "State reset restores BE38 bit80 only when 1A256 reports B52C " +
            "bit7 set. The running path is instruction-tested and preserves " +
            "all 256 flag values, including permission cleared by master " +
            "pressure guard. See GUARD_EXECUTION_AUDIT.md."
        );
        setPlateComment(
            toAddr("0001fb16"),
            "Writes coefficient indices 1..21 in 22-float arrays B9D0/BA28, " +
            "88 bytes per bank; slot 0 is initialized by 1F1DC. Master patch supplies both banks from one post-turbo " +
            "AEM signal; these stock pre-turbo response calibrations remain unchanged."
        );
        setPlateComment(
            toAddr("0001fcd4"),
            "Applies the stock 21-float history at BA90/BAE4 (84 bytes per bank), using conditioned " +
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
