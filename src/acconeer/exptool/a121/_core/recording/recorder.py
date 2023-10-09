# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from typing import Any, Optional

import typing_extensions as te

from acconeer.exptool._core.entities import ClientInfo
from acconeer.exptool.a121._core.entities import (
    Metadata,
    Result,
    SensorCalibration,
    ServerInfo,
    SessionConfig,
)


class RecorderAttachable(te.Protocol):
    """Dependecy Inversion interface for clients"""

    def attach_recorder(self, recorder: Recorder) -> None:
        ...

    def detach_recorder(self) -> Optional[Recorder]:
        ...


class Recorder(te.Protocol):
    """The interface a Recorder needs to follow"""

    def _start(
        self,
        *,
        client_info: ClientInfo,
        server_info: ServerInfo,
    ) -> None:
        ...

    def _start_session(
        self,
        *,
        session_config: SessionConfig,
        extended_metadata: list[dict[int, Metadata]],
        calibrations: Optional[dict[int, SensorCalibration]],
        calibrations_provided: Optional[dict[int, bool]],
    ) -> None:
        ...

    def _sample(self, extended_result: list[dict[int, Result]]) -> None:
        ...

    def _stop_session(self) -> None:
        ...

    def close(self) -> Any:
        ...

    def __enter__(self) -> te.Self:
        return self

    def __exit__(self, *args: Any, **kwargs: Any) -> None:
        self.close()
