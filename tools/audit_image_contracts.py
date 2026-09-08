#!/usr/bin/env python3
"""Check saved-image contracts and replay the image-specific load-status branch.

Uses saved bytes and bounded instruction fixtures; never opens a serial port.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from test_wideband_fuel_guard_execution import GuardMachine  # noqa: E402
from test_load_conditioning_execution import LoadConditioningMachine  # noqa: E402

IMAGES = {
    "stock": "2005 BLE MT.bin",
    "main": "master_patch/D2WD610H_master_patch.bin",
    "v2": "master_patch_v2/D2WD610H_master_patch_v2.bin",
}
PINS = {
    "stock": "ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee",
    "main": "154760a5f2fdadbf6d9221480595f58dc77c6a4eccc492f50899c815aca79e4d",
    "v2": "2fe5f9cc7f960bff1efd784bb29e6c984ccbc025f1d8029c920fd52a3ce25ac9",
}


class StatusAwareLoadMachine(LoadConditioningMachine):
    """Supply the executed image-specific getter result to the existing frame."""

    status_result = None

    def write(self, address, value, size=4, record=False):
        if address == self.STACK - 0x80 + 0x1C and size == 1 and self.status_result is not None:
            value = self.status_result
        return super().write(address, value, size, record)


def main():
    images = {name: (ROOT / path).read_bytes() for name, path in IMAGES.items()}
    report = {"images": {}, "load_fallback_cases": []}
    for name, blob in images.items():
        assert len(blob) == 0x80000
        assert hashlib.sha256(blob).hexdigest() == PINS[name]
        u32 = lambda a: struct.unpack_from(">I", blob, a)[0]
        f32 = lambda a: struct.unpack_from(">f", blob, a)[0]
        report["images"][name] = {
            "path": IMAGES[name], "sha256": PINS[name],
            "load_status_pointer_173FC": f"{u32(0x173FC):08X}",
            "fan_pointer_3FD8C": f"{u32(0x3FD8C):08X}",
            "map_offset_72810": f32(0x72810), "map_slope_72814": f32(0x72814),
            "conditioned_load_alpha_73968": f32(0x73968),
            "slow_negative_gain_76030": f32(0x76030),
            "falling_history_alpha_76050": f32(0x76050),
            "dashpot_decrement_7963C": f32(0x7963C),
            "sd_minimum_7DD10": f32(0x7DD10) if name != "stock" else None,
        }
        if name == "stock":
            continue
        for flag in (0, 0x40):
            getter = GuardMachine(blob)
            getter.write(0xFFFFD26F, flag, 1)
            status = getter.invoke(u32(0x173FC), set())
            for airflow in (12.5, 20.0):
                machine = StatusAwareLoadMachine(blob, load=.5, rpm=1500, coolant=45)
                machine.status_result = status
                result = machine.condition(airflow, 1500, coolant=45, map_mmhg=250)
                expected = (.5749 if status else .5 + .06 * (airflow * 60 / 1500 - .5))
                assert abs(result - expected) < 2e-6, (name, flag, airflow, result)
                report["load_fallback_cases"].append({
                    "image": name, "d26f": flag, "getter_result": status,
                    "airflow_g_s": airflow, "rpm": 1500, "initial_load": .5,
                    "processed_map_mmhg": 250, "result_load_g_rev": result,
                })
    stock = images["stock"]
    assert struct.unpack_from(">I", stock, 0x3F97C)[0] == 0xFFFFCD7F
    assert struct.unpack_from(">I", stock, 0x3FA80)[0] == 0xFFFFCD80
    for n in range(6):
        a = 0xFA94 + 12*n
        assert struct.unpack_from(">IIH", stock, a) == (0xFFFFF640+2*n, 0xFFFFF444+2*n, 1<<n)
        b = 0xFADC + 24*n
        assert struct.unpack_from(">IIIIIH", stock, b) == (
            0xFFFFF650+2*n, 0xFFFFF614+2*n, 0xFFFFF604+2*n,
            0xFFFFF602, 0xFFFFF666, 0x100<<n)
    assert struct.unpack_from(">I", stock, 0x4FC30)[0] == 0x7D790
    report["descriptor_and_literal_checks"] = "PASS: FA94/FADC records; fan RAM literals; internal checksum end"
    report["limits"] = [
        "The load replay executes each image's status getter and retained 1753A..1770A body.",
        "The caller frame and upstream sensor/status producers are supplied fixtures; table interpolation is mathematical.",
        "D26F bit40 is forced for the diagnostic cases; this does not establish its state during historical captures.",
        "No calibration or firmware artifact is written. Timing, engine response and physical sensor transfer are not validated.",
    ]
    destination = ROOT / "docs/reference/evidence/image_contracts.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved-image contracts and 8 load-status cases PASS -> {destination}")


if __name__ == "__main__":
    main()
