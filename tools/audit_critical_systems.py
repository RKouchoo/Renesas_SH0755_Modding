import sys
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "master_patch_v2"))

from audit_all_tables import parse_all

tables = parse_all()
t_map = {t['name']: t for t in tables}

print("Running deep systematic audit on all 13 critical systems...")

# 1. DBW Requested Torque vs Target Throttle
t_rt = t_map["Requested Torque (Accelerator Pedal)"]
t_tt = t_map["Target Throttle Plate Position (Requested Torque)"]
print(f"1. DBW: RT shape={t_rt['sizex']}x{t_rt['sizey']}, min={min(t_rt['scaled'])}, max={max(t_rt['scaled'])}")
print(f"        TT shape={t_tt['sizex']}x{t_tt['sizey']}, min={min(t_tt['scaled'])}, max={max(t_tt['scaled'])}")

# Check 0% pedal column in RT and 0 torque column in TT
rt_col0 = [t_rt['scaled'][r * t_rt['sizex'] + 0] for r in range(t_rt['sizey'])]
tt_col0 = [t_tt['scaled'][r * t_tt['sizex'] + 0] for r in range(t_tt['sizey'])]
print(f"   * RT col 0 (0% pedal): all zeros? {all(x == 0 for x in rt_col0)}")
print(f"   * TT col 0 (0 torque): all zeros? {all(x == 0 for x in tt_col0)}")

# Check 100% pedal in RT and max torque in TT
rt_col_max = [t_rt['scaled'][r * t_rt['sizex'] + t_rt['sizex'] - 1] for r in range(t_rt['sizey'])]
tt_col_max = [t_tt['scaled'][r * t_tt['sizex'] + t_tt['sizex'] - 1] for r in range(t_tt['sizey'])]
print(f"   * RT max pedal: min={min(rt_col_max):.1f}, max={max(rt_col_max):.1f}")
print(f"   * TT max torque: min={min(tt_col_max):.1f}%, max={max(tt_col_max):.1f}%")

# 2. Transient Fueling Multipliers
with open("master_patch_v2/D2WD610H_master_patch_v2.bin", "rb") as f:
    rom = f.read()

pos_ect = struct.unpack(">16H", rom[0x76D08:0x76D08+32])
neg_ect = struct.unpack(">16H", rom[0x76D48:0x76D48+32])
print(f"2. Transients: Positive ECT raw max = {max(pos_ect)} ({max(pos_ect)*0.000488281:.2f}x max mult)")
print(f"               Negative ECT raw max = {max(neg_ect)} ({max(neg_ect)*0.000488281:.2f}x max mult)")
dashpot = struct.unpack(">f", rom[0x7963C:0x79640])[0]
trans_filt = struct.unpack(">f", rom[0x76050:0x76054])[0]
print(f"               Dashpot decel air decrement = {dashpot:.2f} (optimal 0.50)")
print(f"               Transient falling load filter = {trans_filt:.3f} (optimal 0.080)")

# 3. AVLS Switching
engage_rpm = struct.unpack(">f", rom[0x7D4BC:0x7D4C0])[0]
release_rpm = struct.unpack(">f", rom[0x7D4B8:0x7D4BC])[0]
print(f"3. AVLS: Engage = {engage_rpm:.0f} RPM, Release = {release_rpm:.0f} RPM")

# Check AVLS pedal threshold tables (0x7D67C, 0x7D6B4)
pedal_norm = struct.unpack(">7f", rom[0x7D67C:0x7D67C+28])
pedal_hot = struct.unpack(">7f", rom[0x7D6B4:0x7D6B4+28])
print(f"   * AVLS Normal Pedal thresholds: {[round(x, 1) for x in pedal_norm]}")
print(f"   * AVLS Hot Pedal thresholds:    {[round(x, 1) for x in pedal_hot]}")

# 4. Failsafes
lean_arm = struct.unpack(">f", rom[0x7EAD4:0x7EAD8])[0]
lean_reset = struct.unpack(">f", rom[0x7EAD8:0x7EADC])[0]
lean_afr = struct.unpack(">f", rom[0x7EADC:0x7EAE0])[0]
overb_fc = struct.unpack(">f", rom[0x7D8C0:0x7D8C4])[0]
sd_map_min = struct.unpack(">f", rom[0x7DD10:0x7DD14])[0]
sd_map_max = struct.unpack(">f", rom[0x7DD14:0x7DD18])[0]
sd_failsafe_air = struct.unpack(">f", rom[0x7DD00:0x7DD04])[0]

print(f"4. Failsafes: Lean Cut Arm = {lean_arm/51.7149:.2f} psi, Reset = {lean_reset/51.7149:.2f} psi, Trip AFR = {lean_afr*14.64:.2f}")
print(f"              Hard Overboost = {overb_fc/51.7149:.2f} psi relative")
print(f"              SD MAP valid range = {sd_map_min:.1f} to {sd_map_max:.1f} mmHg (0 to {sd_map_max*0.133322:.1f} kPa)")
print(f"              SD Failsafe Airflow = {sd_failsafe_air:.1f} g/s")

# 5. Knock Authority & IAM
iam_init = struct.unpack(">f", rom[0x77FD8:0x77FDC])[0]
flkc_range = struct.unpack(">4f", rom[0x78040:0x78050])
rough_range = struct.unpack(">4f", rom[0x77FEC:0x77FFC])
flkc_cols = struct.unpack(">7f", rom[0x78050:0x78050+28])
print(f"5. Knock: Initial IAM = {iam_init:.2f}")
print(f"          FLKC load range = {[round(x, 2) for x in flkc_range]}")
print(f"          Rough (IAM) load range = {[round(x, 2) for x in rough_range]}")
print(f"          FLKC columns = {[round(x, 2) for x in flkc_cols]}")
