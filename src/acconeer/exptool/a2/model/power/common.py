# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved
from __future__ import annotations

from acconeer.exptool import a2

from .domain import CurrentBreakdown
from .lookup import SensorConstants


def get_idle_rs_current(
    config: a2.SessionConfig,
    sensor: SensorConstants,
) -> CurrentBreakdown:
    """
    Returns the RS current while idling between frames
    """
    if config.update_rate is None and config.sensor_config.frame_rate is not None:
        return sensor.inter_frame_rs_currents[config.sensor_config.inter_frame_idle_state]
    return CurrentBreakdown.zero()
