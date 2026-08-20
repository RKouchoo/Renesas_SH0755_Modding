// Reapply the stock-function names and comments established while auditing
// D2WD610H master_patch. Safe to run repeatedly on the canonical stock program.
// @category D2WD610H

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
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

    @Override
    public void run() throws Exception {
        createOrRename("00001884", "diagnostic_request_download_handle");
        createOrRename("00002458", "float_divide_guarded");
        createOrRename("000024c0", "float_clamp");
        createOrRename("000024fc", "float_difference_exceeds_tolerance");
        createOrRename("000078ac", "analog_sensor_abac_range_classify");
        createOrRename("000079b4", "analog_sensor_abbc_range_classify");
        createOrRename("00007a14", "map_sensor_voltage_to_pressure_process");
        createOrRename("00007a56", "map_sensor_raw_adc_range_classify");
        createOrRename("000098cc", "injector_battery_voltage_latency_lookup");
        createOrRename("0000a9a8", "injector_control_lookup_sequence_a9a8");
        createOrRename("0000b690", "front_af_sensor_pair_signal_process");
        createOrRename("00013330", "runtime_status_b6c0_bit7_is_set");
        createOrRename("00018dac", "front_af_sensor_lambda_condition_filter");
        createOrRename(
            "000192a8", "front_af_sensor_pump_current_pair_offset_clamp_update"
        );
        createOrRename("0001d228", "runtime_status_b748_bit7_is_set");
        createOrRename("0001e0c8", "injector_flow_scaling_factor_update");
        createOrRename("0001ee74", "closed_loop_fuel_control_bank_update");
        createOrRename("00027088", "constant_zero_return");
        createOrRename("00028354", "ign_avcs_tracking_blend_factor_update");
        createOrRename("00028418", "ign_base_timing_map_blend");
        createOrRename("000284b8", "ign_base_timing_select");
        createOrRename("000353b0", "intake_avcs_target_by_avls_mode_update");
        createOrRename("00035750", "intake_avcs_tracking_control_update");
        createOrRename("0003eb68", "knock_correction_advance_max_select");
        createOrRename("0003ffda", "avls_threshold_curve_selector_state_update");
        createOrRename("000400ee", "avls_curve_selector_load_band_latches_update");
        createOrRename("00064fd0", "front_af_sensor_bank1_inhibit_check");
        createOrRename("0006500c", "front_af_sensor_bank2_inhibit_check");
        createOrRename("0006504c", "runtime_status_d26d_bit5_get");

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
            "0xFFFFC984. Legacy A/B identify AVLS modes, not cylinder banks."
        );
        setPlateComment(
            toAddr("00035750"),
            "Downstream intake AVCS tracking/control update using per-bank measured " +
            "and conditioned target state. The legacy A/B target maps selected " +
            "upstream are AVLS operating modes, not bank identities."
        );
        setPlateComment(
            toAddr("0003ffda"),
            "Updates AVLS threshold-curve selector state 0xFFFFCD9C. Normal valid " +
            "operation uses hysteretic fallback-load bands: state 1 below the " +
            "first band or when gated, state 2 after the 15-unit latch while the " +
            "115-unit latch is clear, and state 3 after the 115-unit latch. " +
            "Runtime-status, delay, and fault gates can force state 1."
        );
        setPlateComment(
            toAddr("000400ee"),
            "Updates two hysteretic latches in 0xFFFFCD9E from fallback load " +
            "0xFFFFCF94: bit 0 sets at 15 and clears below 13; bit 1 sets at 115 " +
            "and clears below 113. The selector update uses these to choose " +
            "state 1, 2, or 3."
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
