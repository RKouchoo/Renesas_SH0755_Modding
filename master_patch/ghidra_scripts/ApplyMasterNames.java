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
        createOrRename("00028354", "ign_blend_factor_from_advance_multiplier");
        createOrRename("00028418", "ign_base_timing_map_blend");
        createOrRename("000284b8", "ign_base_timing_select");
        createOrRename("0003eb68", "knock_correction_advance_max_select");
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
            "Builds and clamps the effective ignition advance-multiplier blend " +
            "factor published at 0xFFFFC17C. A factor of 1.0 selects the primary " +
            "timing endpoint; 0.0 selects the conservative endpoint."
        );
        setPlateComment(
            toAddr("00028418"),
            "Looks up the six legacy base maps. For each selectable cam path, " +
            "timing = multiplier-1.0 endpoint * k + multiplier-0.0 endpoint * " +
            "(1-k), using k at 0xFFFFC17C."
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
