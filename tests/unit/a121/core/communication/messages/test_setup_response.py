# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import typing as t

import pytest

from acconeer.exptool.a121._core.communication.exploration_protocol import (
    ExplorationProtocol,
    messages,
)


class TestSetupResponse:
    @pytest.fixture
    def valid_server_response(self) -> dict[str, t.Any]:
        return {
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
                        "high_speed_mode": True,
                    },
                ],
            ],
        }

    @pytest.fixture
    def invalid_server_response(self) -> dict[str, t.Any]:
        return {"status": "ok"}

    def test_parse(
        self, valid_server_response: dict[str, t.Any], invalid_server_response: dict[str, t.Any]
    ) -> None:
        assert (
            type(ExplorationProtocol.parse_message(valid_server_response, bytes()))
            == messages.SetupResponse
        )
        _ = messages.SetupResponse.parse(valid_server_response, bytes())

        with pytest.raises(messages.ParseError):
            messages.SetupResponse.parse(invalid_server_response, bytes())

    def test_apply(self) -> None:
        pytest.skip("Hard to unit test. Relies on system tests for correctness.")
