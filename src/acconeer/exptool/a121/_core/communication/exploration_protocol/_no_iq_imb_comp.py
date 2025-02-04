# Copyright (c) Acconeer AB, 2025
# All rights reserved

from __future__ import annotations

from typing import Any, Optional

from acconeer.exptool.a121._core.entities import SensorCalibration, SessionConfig
from acconeer.exptool.a121._core.utils import (
    iterate_extended_structure_values,
    map_over_extended_structure,
)

from ._latest import ExplorationProtocol, ExplorationProtocolError


class ExplorationProtocol_No_IQ_Imb_Comp(ExplorationProtocol):
    @classmethod
    def setup_command(
        cls,
        session_config: SessionConfig,
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> bytes:
        for sensor_config in iterate_extended_structure_values(session_config.groups):
            if any(ssc.iq_imbalance_compensation for ssc in sensor_config.subsweeps):
                msg = "Connected Exploration server does not support IQ imbalance compensation."
                raise ExplorationProtocolError(msg)

        return super().setup_command(session_config, calibrations)

    @classmethod
    def _setup_command_preprocessing(cls, session_config: SessionConfig) -> dict[str, Any]:
        result = super()._setup_command_preprocessing(session_config)
        result["groups"] = map_over_extended_structure(cls._remove_iq_imb_comp, result["groups"])

        return result

    @classmethod
    def _remove_iq_imb_comp(cls, sensor_config_dict: dict[str, Any]) -> dict[str, Any]:
        for subsweep_config_dict in sensor_config_dict["subsweeps"]:
            subsweep_config_dict.pop("iq_imbalance_compensation")
        return sensor_config_dict
