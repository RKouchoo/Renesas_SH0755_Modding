# Native FastECU / D2WD610H flash-kernel correction

Status, 2026-09-07 21:17:44: **vehicle Test Write passed** with the dedicated
180nm kernel v1.01. Upload, identity, flash initialization, RAM-buffer transfer
and CRC checks succeeded. **Actual erase/programming remains unverified;
the ECU flash contents were unchanged by this test.**
The Pico remains on bridge firmware 1.1.2. This is an ECU RAM kernel, not Pico
firmware and not an engine-ROM patch.

Native FastECU is the supported path for this project's raw USB CDC adapter.
EcuFlash/OpenPort compatibility would require a separate host/adapter protocol
implementation; moving EcuFlash into a Windows VM does not supply that layer.
See [adapter test results](../TEST_RESULTS.md) for the working full read and
minimal RomRaider RPM profile.

## Observed failure

The installed generic `ssmk_kline_sh7055.bin` has SHA-256
`22bb4c2de1d042074e539e2fe043dd1ceb30fa1815d1ba1d04c239b5018dd5ad`.
Its decoded flash initialization uses the 350nm register tests. Test-write
initialization sent `BE EF 00 01 21 CF` and received
`BE EF 00 03 7F 21 06 56`: a complete, checksum-valid negative reply, detail
`0x06`. In this driver that combines SWE and FKEY compatibility-test failures.
This is not a missing K-line response and occurred before any erase request.
The dedicated SH7055 180nm backend subsequently passed vehicle Test Write.
This confirms initialization and the protected transfer/validation path,
not yet actual erase/programming.

