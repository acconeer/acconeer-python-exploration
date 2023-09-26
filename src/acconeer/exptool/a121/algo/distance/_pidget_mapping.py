# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

from acconeer.exptool import a121
from acconeer.exptool.app.new.ui.plugin_components import PidgetFactoryMapping, pidgets
from acconeer.exptool.app.new.ui.plugin_components.pidgets.hooks import (
    disable_if,
    enable_if,
    parameter_is,
)

from ._detector import PeakSortingMethod, ReflectorShape, ThresholdMethod


def get_pidget_mapping() -> PidgetFactoryMapping:
    return {
        "start_m": pidgets.FloatPidgetFactory(
            name_label_text="Range start:",
            suffix=" m",
            decimals=3,
        ),
        "end_m": pidgets.FloatPidgetFactory(
            name_label_text="Range end:",
            suffix=" m",
            decimals=3,
        ),
        "close_range_leakage_cancellation": pidgets.CheckboxPidgetFactory(
            name_label_text="Enable close range leakage cancellation"
        ),
        "max_step_length": pidgets.OptionalIntPidgetFactory(
            name_label_text="Max step length:",
            checkbox_label_text="Set",
            limits=(1, None),
            init_set_value=12,
        ),
        "max_profile": pidgets.EnumPidgetFactory(
            name_label_text="Max profile:",
            enum_type=a121.Profile,
            label_mapping={
                a121.Profile.PROFILE_1: "1 (shortest)",
                a121.Profile.PROFILE_2: "2",
                a121.Profile.PROFILE_3: "3",
                a121.Profile.PROFILE_4: "4",
                a121.Profile.PROFILE_5: "5 (longest)",
            },
        ),
        "reflector_shape": pidgets.EnumPidgetFactory(
            name_label_text="Reflector shape:",
            enum_type=ReflectorShape,
            label_mapping={
                ReflectorShape.GENERIC: "Generic",
                ReflectorShape.PLANAR: "Planar",
            },
        ),
        "peaksorting_method": pidgets.EnumPidgetFactory(
            name_label_text="Peak sorting method:",
            enum_type=PeakSortingMethod,
            label_mapping={
                PeakSortingMethod.CLOSEST: "Closest",
                PeakSortingMethod.STRONGEST: "Strongest",
            },
        ),
        "threshold_method": pidgets.EnumPidgetFactory(
            name_label_text="Threshold method:",
            enum_type=ThresholdMethod,
            label_mapping={
                ThresholdMethod.CFAR: "CFAR",
                ThresholdMethod.FIXED: "Fixed amplitude",
                ThresholdMethod.FIXED_STRENGTH: "Fixed strength",
                ThresholdMethod.RECORDED: "Recorded",
            },
        ),
        "fixed_threshold_value": pidgets.FloatPidgetFactory(
            name_label_text="Fixed amplitude threshold value:",
            decimals=1,
            limits=(0, None),
            hooks=enable_if(parameter_is("threshold_method", ThresholdMethod.FIXED)),
        ),
        "fixed_strength_threshold_value": pidgets.FloatPidgetFactory(
            name_label_text="Fixed strength threshold value:",
            decimals=1,
            hooks=enable_if(parameter_is("threshold_method", ThresholdMethod.FIXED_STRENGTH)),
            suffix="dBsm",
        ),
        "num_frames_in_recorded_threshold": pidgets.IntPidgetFactory(
            name_label_text="Num frames in rec. thr.:",
            limits=(1, None),
        ),
        "threshold_sensitivity": pidgets.FloatSliderPidgetFactory(
            name_label_text="Threshold sensitivity:",
            decimals=2,
            limits=(0, 1),
            show_limit_values=False,
            hooks=disable_if(
                parameter_is("threshold_method", ThresholdMethod.FIXED),
                parameter_is("threshold_method", ThresholdMethod.FIXED_STRENGTH),
            ),
        ),
        "signal_quality": pidgets.FloatSliderPidgetFactory(
            name_label_text="Signal quality:",
            decimals=1,
            limits=(-10, 35),
            show_limit_values=False,
            limit_texts=("Less power", "Higher quality"),
        ),
        "update_rate": pidgets.OptionalFloatPidgetFactory(
            name_label_text="Update rate:",
            checkbox_label_text="Set",
            limits=(1, None),
            init_set_value=20,
        ),
    }
