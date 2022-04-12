from __future__ import annotations

from typing import Any


try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol  # type: ignore[misc]

from acconeer.exptool.a121._entities import ClientInfo, Metadata, Result, ServerInfo, SessionConfig


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
