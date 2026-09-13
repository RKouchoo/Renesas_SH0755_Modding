#!/usr/bin/env python3
"""Run the September 12 bounded process-flow suites; no ECU or BIN writes.

These tests cover explicit native paths and fixtures, not full ECU state or
measured deadlines. See docs/reference/PATCH_PROCESS_FLOW.md for remaining
edges and the individual module docstrings for test boundaries.
"""
import _analysis_paths
import argparse
import hashlib
import importlib
from io import StringIO
import json
from pathlib import Path
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    'test_runtime_rom_checksum_execution',
    'test_startup_retained_process_flow',
    'test_retained_reset_process_flow',
    'test_ssm_command_process_flow',
    'test_diagnostic_enable_flow',
    'test_cylinder_disable_process_flow',
    'test_wideband_monitor_process_flow',
    'test_cam_iam_timing_process_flow',
    'test_knock_cell_process_flow',
    'test_knock_retained_process_flow',
    'test_knock_learning_process_flow',
    'test_knock_feedback_process_flow',
    'test_knock_event_process_flow',
    'test_timing_feedback_process_flow',
    'test_idle_feedback_process_flow',
    'test_dormant_patch_process_flow',
    'test_fan_retired_process_flow',
    'test_barometric_process_flow',
    'test_avls_phase_process_flow',
    'test_avls_actuator_process_flow',
    'test_avls_diagnostic_process_flow',
    'test_runtime_switch_process_flow',
    'test_shutdown_process_flow',
    'test_diagnostic_readiness_process_flow',
    'test_diagnostic_mode_process_flow',
    'test_diagnostic_record_process_flow',
    'test_injector_device_process_flow',
    'test_ignition_device_process_flow',
    'test_tip_in_device_process_flow',
    'test_purge_process_flow',
    'test_iat_process_flow',
    'test_iat_fault_process_flow',
    'test_dbw_arbitration_process_flow',
    'test_throttle_tracking_process_flow',
    'test_fuel_learning_process_flow',
    'test_wideband_feedback_process_flow',
    'test_wideband_heater_process_flow',
    'test_adc_handoff_process_flow',
    'test_wideband_status_dependency_flow',
    'test_wideband_cruise_process_flow',
    'test_wideband_readiness_diagnostics',
    'test_purge_monitor_shared_state_flow',
    'test_airflow_task_process_flow',
    'test_legacy_o2_process_flow',
    'test_avcs_target_process_flow',
    'test_avcs_actuator_process_flow',
    'test_avcs_controller_process_flow',
    'test_avcs_diagnostic_process_flow',
    'test_cam_performance_process_flow',
    'test_cam_sensor_process_flow',
    'test_cam_selector_process_flow',
    'test_engine_timeout_process_flow',
    'test_sync_transition_process_flow',
    'test_phase_activation_process_flow',
    'test_patch_preemption_process_flow',
    'test_crank_observation_process_flow',
    'test_crank_decoder_process_flow',
    'test_capture_inhibit_process_flow',
    'test_native_inhibit_sources_process_flow',
    'test_received_cut_process_flow',
    'test_torque_mode_process_flow',
    'test_avcs_event_process_flow',
)


def run():
    from test_runtime_rom_checksum_execution import before_pump_scaling
    images = {name: (ROOT/path).read_bytes() for name, path in (
        ('main', 'master_patch/D2WD610H_master_patch.bin'),
        ('v2', 'master_patch_v2/D2WD610H_master_patch_v2.bin'))}
    images['captured'] = before_pump_scaling(images['v2'])
    rows = []
    for name in MODULES:
        module = importlib.import_module(name)
        variants = images.items() if name == 'test_cylinder_disable_process_flow' else [('internal', None)]
        for variant, image in variants:
            saved = getattr(module, 'IMAGE', None)
            if image is not None:
                module.IMAGE = image
            transcript = StringIO()
            started = time.monotonic()
            try:
                suite = unittest.defaultTestLoader.loadTestsFromModule(module)
                result = unittest.TextTestRunner(stream=transcript, verbosity=2).run(suite)
            finally:
                if image is not None:
                    module.IMAGE = saved
            row = dict(module=name, variant=variant, passed=result.wasSuccessful(),
                       groups=result.testsRun, elapsed_seconds=round(time.monotonic()-started, 3),
                       transcript=transcript.getvalue())
            rows.append(row)
            print(f"{'PASS' if row['passed'] else 'FAIL'} {name} [{variant}]: {row['groups']} groups",
                  flush=True)
            if not row['passed']:
                print(row['transcript'], flush=True)
    return dict(scope='Bounded native process-flow tests, not a complete state-machine or vehicle proof.',
                image_sha256={k: hashlib.sha256(v).hexdigest() for k, v in images.items()},
                passed=all(row['passed'] for row in rows),
                groups=sum(row['groups'] for row in rows), results=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional JSON evidence destination')
    args = parser.parse_args()
    if args.output is not None and args.output.suffix != '.json':
        parser.error('Evidence output must have .json extension')
    report = run()
    if args.output is not None:
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(0 if report['passed'] else 1)
