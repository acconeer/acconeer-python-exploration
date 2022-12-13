# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

from acconeer.exptool.a121._core.peripherals.communication.message import Message

from .parse_error import ParseError


class SystemInfoDict(te.TypedDict):
    rss_version: str
    sensor: str
    sensor_count: int
    ticks_per_second: int
    hw: te.NotRequired[t.Optional[str]]
    max_baudrate: te.NotRequired[int]


@attrs.frozen
class SystemInfoResponse(Message):
    system_info: SystemInfoDict

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> SystemInfoResponse:
        try:
            return cls(header["system_info"])
        except KeyError as ke:
            raise ParseError from ke
