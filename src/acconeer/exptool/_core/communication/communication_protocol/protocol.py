# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import abc
import typing as t

from .messages import Message


_ConfigT = t.TypeVar("_ConfigT", contravariant=True)


class CommunicationProtocol(abc.ABC, t.Generic[_ConfigT]):
    end_sequence: t.ClassVar[bytes] = b"\n"

    @classmethod
    @abc.abstractmethod
    def setup_command(cls, config: _ConfigT) -> bytes:
        """The `setup` command."""
        pass

    @classmethod
    @abc.abstractmethod
    def parse_message(cls, header: dict[str, t.Any], payload: bytes) -> Message:
        """Parses any supported Message given a header and a payload"""
        pass

    @classmethod
    def get_system_info_command(cls) -> bytes:
        """The `get_system_info` command."""
        return b'{"cmd":"get_system_info"}\n'

    @classmethod
    def get_sensor_info_command(cls) -> bytes:
        return b'{"cmd":"get_sensor_info"}\n'

    @classmethod
    def start_streaming_command(cls) -> bytes:
        return b'{"cmd":"start_streaming"}\n'

    @classmethod
    def stop_streaming_command(cls) -> bytes:
        return b'{"cmd":"stop_streaming"}\n'

    @classmethod
    def set_baudrate_command(cls, baudrate: int) -> bytes:
        return b'{"cmd":"set_uart_baudrate","baudrate":' + str(baudrate).encode("ascii") + b"}\n"
