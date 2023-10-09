# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

from acconeer.exptool.a121._core.entities import PRF, SensorCalibration, SessionConfig
from acconeer.exptool.a121._core.utils import iterate_extended_structure_values

from ._latest import ExplorationProtocolError
from ._no_15_6_mhz import ExplorationProtocol_No_15_6MHz_PRF


class ExplorationProtocol_No_5_2MHz_PRF(ExplorationProtocol_No_15_6MHz_PRF):
    @classmethod
    def setup_command(
        cls,
        session_config: SessionConfig,
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> bytes:
        for sensor_config in iterate_extended_structure_values(session_config.groups):
            if any(ssc.prf == PRF.PRF_5_2_MHz for ssc in sensor_config.subsweeps):
                raise ExplorationProtocolError(
                    "Connected Exploration server does not support 5.2MHz PRF."
                )

        return super().setup_command(session_config, calibrations)
