# Copyright (c) Acconeer AB, 2022
# All rights reserved
from unittest.mock import Mock

import pytest

from acconeer.exptool.a121._core.peripherals import ExplorationProtocol
from acconeer.exptool.a121._core.peripherals.communication.exploration_protocol import messages


class TestGetSystemInfoReponse:
    @pytest.fixture
    def valid_server_response(self) -> dict:
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
    def invalid_server_response(self) -> dict:
        return {"status": "ok"}

    def test_parse(self, valid_server_response: dict, invalid_server_response: dict) -> None:
        assert (
            type(ExplorationProtocol.parse_message(valid_server_response, bytes()))
            == messages.SystemInfoResponse
        )
        _ = messages.SystemInfoResponse.parse(valid_server_response, bytes())

        with pytest.raises(messages.ParseError):
            messages.SystemInfoResponse.parse(invalid_server_response, bytes())

    def test_apply(self, valid_server_response: dict, mock_client: Mock) -> None:
        resp = messages.SystemInfoResponse.parse(valid_server_response, bytes())
        resp.apply(mock_client)
        assert mock_client._system_info is not None
        assert mock_client._system_info["rss_version"] == "v2.9.0"
        assert mock_client._system_info["sensor"] == "sensor_version"
        assert mock_client._system_info["sensor_count"] == 5
        assert mock_client._system_info["ticks_per_second"] == 1000000
        assert mock_client._system_info.get("hw") == "linux"
