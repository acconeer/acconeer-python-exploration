# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import attrs

from acconeer.exptool.a121._core.mediators import AgnosticClientFriends, Message
from acconeer.exptool.a121._core.mediators.agnostic_client import SystemInfoDict

from .parse_error import ParseError


@attrs.frozen
class SystemInfoResponse(Message):
    system_info: SystemInfoDict

    def apply(self, client: AgnosticClientFriends) -> None:
        if client._system_info is None:
            client._system_info = self.system_info
        else:
            raise RuntimeError(f"{client} already has system info set.")

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> SystemInfoResponse:
        try:
            return cls(header["system_info"])
        except KeyError as ke:
            raise ParseError from ke
