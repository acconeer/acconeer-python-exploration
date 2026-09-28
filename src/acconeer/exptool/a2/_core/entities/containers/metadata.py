# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved
from __future__ import annotations

import attrs


@attrs.frozen
class Metadata:
    tick_period: int
    sensor_calibration: str | None
    update_period: float | None
