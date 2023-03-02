# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import typing as t

import pytest

from acconeer.exptool.a121._core.peripherals import ExplorationProtocol
from acconeer.exptool.a121._core.peripherals.communication.exploration_protocol import messages


class TestGetSensorInfoResponse:
    @pytest.fixture
    def valid_server_response(self) -> dict[str, t.Any]:
        return {
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

    @pytest.fixture
    def invalid_server_response(self) -> dict[str, t.Any]:
        return {"status": "ok"}

    def test_parse(
        self, valid_server_response: dict[str, t.Any], invalid_server_response: dict[str, t.Any]
    ) -> None:
        assert (
            type(ExplorationProtocol.parse_message(valid_server_response, bytes()))
            == messages.SensorInfoResponse
        )
        _ = messages.SensorInfoResponse.parse(valid_server_response, bytes())

        with pytest.raises(messages.ParseError):
            messages.SensorInfoResponse.parse(invalid_server_response, bytes())
