# Copyright (c) Acconeer AB, 2024
# All rights reserved

import os
import signal
import subprocess

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
    "run_cmd, timeout",
    [
        pytest.param("examples/a121/extended_config.py --mock", None),
        pytest.param(
            "examples/a121/load_record.py tests/processing/a121/data_files/recorded_data/input.h5",
            None,
        ),
        pytest.param("examples/a121/plot.py --mock", 3),
        pytest.param(
            "examples/a121/post_process_sparse_iq.py tests/processing/a121/data_files/recorded_data/input.h5",
            None,
        ),
        pytest.param("examples/a121/reuse_calibration.py --mock", None),
        pytest.param("examples/a121/subsweeps.py --mock", 3),
        pytest.param("examples/a121/algo/bilateration/bilaterator.py --mock", 4),
        pytest.param("examples/a121/algo/breathing/breathing_with_gui.py --mock", 5),
        pytest.param("examples/a121/algo/breathing/breathing.py --mock", 3),
        pytest.param("examples/a121/algo/distance/detector.py --mock", 6),
        pytest.param("examples/a121/algo/distance/processor.py --mock", 3),
        pytest.param("examples/a121/algo/obstacle/detector.py --mock", 6),
        pytest.param("examples/a121/algo/parking/parking.py --mock", 5),
        pytest.param("examples/a121/algo/phase_tracking/phase_tracking.py --mock", 3),
        pytest.param("examples/a121/algo/presence/detector.py --mock", 3),
        pytest.param("examples/a121/algo/presence/processor.py --mock", 3),
        pytest.param("examples/a121/algo/smart_presence/processor.py --mock", 4),
        pytest.param("examples/a121/algo/smart_presence/ref_app.py --mock", 4),
        pytest.param("examples/a121/algo/sparse_iq/sparse_iq.py --mock", 3),
        pytest.param("examples/a121/algo/speed/detector.py --mock", 4),
        pytest.param("examples/a121/algo/speed/processor.py --mock", 5),
        pytest.param("examples/a121/algo/surface_velocity/example_app.py --mock", 3),
        pytest.param("examples/a121/algo/surface_velocity/processor.py --mock", 4),
        pytest.param("examples/a121/algo/tank_level/tank_level_with_gui.py --mock", 5),
        pytest.param("examples/a121/algo/tank_level/tank_level.py --mock", 5),
        pytest.param("examples/a121/algo/touchless_button/processor.py --mock", 4),
        pytest.param("examples/a121/algo/vibration/example_app.py --mock", 3),
        pytest.param("examples/a121/algo/vibration/processor.py --mock", 3),
        pytest.param("examples/a121/algo/waste_level/processor.py --mock", 3),
    ],
)
def test_a121_examples(run_cmd, timeout):
    p = subprocess.Popen(["python3"] + run_cmd.split())
    max_retries = 1
    retries = 0
    done = False
    interrupted = False
    ret = 1

    while retries <= max_retries and not done:
        try:
            ret = p.wait(timeout=timeout)
            done = True
        except subprocess.TimeoutExpired:
            if not interrupted:
                p.send_signal(signal.SIGINT)
                interrupted = True
            else:
                retries += 1

    assert ret == 0
