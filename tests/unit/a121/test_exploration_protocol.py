import json

from acconeer.exptool import a121
from acconeer.exptool.a121._protocol import ExplorationProtocol


def test_get_system_info_command():
    assert ExplorationProtocol.get_system_info_command() == b'{"cmd":"get_system_info"}\n'


def test_get_sensor_info_command():
    assert ExplorationProtocol.get_sensor_info_command() == b'{"cmd":"get_sensor_info"}\n'


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
