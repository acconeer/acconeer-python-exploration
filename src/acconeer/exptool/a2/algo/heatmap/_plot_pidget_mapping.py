# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.a2.algo.heatmap.plot_config_common import HeatmapPlotConfig
from acconeer.exptool.app.new.ui import pidgets
from acconeer.exptool.app.new.ui.components.types import PidgetFactoryMapping


def get_plot_config_pidget_mapping() -> PidgetFactoryMapping:
    return {
        "max_2d_heat": pidgets.OptionalIntPidgetFactory(
            name_label_text="Max heatmap value:",
            name_label_tooltip=get_attribute_docstring(HeatmapPlotConfig, "max_2d_heat"),
            limits=(1, 1000000000),
        ),
        "log_scale_output": pidgets.CheckboxPidgetFactory(
            name_label_text="Apply log scale (dB)",
            name_label_tooltip=get_attribute_docstring(HeatmapPlotConfig, "log_scale_output"),
        ),
        "normalized_heat_cutoff": pidgets.FloatSliderPidgetFactory(
            name_label_text="Angular heat cutoff:",
            name_label_tooltip=get_attribute_docstring(
                HeatmapPlotConfig, "normalized_heat_cutoff"
            ),
            limits=(0, 1),
            decimals=2,
        ),
    }
