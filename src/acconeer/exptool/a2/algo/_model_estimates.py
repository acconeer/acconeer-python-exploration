# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Rate estimates from :mod:`acconeer.exptool.a2.model`, for user-facing
convenience checks only.

The model's outputs can change between releases. Use these estimates only where
a changed value cannot alter a processor or detector result or a generated
configuration, e.g. a hint that an update rate is out of reach. This is the
only module in :mod:`acconeer.exptool.a2.algo` that may import
:mod:`acconeer.exptool.a2.model`.
"""

from __future__ import annotations

from acconeer.exptool import a2
from acconeer.exptool.a2.model import power as a2_power


_APS_IDLE = a2_power.SensorConstants.ApsIdleState.APS_HF_WFI
_APS_ACTIVE = a2_power.SensorConstants.ApsActiveState.APS_HF


def estimated_max_frame_rate(session_config: a2.SessionConfig) -> float:
    """Highest frame rate (Hz) for ``session_config``: the inverse of the power
    model's active-frame duration."""
    return 1.0 / a2_power.frame_active(session_config, _APS_IDLE, _APS_ACTIVE).duration


def estimated_max_sweep_rate(sensor_config: a2.SensorConfig) -> float:
    """Highest sweep rate (Hz) for ``sensor_config``: the inverse of the power
    model's active-sweep duration."""
    return 1.0 / a2_power.sweep_active(sensor_config, _APS_IDLE).duration
