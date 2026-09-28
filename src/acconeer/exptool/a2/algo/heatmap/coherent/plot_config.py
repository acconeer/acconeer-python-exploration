# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from enum import Enum, auto

import attrs
import typing_extensions as te

from acconeer.exptool._core.class_creation.enum import find_by_name
from acconeer.exptool.a2.algo.heatmap.plot_config_common import (
    HeatmapPlotConfig,
)


@attrs.mutable
class CoherentHeatmapPlotConfig(HeatmapPlotConfig):
    class DisplayMode(Enum):
        """Display mode. ``ABSOLUTE`` returns absolute of complex value. ``ANGLE`` returns complex argument."""

        ABSOLUTE = auto()
        ANGLE = auto()

        @classmethod
        def _missing_(cls, value: object) -> te.Self | None:
            if isinstance(value, str):
                return find_by_name(cls, value)
            else:
                return None

    display_mode: DisplayMode = attrs.field(
        default=DisplayMode.ANGLE,
        converter=DisplayMode,
    )

    @classmethod
    def default(cls) -> te.Self:
        return cls()
