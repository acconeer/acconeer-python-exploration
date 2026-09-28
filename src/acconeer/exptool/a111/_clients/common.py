# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    """Little middle-class that enables string equality checking and is an enum."""


class Protocol(_StrEnum):
    EXPLORATION = "exploration"
    MODULE = "module"
    STREAMING = "streaming"


class Link(_StrEnum):
    SOCKET = "socket"
    UART = "uart"
    SPI = "spi"


ProtocolArg = str | Protocol
LinkArg = str | Link
