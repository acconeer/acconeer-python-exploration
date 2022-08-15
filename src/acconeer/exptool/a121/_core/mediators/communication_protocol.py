# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Tuple

from typing_extensions import Protocol

from acconeer.exptool.a121._core.entities import (
    Metadata,
    Result,
    SensorInfo,
    ServerInfo,
    SessionConfig,
)


class CommunicationProtocol(Protocol):
    end_sequence: bytes

    @classmethod
    def get_system_info_command(cls) -> bytes:
        """The `get_system_info` command."""
        ...

    @classmethod
    def get_system_info_response(
        cls, bytes_: bytes, sensor_infos: dict[int, SensorInfo]
    ) -> Tuple[ServerInfo, str]:
        """Reads the response of `get_system_info` and parses it to a `ServerInfo`."""
        ...

    @classmethod
    def get_sensor_info_command(cls) -> bytes:
        """The `get_sensor_info` command."""
        ...

    @classmethod
    def get_sensor_info_response(cls, bytes_: bytes) -> dict[int, SensorInfo]:
        """Reads the response of `get_sensor_info` and returns
        a dict of the mapping sensor_id -> SensorInfo
        """
        ...

    @classmethod
    def setup_command(cls, session_config: SessionConfig) -> bytes:
        """The `setup` command."""
        ...

    @classmethod
    def setup_response(
        cls, bytes_: bytes, context_session_config: SessionConfig
    ) -> list[dict[int, Metadata]]:
        """Parses the reponse of the `setup` command and parses it to an extended Metadata."""
        ...

    @classmethod
    def start_streaming_command(cls) -> bytes:
        """The `start_streaming` command."""
        ...

    @classmethod
    def start_streaming_response(cls, bytes_: bytes) -> None:
        """Response of `start_streaming` command. May raise an exception if
        the server could not start streaming
        """
        ...

    @classmethod
    def get_next_header(
        cls, bytes_: bytes, extended_metadata: list[dict[int, Metadata]], ticks_per_second: int
    ) -> Tuple[int, list[dict[int, Result]]]:
        """Parses the header of a data package. Returns the payload size and
        partial (incomplete) Results.
        """
        ...

    @classmethod
    def get_next_payload(
        cls, bytes_: bytes, partial_results: list[dict[int, Result]]
    ) -> list[dict[int, Result]]:
        """Parses the payload of the data package. Populates the partial (incomplete)
        Results with data from the payload.
        """
        ...

    @classmethod
    def stop_streaming_command(cls) -> bytes:
        """The `stop_streaming` command"""
        ...

    @classmethod
    def stop_streaming_response(cls, bytes_: bytes) -> None:
        """Response of `stop_streaming` command. May raise an exception if
        the server could not stop streaming
        """
        ...
