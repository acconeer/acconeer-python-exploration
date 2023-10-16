# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from typing import Optional

from acconeer.exptool.a121._core.entities import (
    SensorCalibration,
    SessionConfig,
)
from acconeer.exptool.a121._core.utils import iterate_extended_structure


def get_calibrations_provided(
    session_config: SessionConfig,
    calibrations: Optional[dict[int, SensorCalibration]] = None,
) -> dict[int, bool]:
    calibrations_provided = {}
    for _, sensor_id, _ in iterate_extended_structure(session_config.groups):
        if calibrations:
            calibrations_provided[sensor_id] = sensor_id in calibrations
        else:
            calibrations_provided[sensor_id] = False

    return calibrations_provided
