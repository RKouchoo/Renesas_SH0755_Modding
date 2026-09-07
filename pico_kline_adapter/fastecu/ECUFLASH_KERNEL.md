# EcuFlash sti04 / SH7055 kernel candidate

2026-09-07, offline investigation only. User reports the car was last
successfully flashed using EcuFlash's `sti04` / SH7055 path. This makes that
implementation useful evidence, but the exact EcuFlash version used for that
operation has not yet been established from an old successful log.

## Confirmed from the locally available installer

- File: `/Users/regan/Downloads/ecuflash_1444870_win.exe`.
- Installer product/file version: `1.44.0.4870`.
- SHA-256: `e9242d8882530fc320164f13e4107ceff9c862f5bd2e66debdbebe4895fffa0b`.
- `rommetadata/read templates/read_sti04.xml` declares flashmethod `sti04`,
  memory model `SH7055`, and checksum module `subarudbw`.
- The archive listing does not expose a standalone SH7055 flash-kernel binary.
  Its main `ecuflash.exe` has an unusual/packed-looking PE layout and does not
  expose ordinary kernel identity strings in a simple static string scan.
  This is evidence that extraction needs more work, not proof of a particular
  packer or the precise internal payload location.
- No raw EcuFlash ECU kernel has been recovered or audited yet. The XML
  template cannot substitute for one.

Extraction was performed without executing the Windows installer or program,
under `/private/tmp/ecuflash-kernel-inspect/`. The temporary extraction tool
was the publisher's macOS 7-Zip 26.03; archive SHA-256
`5ca87677072c59f5602e5c49baa27d4694bacd2259b4e507f0094249d4281480`
matched the official GitHub release asset digest. Nothing was installed
globally, no drivers were run and no vehicle communications occurred.

## Compatibility checks still required

FastECU's `kernelcomms.h` names the `BE EF` command family as OpenECU-style
commands. It is therefore premature to claim EcuFlash must use a different
runtime protocol. It is equally premature to assume a drop-in replacement.

Compare the recovered candidate with the actual FastECU host expectations:

1. SH7055 silicon/flash variant, load address and entry point (current
   FastECU path uploads at `FFFF6004`), memory layout and watchdog handling.
2. Upload encryption and aligned 16-bit `5AA5` checksum, then 62,500-baud
   runtime framing, command IDs, reply lengths and checksums.
3. ROM/buffer CRC: current host polynomial `5AA5A55A`, 512-byte messages and
   4096-byte validation buffers. Do not assume ordinary CRC-32 is equivalent.
4. Flash-disable/test-mode behavior, actual erase/programming commands and
   flash-enable requirements. Check any extra adapter output used by EcuFlash;
   successful operation with an OpenPort does not prove K-line alone supplies
   every condition it used.
5. Exact candidate identity and content hash under a separate reviewed
   profile. Never overwrite the generic or dedicated 180nm kernel filenames
   to bypass the identity guard.

Tactrix's [EcuFlash release notes](https://www.tactrix.com/index.php?Itemid=58&id=36&layout=blog&option=com_content&view=category)
include applying 12 V Vpp for 2004–2007 DBW Subarus in case a model checks it.
That is a reason to audit the requirement for this ECU, **not** an instruction
to apply voltage to an unverified pin.

Subsequent result: at 21:17:44 the dedicated FastECU 180nm v1.01 kernel passed
vehicle Test Write, with flash contents unchanged. This removes the immediate
need to recover an EcuFlash kernel just to clear the initialization blocker;
actual programming remains untested. EcuFlash-kernel extraction is still an
unverified alternative, not an installed solution. See TEST_RESULTS.md one
directory above. No engine ROM or stock reference was changed here.
