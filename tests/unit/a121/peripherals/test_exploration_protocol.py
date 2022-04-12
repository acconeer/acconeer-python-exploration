import json

import numpy as np

from acconeer.exptool import a121
from acconeer.exptool.a121._entities import SensorDataType
from acconeer.exptool.a121._peripherals import ExplorationProtocol


def test_get_system_info_command():
    assert ExplorationProtocol.get_system_info_command() == b'{"cmd":"get_system_info"}\n'


def test_get_system_info_response():
    response = json.dumps(
        {
            "status": "ok",
            "rss_version": "v2.9.0",
            "sensor": "sensor_version",
            "sensor_count": 5,
            "ticks_per_second": 1000000,
            "hw": "linux",
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
                        "subsweeps": [{"hwaas": 8}],
                        "sweeps_per_frame": 1,
                    },
                },
            ]
        ],
        "update_rate": 20,
    }

    assert json.loads(ExplorationProtocol.setup_command(config)) == expected_dict


def test_setup_response():
    response = json.dumps(
        {
            "status": "ok",
            "tick_period": 50,
            "payload_size": 0,
            "metadata": [
                [  # Group 1
                    {
                        "sweep_data_length": 240,
                        "frame_data_length": 240,
                        "subsweep_data_offset": [0],
                        "subsweep_data_length": [240],
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
        {
            1: a121.Metadata(
                sweep_data_length=240,
                frame_data_length=240,
                subsweep_data_offset=np.array([0]),
                subsweep_data_length=np.array([240]),
                data_type=SensorDataType.INT_16_COMPLEX,
            )
        },
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
