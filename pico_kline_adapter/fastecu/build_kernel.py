#!/usr/bin/env python3
"""Build the reviewed SH7055/180 nm K-line RAM kernel; never access the ECU.

Requires the pinned FastECU-kernels checkout plus the local safety patch and a
SuperH GCC toolchain. Output is intentionally separate from installed kernels.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REVISION = "92adf6bf2009da6dbc330430e1b9209fa6084d83"
SOURCES = ("cmd_parser.c", "eep_funcs.c", "main.c", "crc.c", "mfg_ssm.c",
           "wdt.c", "platf_7055.c", "pl_flash_705x_180nm.c")


def run(args, **kwargs):
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--prefix", required=True, help="Path prefix ending in sh-elf")
    parser.add_argument("--output", type=Path, default=HERE / "build")
    args = parser.parse_args()
    source = args.source.resolve()
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise SystemExit(f"Refusing unreviewed upstream revision: {revision}")
    linker = source / "ldscripts/lkr_subaru_7055_180.ld"
    if not linker.is_file():
        raise SystemExit("Dedicated 180 nm memory-reservation linker script is missing")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cc = args.prefix + "-gcc"
    flags = ["-m2", "-mb", "-Os", "-ffreestanding", "-fno-builtin",
             "-ffunction-sections", "-fdata-sections", "-fomit-frame-pointer",
             "-std=gnu99", "-Wall", "-Wextra", "-Wstrict-prototypes",
             "-fstack-usage", "-g", "-DSH7055", "-DKLINE", "-DVER_180",
             "-Dssmk", '-DPLATF="SH7055"', "-DEEP_COMMS3", "-DEEP_COMMS3_CS_PJ3",
             "-I", str(HERE / "freestanding"), "-I", str(source)]
    objects = []
    for path in [source / name for name in SOURCES] + [HERE / "freestanding/memory.c"]:
        obj = output / (path.stem + ".o")
        run([cc, *flags, "-c", path, "-o", obj], cwd=output)
        objects.append(obj)
    start = output / "start_ssm.o"
    run([cc, "-m2", "-mb", "-g", "-x", "assembler-with-cpp", "-c",
         source / "start_ssm.s", "-o", start], cwd=output)
    elf = output / "ssmk_kline_sh7055_180_d2wd.elf"
    binary = elf.with_suffix(".bin")
    run([cc, "-m2", "-mb", "-nostdlib", start, *objects, "-T", linker,
         f"-Wl,-Map={elf.with_suffix('.map')},--cref,--gc-sections",
         "-lgcc", "-o", elf], cwd=output)
    run([args.prefix + "-objcopy", "-O", "binary", "-S", elf, binary])
    run([args.prefix + "-size", "-A", elf])
    with elf.with_suffix(".disasm").open("w") as stream:
        run([args.prefix + "-objdump", "-d", elf], stdout=stream)
    data = binary.read_bytes()
    if not 0 < len(data) <= 0x8000 - 0x6004:
        raise SystemExit("Kernel upload payload reaches reserved flash microcode RAM")
    if b"SH7055 180nm D2WD610H" not in data:
        raise SystemExit("Unique reviewed-kernel identity is missing")
    manifest = {
        "upstream_revision": revision,
        "source_sha256": {
            str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(source.rglob("*"))
            if path.is_file() and path.suffix in {".c", ".h", ".s", ".ld"}
            and ".git" not in path.parts
        },
        "support_sha256": {
            str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [Path(__file__).resolve(), *sorted((HERE / "freestanding").glob("*"))]
            if path.is_file()
        },
        "compiler": subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
        "flags": flags,
        "load_address": "0xFFFF6004",
        "payload_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "status": "BUILT ONLY: not vehicle-tested or flash-qualified",
    }
    binary.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
