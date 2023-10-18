# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

import pytest

from acconeer.exptool._core.communication.communication_protocol import messages
from acconeer.exptool.a121._core.communication.exploration_protocol import (
    ExplorationProtocol,
)


class TestStartStreamingResponse:
    @pytest.fixture
    def valid_server_response(self) -> dict[str, t.Any]:
        return {"status": "start", "payload_size": 0, "message": "Start streaming."}

    @pytest.fixture
    def invalid_server_response(self) -> dict[str, t.Any]:
        return {"status": "ok"}

    def test_parse(
        self, valid_server_response: dict[str, t.Any], invalid_server_response: dict[str, t.Any]
    ) -> None:
        assert (
            type(ExplorationProtocol.parse_message(valid_server_response, bytes()))
            == messages.StartStreamingResponse
        )
        _ = messages.StartStreamingResponse.parse(valid_server_response, bytes())

        with pytest.raises(messages.ParseError):
            messages.StartStreamingResponse.parse(invalid_server_response, bytes())
