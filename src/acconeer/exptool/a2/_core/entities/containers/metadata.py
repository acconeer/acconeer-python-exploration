# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved
from __future__ import annotations

import typing as t

import attrs


@attrs.frozen
class Metadata:
    tick_period: int
    sensor_calibration: t.Optional[str]
    update_period: t.Optional[float]
