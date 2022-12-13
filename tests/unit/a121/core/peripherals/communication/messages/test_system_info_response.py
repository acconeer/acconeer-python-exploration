# Copyright (c) Acconeer AB, 2022
# All rights reserved

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
