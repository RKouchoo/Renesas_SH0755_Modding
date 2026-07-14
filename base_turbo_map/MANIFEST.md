# Build Manifest

Build date: 2026-07-15. Target: D2WD610H / ECU ID `3C5A387116`, 512 KiB Renesas SH7055 ROM.

| Artifact | SHA-256 |
|---|---|
| Canonical root stock `../2005 BLE MT.bin` | `ed0fe0341d97fb760c2cda3f07277f861495d32f6520e3ce8047b8b0f7bfd4ee` |
| Original SRF `../base_roms/2005 BLE MT.srf` | `05eae5322072449d90e20e20125d5333738675168d623a320735958bfc7619aa` |
| Combined reference `../patch/D2WD610H_boost_single_front_af.bin` | `019e06e509afce2e798bfe29543e2536524c259d3ab6683c7dd3131ee069fb5e` |
| A4TE002B STI-pink donor `../base_roms/A4TE002B-2003-JDM-Subaru-Impreza-STi.hex` | `e3cc868a51476aaa25c1ffb63e8af8ba3e35ca4ace404e842f193bf117754b44` |
| Base turbo output `D2WD610H_5psi_98RON_base_turbo.bin` | `fd9a9354c7a9f2d82813253d41b17adb058b68ceb3f426a0c197a6322fbf2c0f` |

The SRF parser confirms its `MEMD` payload at file offset `0x1CD` is byte-identical to both stock
BIN copies. The combined stage is regenerated from that stock payload and must be byte-identical to
the canonical combined artifact before calibration begins.

The 192-KiB injector donor must identify as `A4TE002B` at `0x200`, match the hash above, and contain
flow raw `4900` at `0x2866B` plus latency raw `{697,372,245,171,95}` at `0x28673`. Source:
[bludgod/RomRaider commit 639f3c7](https://github.com/bludgod/RomRaider/blob/639f3c73c1bd8efee48347bd71bb064211b95242/JDM/Impreza/A4TE002B-2003-JDM-Subaru-Impreza-STi.hex).

Final Subaru checksum table entry:

- table: `0x7FB80`;
- covered start/end: `0x00002000` / `0x0007FAF7`;
- stored checksum difference: `0x4BD6335B`;
- additive target: `0x5AA5A55A`;
- validation: pass.

The checksum implementation follows the open-source RomRaider `RomChecksum` algorithm: sum
big-endian 32-bit words over the declared range modulo 2^32 and store
`0x5AA5A55A - sum` in the table entry.

Verification result:

```text
base turbo map binary audit PASS
calibration delta: 1043 bytes across 39 owned writes
fueling: no high-load cell made leaner; both banks matched
injectors: A4TE002B STI-pink scalar/deadtime; ratio-scaled cranking/tip-in IPW
ignition: no base/KCA cell made more advanced; axes extend to 3.0 g/rev
AVLS: eligible at 2500 RPM; forced high cam 3200/3000 RPM
boost: zero WGDC, Kp, and maximum duty; hard cut retained
operating range: 6800/6770 RPM; 5 psi target held through redline
MAF/load limits: MAF max-encoded; engine-load cap retained at 4.0 g/rev
```

No Ghidra session was used for this calibration pass. All edited items were already identified,
named, documented tables with matching RomRaider definitions; therefore no new Ghidra functions
were inspected or left unnamed.
