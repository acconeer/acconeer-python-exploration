# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import abc
import typing as t

import typing_extensions as te


class Message(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> te.Self:
        """Assumes that header and payload contains needed information and tries to parse.

        :param header: Message header
        :param payload: payload
        :raises Exception: whenever an error occurs (assumption doesn't hold)

        :returns: A freshly parsed Message
        """
        ...


class ParseError(Exception):
    pass
