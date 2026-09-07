#!/usr/bin/env python3
"""Read Pico K-line diagnostics over USB EP0 without opening its serial port.

Requires firmware 1.1.2 or newer with the KLD1 diagnostics request and libusb
(on macOS: Homebrew's libusb). This helper never claims an interface, detaches a
driver, changes configuration, resets the device, or transmits on K-line.
Reported GPIO levels are digital samples, not voltmeter measurements: they do
not establish the actual K-line voltage or prove that the wiring is correct.

Examples:
    python3 read_diagnostics.py
    python3 read_diagnostics.py --watch 10 --interval 1
    python3 read_diagnostics.py --serial YOUR_PICO_SERIAL
"""

import argparse
import ctypes
import ctypes.util
import json
import math
import struct
import sys
import time


VID = 0x2E8A
PID = 0x000A
MAGIC = 0x31444C4B
PACKET_LENGTH = 64
FLAG_NAMES = (
    "usb_mounted",
    "tud_ready",
    "dtr",
    "rts",
    "break_active",
    "coding_pending",
    "gp4_level",
    "gp5_level",
)
COUNTER_NAMES = (
    "host_rx_bytes",
    "uart_tx_bytes",
    "uart_rx_bytes",
    "usb_tx_queued_bytes",
    "error_count",
    "uart_error_bits",
    "host_to_line_pending",
    "line_to_host_pending",
)


class DiagnosticsError(Exception):
    """A USB operation or diagnostics packet could not be validated."""


def decode_snapshot(packet):
    """Decode and validate a 64-byte KLD1 packet, without USB or other I/O."""
    if len(packet) != PACKET_LENGTH:
        raise DiagnosticsError(
            f"Expected {PACKET_LENGTH} diagnostics bytes; received {len(packet)}."
        )
    words = struct.unpack("<16I", packet)
    if words[0] != MAGIC:
        raise DiagnosticsError(
            f"Unexpected diagnostics magic 0x{words[0]:08x}; expected KLD1."
        )
    major = words[1] >> 16
    minor = (words[1] >> 8) & 0xFF
    patch = words[1] & 0xFF
    if major == 0:
        raise DiagnosticsError("Invalid firmware version in diagnostics packet.")
    if words[3] & ~0xFF:
        raise DiagnosticsError(
            f"Unknown KLD1 flag bits in 0x{words[3]:08x}; update this helper."
        )
    result = {
        "protocol": "KLD1",
        "firmware": f"{major}.{minor}.{patch}",
        "uptime_ms": words[2],
        "flags": {
            name: bool(words[3] & (1 << bit))
            for bit, name in enumerate(FLAG_NAMES)
        },
        "tx_gpio_ctrl": f"0x{words[4]:08x}",
        "rx_gpio_ctrl": f"0x{words[5]:08x}",
        "requested_baud": words[6],
        "actual_baud": words[7],
    }
    result.update(zip(COUNTER_NAMES, words[8:]))
    return result


class DeviceDescriptor(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("bcdUSB", ctypes.c_uint16),
        ("bDeviceClass", ctypes.c_uint8),
        ("bDeviceSubClass", ctypes.c_uint8),
        ("bDeviceProtocol", ctypes.c_uint8),
        ("bMaxPacketSize0", ctypes.c_uint8),
        ("idVendor", ctypes.c_uint16),
        ("idProduct", ctypes.c_uint16),
        ("bcdDevice", ctypes.c_uint16),
        ("iManufacturer", ctypes.c_uint8),
        ("iProduct", ctypes.c_uint8),
        ("iSerialNumber", ctypes.c_uint8),
        ("bNumConfigurations", ctypes.c_uint8),
    ]


def load_libusb():
    candidates = [
        "/opt/homebrew/lib/libusb-1.0.dylib",
        "/usr/local/lib/libusb-1.0.dylib",
        ctypes.util.find_library("usb-1.0"),
    ]
    library = None
    for candidate in dict.fromkeys(candidates):
        if not candidate:
            continue
        try:
            library = ctypes.CDLL(candidate)
            break
        except OSError:
            pass
    if library is None:
        raise DiagnosticsError(
            "libusb was not found. On macOS, install it with: brew install libusb"
        )

    pointer = ctypes.c_void_p
    pointer_to_pointer = ctypes.POINTER(pointer)
    byte_pointer = ctypes.POINTER(ctypes.c_ubyte)
    signatures = {
        "libusb_init": ([pointer_to_pointer], ctypes.c_int),
        "libusb_exit": ([pointer], None),
        "libusb_get_device_list": (
            [pointer, ctypes.POINTER(pointer_to_pointer)], ctypes.c_ssize_t
        ),
        "libusb_free_device_list": ([pointer_to_pointer, ctypes.c_int], None),
        "libusb_get_device_descriptor": (
            [pointer, ctypes.POINTER(DeviceDescriptor)], ctypes.c_int
        ),
        "libusb_open": ([pointer, pointer_to_pointer], ctypes.c_int),
        "libusb_close": ([pointer], None),
        "libusb_get_string_descriptor_ascii": (
            [pointer, ctypes.c_uint8, byte_pointer, ctypes.c_int], ctypes.c_int
        ),
        "libusb_control_transfer": (
            [pointer, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint16,
             ctypes.c_uint16, byte_pointer, ctypes.c_uint16, ctypes.c_uint],
            ctypes.c_int,
        ),
        "libusb_error_name": ([ctypes.c_int], ctypes.c_char_p),
    }
    for name, (arguments, return_type) in signatures.items():
        function = getattr(library, name)
        function.argtypes = arguments
        function.restype = return_type
    return library


