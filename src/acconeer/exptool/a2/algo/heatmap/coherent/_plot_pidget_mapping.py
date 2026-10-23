# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from acconeer.exptool._core.docstrings import get_docstring
from acconeer.exptool.a2.algo.heatmap._plot_pidget_mapping import (
    get_plot_config_pidget_mapping as _get_common_pidget_mapping,
)
from acconeer.exptool.a2.algo.heatmap.coherent.plot_config import (
    CoherentHeatmapPlotConfig,
)
from acconeer.exptool.app.new.ui import pidgets
from acconeer.exptool.app.new.ui.components.types import PidgetFactoryMapping


def get_plot_config_pidget_mapping() -> PidgetFactoryMapping:
    return {
        **_get_common_pidget_mapping(),
        "display_mode": pidgets.EnumPidgetFactory(
            name_label_text="Display mode:",
            name_label_tooltip=get_docstring(CoherentHeatmapPlotConfig.DisplayMode) or "",
            enum_type=CoherentHeatmapPlotConfig.DisplayMode,
            label_mapping={
                CoherentHeatmapPlotConfig.DisplayMode.ABSOLUTE: "Absolute",
                CoherentHeatmapPlotConfig.DisplayMode.ANGLE: "Angle",
            },
        ),
    }
