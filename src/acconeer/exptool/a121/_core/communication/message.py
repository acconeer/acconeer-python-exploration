# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import abc
import typing as t


MessageT = t.TypeVar("MessageT", bound="Message")


class Message(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def parse(cls: t.Type[MessageT], header: t.Dict[str, t.Any], payload: bytes) -> MessageT:
        """Assumes that header and payload contains needed information and tries to parse.

        :param header: Message header
        :param payload: payload
        :raises Exception: whenever an error occurs (assumption doesn't hold)

        :returns: A freshly parsed Message
        """
        ...
