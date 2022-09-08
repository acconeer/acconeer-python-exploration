# Copyright (c) Acconeer AB, 2022
# All rights reserved


import pytest

from acconeer.exptool.a121._core.peripherals import ExplorationProtocol
from acconeer.exptool.a121._core.peripherals.communication.exploration_protocol import messages


class TestStartStreamingResponse:
    @pytest.fixture
    def valid_server_response(self):
        return {"status": "start", "payload_size": 0, "message": "Start streaming."}

    @pytest.fixture
    def invalid_server_response(self):
        return {"status": "ok"}

    def test_parse(self, valid_server_response, invalid_server_response):
        assert (
            type(ExplorationProtocol.parse_message(valid_server_response, bytes()))
            == messages.StartStreamingResponse
        )
        _ = messages.StartStreamingResponse.parse(valid_server_response, bytes())

        with pytest.raises(messages.ParseError):
            messages.StartStreamingResponse.parse(invalid_server_response, bytes())

    def test_apply(self, valid_server_response, mock_client):
        mock_client._session_is_started = False
        resp = messages.StartStreamingResponse.parse(valid_server_response, bytes())
        resp.apply(mock_client)
        assert mock_client._session_is_started
