# Denso Scaling Architecture, FPU Latency, and Math Optimizations

[Reference home](README.md) · [Signals](SIGNALS.md) · [Findings](FINDINGS.md)

## 1. The Hitachi / Renesas SH-2E FPU Architecture

The `SH7055F` microcontroller powering the D2WD610H ECU utilizes an **SH-2E 32-bit RISC core** running at 40 MHz.

### Instruction Latencies on SH-2E
| Instruction Category | Instructions | Execution Latency |
|---|---|:---:|
| **Integer Arithmetic** | `ADD`, `SUB`, `MOV`, `SHLL`, `SHLR`, `CMP` | **1 clock cycle** (25 ns) |
| **Integer Multiply** | `DMULS.L` ($32 \times 32 \rightarrow 64$-bit `MACH:MACL`) | **2–4 clock cycles** |
| **Float Arithmetic** | `FADD`, `FSUB`, `FLOAT`, `FTRC` | **1 clock cycle** |
| **Float Multiply** | `FMUL`, `FMAC` | **2–4 clock cycles** |
| **Float Division** | `FDIV` | **34 to 36 clock cycles** (850–900 ns) |
| **Float Square Root**| `FSQRT` | **34+ clock cycles** |

---

## 2. Denso's Fixed-Point Integer Trick ($2^{16} = 65,536$)

Because a single `FDIV` consumes up to 36 cycles, Denso automotive engineers strictly avoided float division in real-time execution loops. To achieve ultra-fast division without an `FDIV`, Denso stored table parameters as **16-bit integers (`uint16`) scaled by $2^{16} = 65,536$**:

$$\frac{1}{65,536} = \mathbf{0.0000152587890625}$$

### Why This Is Free in Hardware:
When the SH-2E executes a 32-bit integer multiplication (`DMULS.L`), the 64-bit result lands across two dedicated registers:
* `MACL` (lower 32 bits)
* `MACH` (upper 32 bits)

Dividing any number by 65,536 is physically identical to reading the upper 16 bits or taking `MACH`. It requires **zero division instructions** and takes only 2 clock cycles.

---

## 3. Demystifying the "Big Scale Factor Floats"

### A. The Hardware Scaling: `0.0019073486328125`
In the Target Throttle Plate Position descriptor at `0x607D4`, the scale factor is stored as:
$$\frac{125}{65,536} = \mathbf{0.0019073486328125}$$

* **What it actually measures:** Physical throttle plate opening in **degrees ($0.0^\circ$ to $84.0^\circ$)**.
* **Why 84 degrees:** The Hitachi electronic drive-by-wire throttle body on the EZ30 physically rotates through an arc of exactly $84^\circ$ from the mechanical idle stop to the wide-open stop.

### B. The RomRaider Helper Float: `0.002270655357`
In the RomRaider XML definitions (`D2WD610H.xml` and `D2WD610H_AVLS.xml`), the display expression for Target Throttle Plate Position is:
```xml
<scaling units="Target Throttle Plate Opening Angle (%)" expression="x*.002270655357" ... />
```
* **Why it differs:** Tuners find $0^\circ$–$84^\circ$ confusing and expect throttle to read on a normalized **$0\%$ to $100\%$ scale**.
* **The conversion:**
  $$0.0019073486328125 \times \frac{100\%}{84^\circ} = \mathbf{0.002270653134...}$$
* RomRaider's `0.002270655357` is simply a **convenience helper float** designed to display human-readable percentages in the GUI. The ECU hardware itself computes native degrees via `0.0019073486328125`.

### C. Base Idle Air: `0.00152587890625`
The Base Idle Air tables at `0x79C9C` and `0x79CBC` use:
$$\frac{100}{65,536} = \mathbf{0.00152587890625}$$
Denso takes the 16-bit raw integer, multiplies by 100, and drops the lower 16 bits to produce grams per second.

---

## 4. Can This Math Trick Optimize Our Patches?

### Speed Density Analysis (`speed_density_component.py`):
* Our SD airflow wrapper (`0x0007E18C`) was designed from inception with **pre-inverted scalar constants**:
  * Instead of dividing by temperature $T$, it pre-calculates the 20°C standard scalar and uses an IAT compensation multiplier curve.
  * Instead of dividing by displacement or gas constants, it pre-computes:
    $$\text{Airflow Constant} = \frac{1}{2 \times 60 \times R \times T_{\text{std}}}$$
* **Instruction Count:** The SD wrapper executes exactly **6 `FMUL` instructions** (2–4 cycles each) and **zero `FDIV` instructions**.
* **Execution Time:** ~150 clock cycles total (~3.7 microseconds at 40 MHz).
* **Conclusion:** Converting to fixed-point integer math is **unnecessary and counterproductive**:
  * The native ECU signals consumed by SD (`0xFFFFB420` MAF, `0xFFFFB544` RPM, `0xFFFFABC4` MAP, `0xFFFFB3B8` IAT) are already native single-precision IEEE 754 floats in RAM.
  * Converting float $\rightarrow$ integer $\rightarrow$ float would add register shuffling and conversion latency for zero performance gain.

---

## 5. Is the Wideband AFR ADC Conversion Intensive on the FPU?

**No. It is virtually instantaneous.**

### Exact Instruction Audit of `build_wideband_update` (`0x0007F100`):
1. `mov.w @r1, r0` $\rightarrow$ reads raw 16-bit MAF ADC count (`0xFFFF87E2`) (1 cycle).
2. `float fpul, fr0` $\rightarrow$ converts unsigned ADC count to float (1 cycle).
3. `fmul fr1, fr0` $\rightarrow$ multiplies by `5.0 / 65536.0` (`RAW_TO_VOLTS`) (3 cycles).
4. `fcmp/gt` $\rightarrow$ checks $0.50\text{ V} \le \text{volts} \le 4.50\text{ V}$ window (2 cycles).
5. `fmul fr1, fr0` $\rightarrow$ multiplies volts by `LAMBDA_SLOPE` ($2.0 / 14.64$) (3 cycles).
6. `fadd fr1, fr0` $\rightarrow$ adds `LAMBDA_OFFSET` ($10.0 / 14.64$) (1 cycle).
7. `fmov.s fr0, @r1` $\rightarrow$ publishes to Bank 1/2 and logger mirrors.

### Summary:
* **Zero `FDIV` instructions.**
* **Only 2 `FMUL` and 1 `FADD` instructions.**
* **Total execution time:** **Under 40 clock cycles (~1.0 microsecond)**.
* The wideband decoding routine is lighter than the stock factory MAF polynomial lookup that it replaced. It places virtually zero load on the SH-2E FPU.
