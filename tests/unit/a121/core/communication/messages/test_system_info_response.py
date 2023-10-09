# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import typing as t

import pytest

from acconeer.exptool.a121._core.communication.exploration_protocol import (
    ExplorationProtocol,
    messages,
)


class TestGetSystemInfoReponse:
    @pytest.fixture
    def valid_server_response(self) -> dict[str, t.Any]:
        return {
            "status": "ok",
            "system_info": {
                "rss_version": "v2.9.0",
                "sensor": "sensor_version",
                "sensor_count": 5,
                "ticks_per_second": 1000000,
                "hw": "linux",
            },
        }

    @pytest.fixture
    def invalid_server_response(self) -> dict[str, t.Any]:
        return {"status": "ok"}

    def test_parse(
        self, valid_server_response: dict[str, t.Any], invalid_server_response: dict[str, t.Any]
    ) -> None:
        assert (
            type(ExplorationProtocol.parse_message(valid_server_response, bytes()))
            == messages.SystemInfoResponse
        )
        _ = messages.SystemInfoResponse.parse(valid_server_response, bytes())

        with pytest.raises(messages.ParseError):
            messages.SystemInfoResponse.parse(invalid_server_response, bytes())
