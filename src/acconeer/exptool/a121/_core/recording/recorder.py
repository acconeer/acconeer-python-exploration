# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import typing_extensions as te

from acconeer.exptool._core import recording
from acconeer.exptool.a121._core.entities import (
    Metadata,
    Result,
    SensorCalibration,
    ServerInfo,
    SessionConfig,
)


class Recorder(
    recording.Recorder[
        SessionConfig,  # Config type
        list[dict[int, Metadata]],  # Metadata type
        list[dict[int, Result]],  # Result type
        ServerInfo,  # Server info type
    ],
    te.Protocol,
):
    def _start_session(
        self,
        *,
        config: SessionConfig,
        metadata: list[dict[int, Metadata]],
        calibrations: dict[int, SensorCalibration] | None = None,
        calibrations_provided: dict[int, bool] | None = None,
    ) -> None: ...


RecorderAttachable: te.TypeAlias = recording.RecorderAttachable[Recorder]
