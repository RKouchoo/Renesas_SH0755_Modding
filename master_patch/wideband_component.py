#!/usr/bin/env python3
"""Permanent four-stock-O2 delete and external-wideband input component.

This component is intentionally master-patch-only.  It replaces the stock
dual-front A/F signal producer with a 0--5 V wideband decoder on the former MAF
ADC channel, leaves the stock lambda conditioning/closed-loop consumers in
place, bypasses the stock front pump-current diagnostic and every traced rear
O2 processing stage, and clears all 18 mapped D2WD610H O2 DTC switches.

The default calibration is the P0/P1 analog output documented by the supplied,
seller-labelled AEM 50-4110 / 30-4110-style controller:

    gasoline AFR = 2.0 * volts + 10.0
    lambda = (2.0 * volts + 10.0) / 14.64

The controller advertises a legitimate 0--5 V span.  Firmware deliberately
accepts only 0.50--4.50 V (11--19 gasoline AFR) as a conservative operating
plausibility window.  This is not a controller-health test: the supplied unit's
warm-up and disconnected-sensor voltages remain physically unverified and may
fall inside the window.  An out-of-window input publishes 1.0 lambda to the
front-sensor paths but forces both readiness metrics to zero, which makes the
Ghidra-verified bank inhibit helpers return the stock inhibited value (2).  The
logger value at 0xFFFFB098 becomes 0.0 on such a rejection.  A master-only guard
also forces boost-solenoid duty to zero whenever the wideband voltage, MAP/RPM/
IAT validity, minimum boost RPM, or speed-density result is not ready for
electronic control.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PATCH_DIR = ROOT / "patch"
SD_DIR = ROOT / "speed_density"
for directory in (PATCH_DIR, SD_DIR):
    sys.path.insert(0, str(directory))

from sh2_asm import Asm  # noqa: E402
import patch_boost as boost  # noqa: E402
import patch_speed_density as speed_density  # noqa: E402


# Ghidra-verified stock hooks and task pointers.
FRONT_AF_PROCESS_ENTRY = 0x0000B690
FRONT_AF_PROCESS_ENTRY_STOCK = bytes.fromhex("2fe62fd62fc62fb62fa62f96")
FRONT_PUMP_DIAG_TASK_PTR = 0x00006A6C
STOCK_FRONT_PUMP_DIAG_TASK = 0x0000B658
BANK1_INHIBIT_ENTRY = 0x00064FD0
BANK1_INHIBIT_ENTRY_STOCK = bytes.fromhex("907a6000c8088f020009000b")
BANK2_INHIBIT_ENTRY = 0x0006500C
BANK2_INHIBIT_ENTRY_STOCK = bytes.fromhex("905c6000c901600c20088f02")

REAR_O2_PROCESS_ENTRY = 0x0000E0D0
REAR_O2_PROCESS_ENTRY_STOCK = bytes.fromhex("2fd6e020d521e700d421e600")
REAR_O2_TASK_POINTERS = (
    (0x00011488, 0x00033B12, "rear O2 threshold task"),
    (0x0001148C, 0x00033AAC, "rear O2 filter task"),
    (0x00011490, 0x00033970, "rear O2 response-integrator task"),
    (0x00011494, 0x00034BE4, "rear O2 response-ratio task"),
    (0x000114A0, 0x00069568, "rear O2 voltage-diagnostic task"),
)
NOOP_TASK = 0x000066C2  # sensor_processing_return_stub: rts; nop

# The ADC hardware scan remains active after the speed-density component NOPs
# the stock MAF conversion.  This raw unsigned word is therefore available for
# the external wideband without reusing any stock oxygen-sensor input circuit.
RAW_WIDEBAND_ADC = 0xFFFFAB06
RAW_ADC_TO_VOLTS = 5.0 / 65536.0

FRONT_LAMBDA_BANK1 = 0xFFFFAE60
FRONT_LAMBDA_BANK2 = 0xFFFFAE64
FRONT_CURRENT_BANK1 = 0xFFFFAE68
FRONT_CURRENT_BANK2 = 0xFFFFAE6C
FRONT_READY_METRIC_BANK1 = 0xFFFFAE70
FRONT_READY_METRIC_BANK2 = 0xFFFFAE74
WIDEBAND_LOG_LAMBDA_BANK1 = 0xFFFFB098
WIDEBAND_LOG_LAMBDA_BANK2 = 0xFFFFB09C

# All D2WD610H O2 sensor/heater switches present in the matching definition.
# No extra P0133/P0139/P0140/P0141/P0159/P0160/P0161 switches are mapped for
# this calibration, so the traced runtime tasks are bypassed as well.
DISABLED_O2_DTC_SWITCHES = {
    "P0031": 0x0005BDAC,
    "P0032": 0x0005BDAA,
    "P0037": 0x0005BDAB,
    "P0038": 0x0005BDA9,
    "P0051": 0x0005BDB4,
    "P0052": 0x0005BDB3,
    "P0057": 0x0005BDC1,
    "P0058": 0x0005BDC2,
    "P0131": 0x0005BDA0,
    "P0132": 0x0005BDA2,
    "P0134": 0x0005BDBD,
    "P0137": 0x0005BD9F,
    "P0138": 0x0005BDA4,
    "P0151": 0x0005BDA1,
    "P0152": 0x0005BDA3,
    "P0154": 0x0005BDBC,
    "P0157": 0x0005BDC3,
    "P0158": 0x0005BDC4,
}

# Free-space layout.  0x7D91C is retained because the existing conservative
# calibration builder uses it as the O2-component signature.  The code lives
# after the speed-density component (which ends at 0x7E39B) and before the
# checksum-covered free-space ceiling at 0x7FAF7.
MASTER_O2_SIGNATURE_ADDR = 0x0007D91C
CONSTANTS_ADDR = 0x0007E400
RAW_TO_VOLTS_ADDR = 0x0007E400
LAMBDA_SLOPE_ADDR = 0x0007E404
LAMBDA_OFFSET_ADDR = 0x0007E408
VALID_MIN_VOLTS_ADDR = 0x0007E40C
VALID_MAX_VOLTS_ADDR = 0x0007E410
READY_VALID_VALUE_ADDR = 0x0007E414
READY_THRESHOLD_ADDR = 0x0007E418
WIDEBAND_UPDATE_ADDR = 0x0007E440
INHIBIT_HELPER_ADDR = 0x0007E520
BOOST_READY_GUARD_ADDR = 0x0007E560
COMPONENT_END = 0x0007E6FF

# Supplied P0/P1 table: 0 V = 10.00 gasoline AFR and each 0.125 V step adds
# 0.25 AFR.  The same sheet defines gasoline AFR as lambda * 14.64.
GASOLINE_STOICH_AFR = 14.64
AFR_SLOPE_PER_VOLT = 2.0
AFR_OFFSET = 10.0
LAMBDA_SLOPE = AFR_SLOPE_PER_VOLT / GASOLINE_STOICH_AFR
LAMBDA_OFFSET = AFR_OFFSET / GASOLINE_STOICH_AFR
VALID_MIN_VOLTS = 0.50
VALID_MAX_VOLTS = 4.50
READY_VALID_VALUE = 50.0
READY_THRESHOLD = 35.0


def be32(value: int) -> bytes:
    return struct.pack(">I", value & 0xFFFFFFFF)


def f32(value: float) -> bytes:
    return struct.pack(">f", value)


def build_entry_hook(address: int, target: int) -> bytes:
    """Twelve-byte tail-jump hook with an inline literal."""
    assembler = Asm(address)
    assembler.movl_pool(1, target).jmp(1).nop().nop()
    result = assembler.assemble()
    assert len(result) == 12
    return result


def emit_store_float(assembler: Asm, source_fr: int, destination: int) -> None:
    assembler.movl_pool(1, destination).fmov_store(source_fr, 1)


def build_wideband_update() -> bytes:
    """Decode the former-MAF ADC and publish two synthetic front A/F banks."""
    a = Asm(WIDEBAND_UPDATE_ADDR)

    # Controller volts = unsigned ADC count * 5/65536.
    a.movl_pool(1, RAW_WIDEBAND_ADC)
    a.movw_at(0, 1).extu_w(0, 0).lds_fpul(0).float_fpul(0)
    a.movl_pool(1, RAW_TO_VOLTS_ADDR).fmov_load(1, 1).fmul(1, 0)
    a.fcmpeq(0, 0).bf("invalid")

    # Inclusive 0.50--4.50 V plausibility window. NaN constants fail closed.
    a.movl_pool(1, VALID_MIN_VOLTS_ADDR).fmov_load(1, 1)
    a.fcmpeq(1, 1).bf("invalid")
    a.fcmpgt(0, 1).bt("invalid")  # minimum > volts
    a.movl_pool(1, VALID_MAX_VOLTS_ADDR).fmov_load(1, 1)
    a.fcmpeq(1, 1).bf("invalid")
    a.fcmpgt(1, 0).bt("invalid")  # volts > maximum

    # Supplied 50-4110 P0/P1 analog transfer. Reject NaN/non-positive/infinite.
    a.movl_pool(1, LAMBDA_SLOPE_ADDR).fmov_load(1, 1).fmul(1, 0)
    a.movl_pool(1, LAMBDA_OFFSET_ADDR).fmov_load(1, 1).fadd(1, 0)
    a.fcmpeq(0, 0).bf("invalid")
    a.fldi0(2).fcmpgt(2, 0).bf("invalid")
    a.movl_pool(1, 0x0007E188).fmov_load(2, 1)  # SD component's FLT_MAX
    a.fcmpgt(2, 0).bt("invalid")

    # Valid lambda feeds both stock bank paths and both logger mirrors.
    for destination in (
        FRONT_LAMBDA_BANK1,
        FRONT_LAMBDA_BANK2,
        WIDEBAND_LOG_LAMBDA_BANK1,
        WIDEBAND_LOG_LAMBDA_BANK2,
    ):
        emit_store_float(a, 0, destination)
    a.fldi0(1)
    emit_store_float(a, 1, FRONT_CURRENT_BANK1)
    emit_store_float(a, 1, FRONT_CURRENT_BANK2)
    a.movl_pool(1, READY_VALID_VALUE_ADDR).fmov_load(1, 1)
    emit_store_float(a, 1, FRONT_READY_METRIC_BANK1)
    emit_store_float(a, 1, FRONT_READY_METRIC_BANK2)
    a.rts().nop()

    # Fault behavior: stoichiometric placeholder for stock signal consumers,
    # zero logger sentinel, zero pump-current placeholders, and not-ready state.
    a.label("invalid")
    a.fldi1(0)
    emit_store_float(a, 0, FRONT_LAMBDA_BANK1)
    emit_store_float(a, 0, FRONT_LAMBDA_BANK2)
    a.fldi0(1)
    for destination in (
        WIDEBAND_LOG_LAMBDA_BANK1,
        WIDEBAND_LOG_LAMBDA_BANK2,
        FRONT_CURRENT_BANK1,
        FRONT_CURRENT_BANK2,
        FRONT_READY_METRIC_BANK1,
        FRONT_READY_METRIC_BANK2,
    ):
        emit_store_float(a, 1, destination)
    a.rts().nop()
    return a.assemble()


def build_inhibit_helper() -> bytes:
    """Return stock status 0 when ready, otherwise inhibited status 2."""
    a = Asm(INHIBIT_HELPER_ADDR)
    a.movl_pool(1, FRONT_READY_METRIC_BANK1).fmov_load(0, 1)
    a.movl_pool(1, READY_THRESHOLD_ADDR).fmov_load(1, 1)
    a.fcmpgt(1, 0).bt("ready")  # ready metric > threshold; NaN is invalid
    a.rts().mov_imm(2, 0)
    a.label("ready")
    a.rts().mov_imm(0, 0)
    return a.assemble()


def emit_runtime_range_gate(
    assembler: Asm,
    value_address: int,
    minimum_address: int,
    maximum_address: int,
) -> None:
    """Branch to ``invalid`` unless value and both bounds form a valid range."""
    assembler.movl_pool(1, value_address).fmov_load(0, 1)
    assembler.fcmpeq(0, 0).bf("invalid")
    assembler.movl_pool(1, minimum_address).fmov_load(1, 1)
    assembler.fcmpeq(1, 1).bf("invalid")
    assembler.fcmpgt(0, 1).bt("invalid")  # minimum > value
    assembler.movl_pool(1, maximum_address).fmov_load(1, 1)
    assembler.fcmpeq(1, 1).bf("invalid")
    assembler.fcmpgt(1, 0).bt("invalid")  # value > maximum


def build_boost_ready_guard() -> bytes:
    """Tail-gate boost on wideband and current speed-density prerequisites."""
    a = Asm(BOOST_READY_GUARD_ADDR)

    # Both feedback banks are usable only while voltage passes plausibility.
    a.movl_pool(1, FRONT_READY_METRIC_BANK1).fmov_load(0, 1)
    a.movl_pool(1, READY_THRESHOLD_ADDR).fmov_load(1, 1)
    a.fcmpgt(1, 0).bf("invalid")

    # Never command electronic duty when any live speed-density input is NaN,
    # infinite, outside its editable validity window, or has malformed bounds.
    emit_runtime_range_gate(
        a,
        speed_density.MAP_ADDR,
        speed_density.MAP_MIN_ADDR,
        speed_density.MAP_MAX_ADDR,
    )
    emit_runtime_range_gate(
        a,
        speed_density.RPM_ADDR,
        speed_density.RPM_MIN_ADDR,
        speed_density.RPM_MAX_ADDR,
    )
    emit_runtime_range_gate(
        a,
        speed_density.IAT_ADDR,
        speed_density.IAT_MIN_ADDR,
        speed_density.IAT_MAX_ADDR,
    )

    # The first shared boost-table breakpoint is also the minimum electronic-
    # control RPM. This prevents Kp from energizing the valve during key-on or
    # cranking while keeping the gate aligned with an editable RomRaider axis.
    a.movl_pool(1, boost.RPM_AXIS).fmov_load(1, 1)
    a.fcmpeq(1, 1).bf("invalid")
    a.movl_pool(1, speed_density.RPM_ADDR).fmov_load(0, 1)
    a.fcmpgt(0, 1).bt("invalid")  # first boost RPM > current RPM

    # The SD helper publishes its fixed 500 g/s sentinel for every other bad
    # calibration/lookup/arithmetic path. At this 5 psi baseline legitimate
    # modeled airflow is well below the sentinel; equality therefore fails
    # closed even if the normal configurable airflow cap is also reached.
    a.movl_pool(1, speed_density.FINAL_MASS_AIRFLOW_ADDR).fmov_load(0, 1)
    a.fcmpeq(0, 0).bf("invalid")
    a.movl_pool(1, speed_density.FAILSAFE_AIRFLOW_ADDR).fmov_load(1, 1)
    a.fcmpeq(1, 1).bf("invalid")
    a.fcmpeq(1, 0).bt("invalid")

    a.movl_pool(1, boost.STUB_ADDR).jmp(1).nop()
    a.label("invalid")
    a.fldi0(4)
    a.movl_pool(1, boost.STOCK_OUTPUT).jmp(1).nop()
    return a.assemble()


def build_blobs() -> list[tuple[str, int, bytes]]:
    constants = b"".join(
        f32(value)
        for value in (
            RAW_ADC_TO_VOLTS,
            LAMBDA_SLOPE,
            LAMBDA_OFFSET,
            VALID_MIN_VOLTS,
            VALID_MAX_VOLTS,
            READY_VALID_VALUE,
            READY_THRESHOLD,
        )
    )
    return [
        ("master_O2_signature", MASTER_O2_SIGNATURE_ADDR, b"\x01"),
        ("wideband_constants", CONSTANTS_ADDR, constants),
        ("wideband_front_pair_update", WIDEBAND_UPDATE_ADDR, build_wideband_update()),
        ("wideband_bank_inhibit_helper", INHIBIT_HELPER_ADDR, build_inhibit_helper()),
        ("wideband_boost_ready_guard", BOOST_READY_GUARD_ADDR, build_boost_ready_guard()),
    ]


def checked_write(
    rom: bytearray,
    address: int,
    expected: bytes,
    replacement: bytes,
    label: str,
) -> None:
    current = bytes(rom[address : address + len(expected)])
    if current != expected:
        raise SystemExit(
            "REFUSING: %s @0x%05X is %s (expected %s)"
            % (label, address, current.hex(), expected.hex())
        )
    rom[address : address + len(replacement)] = replacement


def apply_to_rom(rom: bytearray) -> list[tuple[str, int, bytes]]:
    """Apply the permanent master O2/wideband component to a stock-derived ROM."""
    if len(rom) != 0x80000:
        raise SystemExit("REFUSING: wideband component requires a 512 KiB ROM")

    blobs = build_blobs()
    for name, address, data in blobs:
        end = address + len(data)
        if name == "master_O2_signature":
            allowed = address == MASTER_O2_SIGNATURE_ADDR and end <= 0x7D920
        else:
            allowed = CONSTANTS_ADDR <= address and end - 1 <= COMPONENT_END
        if not allowed:
            raise SystemExit("layout error: %s @0x%05X..0x%05X" % (name, address, end - 1))
        if any(byte != 0xFF for byte in rom[address:end]):
            raise SystemExit(
                "REFUSING: %s @0x%05X..0x%05X is not free flash"
                % (name, address, end - 1)
            )

    checked_write(
        rom,
        FRONT_AF_PROCESS_ENTRY,
        FRONT_AF_PROCESS_ENTRY_STOCK,
        build_entry_hook(FRONT_AF_PROCESS_ENTRY, WIDEBAND_UPDATE_ADDR),
        "front A/F pair signal-process entry",
    )
    checked_write(
        rom,
        BANK1_INHIBIT_ENTRY,
        BANK1_INHIBIT_ENTRY_STOCK,
        build_entry_hook(BANK1_INHIBIT_ENTRY, INHIBIT_HELPER_ADDR),
        "bank-1 front A/F inhibit helper",
    )
    checked_write(
        rom,
        BANK2_INHIBIT_ENTRY,
        BANK2_INHIBIT_ENTRY_STOCK,
        build_entry_hook(BANK2_INHIBIT_ENTRY, INHIBIT_HELPER_ADDR),
        "bank-2 front A/F inhibit helper",
    )
    checked_write(
        rom,
        FRONT_PUMP_DIAG_TASK_PTR,
        be32(STOCK_FRONT_PUMP_DIAG_TASK),
        be32(NOOP_TASK),
        "front A/F pump-current diagnostic task pointer",
    )
    checked_write(
        rom,
        REAR_O2_PROCESS_ENTRY,
        REAR_O2_PROCESS_ENTRY_STOCK,
        build_entry_hook(REAR_O2_PROCESS_ENTRY, NOOP_TASK),
        "rear O2 pair ADC-conversion entry",
    )
    for pointer, stock_target, label in REAR_O2_TASK_POINTERS:
        checked_write(rom, pointer, be32(stock_target), be32(NOOP_TASK), label)
    for code, address in DISABLED_O2_DTC_SWITCHES.items():
        checked_write(rom, address, b"\x01", b"\x00", "%s O2 DTC switch" % code)

    # boost.apply_to_rom() must run first; retain its full controller and add a
    # master-only ready gate ahead of it.
    checked_write(
        rom,
        boost.HIJACK_LITERAL,
        be32(boost.STUB_ADDR),
        be32(BOOST_READY_GUARD_ADDR),
        "boost output tail-call literal",
    )

    for _, address, data in blobs:
        rom[address : address + len(data)] = data
    return blobs


if __name__ == "__main__":
    raise SystemExit("wideband_component.py is a component; run build_master_patch.py")
