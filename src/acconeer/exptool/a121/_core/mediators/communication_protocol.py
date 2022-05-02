from __future__ import annotations

from typing import Tuple

from acconeer.exptool.a121._core.entities import Metadata, Result, ServerInfo, SessionConfig

from typing_extensions import Protocol


class CommunicationProtocol(Protocol):
    end_sequence: bytes

    def get_system_info_command(self) -> bytes:
        """The `get_system_info` command."""
        ...

    def get_system_info_response(self, bytes_: bytes) -> ServerInfo:
        """Reads the response of `get_system_info` and parses it to a `ServerInfo`."""
        ...

    def get_sensor_info_command(self) -> bytes:
        """The `get_sensor_info` command."""
        ...

    def get_sensor_info_response(self, bytes_: bytes) -> list[int]:
        """Reads the response of `get_sensor_info` and returns a list of connected sensor_ids."""
        ...

    def setup_command(self, session_config: SessionConfig) -> bytes:
        """The `setup` command."""
        ...

    def setup_response(
        self, bytes_: bytes, context_session_config: SessionConfig
    ) -> list[dict[int, Metadata]]:
        """Parses the reponse of the `setup` command and parses it to an extended Metadata."""
        ...

    def start_streaming_command(self) -> bytes:
        """The `start_streaming` command."""
        ...

    def start_streaming_response(self, bytes_: bytes) -> None:
        """Response of `start_streaming` command. May raise an exception if
        the server could not start streaming
        """
        ...

    def get_next_header(
        self, bytes_: bytes, extended_metadata: list[dict[int, Metadata]], ticks_per_second: int
    ) -> Tuple[int, list[dict[int, Result]]]:
        """Parses the header of a data package. Returns the payload size and
        partial (incomplete) Results.
        """
        ...

    def get_next_payload(
        self, bytes_: bytes, partial_results: list[dict[int, Result]]
    ) -> list[dict[int, Result]]:
        """Parses the payload of the data package. Populates the partial (incomplete)
        Results with data from the payload.
        """
        ...

    def stop_streaming_command(self) -> bytes:
        """The `stop_streaming` command"""
        ...

    def stop_streaming_response(self, bytes_: bytes) -> None:
        """Response of `stop_streaming` command. May raise an exception if
        the server could not stop streaming
        """
        ...
