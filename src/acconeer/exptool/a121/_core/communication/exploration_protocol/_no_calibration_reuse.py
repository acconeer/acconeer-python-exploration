# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

from acconeer.exptool.a121._core.entities import SensorCalibration, SessionConfig

from ._latest import ExplorationProtocolError
from ._no_5_2_mhz import ExplorationProtocol_No_5_2MHz_PRF


class ExplorationProtocol_NoCalibrationReuse(ExplorationProtocol_No_5_2MHz_PRF):
    @classmethod
    def setup_command(
        cls,
        session_config: SessionConfig,
        calibrations: dict[int, SensorCalibration] | None = None,
    ) -> bytes:
        if calibrations:
            raise ExplorationProtocolError(
                "Connected Exploration server does not support "
                + "calibration reuse (passing 'calibrations')"
            )
        return super().setup_command(session_config, None)
