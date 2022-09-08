# Copyright (c) Acconeer AB, 2022
# All rights reserved

import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core.peripherals import ExplorationProtocol
from acconeer.exptool.a121._core.peripherals.communication.exploration_protocol import messages


class TestGetSensorInfoResponse:
    @pytest.fixture
    def valid_server_response(self):
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
    def invalid_server_response(self):
        return {"status": "ok"}

    def test_parse(self, valid_server_response, invalid_server_response):
        assert (
            type(ExplorationProtocol.parse_message(valid_server_response, bytes()))
            == messages.SensorInfoResponse
        )
        _ = messages.SensorInfoResponse.parse(valid_server_response, bytes())

        with pytest.raises(messages.ParseError):
            messages.SensorInfoResponse.parse(invalid_server_response, bytes())

    def test_apply(self, valid_server_response, mock_client):
        resp = messages.SensorInfoResponse.parse(valid_server_response, bytes())
        resp.apply(mock_client)

        assert mock_client._sensor_infos == {
            1: a121.SensorInfo(connected=True),
            2: a121.SensorInfo(connected=False),
            3: a121.SensorInfo(connected=True),
            4: a121.SensorInfo(connected=False),
            5: a121.SensorInfo(connected=False),
        }
