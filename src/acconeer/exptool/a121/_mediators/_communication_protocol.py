from __future__ import annotations

from acconeer.exptool.a121 import Metadata, ServerInfo, SessionConfig

from typing_extensions import Protocol


class CommunicationProtocol(Protocol):
    def get_system_info_command(self) -> bytes:
        ...

    def get_system_info_response(self, bytes_: bytes) -> ServerInfo:
        ...

    def get_sensor_info_command(self) -> bytes:
        ...

    def get_sensor_info_response(self, bytes_: bytes) -> list[int]:
        ...

    def setup_command(self, session_config: SessionConfig) -> bytes:
        ...

    def setup_response(
        self, bytes_: bytes, context_session_config: SessionConfig
    ) -> list[dict[int, Metadata]]:
        ...
