# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import typing_extensions as te

from acconeer.exptool.a121._core.mediators import AgnosticClientFriends, Message

from .parse_error import ParseError


class StartStreamingResponseHeader(te.TypedDict):
    status: te.Literal["start"]


class StopStreamingResponseHeader(te.TypedDict):
    status: te.Literal["stop"]


class StartStreamingResponse(Message):
    def apply(self, client: AgnosticClientFriends) -> None:
        if client._session_is_started:
            raise RuntimeError("Client received a start response when already started.")
        else:
            client._session_is_started = True

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> StartStreamingResponse:
        t.cast(StartStreamingResponseHeader, header)

        if header["status"] == "start":
            return cls()
        else:
            raise ParseError


class StopStreamingResponse(Message):
    def apply(self, client: AgnosticClientFriends) -> None:
        if client._session_is_started:
            client._session_is_started = False
        else:
            raise RuntimeError("Client received a stop response when already stopped.")

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> StopStreamingResponse:
        t.cast(StopStreamingResponseHeader, header)

        if header["status"] == "stop":
            return cls()
        else:
            raise ParseError
