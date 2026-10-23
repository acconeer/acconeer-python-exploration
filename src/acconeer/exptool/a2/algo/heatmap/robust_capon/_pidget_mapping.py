# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved

from __future__ import annotations

from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.app.new.ui import pidgets
from acconeer.exptool.app.new.ui.components.types import PidgetFactoryMapping

from .config import HeatmapConfig


def get_config_pidget_mapping() -> PidgetFactoryMapping:
    return {
        "covariance_matrix_time_constant_s": pidgets.FloatSliderPidgetFactory(
            name_label_text="Covar. matrix time constant:",
            name_label_tooltip=get_attribute_docstring(
                HeatmapConfig, "covariance_matrix_time_constant_s"
            ),
            limits=(0.01, 20),
            decimals=2,
            suffix=" s",
            log_scale=True,
        ),
        "high_pass_filter_time_constant_s": pidgets.FloatSliderPidgetFactory(
            name_label_text="High-pass filter time constant:",
            name_label_tooltip=get_attribute_docstring(
                HeatmapConfig, "high_pass_filter_time_constant_s"
            ),
            limits=(0.01, 20),
            decimals=2,
            suffix=" s",
            log_scale=True,
        ),
        "steering_vector_epsilon": pidgets.FloatSliderPidgetFactory(
            name_label_text="Steering vector epsilon uncertainty:",
            name_label_tooltip=get_attribute_docstring(HeatmapConfig, "steering_vector_epsilon"),
            limits=(0, 0.5),
            decimals=2,
            suffix="",
            log_scale=False,
        ),
        "num_az_angles": pidgets.IntPidgetFactory(
            name_label_text="Num az angles:",
            name_label_tooltip=get_attribute_docstring(HeatmapConfig, "num_az_angles"),
            limits=(0, 180),
        ),
        "az_angle_range": pidgets.FloatRangeSliderPidgetFactory(
            name_label_text="Az angle range:",
            name_label_tooltip=get_attribute_docstring(HeatmapConfig, "az_angle_range"),
            limits=(-60.0, 60.0),
            decimals=1,
        ),
        "num_el_angles": pidgets.IntPidgetFactory(
            name_label_text="Num el angles:",
            name_label_tooltip=get_attribute_docstring(HeatmapConfig, "num_el_angles"),
            limits=(0, 180),
        ),
        "el_angle_range": pidgets.FloatRangeSliderPidgetFactory(
            name_label_text="El angle range:",
            name_label_tooltip=get_attribute_docstring(HeatmapConfig, "el_angle_range"),
            limits=(-60.0, 60.0),
            decimals=1,
        ),
    }
