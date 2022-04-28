from __future__ import annotations

from typing import Any

from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    Result,
    ServerInfo,
    SessionConfig,
)

from typing_extensions import Protocol


class Recorder(Protocol):
    def start(
        self,
        *,
        client_info: ClientInfo,
        extended_metadata: list[dict[int, Metadata]],
        server_info: ServerInfo,
        session_config: SessionConfig,
    ) -> None:
        ...

    def sample(self, extended_result: list[dict[int, Result]]) -> None:
        ...

    def stop(self) -> Any:
        ...
