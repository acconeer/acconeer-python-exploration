# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

import typing_extensions as te

from .message import Message


_ConfigT = t.TypeVar("_ConfigT", contravariant=True)


class CommunicationProtocol(te.Protocol[_ConfigT]):
    end_sequence: bytes

    @classmethod
    def get_system_info_command(cls) -> bytes:
        """The `get_system_info` command."""
        ...

    @classmethod
    def get_sensor_info_command(cls) -> bytes:
        """The `get_sensor_info` command."""
        ...

    @classmethod
    def setup_command(cls, config: _ConfigT) -> bytes:
        """The `setup` command."""
        ...

    @classmethod
    def start_streaming_command(cls) -> bytes:
        """The `start_streaming` command."""
        ...

    @classmethod
    def stop_streaming_command(cls) -> bytes:
        """The `stop_streaming` command"""
        ...

    @classmethod
    def set_baudrate_command(cls, baudrate: int) -> bytes:
        ...

    @classmethod
    def parse_message(cls, header: dict[str, t.Any], payload: bytes) -> Message:
        """Parses any supported Message given a header and a payload"""
        ...