class PicoDiagnostics:
    def __init__(self, serial=None):
        self.lib = load_libusb()
        self.context = ctypes.c_void_p()
        self.handle = ctypes.c_void_p()
        self.serial = None
        result = self.lib.libusb_init(ctypes.byref(self.context))
        if result < 0:
            raise DiagnosticsError(f"libusb initialization failed: {self.error(result)}")
        try:
            self.select_device(serial)
        except BaseException:
            self.close()
            raise

    def error(self, code):
        name = self.lib.libusb_error_name(code)
        return name.decode("ascii", errors="replace") if name else str(code)

    def read_serial(self, handle, index):
        if index == 0:
            return None
        buffer = (ctypes.c_ubyte * 256)()
        size = self.lib.libusb_get_string_descriptor_ascii(handle, index, buffer, 256)
        if size < 0:
            raise DiagnosticsError(f"Cannot read Pico serial number: {self.error(size)}")
        try:
            return bytes(buffer[:size]).decode("ascii")
        except UnicodeDecodeError as error:
            raise DiagnosticsError("Pico serial descriptor was not ASCII.") from error

    def select_device(self, requested_serial):
        devices = ctypes.POINTER(ctypes.c_void_p)()
        count = self.lib.libusb_get_device_list(self.context, ctypes.byref(devices))
        if count < 0:
            raise DiagnosticsError(f"USB enumeration failed: {self.error(count)}")
        try:
            candidates = []
            for index in range(count):
                descriptor = DeviceDescriptor()
                result = self.lib.libusb_get_device_descriptor(
                    devices[index], ctypes.byref(descriptor)
                )
                if result < 0:
                    raise DiagnosticsError(
                        f"Cannot inspect a USB device descriptor: {self.error(result)}"
                    )
                if descriptor.idVendor == VID and descriptor.idProduct == PID:
                    candidates.append((devices[index], descriptor.iSerialNumber))
            if not candidates:
                raise DiagnosticsError("No Pico USB CDC device (2e8a:000a) was found.")
            if requested_serial is None and len(candidates) != 1:
                raise DiagnosticsError(
                    f"Found {len(candidates)} matching Picos; select one with --serial."
                )
            matches = 0
            for device, serial_index in candidates:
                handle = ctypes.c_void_p()
                result = self.lib.libusb_open(device, ctypes.byref(handle))
                if result < 0:
                    raise DiagnosticsError(f"Cannot open a matching Pico: {self.error(result)}")
                try:
                    serial = self.read_serial(handle, serial_index)
                    if requested_serial is None or serial == requested_serial:
                        matches += 1
                        if matches > 1:
                            raise DiagnosticsError(
                                "Multiple Picos have the requested serial; disconnect duplicates."
                            )
                        self.handle = handle
                        self.serial = serial
                        handle = ctypes.c_void_p()
                finally:
                    if handle.value:
                        self.lib.libusb_close(handle)
            if matches != 1:
                raise DiagnosticsError("No matching Pico has the requested serial number.")
        finally:
            self.lib.libusb_free_device_list(devices, 1)

    def snapshot(self):
        buffer = (ctypes.c_ubyte * PACKET_LENGTH)()
        size = self.lib.libusb_control_transfer(
            self.handle, 0xC0, 0x40, 0, 0, buffer, PACKET_LENGTH, 1500
        )
        if size == -9:  # LIBUSB_ERROR_PIPE: unsupported request / endpoint stall.
            raise DiagnosticsError(
                "Pico stalled the diagnostics request. Firmware may predate 1.1.2 "
                "or lack KLD1 diagnostics; no K-line traffic was sent."
            )
        if size < 0:
            raise DiagnosticsError(f"USB diagnostics read failed: {self.error(size)}")
        result = decode_snapshot(bytes(buffer[:size]))
        result["usb_serial"] = self.serial
        return result

    def close(self):
        if self.handle.value:
            self.lib.libusb_close(self.handle)
            self.handle = ctypes.c_void_p()
        if self.context.value:
            self.lib.libusb_exit(self.context)
            self.context = ctypes.c_void_p()

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.close()


def snapshot_count(value):
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("watch count must be an integer from 1 to 30") from error
    if not 1 <= number <= 30:
        raise argparse.ArgumentTypeError("watch count must be from 1 to 30")
    return number


def snapshot_interval(value):
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("interval must be from 0.1 to 5 seconds") from error
    if not math.isfinite(number) or not 0.1 <= number <= 5:
        raise argparse.ArgumentTypeError("interval must be from 0.1 to 5 seconds")
    return number


def ascii_serial(value):
    if not value or not value.isascii():
        raise argparse.ArgumentTypeError("serial must be a nonempty ASCII string")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--serial", type=ascii_serial, help="select the Pico with this exact USB serial")
    parser.add_argument("--watch", type=snapshot_count, metavar="N", help="print N JSON-line snapshots (1–30)")
    parser.add_argument("--interval", type=snapshot_interval, default=1.0, metavar="SECONDS", help="watch interval, 0.1–5 seconds (default: 1)")
    args = parser.parse_args(argv)
    try:
        with PicoDiagnostics(args.serial) as pico:
            for index in range(args.watch or 1):
                if index:
                    time.sleep(args.interval)
                print(json.dumps(pico.snapshot(), indent=None if args.watch else 2), flush=True)
    except DiagnosticsError as error:
        print(f"Diagnostics: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
