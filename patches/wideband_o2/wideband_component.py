#!/usr/bin/env python3
"""Permanent four-stock-O2 delete and external-wideband input component.

This component is intentionally master-patch-only.  It replaces the stock
dual-front A/F signal producer with a 0--5 V wideband decoder on the former MAF
ADC channel, leaves the stock lambda conditioning/closed-loop consumers in
place, bypasses the stock front pump-current diagnostic, and clears all 18
mapped D2WD610H O2 DTC switches. Native AVCS current feedback, output and
diagnostics remain active; those routines were previously mislabelled rear O2.

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
logger value at 0xFFFFAE8C becomes 0.0 on such a rejection. The former boost
actuator guard is retired: its output was misidentified radiator-fan PWM.
Its reserved allocation contains only a return and erased bytes. Stock fan
control remains intact; independent overboost and lean fuel cuts are separate
components, not an electronic wastegate controller.

The retained-sensor audit neutralizes factory atmospheric lambda correction,
auxiliary fuel adders, and feedback-target corrections dependent on legacy O2
voltages. Some other raw
voltage consumers remain; this is not a claim of complete circuit independence.

Process-flow finding, 2026-09-13: leaving the native feedback consumers in
place does not preserve their operation. The installed 50/0 readiness scheme
conflicts with 1903A: valid 50 clears B512/B513 bits C0, so 1EE0C publishes
B90D/B90E=0 and each scheduled bank update resets B8D4/B8D8 to 1.0.
See docs/reference/PATCH_PROCESS_FLOW.md and the connected native feedback
tests. No readiness calibration change is made by this audit; heater and
other consumers must be reviewed before changing this shared convention.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import struct
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PATCH_DIR = ROOT / "patches/core"
SD_DIR = ROOT / "patches/speed_density"
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

# 2026-09-13 full-flow correction: these belong to the OCV solenoids.
# 34BE4 -> DF00 -> E290 writes BFR6A/B at F510/F512. 69568 reports
# P2088/P2089/P2092/P2093. Never retire them as oxygen-sensor processing.
AVCS_CURRENT_PROCESS_ENTRY = 0x0000E0D0
AVCS_CURRENT_PROCESS_ENTRY_STOCK = bytes.fromhex("2fd6e020d521e700d421e600")
PRESERVED_AVCS_TASK_POINTERS = (
    (0x00011488, 0x00033B12, "AVCS current reference task"),
    (0x0001148C, 0x00033AAC, "AVCS current filter/error task"),
    (0x00011490, 0x00033970, "AVCS current integrator task"),
    (0x00011494, 0x00034BE4, "AVCS duty/PWM output task"),
    (0x000114A0, 0x00069568, "OCV solenoid circuit diagnostic task"),
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
# The replaced B690 producer owned this raw front-current pair. Its only
# remaining writer is startup B49A, which zeroes both before task operation.
# B098/B09C belong to native OCV-current feedback and must remain untouched.
WIDEBAND_LOG_LAMBDA_BANK1 = 0xFFFFAE8C
WIDEBAND_LOG_LAMBDA_BANK2 = 0xFFFFAE90

# All D2WD610H O2 sensor/heater switches present in the matching definition.
# No extra P0133/P0139/P0140/P0141/P0159/P0160/P0161 switches are mapped for
# this calibration. Retained voltage workers are documented separately.
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
# after the speed-density wrapper (which ends at 0x7E3A3) and before the
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
# Exact end of the guard allocation.  Dual-VE ownership begins at 0x7E640;
# keeping this bound exact makes any future wideband growth fail instead of
# silently entering the next component's region.
COMPONENT_END = 0x0007E63F

# Supplied P0/P1 table: 0 V = 10.00 gasoline AFR and each 0.125 V step adds
# 0.25 AFR.  The same sheet defines gasoline AFR as lambda * 14.64.
GASOLINE_STOICH_AFR = 14.64
AFR_SLOPE_PER_VOLT = 2.0
AFR_OFFSET = 10.0
LAMBDA_SLOPE = AFR_SLOPE_PER_VOLT / GASOLINE_STOICH_AFR
LAMBDA_OFFSET = AFR_OFFSET / GASOLINE_STOICH_AFR
VALID_MIN_VOLTS = 0.50
VALID_MAX_VOLTS = 4.50
# Known native-status incompatibility at this value; see module audit note.
READY_VALID_VALUE = 50.0
READY_THRESHOLD = 35.0

# These factory-sensor corrections are incompatible with an externally decoded
# lambda source. Neutralize their data while retaining the surrounding logic.
# 18DAC computes 1 + (lambda - 1) * lookup(5EA2C, baro); Q15 0x8000 is unity.
# 49B20 adds either zero or one of the two constants below to D114/D118 after
# comparing conditioned lambda with disconnected legacy O2 voltages ABCC/ABD0.
# This is an additive fuel term, NOT the main short-term feedback controller.
STOCK_SENSOR_DATA_PATCHES = (
    ("external lambda: unity factory atmospheric correction", 0x73E08,
     bytes.fromhex("b3339b448df48000"), bytes.fromhex("8000800080008000")),
    ("legacy O2-voltage auxiliary fuel adders disabled", 0x76384,
     bytes.fromhex("3e8000003e800000"), b"\x00" * 8),
    ("legacy O2-voltage bank target offset disabled", 0x760F0,
     bytes.fromhex("bd23d70a"), b"\x00" * 4),
)
# 202B8 forms the main lambda-feedback target. BD04/BD08 are a separate
# voltage-based trim produced by 21F0C, including its stored 8200/8208 baseline.
# Ignore this contribution at the consumer; retain every other target term,
# clamp, main lambda-feedback controller and its ordinary learned fuel trims.
# Bank 1's load is in a BRA delay slot: FLDI0 is also a single SH-2E word.
STOCK_SENSOR_CODE_PATCHES = (
    ("bank 1 target ignores legacy voltage trim", 0x202CC,
     bytes.fromhex("f428"), bytes.fromhex("f48d")),
    ("bank 2 target ignores legacy voltage trim", 0x202D0,
     bytes.fromhex("f418"), bytes.fromhex("f48d")),
)
STOCK_SENSOR_PATCHES = STOCK_SENSOR_DATA_PATCHES + STOCK_SENSOR_CODE_PATCHES
STOCK_SENSOR_CONSUMER_HASHES = (
    (0x18DAC, 0x18FDC, "1c5f196779bd34ad348440281a7f5bbc543e67f5e8fd72f6671fe0017f4d27d1"),
    (0x49B20, 0x49C40, "f4cd9c92dfdee0fc56ac14dbfc5b2a606fff3b74184184b6894ead97b8533f31"),
    (0x20564, 0x205FA, "b3df6ac4d1137c21bc3c9f222bf0249297e5a9875623f6cc7c5b3fcab155e510"),
    (0x20658, 0x20680, "d9ce9ccc0ba9fb1efcd180b4b97aa8ac03a24c1f856e439b1ab400033b87f292"),
    (0x202B8, 0x20326, "466008c5b2ede9cabc599b40d2f21850c7a9d0f54eaabaee4b1a098449924fea"),
    (0x203C2, 0x203F0, "1a671f5b7eb9738953e0036c9f0e8c67e021122561cfe74dddadebdf5eaecfcd"),
    (0x24C0, 0x24DA, "418acd98c9daff410179b5f38d2b96369b6c6eebc47674aa744cfbacd88b09d3"),
)


def check_stock_sensor_consumers(rom: bytes | bytearray) -> None:
    if bytes(rom[0x5EA2C:0x5EA40]) != bytes.fromhex(
        "0004080000073df800073e083800000000000000"
    ):
        raise SystemExit("REFUSING: factory lambda atmospheric descriptor changed")
    for address, expected in (
        (0x5F2E8, "000504000007689c000768b03ba0000000000000"),
        (0x4B27C, "ffffb8f4ffffbb50ffffb900ffffb910ffffb8f8ffffbb54ffffb904ffffb914"),
        (0x4B2CC, "ffffb918ffffbb64ffffbc64ffffbca9ffffb919ffffbb66ffffbc68ffffbcaa"),
        (0x760F4, "00000000"),  # Other bank-offset branch must also stay zero.
    ):
        data = bytes.fromhex(expected)
        if bytes(rom[address:address + len(data)]) != data:
            raise SystemExit(f"REFUSING: legacy voltage descriptor/data changed @0x{address:05X}")
    for start, end, digest in STOCK_SENSOR_CONSUMER_HASHES:
        consumer = bytearray(rom[start:end])
        # Verify stock and installed images with the same anchors. Only exact
        # replacement words are normalized; any other modification still fails.
        for _, address, expected, replacement in STOCK_SENSOR_CODE_PATCHES:
            if start <= address and address + len(replacement) <= end:
                offset = address - start
                if consumer[offset:offset + len(replacement)] == replacement:
                    consumer[offset:offset + len(expected)] = expected
        if hashlib.sha256(consumer).hexdigest() != digest:
            raise SystemExit(f"REFUSING: factory sensor consumer changed @0x{start:05X}")


def apply_stock_sensor_corrections(rom: bytearray) -> None:
    """Guard every anchor before any bounded data/instruction writes."""
    check_stock_sensor_consumers(rom)
    for label, address, expected, _ in STOCK_SENSOR_PATCHES:
        if bytes(rom[address:address + len(expected)]) != expected:
            raise SystemExit(f"REFUSING: {label} bytes changed @0x{address:05X}")
    for _, address, _, replacement in STOCK_SENSOR_PATCHES:
        rom[address:address + len(replacement)] = replacement


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
    """Retired actuator guard; preserve allocation, no output/state access.

    The former guard targeted radiator-fan PWM. Electronic actuator support
    is removed, not merely switched off. Wideband decoding/inhibits and the
    independent pressure/lean fuel-cut safety remain active elsewhere.
    """
    return bytes.fromhex("000b0009") + b"\xff" * (
        COMPONENT_END + 1 - BOOST_READY_GUARD_ADDR - 4
    )


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
        ("retired_actuator_guard_reservation", BOOST_READY_GUARD_ADDR, build_boost_ready_guard()),
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


def check_avcs_dependencies(rom: bytes | bytearray) -> None:
    """Reject the former OCV deletion or edits to the restored native loop."""
    for pointer, target, label in PRESERVED_AVCS_TASK_POINTERS:
        if bytes(rom[pointer:pointer+4]) != be32(target):
            raise SystemExit(f"REFUSING: {label} must remain native @0x{pointer:05X}")
    for start, end, digest in (
        (0xDF00, 0xE314, "ed207f8dde9f0a56037bef64ff760746612ee2e9cd08bc0adb426a1abb606ab0"),
        (0x33964, 0x33B92, "d37f9738a7145eb7da728a6727b61f7c8db086522e058e82d6db56666d14972e"),
        (0x34BE4, 0x34D50, "a40b408e81c14ce087b53508a343db4fd4d5fec971f1352cd0769fc1a98eb2ee"),
    ):
        if hashlib.sha256(rom[start:end]).hexdigest() != digest:
            raise SystemExit(f"REFUSING: native AVCS dependency changed @0x{start:05X}")


def check_reclaimed_front_scratch(rom: bytes | bytearray) -> None:
    """Prove the two native owners of relocated scratch are bypassed.

    AE8C/AE90 were B690 raw-current values; B49A initializes them to zero.
    AE9C/AEA0 are a two-bank intermediate owned only by B8CC, whose sole
    runtime entry is B658 at task pointer 6A6C. The retained BAE0/BCB4 ADC
    handshake uses AE84/88, AEC0/4 and AEC8, not either reclaimed range.
    """
    if bytes(rom[FRONT_AF_PROCESS_ENTRY:FRONT_AF_PROCESS_ENTRY+12]) != (
            build_entry_hook(FRONT_AF_PROCESS_ENTRY, WIDEBAND_UPDATE_ADDR)):
        raise SystemExit("REFUSING: raw front-current producer still owns WB logger RAM")
    if bytes(rom[FRONT_PUMP_DIAG_TASK_PTR:FRONT_PUMP_DIAG_TASK_PTR+4]) != be32(NOOP_TASK):
        raise SystemExit("REFUSING: front impedance producer still owns lean-cut RAM")
    for start, end, digest in (
        (0xB8CC, 0xBAE0, "96cbd035f8a247ce4e355f8048fe7ff6f7de72d90f9adee64b7626ca919b7a20"),
        (0xB49A, 0xB554, "72add82c1fc228b74ce6c5e9456cb2a6a721dccd1d2300e6ec3de78aeb366984"),
    ):
        if hashlib.sha256(rom[start:end]).hexdigest() != digest:
            raise SystemExit(f"REFUSING: reclaimed front scratch owner changed @0x{start:05X}")


def apply_to_rom(rom: bytearray) -> list[tuple[str, int, bytes]]:
    """Apply the permanent master O2/wideband component to a stock-derived ROM."""
    if len(rom) != 0x80000:
        raise SystemExit("REFUSING: wideband component requires a 512 KiB ROM")

    check_avcs_dependencies(rom)

    # Refuse an upstream fan hijack before making any O2 changes. This is an
    # identity check, never an output hook owned by this component.
    if bytes(rom[boost.HIJACK_LITERAL : boost.HIJACK_LITERAL + 4]) != be32(boost.STOCK_OUTPUT):
        raise SystemExit("REFUSING: stock radiator-fan output literal was changed")

    # Preflight the consumer identity and original correction bytes before any
    # wideband edits. The final writes below use the same guarded helper.
    check_stock_sensor_consumers(rom)
    for label, address, expected, _ in STOCK_SENSOR_PATCHES:
        if bytes(rom[address:address + len(expected)]) != expected:
            raise SystemExit(f"REFUSING: {label} bytes changed @0x{address:05X}")

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
    for code, address in DISABLED_O2_DTC_SWITCHES.items():
        checked_write(rom, address, b"\x01", b"\x00", "%s O2 DTC switch" % code)

    for _, address, data in blobs:
        rom[address : address + len(data)] = data
    apply_stock_sensor_corrections(rom)
    return blobs


if __name__ == "__main__":
    raise SystemExit("wideband_component.py is a component; run build_master_patch.py")
