# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Any, Optional

from typing_extensions import Protocol

from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    Result,
    SensorCalibration,
    ServerInfo,
    SessionConfig,
)


class Recorder(Protocol):
    def _start(
        self,
        *,
        client_info: ClientInfo,
        extended_metadata: list[dict[int, Metadata]],
        server_info: ServerInfo,
        session_config: SessionConfig,
        calibrations: Optional[dict[int, SensorCalibration]],
        calibrations_provided: Optional[dict[int, bool]],
    ) -> None:
        ...

    def _sample(self, extended_result: list[dict[int, Result]]) -> None:
        ...

    def _stop(self) -> Any:
        ...
