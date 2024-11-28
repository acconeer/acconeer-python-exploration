# Copyright (c) Acconeer AB, 2024
# All rights reserved

import os
import signal
import subprocess
import sys

import pytest


@pytest.fixture(scope="session", autouse=True)
def set_env():
    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        yield
        del os.environ["QT_QPA_PLATFORM"]
    else:
        yield


@pytest.mark.parametrize(
    ("run_cmd"),
    [
        "examples/a121/extended_config.py --mock",
        "examples/a121/load_record.py tests/processing/a121/data_files/recorded_data/input.h5",
        "examples/a121/plot.py --mock",
        "examples/a121/post_process_sparse_iq.py tests/processing/a121/data_files/recorded_data/input.h5",
        "examples/a121/reuse_calibration.py --mock",
        "examples/a121/subsweeps.py --mock",
        "examples/a121/algo/bilateration/bilaterator.py --mock",
        "examples/a121/algo/breathing/breathing_with_gui.py --mock",
        "examples/a121/algo/breathing/breathing.py --mock",
        "examples/a121/algo/distance/detector.py --mock",
        "examples/a121/algo/distance/processor.py --mock",
        "examples/a121/algo/obstacle/detector.py --mock",
        "examples/a121/algo/parking/parking.py --mock",
        "examples/a121/algo/phase_tracking/phase_tracking.py --mock",
        "examples/a121/algo/presence/detector.py --mock",
        "examples/a121/algo/presence/processor.py --mock",
        "examples/a121/algo/smart_presence/processor.py --mock",
        "examples/a121/algo/smart_presence/ref_app.py --mock",
        "examples/a121/algo/sparse_iq/sparse_iq.py --mock",
        "examples/a121/algo/speed/detector.py --mock",
        "examples/a121/algo/speed/processor.py --mock",
        "examples/a121/algo/surface_velocity/example_app.py --mock",
        "examples/a121/algo/surface_velocity/processor.py --mock",
        "examples/a121/algo/tank_level/tank_level_with_gui.py --mock",
        "examples/a121/algo/tank_level/tank_level.py --mock",
        "examples/a121/algo/touchless_button/processor.py --mock",
        "examples/a121/algo/vibration/example_app.py --mock",
        "examples/a121/algo/vibration/processor.py --mock",
        "examples/a121/algo/waste_level/processor.py --mock",
    ],
)
def test_a121_examples(run_cmd):
    start_grace_period_s = 3
    interrupt_timeout_s = 3
    kill_timeout_s = 1

    p = subprocess.Popen([sys.executable] + run_cmd.split())

    # The example is non-interactive and without while-loop
    # This is also where we whould find examples that don't run
    try:
        returncode = p.wait(timeout=start_grace_period_s)
    except subprocess.TimeoutExpired:
        pass
    else:
        assert returncode == 0
        return

    # The example is long-running and expects the user to interrupt it.
    try:
        p.send_signal(signal.SIGINT)
        returncode = p.wait(timeout=interrupt_timeout_s)
    except subprocess.TimeoutExpired:
        pass
    else:
        assert returncode in [0, -signal.SIGINT]
        return

    # The example didn't clean-up properly. Kill it.
    try:
        p.send_signal(signal.SIGKILL)
        returncode = p.wait(timeout=kill_timeout_s)
    except subprocess.TimeoutExpired:
        pytest.fail(f"{run_cmd} did not exit within {kill_timeout_s} seconds after kill signal.")
    else:
        assert returncode in [0, -signal.SIGKILL]
        return
