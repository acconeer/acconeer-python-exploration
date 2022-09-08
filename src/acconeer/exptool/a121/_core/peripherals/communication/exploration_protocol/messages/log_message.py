# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

from acconeer.exptool.a121._core.mediators import AgnosticClientFriends, Message

from .parse_error import ParseError


LogLevelStr = t.Union[
    te.Literal["ERROR"],
    te.Literal["WARNING"],
    te.Literal["INFO"],
    te.Literal["VERBOSE"],
    te.Literal["DEBUG"],
]


class LogMessageHeader(te.TypedDict):
    level: LogLevelStr
    timestamp: int
    module: str
    log: str


@attrs.frozen
class LogMessage(Message):
    def apply(self, client: AgnosticClientFriends) -> None:
        pass

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> LogMessage:
        t.cast(LogMessageHeader, header)

        if header["status"] == "log":
            return cls()

        raise ParseError
