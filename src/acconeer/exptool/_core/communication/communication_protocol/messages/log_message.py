# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

from .message import Message, ParseError


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
    message: ServerLog

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> LogMessage:
        t.cast(LogMessageHeader, header)

        if header["status"] == "log":
            return cls(
                ServerLog(
                    level=header["level"],
                    timestamp=header["timestamp"],
                    module=header["module"],
                    log=header["log"],
                )
            )
        raise ParseError


@attrs.frozen(kw_only=True)
class ServerLog:
    level: str
    timestamp: int
    module: str
    log: str
