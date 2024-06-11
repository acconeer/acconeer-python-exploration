# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import typing as t

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
        t.List[t.Dict[int, Metadata]],  # Metadata type
        t.List[t.Dict[int, Result]],  # Result type
        ServerInfo,  # Server info type
    ],
    te.Protocol,
):
    def _start_session(
        self,
        *,
        config: SessionConfig,
        metadata: t.List[t.Dict[int, Metadata]],
        calibrations: t.Optional[t.Dict[int, SensorCalibration]] = None,
        calibrations_provided: t.Optional[t.Dict[int, bool]] = None,
    ) -> None: ...


RecorderAttachable: te.TypeAlias = recording.RecorderAttachable[Recorder]
