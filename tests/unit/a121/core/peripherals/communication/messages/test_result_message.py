# Copyright (c) Acconeer AB, 2022
# All rights reserved

import pytest

from acconeer.exptool.a121._core.peripherals import ExplorationProtocol
from acconeer.exptool.a121._core.peripherals.communication.exploration_protocol import messages


class TestResultMessage:
    @pytest.fixture
    def valid_server_message(self) -> dict:
        return {
            "status": "ok",
            "result_info": [
                [
                    {
                        "tick": 0,
                        "data_saturated": False,
                        "temperature": 0,
                        "frame_delayed": False,
                        "calibration_needed": False,
                    }
                ]
            ],
            "payload_size": 4,
        }

    @pytest.fixture
    def server_payload(self) -> bytes:
        return bytes([0, 0, 1, 1])

    @pytest.fixture
    def invalid_server_message(self) -> dict:
        return {"status": "ok"}

    def test_parse(
        self, valid_server_message: dict, server_payload: bytes, invalid_server_message: dict
    ) -> None:
        assert (
            type(ExplorationProtocol.parse_message(valid_server_message, server_payload))
            == messages.ResultMessage
        )
        _ = messages.ResultMessage.parse(valid_server_message, server_payload)

        with pytest.raises(messages.ParseError):
            messages.ResultMessage.parse(invalid_server_message, server_payload)

    def test_apply(self) -> None:
        pytest.skip("Hard to unit test. Relies on system tests for correctness.")
