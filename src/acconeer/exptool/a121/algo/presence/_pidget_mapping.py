# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

from acconeer.exptool import a121
from acconeer.exptool.app.new.ui.plugin_components import PidgetGroupFactoryMapping, pidgets
from acconeer.exptool.app.new.ui.plugin_components.pidgets.hooks import (
    disable_if,
    parameter_is,
)


def get_pidget_mapping() -> PidgetGroupFactoryMapping:
    service_parameters = {
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
        "profile": pidgets.OptionalEnumPidgetFactory(
            name_label_text="Profile:",
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
            checkbox_label_text="Override",
            limits=(1, None),
            init_set_value=24,
        ),
        "frame_rate": pidgets.FloatPidgetFactory(
            name_label_text="Frame rate:",
            suffix=" Hz",
            decimals=1,
            limits=(1, 100),
        ),
        "sweeps_per_frame": pidgets.IntPidgetFactory(
            name_label_text="Sweeps per frame:",
            limits=(1, 4095),
        ),
        "hwaas": pidgets.IntPidgetFactory(
            name_label_text="HWAAS:",
            limits=(1, 511),
        ),
        "inter_frame_idle_state": pidgets.EnumPidgetFactory(
            enum_type=a121.IdleState,
            name_label_text="Inter frame idle state:",
            label_mapping={
                a121.IdleState.DEEP_SLEEP: "Deep sleep",
                a121.IdleState.SLEEP: "Sleep",
                a121.IdleState.READY: "Ready",
            },
        ),
    }
    intra_parameters = {
        "intra_detection_threshold": pidgets.FloatSliderPidgetFactory(
            name_label_text="Intra detection threshold:",
            decimals=2,
            limits=(0, 5),
        ),
        "intra_frame_time_const": pidgets.FloatSliderPidgetFactory(
            name_label_text="Intra time constant:",
            suffix=" s",
            decimals=2,
            limits=(0, 1),
        ),
        "intra_output_time_const": pidgets.FloatSliderPidgetFactory(
            name_label_text="Intra output time constant:",
            suffix=" s",
            decimals=2,
            limits=(0.01, 20),
            log_scale=True,
        ),
    }
    inter_parameters = {
        "inter_phase_boost": pidgets.CheckboxPidgetFactory(name_label_text="Enable phase boost"),
        "inter_detection_threshold": pidgets.FloatSliderPidgetFactory(
            name_label_text="Inter detection threshold:",
            decimals=2,
            limits=(0, 5),
        ),
        "inter_frame_fast_cutoff": pidgets.FloatSliderPidgetFactory(
            name_label_text="Inter fast cutoff freq.:",
            suffix=" Hz",
            decimals=2,
            limits=(1, 50),
            log_scale=True,
        ),
        "inter_frame_slow_cutoff": pidgets.FloatSliderPidgetFactory(
            name_label_text="Inter slow cutoff freq.:",
            suffix=" Hz",
            decimals=2,
            limits=(0.01, 1),
            log_scale=True,
        ),
        "inter_frame_deviation_time_const": pidgets.FloatSliderPidgetFactory(
            name_label_text="Inter time constant:",
            suffix=" s",
            decimals=2,
            limits=(0.01, 20),
            log_scale=True,
        ),
        "inter_output_time_const": pidgets.FloatSliderPidgetFactory(
            name_label_text="Inter output time constant:",
            suffix=" s",
            decimals=2,
            limits=(0.01, 20),
            log_scale=True,
        ),
        "inter_frame_presence_timeout": pidgets.OptionalIntPidgetFactory(
            name_label_text="Presence timeout:",
            checkbox_label_text="Enable",
            suffix=" s",
            limits=(1, 30),
            init_set_value=5,
        ),
    }
    return {
        pidgets.FlatPidgetGroup(): service_parameters,
        pidgets.FlatPidgetGroup(): {
            "intra_enable": pidgets.CheckboxPidgetFactory(
                name_label_text="Enable intra (fast) motion detection"
            ),
        },
        pidgets.FlatPidgetGroup(
            hooks=disable_if(parameter_is("intra_enable", False)),
        ): intra_parameters,
        pidgets.FlatPidgetGroup(): {
            "inter_enable": pidgets.CheckboxPidgetFactory(
                name_label_text="Enable inter (slow) motion detection"
            ),
        },
        pidgets.FlatPidgetGroup(
            hooks=disable_if(parameter_is("inter_enable", False)),
        ): inter_parameters,
    }