Evidence: local FastECU syslog
`~/.config/FastECU/0.1.0-beta.5/syslogs/log_fastecu_2026-09-07_20h16m32s.txt`;
installed-binary disassembly; and the corresponding
[upstream flash drivers](https://github.com/miikasyvanen/FastECU-kernels/tree/development-iso15765).

## Dedicated replacement

- File: `ssmk_kline_sh7055_180_d2wd.bin`, 4,868 bytes.
- SHA-256: `77364d1235c7f7c7df43688761c38d7a72775be1aec0b114ec3ef661b24c0da7`.
- Runtime identity: `FastECU SH7055 180nm D2WD610H K-Line v1.01`.
- Profile: **Subaru / Legacy/Liberty D2WD610H TEST / 3.0R EZ30R 180nm**.
- Protocol `sub_ecu_denso_sh7055_04_d2wd610h_180`, alias `d2wd610h_180`.
- K-line only, SH7055 / 512 KiB, load address `0xFFFF6004`.

The existing `sti04` profile and generic kernel are unchanged. The dedicated
vehicle entry is appended, preserving existing selection indices. It is not
automatically selected. User configuration backup:
`~/.config/FastECU/0.1.0-beta.5/config/protocols.cfg.before-d2wd180-20260907`.

Actual linked memory allocation (all addresses inclusive):

| Purpose | Address range |
|---|---|
| Uploaded code and read-only constants | `FFFF6004–FFFF7307` |
| Reserved erase microcode | `FFFF8000–FFFF87FF` |
| Reserved programming microcode | `FFFF8800–FFFF8FFF` |
| BSS buffers and globals, NOLOAD | `FFFF9000–FFFFB13F` |
| Reserved stack, initial SP `FFFFCFFC` | `FFFFC000–FFFFCFFF` |

The initial contiguous upstream linker arrangement would not reserve the
microcode destinations. The dedicated linker uses separate regions and
assertions. Startup clears the relocated BSS using linker symbols. The ELF
is SH-2, big-endian (`-m2 -mb`), an instruction subset suitable for SH-2E.
No Ghidra project or stock ROM was modified for this audit.

Additional kernel fixes in `kernel_180nm.patch`:

- Do not restore an unsaved VBR/interrupt mask on early initialization errors.
- Always restore saved CPU state after microcode-copy attempts and clear FKEY.
- Preserve combined error flags; reject invalid erase addresses and writes
  extending past the 512 KiB ROM boundary.
- One definition of the flash buffer, compatible with current GCC defaults.
- Separate test-mode protection gates remain before actual erase/program calls.

Programming clock remains the upstream 40 MHz assumption. The old kernel's
working 62,500-baud timing is supporting evidence, not a new clock measurement.
Stack separation and instruction checks do not validate all silicon behavior.

## Host changes

`host_flash_safety.patch` records changes to the native FastECU host and its
dedicated protocol configuration. They validate complete kernel reply frames,
report initialization error details, validate image/buffer geometry, and return
failure if a real write leaves CRC differences. The dedicated kernel path also
requires the exact runtime identity and a D2WD610H / 512 KiB target image.
Upload checksum construction now stays inside the allocated byte array.

The kernel's reported **11.2 V is a fixed placeholder**, not measured vehicle
voltage. The host labels it unverified. Supply stability needs an independent
check; that field cannot be used as permission to flash.

Test-write success means RAM transfer and CRC validation with erase/program
disabled. It does not prove a real erase or programming cycle will succeed.
Test mode still takes over ECU execution and initializes flash microcodes in
RAM: engine off, correct test connectors, stable power, and exclusive serial
port access are required.

## Vehicle Test Write passed — 21:17:44

The latest attempt in `log_fastecu_2026-09-07_21h14m56s.txt` used the exact
dedicated filename and runtime identity, then received `BE EF 00 01 61 0F`
for `FLASH_DISABLE` instead of the old kernel's negative response. It
transferred/validated the differing 64 KiB block at `00070000` in test mode.
The final pass message was at 21:17:44.672, with ECU flash CRCs unchanged.
The remaining block-15 mismatch is expected: Test Write does not install the
target calibration. Full details are in [TEST_RESULTS.md](../TEST_RESULTS.md).

Some inherited host log wording still says "Erasing ... erased" and marks
"Flash mode succesfully set" as `(EE)`. In this test the erase call was
protected/no-op and the mode response was a valid positive ACK; those words
are misleading, not evidence of an erase or an initialization failure.

## Repeating Test Write / next real-write checkpoint

The following Test Write procedure has now passed. Before a real Write,
confirm the exact intended image and independent supply stability. Keep the
dedicated profile selected and require final CRC agreement plus read-back.
The successful dry run does not establish actual erase/program behavior.

1. Close RomRaider and any other serial client. Confirm engine off and stable
   vehicle power; do not treat the placeholder voltage as a measurement.
2. If a previous kernel is still running and **no real erase/write has been
   attempted**, cycle ignition as appropriate before starting the new test.
   Never apply this restart instruction during a failed real flash operation.
3. Open the intended D2WD610H image, then select the dedicated D2WD610H TEST
   vehicle profile, K-line and the Pico `/dev/cu.usbmodem...` port. Loading or
   reselecting a ROM whose definition says `sti04` can restore the generic
   profile: select the dedicated vehicle **after** loading, and verify the
   operation log names `ssmk_kline_sh7055_180_d2wd.bin` before proceeding.
4. Run **Test Write**, not Write. Verify the exact 180nm identity above, then
   inspect initialization, all buffer-transfer/CRC replies and final status.
5. Stop on any error. Preserve the log. A real write is a separate next step
   after review of the test and confirmation of the exact intended image.
6. A real write must finish with matching block CRCs and ideally a complete
   read-back comparison before considering it verified.

## Rebuild and provenance

Upstream [FastECU-kernels](https://github.com/miikasyvanen/FastECU-kernels),
revision `92adf6bf2009da6dbc330430e1b9209fa6084d83`.
Clone that revision, apply `kernel_180nm.patch`, then use `build_kernel.py`:

```sh
python3 build_kernel.py --source /path/to/FastECU-kernels \
  --prefix /path/to/toolchain/bin/sh-elf --output /path/to/build
```

The local build used [NewOS GCC 14.2.0 Darwin arm64](https://newos.org/toolchains/):
archive `sh-elf-14.2.0-Darwin-arm64.tar.xz`, publisher SHA-256
`08ae3bf848267597214af0ef6ee80027592d472f070afac959fffdc8a9fe2eca`.
On this Mac its assembler/linker need
`DYLD_LIBRARY_PATH=/opt/homebrew/opt/zstd/lib` to resolve libzstd.
No compiler or toolchain installation was changed globally.

`freestanding/` supplies the three minimal memory routines needed by this
no-libc build. The JSON manifest records compiler flags and source hashes;
the map and disassembly accompany the binary. `kernel_source_180nm.tar.gz`
contains the modified upstream source, headers, linker scripts and license
alongside the reviewable patch. Kernel license: GPLv3 or later, see COPYING.txt.
The local build helper and memory routines are supplied alongside the source.

Offline regression checks:

```sh
python3 tests/audit_kernel.py ssmk_kline_sh7055_180_d2wd.elf ssmk_kline_sh7055_180_d2wd.bin
python3 tests/test_kernel_reply_validator.py
```

Both pass. The first executes 29 compiled protected/rejected erase/write paths
and 10 enabled-but-invalid cases in a deliberately limited, fail-closed SH-2
interpreter; any unexpected call or MMIO access fails. This is not a full ECU
emulator. The second compiles the actual host reply/identity/upload helpers
and checks malformed replies, old-kernel rejection and checksum/alignment.

The native FastECU checkout is `/Users/regan/Dev/FastECU`, base revision
`d7198f1c47791e67738576015789ebc2d740e55e`; existing Qt/macOS serial compatibility
changes are separate and preserved. Build its configured ARM64 application with
`make -j8` in `build-macos-6112`. To reproduce this update, apply the host patch
and copy the dedicated `.bin` into FastECU's `kernels/` before building; the
patched resource list embeds it without replacing the generic kernel.
This local app uses Homebrew Qt libraries and
is not a self-contained redistributable package.

Nothing here makes the provisional engine calibration validated for driving.
See the master-patch commissioning documents and the current image comparison
in [TEST_RESULTS.md](../TEST_RESULTS.md).
