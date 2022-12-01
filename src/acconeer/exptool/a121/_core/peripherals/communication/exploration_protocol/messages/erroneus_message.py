# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

from acconeer.exptool.a121._core.mediators import AgnosticClientFriends, Message
from acconeer.exptool.a121._core.peripherals.communication.exploration_protocol.server_error import (  # noqa: E501
    ServerError,
)

from .parse_error import ParseError


class ErrorMessageHeader(te.TypedDict):
    status: te.Literal["error"]
    message: str


@attrs.frozen
class ErroneousMessage(Message):
    message: str

    def apply(self, client: AgnosticClientFriends) -> None:
        last_error = ""
        for log in client._log_queue:
            if log.level == "ERROR" and "exploration_server" not in log.module:
                last_error = f" ({log.log})"
        raise ServerError(f"{self.message}{last_error}")

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> ErroneousMessage:
        t.cast(ErrorMessageHeader, header)

        if header["status"] == "error":
            return cls(header["message"])

        raise ParseError
