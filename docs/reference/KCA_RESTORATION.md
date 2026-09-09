# KCA Functionality Restoration & Timing Split — 2026-09-09

[Reference home](README.md) · [Signals](SIGNALS.md) · [Findings](FINDINGS.md)

## Background

Subaru factory ECUs calculate ignition timing using the additive formula:
$$\text{Total Timing} = \text{Base Timing} + (\text{Knock Correction Advance [KCA]} \times \text{IAM}) - \text{Feedback Knock (FBKC)} - \text{Fine Learning (FLKC)}$$

In the factory naturally aspirated EZ30R calibration, Subaru intentionally retarded the Base Timing tables (running negative values like -5° to -14° under heavy load at low RPM) and placed +10° to +18° of advance into the KCA tables.

### The Problem in Early Turbo Master Patches
1. The previous patch author zeroed out KCA Max for all loads $\ge 1.22$ g/rev on the assumption that "knock advance under boost is dangerous."
2. However, the author left Base Timing constrained to the resampled factory base maps, which were designed assuming +15° of KCA would be added on top.
3. This left the engine firing at only 4°–7° under load, causing severe sluggishness, high EGTs, and late combustion that blew unburned oxygen into the exhaust (reading false lean 18.1 AFR on the wideband).
4. Furthermore, zeroing KCA disabled the **Ignition Advance Multiplier (IAM)** global safety net: if the engine ever encountered bad fuel or severe heat-soak, dropping IAM had zero effect ($0.0 \times 0 = 0$).

---

## The Solution: Middle-Ground Turbo Timing Split

KCA functionality is fully restored in `master_patch_v2` using the standard factory turbo architecture:

### 1. Base Timing (The Safe Floor)
Base Timing represents the safe, limp-home floor if IAM drops to 0.0:
* **Off-boost / Light Cruise (loads $\le 1.09$ g/rev):** Retains full factory cruise advance (24°–42°) with the low-RPM tip-in floor (10°–15° at 800–1600 RPM).
* **Under 5 psi Boost (loads 1.60–2.00 g/rev):**
  * 2000 RPM: **7.5°**
  * 2800 RPM: **9.0°**
  * 3200 RPM: **9.5°**
  * 3600 RPM: **10.5°**
  * 4400 RPM: **12.0°**
  * 5200 RPM: **13.0°**
  * 6000 RPM: **14.0°**
  * 6800 RPM: **15.0°**

### 2. KCA Max (The Active Knock Margin)
KCA Max provides active advance scaled by IAM:
* **Under Boost (loads 1.40–2.00 g/rev):** **+4.0° to +4.5°**
* **Moderate Off-Boost (loads 1.09–1.22 g/rev):** **+5.5° to +7.0°**
* **High Boost Reserve (loads 2.50–4.00 g/rev):** Tapers down to **+2.5° to +3.5°**

### 3. Normal Running Total Timing (IAM = 1.0)
$$\text{Total Timing} = \text{Base Timing} + \text{KCA}$$
When running on quality 98 RON fuel, total advance under 5 psi boost is:
* **2000 RPM:** $\sim \mathbf{11.5^\circ}$
* **2800 RPM:** $\sim \mathbf{13.2^\circ}$
* **3200 RPM:** $\sim \mathbf{13.7^\circ}$
* **3600 RPM:** $\sim \mathbf{14.7^\circ}$
* **4400 RPM:** $\sim \mathbf{16.2^\circ}$
* **5200 RPM:** $\sim \mathbf{17.2^\circ}$
* **6000 RPM:** $\sim \mathbf{18.2^\circ}$

### 4. Safety Protection Restored
If detonation occurs or bad fuel is encountered, the ECU reduces IAM (e.g. from 1.0 down to 0.5 or 0.0), automatically pulling up to **4.5° of timing across the entire boosted operating range**, safely protecting the 10.7:1 compression motor.
