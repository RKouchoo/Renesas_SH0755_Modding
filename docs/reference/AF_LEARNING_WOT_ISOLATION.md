# A/F Learning Range D Isolation for WOT / Boost Safety — 2026-09-09

[Reference home](README.md) · [Signals](SIGNALS.md) · [Findings](FINDINGS.md)

## Background & Rationale

Subaru factory ECUs partition closed-loop fuel learning (`A/F Learning #1`) into four distinct airflow ranges (A, B, C, D) based on the table **`A/F Learning Airflow Ranges`** at `0x7616C`:

| Range | Airflow Window (Stock) | Typical Operating Region |
|---|---|---|
| **Range A** | 0.0 to 5.0 g/s | Stationary Idle |
| **Range B** | 5.0 to 10.0 g/s | Low-Speed City Cruise |
| **Range C** | 10.0 to 22.0 g/s | Moderate Cruise |
| **Range D** | **22.0 g/s to $\infty$** | **Highway Cruise & High Load** |

---

### The Danger on a Turbo Engine

In factory Subaru firmware, **whatever long-term fuel trim is learned in Range D continues to be applied when the ECU enters Open Loop under Wide Open Throttle (WOT) and boost**:

1. **How it happens:** 
   * On the highway at 100 km/h cruising in 5th/6th gear, airflow is typically **25 to 35 g/s**.
   * Because 25–35 g/s is greater than the stock 22.0 g/s threshold, the ECU enters Range D.
   * If fuel trims learn **-4% or -5%** during steady cruise (e.g. from slight canister purging or fuel temperature drift), that **-5% trim is saved into Range D**.
2. **The WOT Lean-Out:**
   * When you drop a gear and go Wide Open Throttle into full boost, the ECU enters Open Loop.
   * However, the ECU applies Range D's trim to open-loop fueling:
     $$\text{Final Fuel} = \text{Target Fuel} \times (1 + \mathbf{A/F\ Learning\ Range\ D})$$
   * The ECU pulls **5% of fuel out of the engine under full boost**!
   * On a high-compression turbo engine (like an EZ30R at 10.7:1 CR), pulling 5% of fuel under boost causes dangerous lean spikes, knock, and potential engine damage.

---

### The Solution in `master_patch_v2`

The Range C $\rightarrow$ D transition threshold (`0x76174`) is raised from the stock `22.0 g/s` to **`500.0 g/s`**:

```python
# A/F Learning Airflow Ranges at 0x7616C
AF_LEARNING_RANGES = (5.0, 10.0, 500.0)
```

#### How this protects the engine:
1. **Range C Now Covers All Normal Cruising (10.0 to 500.0 g/s):**
   * Closed-loop fuel learning continues to work normally for idle (Range A) and all cruising (Ranges B and C).
   * Emissions and fuel economy remain optimal.
2. **Range D is Permanently Locked at 0.00%:**
   * The car is never in Closed Loop at 500 g/s (the pressure guard forces Open Loop at ~90 kPa).
   * Range D can never be populated or learned. It remains locked at **0.00%**.
3. **Pure Open Loop Under Boost:**
   * When you go WOT into boost, the ECU looks at Range D and sees **0.00%**.
   * **Zero learned fuel trim is applied under boost.**
   * Injected fuel stays 100% true to your calibrated VE and Primary Open Loop target tables with zero drift.
