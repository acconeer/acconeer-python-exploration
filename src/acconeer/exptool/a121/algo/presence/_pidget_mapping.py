# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

from acconeer.exptool import a121
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.app.new.ui.components import PidgetGroupFactoryMapping, pidgets
from acconeer.exptool.app.new.ui.components.pidgets.hooks import (
    disable_if,
    parameter_is,
)

from ._detector import DetectorConfig


def get_pidget_mapping() -> PidgetGroupFactoryMapping:
    service_parameters = {
        "start_m": pidgets.FloatPidgetFactory(
            name_label_text="Range start:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "start_m"),
            suffix=" m",
            decimals=3,
        ),
        "end_m": pidgets.FloatPidgetFactory(
            name_label_text="Range end:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "end_m"),
            suffix=" m",
            decimals=3,
        ),
        "frame_rate": pidgets.FloatPidgetFactory(
            name_label_text="Frame rate:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "frame_rate"),
            suffix=" Hz",
            decimals=1,
            limits=(0.1, 100),
        ),
        "sweeps_per_frame": pidgets.IntPidgetFactory(
            name_label_text="Sweeps per frame:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "sweeps_per_frame"),
            limits=(1, 4095),
        ),
        "inter_frame_idle_state": pidgets.EnumPidgetFactory(
            enum_type=a121.IdleState,
            name_label_text="Inter frame idle state:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "inter_frame_idle_state"),
            label_mapping={
                a121.IdleState.DEEP_SLEEP: "Deep sleep",
                a121.IdleState.SLEEP: "Sleep",
                a121.IdleState.READY: "Ready",
            },
        ),
    }
    signal_parameters = {
        "signal_quality": pidgets.FloatSliderPidgetFactory(
            name_label_text="Signal quality:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "signal_quality"),
            decimals=1,
            limits=(-10.0, 60.0),
        ),
    }
    subsweep_settings = {
        "hwaas": pidgets.IntPidgetFactory(
            name_label_text="HWAAS:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "hwaas"),
            limits=(1, 511),
        ),
        "profile": pidgets.OptionalEnumPidgetFactory(
            name_label_text="Profile:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "profile"),
            checkbox_label_text="Override",
            enum_type=a121.Profile,
            label_mapping={
                a121.Profile.PROFILE_1: "1 (shortest)",
                a121.Profile.PROFILE_2: "2",
                a121.Profile.PROFILE_3: "3",
                a121.Profile.PROFILE_4: "4",
                a121.Profile.PROFILE_5: "5 (longest)",
            },
        ),
        "step_length": pidgets.OptionalIntPidgetFactory(
            name_label_text="Step length:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "step_length"),
            checkbox_label_text="Override",
            limits=(1, None),
            init_set_value=24,
        ),
    }
    intra_parameters = {
        "intra_detection_threshold": pidgets.FloatSliderPidgetFactory(
            name_label_text="Intra detection threshold:",
            name_label_tooltip=get_attribute_docstring(
                DetectorConfig, "intra_detection_threshold"
            ),
            decimals=2,
            limits=(0, 100),
        ),
        "intra_frame_time_const": pidgets.FloatSliderPidgetFactory(
            name_label_text="Intra time constant:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "intra_frame_time_const"),
            suffix=" s",
            decimals=2,
            limits=(0, 1),
        ),
        "intra_output_time_const": pidgets.FloatSliderPidgetFactory(
            name_label_text="Intra output time constant:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "intra_output_time_const"),
            suffix=" s",
            decimals=2,
            limits=(0.01, 20),
            log_scale=True,
        ),
    }
    inter_parameters = {
        "inter_detection_threshold": pidgets.FloatSliderPidgetFactory(
            name_label_text="Inter detection threshold:",
            name_label_tooltip=get_attribute_docstring(
                DetectorConfig, "inter_detection_threshold"
            ),
            decimals=2,
            limits=(0, 100),
        ),
        "inter_frame_fast_cutoff": pidgets.FloatSliderPidgetFactory(
            name_label_text="Inter fast cutoff freq.:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "inter_frame_fast_cutoff"),
            suffix=" Hz",
            decimals=2,
            limits=(1, 50),
            log_scale=True,
        ),
        "inter_frame_slow_cutoff": pidgets.FloatSliderPidgetFactory(
            name_label_text="Inter slow cutoff freq.:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "inter_frame_slow_cutoff"),
            suffix=" Hz",
            decimals=2,
            limits=(0.01, 1),
            log_scale=True,
        ),
        "inter_frame_deviation_time_const": pidgets.FloatSliderPidgetFactory(
            name_label_text="Inter time constant:",
            name_label_tooltip=get_attribute_docstring(
                DetectorConfig, "inter_frame_deviation_time_const"
            ),
            suffix=" s",
            decimals=2,
            limits=(0.01, 20),
            log_scale=True,
        ),
        "inter_output_time_const": pidgets.FloatSliderPidgetFactory(
            name_label_text="Inter output time constant:",
            name_label_tooltip=get_attribute_docstring(DetectorConfig, "inter_output_time_const"),
            suffix=" s",
            decimals=2,
            limits=(0.01, 20),
            log_scale=True,
        ),
        "inter_frame_presence_timeout": pidgets.OptionalIntPidgetFactory(
            name_label_text="Presence timeout:",
            name_label_tooltip=get_attribute_docstring(
                DetectorConfig, "inter_frame_presence_timeout"
            ),
            checkbox_label_text="Enable",
            suffix=" s",
            limits=(1, 30),
            init_set_value=5,
        ),
    }
    return {
        pidgets.FlatPidgetGroup(): service_parameters,
        pidgets.FlatPidgetGroup(): {
            "automatic_subsweeps": pidgets.CheckboxPidgetFactory(
                name_label_text="Enable automatic subsweep config (recommended)",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "automatic_subsweeps"),
            ),
        },
        pidgets.FlatPidgetGroup(
            hooks=disable_if(parameter_is("automatic_subsweeps", False)),
        ): signal_parameters,
        pidgets.FlatPidgetGroup(
            hooks=disable_if(parameter_is("automatic_subsweeps", True)),
        ): subsweep_settings,
        pidgets.FlatPidgetGroup(): {
            "intra_enable": pidgets.CheckboxPidgetFactory(
                name_label_text="Enable intra (fast) motion detection",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "intra_enable"),
            ),
        },
        pidgets.FlatPidgetGroup(
            hooks=disable_if(parameter_is("intra_enable", False)),
        ): intra_parameters,
        pidgets.FlatPidgetGroup(): {
            "inter_enable": pidgets.CheckboxPidgetFactory(
                name_label_text="Enable inter (slow) motion detection",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "inter_enable"),
            ),
        },
        pidgets.FlatPidgetGroup(
            hooks=disable_if(parameter_is("inter_enable", False)),
        ): inter_parameters,
    }
