# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

from acconeer.exptool.a121._core.peripherals.communication.message import Message

from .parse_error import ParseError


class ErrorMessageHeader(te.TypedDict):
    status: te.Literal["error"]
    message: str


@attrs.frozen
class ErroneousMessage(Message):
    message: str

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> ErroneousMessage:
        t.cast(ErrorMessageHeader, header)

        if header["status"] == "error":
            return cls(header["message"])

        raise ParseError
