import copy
import json

import numpy as np
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._entities import (
    ResultContext,
    SensorConfig,
    SensorDataType,
    SessionConfig,
)
from acconeer.exptool.a121._peripherals import ExplorationProtocol


@pytest.fixture
def single_sweep_metadata():
    return a121.Metadata(
        sweep_data_length=100,
        frame_data_length=100,
        subsweep_data_offset=np.array([0]),
        subsweep_data_length=np.array([100]),
        data_type=SensorDataType.INT_16_COMPLEX,
    )


@pytest.mark.parametrize(
    ("function", "kwargs"),
    [
        (ExplorationProtocol.get_system_info_command, {}),
        (ExplorationProtocol.get_sensor_info_command, {}),
        (ExplorationProtocol.setup_command, dict(session_config=SessionConfig(SensorConfig()))),
        (ExplorationProtocol.start_streaming_command, {}),
        (ExplorationProtocol.stop_streaming_command, {}),
        (ExplorationProtocol.stop_streaming_command, {}),
    ],
)
def test_all_command_functions_end_with_linebreak(function, kwargs):
    assert function(**kwargs).endswith(b"\n")


def test_get_system_info_command():
    assert ExplorationProtocol.get_system_info_command() == b'{"cmd":"get_system_info"}\n'


def test_get_system_info_response():
    response = json.dumps(
        {
            "status": "ok",
            "system_info": {
                "rss_version": "v2.9.0",
                "sensor": "sensor_version",
                "sensor_count": 5,
                "ticks_per_second": 1000000,
                "hw": "linux",
            },
        }
    ).encode("ascii")
    expected = a121.ServerInfo(rss_version="v2.9.0", sensor_count=5, ticks_per_second=1000000)

    assert ExplorationProtocol.get_system_info_response(response) == expected


def test_get_sensor_info_command():
    assert ExplorationProtocol.get_sensor_info_command() == b'{"cmd":"get_sensor_info"}\n'


def test_get_sensor_info_response():
    response = json.dumps(
        {
            "status": "ok",
            "payload_size": 0,
            "sensor_info": [
                {"connected": True},
                {"connected": False},
                {"connected": True},
                {"connected": False},
                {"connected": False},
            ],
        }
    ).encode("ascii")
    expected = [1, 3]

    assert ExplorationProtocol.get_sensor_info_response(response) == expected


def test_setup_command_simple_session_config():
    config = a121.SessionConfig(a121.SensorConfig(hwaas=8, sweeps_per_frame=1), update_rate=20)

    expected_dict = {
        "cmd": "setup",
        "groups": [
            [  # first group
                {
                    "sensor_id": 1,
                    "config": {
                        "subsweeps": [a121.SubsweepConfig(hwaas=8).to_dict()],
                        "sweeps_per_frame": 1,
                    },
                },
            ]
        ],
        "update_rate": 20,
    }

    assert json.loads(ExplorationProtocol.setup_command(config)) == expected_dict


def test_setup_response(single_sweep_metadata):
    response = json.dumps(
        {
            "status": "ok",
            "tick_period": 50,
            "payload_size": 0,
            "metadata": [
                [  # Group 1
                    {
                        "sweep_data_length": 100,
                        "frame_data_length": 100,
                        "subsweep_data_offset": [0],
                        "subsweep_data_length": [100],
                        "data_type": "int_16_complex",
                    },
                ],
                [  # Group 2
                    {
                        "sweep_data_length": 100,
                        "frame_data_length": 200,
                        "subsweep_data_offset": [0, 100],
                        "subsweep_data_length": [100, 100],
                        "data_type": "uint_16",
                    },
                ],
            ],
        }
    ).encode("ascii")

    expected = [
        {1: single_sweep_metadata},
        {
            1: a121.Metadata(
                sweep_data_length=100,
                frame_data_length=200,
                subsweep_data_offset=np.array([0, 100]),
                subsweep_data_length=np.array([100, 100]),
                data_type=SensorDataType.UINT_16,
            )
        },
    ]
    context = a121.SessionConfig(
        [{1: a121.SensorConfig(sweeps_per_frame=1)}, {1: a121.SensorConfig(sweeps_per_frame=2)}]
    )

    assert ExplorationProtocol.setup_response(response, context) == expected


