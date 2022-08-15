# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from enum import Enum
from typing import Union


class _StrEnum(str, Enum):
    """Little middle-class that enables string equality checking and is an enum."""

    pass


class Protocol(_StrEnum):
    EXPLORATION = "exploration"
    MODULE = "module"
    STREAMING = "streaming"


class Link(_StrEnum):
    SOCKET = "socket"
    UART = "uart"
    SPI = "spi"


ProtocolArg = Union[str, Protocol]
LinkArg = Union[str, Link]
