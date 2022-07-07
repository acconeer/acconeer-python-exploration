import copy
import json

import numpy as np
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities import (
    INT_16_COMPLEX,
    ResultContext,
    SensorConfig,
    SensorInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.peripherals import (
    ExplorationProtocol,
    ServerError,
    get_exploration_protocol,
)
from acconeer.exptool.a121._core.utils import parse_rss_version


@pytest.fixture
def single_sweep_metadata():
    return a121.Metadata(
        sweep_data_length=100,
        frame_data_length=100,
        subsweep_data_offset=np.array([0]),
        subsweep_data_length=np.array([100]),
        calibration_temperature=10,
        tick_period=50,
        base_step_length_m=0.0025,
        max_sweep_rate=1000.0,
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
    expected = (
        a121.ServerInfo(
            rss_version="v2.9.0",
            sensor_count=5,
            ticks_per_second=1000000,
            sensor_infos={},
            hardware_name="linux",
        ),
        "sensor_version",
    )

    assert ExplorationProtocol.get_system_info_response(response, {}) == expected


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
    expected = {
        1: SensorInfo(connected=True),
        2: SensorInfo(connected=False),
        3: SensorInfo(connected=True),
        4: SensorInfo(connected=False),
        5: SensorInfo(connected=False),
    }

    assert ExplorationProtocol.get_sensor_info_response(response) == expected


@pytest.mark.parametrize("update_rate", [20, None])
def test_setup_command_simple_session_config(update_rate):
    config = a121.SessionConfig(
        a121.SensorConfig(
            subsweeps=[
                a121.SubsweepConfig(
                    hwaas=8,
                    prf=a121.PRF.PRF_6_5_MHz,
                ),
            ],
            sweeps_per_frame=1,
        ),
        update_rate=update_rate,
    )

    expected_dict = {
        "cmd": "setup",
        "groups": [
            [  # first group
                {
                    "sensor_id": 1,
                    "config": {
                        "subsweeps": [
                            {
                                "start_point": 80,
                                "num_points": 160,
                                "step_length": 1,
                                "profile": 3,
                                "hwaas": 8,
                                "receiver_gain": 16,
                                "enable_tx": True,
                                "enable_loopback": False,
                                "phase_enhancement": False,
                                "prf": "6_5_MHz",
                            }
                        ],
                        "sweeps_per_frame": 1,
                        "sweep_rate": 0.0,
                        "frame_rate": 0.0,
                        "continuous_sweep_mode": False,
                        "double_buffering": False,
                        "inter_frame_idle_state": "deep_sleep",
                        "inter_sweep_idle_state": "ready",
                    },
                },
            ]
        ],
    }

    if update_rate is not None:
        expected_dict["update_rate"] = update_rate

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
                        "calibration_temperature": 10,
                        "base_step_length_m": 0.0025,
                        "max_sweep_rate": 1000.0,
                    },
                ],
                [  # Group 2
                    {
                        "sweep_data_length": 100,
                        "frame_data_length": 200,
                        "subsweep_data_offset": [0, 100],
                        "subsweep_data_length": [100, 100],
                        "calibration_temperature": 10,
                        "base_step_length_m": 0.0025,
                        "max_sweep_rate": 1000.0,
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
                calibration_temperature=10,
                tick_period=50,
                base_step_length_m=0.0025,
                max_sweep_rate=1000.0,
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
    ExplorationProtocol.start_streaming_response(response_bytes)

    error_bytes = json.dumps({"status": "error", "message": "error"}).encode("ascii")
    with pytest.raises(ServerError):
        ExplorationProtocol.start_streaming_response(error_bytes)


def test_stop_streaming_command():
    assert ExplorationProtocol.stop_streaming_command() == b'{"cmd":"stop_streaming"}\n'


def test_stop_streaming_response():
    response_bytes = json.dumps(
        {"status": "stop", "payload_size": 0, "message": "Stop streaming."}
    ).encode("ascii")
    ExplorationProtocol.stop_streaming_response(response_bytes)

    response_bytes = json.dumps({"status": "error", "message": "error"}).encode("ascii")
    with pytest.raises(ServerError):
        ExplorationProtocol.stop_streaming_response(response_bytes)


def test_get_next_header(single_sweep_metadata):
    get_next_header = json.dumps(
        {
            "status": "ok",
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
    data_array = np.array(range(100), dtype=INT_16_COMPLEX)
    data_array.resize(1, 100)
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

    first_frame = np.array(range(100), dtype=INT_16_COMPLEX)
    first_frame.resize(1, 100)
    second_frame = np.array(range(100, 200), dtype=INT_16_COMPLEX)
    second_frame.resize(1, 100)

    mock_payload = np.concatenate((first_frame, second_frame)).tobytes()
    assert len(mock_payload) == 800

    full_results = ExplorationProtocol.get_next_payload(mock_payload, partial_results)
    assert len(full_results) == 1

    (group,) = full_results
    assert len(group) == 2

    results = list(group.values())

    for result in results:
        # Make sure frame is resized correctly.
        assert result.frame.shape == (1, 100)

    np.testing.assert_array_equal(
        full_results[0][1].frame, first_frame["real"] + 1j * first_frame["imag"]
    )
    np.testing.assert_array_equal(
        full_results[0][2].frame, second_frame["real"] + 1j * second_frame["imag"]
    )


@pytest.mark.parametrize(
    ("rss_version", "expected_protocol"),
    [
        ("a121-v0.2.0-1-g123", ExplorationProtocol),
        ("a121-v0.4.0-rc1", ExplorationProtocol),
        ("a121-v0.4.0", ExplorationProtocol),
    ],
)
def test_get_exploration_protocol_normal_cases(rss_version, expected_protocol):
    assert get_exploration_protocol(parse_rss_version(rss_version)) == expected_protocol


def test_get_exploration_protocol_special_cases():
    assert get_exploration_protocol() == ExplorationProtocol

    incompatible_version = parse_rss_version("a121-v0.2.0")
    with pytest.raises(Exception):
        get_exploration_protocol(incompatible_version)