def test_start_streaming_command():
    assert ExplorationProtocol.start_streaming_command() == b'{"cmd":"start_streaming"}\n'


def test_start_streaming_response():
    response_bytes = json.dumps(
        {"status": "start", "payload_size": 0, "message": "Start streaming."}
    ).encode("ascii")
    assert ExplorationProtocol.start_streaming_response(response_bytes) is True

    error_bytes = json.dumps({"status": "error"}).encode("ascii")
    assert ExplorationProtocol.start_streaming_response(error_bytes) is False


def test_stop_streaming_command():
    assert ExplorationProtocol.stop_streaming_command() == b'{"cmd":"stop_streaming"}\n'


def test_stop_streaming_response():
    response_bytes = json.dumps(
        {"status": "stop", "payload_size": 0, "message": "Stop streaming."}
    ).encode("ascii")
    assert ExplorationProtocol.stop_streaming_response(response_bytes) is True

    response_bytes = json.dumps({"status": "error"}).encode("ascii")
    assert ExplorationProtocol.stop_streaming_response(response_bytes) is False


def test_get_next_header(single_sweep_metadata):
    get_next_header = json.dumps(
        {
            "result_info": [
                [
                    {
                        "tick": 0,
                        "data_saturated": False,
                        "temperature": 0,
                        "frame_delayed": False,
                        "calibration_needed": False,
                    }
                ]
            ],
            "payload_size": 400,
        }
    ).encode("ascii")

    extended_metadata = [{1: single_sweep_metadata}]

    payload_size, partial_results = ExplorationProtocol.get_next_header(
        get_next_header,
        extended_metadata,
        ticks_per_second=0,
    )
    assert payload_size == 400
    assert partial_results == [
        {
            1: a121.Result(
                data_saturated=False,
                tick=0,
                frame_delayed=False,
                calibration_needed=False,
                temperature=0,
                frame=np.array([0]),
                context=ResultContext(
                    metadata=single_sweep_metadata,
                    ticks_per_second=0,
                ),
            )
        }
    ]


def test_get_next_payload_single_sweep(single_sweep_metadata):
    partial_results = [
        {
            1: a121.Result(
                data_saturated=False,
                tick=0,
                frame_delayed=False,
                calibration_needed=False,
                temperature=0,
                frame=np.array([0]),
                context=ResultContext(
                    metadata=single_sweep_metadata,
                    ticks_per_second=0,
                ),
            )
        }
    ]
    data_array = np.array(range(100), dtype=SensorDataType.INT_16_COMPLEX.value)
    mock_payload = data_array.tobytes()
    assert len(mock_payload) == 400

    full_results = ExplorationProtocol.get_next_payload(mock_payload, partial_results)
    assert len(full_results) == 1
    assert len(full_results[0]) == 1

    np.testing.assert_array_equal(
        full_results[0][1].frame, data_array["real"] + 1j * data_array["imag"]
    )


def test_get_next_payload_multiple_sweep(single_sweep_metadata):
    partial_result = a121.Result(
        data_saturated=False,
        tick=0,
        frame_delayed=False,
        calibration_needed=False,
        temperature=0,
        frame=np.array([0]),
        context=ResultContext(
            metadata=single_sweep_metadata,
            ticks_per_second=0,
        ),
    )
    partial_results = [
        {
            1: partial_result,
            2: copy.deepcopy(partial_result),
        }
    ]

    first_frame = np.array(range(100), dtype=SensorDataType.INT_16_COMPLEX.value)
    second_frame = np.array(range(100, 200), dtype=SensorDataType.INT_16_COMPLEX.value)
    mock_payload = np.concatenate((first_frame, second_frame)).tobytes()
    assert len(mock_payload) == 800

    full_results = ExplorationProtocol.get_next_payload(mock_payload, partial_results)
    assert len(full_results) == 1
    assert len(full_results[0]) == 2

    np.testing.assert_array_equal(
        full_results[0][1].frame, first_frame["real"] + 1j * first_frame["imag"]
    )
    np.testing.assert_array_equal(
        full_results[0][2].frame, second_frame["real"] + 1j * second_frame["imag"]
    )
