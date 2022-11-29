# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import json
from typing import Any, Callable, Optional, Union

import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core.peripherals.communication.exploration_protocol import (
    ExplorationProtocol,
    ExplorationProtocol_0_4_1,
    get_exploration_protocol,
)
from acconeer.exptool.a121._core.utils import parse_rss_version


class TestLatestExplorationProtocolCommands:
    @pytest.mark.parametrize(
        ("function", "kwargs"),
        [
            (ExplorationProtocol.get_system_info_command, {}),
            (ExplorationProtocol.get_sensor_info_command, {}),
            (ExplorationProtocol.setup_command, dict(session_config=a121.SessionConfig())),
            (ExplorationProtocol.start_streaming_command, {}),
            (ExplorationProtocol.stop_streaming_command, {}),
            (ExplorationProtocol.set_baudrate_command, dict(baudrate=0)),
        ],
    )
    def test_all_command_functions_end_with_linebreak(
        self, function: Callable, kwargs: Any
    ) -> None:
        assert function(**kwargs).endswith(b"\n")

    def test_get_system_info_command(self) -> None:
        assert ExplorationProtocol.get_system_info_command() == b'{"cmd":"get_system_info"}\n'

    def test_get_sensor_info_command(self) -> None:
        assert ExplorationProtocol.get_sensor_info_command() == b'{"cmd":"get_sensor_info"}\n'

    def test_start_streaming_command(self) -> None:
        assert ExplorationProtocol.start_streaming_command() == b'{"cmd":"start_streaming"}\n'

    def test_stop_streaming_command(self) -> None:
        assert ExplorationProtocol.stop_streaming_command() == b'{"cmd":"stop_streaming"}\n'

    def test_set_baudrate_command(self) -> None:
        assert (
            ExplorationProtocol.set_baudrate_command(0)
            == b'{"cmd":"set_uart_baudrate","baudrate":0}\n'
        )

    @pytest.mark.parametrize("update_rate", [20, None])
    def test_setup_command(self, update_rate: Optional[Union[float, int]]) -> None:
        # This explicitly sets all fields in order to guard against changes of defaults.
        config = a121.SessionConfig(
            [
                {
                    1: a121.SensorConfig(
                        subsweeps=[
                            a121.SubsweepConfig(
                                start_point=0,
                                num_points=10,
                                step_length=1,
                                profile=a121.Profile.PROFILE_1,
                                hwaas=1,
                                receiver_gain=1,
                                enable_tx=True,
                                enable_loopback=False,
                                phase_enhancement=False,
                                prf=a121.PRF.PRF_6_5_MHz,
                            ),
                        ],
                        sweeps_per_frame=1,
                        sweep_rate=None,
                        frame_rate=None,
                        continuous_sweep_mode=False,
                        double_buffering=False,
                        inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                        inter_sweep_idle_state=a121.IdleState.READY,
                    ),
                },
            ],
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
                                    "start_point": 0,
                                    "num_points": 10,
                                    "step_length": 1,
                                    "profile": 1,
                                    "hwaas": 1,
                                    "receiver_gain": 1,
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
            expected_dict["update_rate"] = update_rate  # type: ignore[assignment]

        assert json.loads(ExplorationProtocol.setup_command(config)) == expected_dict


class TestExplorationProtocolFactory:
    @pytest.mark.parametrize(
        ("rss_version", "expected_protocol"),
        [
            ("a121-v0.4.1", ExplorationProtocol_0_4_1),
            ("a121-v0.4.2-279-gebaf6243f0", ExplorationProtocol_0_4_1),
            ("a121-v0.4.2-280-ge201249eb0", ExplorationProtocol),
            ("a121-v0.5.0", ExplorationProtocol),
            ("a121-v0.6.0", ExplorationProtocol),
        ],
    )
    def test_get_exploration_protocol_compatible_versions(
        self,
        rss_version: str,
        expected_protocol: Union[ExplorationProtocol, ExplorationProtocol_0_4_1],
    ) -> None:
        assert get_exploration_protocol(parse_rss_version(rss_version)) == expected_protocol

    @pytest.mark.parametrize(
        "rss_version",
        ["a121-v0.2.0"],
    )
    def test_get_exploration_protocol_incompatible_versions(self, rss_version: str) -> None:
        assert get_exploration_protocol() == ExplorationProtocol

        with pytest.raises(Exception):
            get_exploration_protocol(parse_rss_version(rss_version))
