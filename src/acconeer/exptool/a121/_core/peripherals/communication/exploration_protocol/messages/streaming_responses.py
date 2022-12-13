# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import typing_extensions as te

from acconeer.exptool.a121._core.peripherals.communication.message import Message

from .parse_error import ParseError


class StartStreamingResponseHeader(te.TypedDict):
    status: te.Literal["start"]


class StopStreamingResponseHeader(te.TypedDict):
    status: te.Literal["stop"]


class StartStreamingResponse(Message):
    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> StartStreamingResponse:
        t.cast(StartStreamingResponseHeader, header)

        if header["status"] == "start":
            return cls()
        else:
            raise ParseError


class StopStreamingResponse(Message):
    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> StopStreamingResponse:
        t.cast(StopStreamingResponseHeader, header)

        if header["status"] == "stop":
            return cls()
        else:
            raise ParseError
