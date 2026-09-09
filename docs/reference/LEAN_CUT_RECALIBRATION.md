# Lean Fuel Cut Recalibration & Fuel Economy Safety — 2026-09-09

[Reference home](README.md) · [Signals](SIGNALS.md) · [Findings](FINDINGS.md)

## Background & Rationale

The master patch includes an integrated wideband-based **Latched Lean Fuel Cut** (`0x7EACD`) designed to protect the engine against fuel starvation (e.g. failing fuel pump, clogged injector, or fuel pressure regulator failure) under boost.

### Why 0.5 PSI / 13.0 AFR Was Overly Aggressive
1. **0.5 PSI Gauge is Practically Naturally Aspirated:**
   * 0.5 psi is only **3.4 kPa above atmospheric pressure** (~100 kPa MAP). 
   * A stock, naturally aspirated EZ30R reaches atmospheric pressure during normal city driving and gentle acceleration. In that region, running **12.8 to 13.5 AFR is completely safe and normal**.
   * Arming a hard safety cut at 0.5 psi meant normal spoolup transitions that momentarily touched 13.0 AFR could trip the cut.
2. **The "Latch" Interruption:**
   * Once tripped, the cut latched until manifold pressure dropped below -0.5 psi (deep vacuum).
   * A false trip during spoolup caused a violent bucking / hesitation, forcing the driver to completely take their foot off the gas to reset it.
3. **Wasted Fuel & Poor Economy ("Petrol is expensive"):**
   * Because the cut was armed at 0.5 psi, the Primary Open Loop fueling table was forced to dump heavy fuel (**11.5–12.0 AFR**) at very low loads (~1.22 g/rev) just to avoid tripping the cut.
   * Dumping fuel at 0–1 psi burns through expensive 98 RON during normal city driving for zero benefit. Piston-melting heat and knock only occur under **actual boost** (3 to 5+ psi), where cylinder pressure is high.

---

## The Solution in `master_patch_v2`

The safety cut thresholds have been recalibrated for the 5 psi wastegate spring setup:

| Parameter | Address | Old Setting | New Master v2 Setting | Purpose |
|---|---|:---:|:---:|---|
| **Arming Pressure** | `0x7EAD4` | **0.50 psi** | **2.50 psi** (~117 kPa MAP) | Stays completely out of the way off-boost. Only arms when the turbo is in real boost. |
| **Reset Pressure** | `0x7EAD8` | **-0.50 psi** (vacuum) | **+1.50 psi** (~110 kPa MAP) | Resets as soon as you back out of boost, rather than forcing you to lift off completely. |
| **AFR Trip Threshold** | `0x7EADC` | **13.0:1** | **12.8:1** (0.874 lambda) | Under 2.5–5.0 psi boost, target is ~11.4:1. If AFR exceeds 12.8:1, fuel cuts to protect the engine. |

---

### Benefits

1. **Daily Driving Fuel Economy:** 
   Off-boost cruising and light-throttle spoolup can run clean, efficient AFRs (13.0–13.8:1) without fear of tripping a hard fuel cut.
2. **Smooth Spoolup:** 
   No false latching or jerky fuel cutouts while rolling into boost.
3. **100% Catastrophic Protection Intact:** 
   If a fuel pump fails or fuel pressure drops while running 5 psi at WOT, the engine is instantly cut and saved before high exhaust gas temperatures or knock can damage pistons.
