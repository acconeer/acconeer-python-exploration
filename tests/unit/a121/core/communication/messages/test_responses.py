# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved
from __future__ import annotations

import typing as t

import pytest

from acconeer.exptool._core.communication.communication_protocol import messages
from acconeer.exptool.a121._core.communication.exploration_protocol import (
    ExplorationProtocol,
)
from acconeer.exptool.a121._core.communication.exploration_protocol import (
    messages as a121_messages,
)


VALID_SERVER_RESPONSES: dict[type[messages.Message], dict[str, t.Any]] = {
    a121_messages.SensorInfoResponse: {
        "status": "ok",
        "payload_size": 0,
        "sensor_info": [
            {"connected": True},
            {"connected": False},
            {"connected": True},
            {"connected": False},
            {"connected": False},
        ],
    },
    messages.SetBaudrateResponse: {"status": "ok", "payload_size": 0, "message": "set baudrate"},
    a121_messages.SetupResponse: {
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
    },
    messages.StartStreamingResponse: {
        "status": "start",
        "payload_size": 0,
        "message": "Start streaming.",
    },
    messages.StopStreamingResponse: {
        "status": "stop",
        "payload_size": 0,
        "message": "Stop streaming.",
    },
    messages.SystemInfoResponse: {
        "status": "ok",
        "system_info": {
            "rss_version": "v2.9.0",
            "sensor": "sensor_version",
            "sensor_count": 5,
            "ticks_per_second": 1000000,
            "hw": "linux",
        },
    },
}


@pytest.mark.parametrize("response_type", VALID_SERVER_RESPONSES, ids=lambda clz: clz.__name__)
def test_valid_response_parses_as_its_type(response_type: type[messages.Message]) -> None:
    server_response = VALID_SERVER_RESPONSES[response_type]
    assert type(ExplorationProtocol.parse_message(server_response, b"")) is response_type
    response_type.parse(server_response, b"")


@pytest.mark.parametrize("response_type", VALID_SERVER_RESPONSES, ids=lambda clz: clz.__name__)
def test_response_without_its_fields_does_not_parse(response_type: type[messages.Message]) -> None:
    with pytest.raises(messages.ParseError):
        response_type.parse({"status": "ok"}, b"")
