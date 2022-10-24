# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

from acconeer.exptool.a121._core.entities import SensorCalibration, SessionConfig

from ._latest import ExplorationProtocol, ExplorationProtocolError


class ExplorationProtocol_0_4_1(ExplorationProtocol):
    @classmethod
    def setup_command(
        cls,
        session_config: SessionConfig,
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> bytes:
        if calibrations:
            raise ExplorationProtocolError("Calibrations are not supported for v0.4.1")
        return super().setup_command(session_config, None)
