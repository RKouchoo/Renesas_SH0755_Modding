import sys
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "master_patch_v2"))

from audit_all_tables import parse_all

tables = parse_all()

# Table lookup by name
t_map = {t['name']: t for t in tables}

print("=== 1. INTAKE AVCS TARGETS ===")
# Low Cam Target A
t_avcs_a = t_map["Intake AVCS Target A (AVLS Low Cam)"]
sx_a, sy_a = t_avcs_a['sizex'], t_avcs_a['sizey']
loads_a = [round(x, 2) for x in t_avcs_a['x_axis']['scaled']]
rpms_a = t_avcs_a['y_axis']['scaled']

print("Low Cam Target A:")
print("RPM \\ Load:", loads_a)
for r in range(sy_a):
    row = [round(t_avcs_a['scaled'][r*sx_a + c], 1) for c in range(sx_a)]
    print(f"{rpms_a[r]:4.0f} RPM: {row}")

# High Cam Target B
t_avcs_b = t_map["Intake AVCS Target B (AVLS High Cam)"]
sx_b, sy_b = t_avcs_b['sizex'], t_avcs_b['sizey']
loads_b = [round(x, 2) for x in t_avcs_b['x_axis']['scaled']]
rpms_b = t_avcs_b['y_axis']['scaled']

print("\nHigh Cam Target B:")
print("RPM \\ Load:", loads_b)
for r in range(sy_b):
    if rpms_b[r] in (1200, 1600, 2000, 2400, 2800, 3200, 3600, 4000, 4800, 5600, 6400):
        row = [round(t_avcs_b['scaled'][r*sx_b + c], 1) for c in range(sx_b)]
        print(f"{rpms_b[r]:4.0f} RPM: {row}")

print("\n=== 2. BASE TIMING SURFACES (Total Timing = Base + KCA @ IAM=1.0) ===")
t_base_a = t_map["Base Timing A (Normal Cam, AVCS 1.0)"]
t_base_d = t_map["Base Timing D (Normal Cam, AVCS 0.0)"]
t_kca_a = t_map["Knock Correction Advance Max A (Normal Cam)"]
sx_t, sy_t = t_base_a['sizex'], t_base_a['sizey']
loads_t = [round(x, 2) for x in t_base_a['x_axis']['scaled']]
rpms_t = t_base_a['y_axis']['scaled']

print("Low Cam Total Timing (Base A + KCA A):")
print("RPM \\ Load:", loads_t)
for r in range(sy_t):
    if 1200 <= rpms_t[r] <= 3600:
        row = [round(t_base_a['scaled'][r*sx_t + c] + t_kca_a['scaled'][r*sx_t + c], 1) for c in range(sx_t)]
        print(f"{rpms_t[r]:4.0f} RPM: {row}")

print("\nLow Cam Total Timing (Base D + KCA A):")
print("RPM \\ Load:", loads_t)
for r in range(sy_t):
    if 1200 <= rpms_t[r] <= 3600:
        row = [round(t_base_d['scaled'][r*sx_t + c] + t_kca_a['scaled'][r*sx_t + c], 1) for c in range(sx_t)]
        print(f"{rpms_t[r]:4.0f} RPM: {row}")

print("\n=== 3. FUELING & SPEED DENSITY VE ===")
t_fuel = t_map["Primary Open Loop Fueling A "]
sx_f, sy_f = t_fuel['sizex'], t_fuel['sizey']
loads_f = [round(x, 2) for x in t_fuel['x_axis']['scaled']]
rpms_f = t_fuel['y_axis']['scaled']

print("Primary Open Loop Fueling A (Estimated AFR):")
print("RPM \\ Load:", loads_f)
for r in range(sy_f):
    if 1200 <= rpms_f[r] <= 3600:
        row = [round(t_fuel['scaled'][r*sx_f + c], 2) for c in range(sx_f)]
        print(f"{rpms_f[r]:4.0f} RPM: {row}")

t_ve_low = t_map["Speed Density VE - AVLS Low Lift"]
sx_v, sy_v = t_ve_low['sizex'], t_ve_low['sizey']
map_v = [round(x) for x in t_ve_low['x_axis']['scaled']]
rpms_v = t_ve_low['y_axis']['scaled']

print("\nLow Lift VE Surface:")
print("RPM \\ MAP:", map_v)
for r in range(sy_v):
    if rpms_v[r] >= 800:
        row = [round(t_ve_low['scaled'][r*sx_v + c], 3) for c in range(sx_v)]
        print(f"{rpms_v[r]:4.0f} RPM: {row}")
