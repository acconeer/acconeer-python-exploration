# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from acconeer.exptool import a2
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.a2.algo._detection_geometry import (
    DEFAULT_ROOM_HEIGHT_M,
    DetectionVolume,
    SensorInstallation,
)
from acconeer.exptool.a2.algo._shared_config import MAX_RANGE_M, WallMountSessionAbstractionConfig
from acconeer.exptool.app.new.ui import pidgets
from acconeer.exptool.app.new.ui.components.types import PidgetGroupFactoryMapping


def get_sensor_installation_pidget_mapping() -> PidgetGroupFactoryMapping:
    return {
        pidgets.FlatPidgetGroup(): {
            "x_rotation": pidgets.FloatPidgetFactory(
                name_label_text="X rotation (tilt):",
                name_label_tooltip=get_attribute_docstring(SensorInstallation, "x_rotation"),
                limits=(-45.0, 45.0),
                decimals=1,
                suffix="°",
            ),
            "y_rotation": pidgets.FloatPidgetFactory(
                name_label_text="Y rotation (roll):",
                name_label_tooltip=get_attribute_docstring(SensorInstallation, "y_rotation"),
                limits=(-180.0, 180.0),
                decimals=1,
                suffix="°",
            ),
            "z_rotation": pidgets.FloatPidgetFactory(
                name_label_text="Z rotation (pan):",
                name_label_tooltip=get_attribute_docstring(SensorInstallation, "z_rotation"),
                limits=(-90.0, 90.0),
                decimals=1,
                suffix="°",
            ),
            "mount_height_m": pidgets.FloatPidgetFactory(
                name_label_text="Mount height:",
                name_label_tooltip=get_attribute_docstring(SensorInstallation, "mount_height_m"),
                limits=(0.0, MAX_RANGE_M),
                decimals=2,
                suffix=" m",
            ),
        }
    }


def get_detection_volume_pidget_mapping() -> PidgetGroupFactoryMapping:
    box = {
        "x_bounds_m": pidgets.OptionalFloatRangeSliderPidgetFactory(
            name_label_text="X bounds:",
            name_label_tooltip=get_attribute_docstring(DetectionVolume, "x_bounds_m"),
            checkbox_label_text="Bound",
            limits=(-MAX_RANGE_M, MAX_RANGE_M),
            init_set_value=(-4.0, 4.0),
            decimals=2,
            suffix=" m",
        ),
        "y_bounds_m": pidgets.OptionalFloatRangeSliderPidgetFactory(
            name_label_text="Y bounds:",
            name_label_tooltip=get_attribute_docstring(DetectionVolume, "y_bounds_m"),
            checkbox_label_text="Bound",
            limits=(-MAX_RANGE_M, MAX_RANGE_M),
            init_set_value=(0.0, 6.0),
            decimals=2,
            suffix=" m",
        ),
    }
    range_and_angles = {
        "start_m": pidgets.OptionalFloatPidgetFactory(
            name_label_text="Start:",
            name_label_tooltip=get_attribute_docstring(DetectionVolume, "start_m"),
            checkbox_label_text="Limit",
            placeholder_text="none",
            limits=(0.0, MAX_RANGE_M),
            init_set_value=0.5,
            decimals=2,
            suffix=" m",
        ),
        "end_m": pidgets.OptionalFloatPidgetFactory(
            name_label_text="End:",
            name_label_tooltip=get_attribute_docstring(DetectionVolume, "end_m"),
            checkbox_label_text="Limit",
            placeholder_text="none",
            limits=(0.0, MAX_RANGE_M),
            init_set_value=5.0,
            decimals=2,
            suffix=" m",
        ),
        "az_angle_range": pidgets.FloatRangeSliderPidgetFactory(
            name_label_text="Az angle range:",
            name_label_tooltip=get_attribute_docstring(DetectionVolume, "az_angle_range"),
            limits=(-80.0, 80.0),
            decimals=1,
            suffix="°",
        ),
        "el_angle_range": pidgets.FloatRangeSliderPidgetFactory(
            name_label_text="El angle range:",
            name_label_tooltip=get_attribute_docstring(DetectionVolume, "el_angle_range"),
            limits=(-60.0, 60.0),
            decimals=1,
            suffix="°",
        ),
    }
    return {
        pidgets.CollapsiblePidgetGroup(label="Box (world frame)", collapsed=False): box,
        pidgets.CollapsiblePidgetGroup(
            label="Range and angles (sensor frame)", collapsed=False
        ): range_and_angles,
    }


def get_session_abstraction_pidget_mapping(
    *, min_sweeps_per_frame: int = 1
) -> PidgetGroupFactoryMapping:
    simple = {
        "signal_quality_db": pidgets.FloatSliderPidgetFactory(
            name_label_text="Signal quality (dB):",
            name_label_tooltip=get_attribute_docstring(
                WallMountSessionAbstractionConfig, "signal_quality_db"
            ),
            limits=(0.0, 50.0),
            decimals=1,
            suffix=" dB",
        ),
        "snr_evaluation_height_m": pidgets.FloatSliderPidgetFactory(
            name_label_text="SNR evaluation height:",
            name_label_tooltip=get_attribute_docstring(
                WallMountSessionAbstractionConfig, "snr_evaluation_height_m"
            ),
            limits=(0.0, DEFAULT_ROOM_HEIGHT_M),
            decimals=2,
            suffix=" m",
        ),
    }
    advanced = {
        "frame_rate": pidgets.FloatSliderPidgetFactory(
            name_label_text="Frame rate:",
            name_label_tooltip=get_attribute_docstring(
                WallMountSessionAbstractionConfig, "frame_rate"
            ),
            limits=(0.5, 100.0),
            decimals=1,
            suffix=" Hz",
        ),
        "max_num_subsweeps": pidgets.IntPidgetFactory(
            name_label_text="Max num subsweeps:",
            name_label_tooltip=get_attribute_docstring(
                WallMountSessionAbstractionConfig, "max_num_subsweeps"
            ),
            limits=(1, a2.SensorConfig.MAX_NUM_SUBSWEEPS - 1),
        ),
        "profile": pidgets.EnumPidgetFactory(
            name_label_text="Profile:",
            name_label_tooltip=get_attribute_docstring(
                WallMountSessionAbstractionConfig, "profile"
            ),
            enum_type=a2.Profile,
            label_mapping={
                a2.Profile.PROFILE_1: "Profile 1",
                a2.Profile.PROFILE_2: "Profile 2",
                a2.Profile.PROFILE_3: "Profile 3",
                a2.Profile.PROFILE_4: "Profile 4",
                a2.Profile.PROFILE_5: "Profile 5",
                a2.Profile.PROFILE_6: "Profile 6",
                a2.Profile.PROFILE_7: "Profile 7",
            },
        ),
        "max_snr_drop_db": pidgets.FloatSliderPidgetFactory(
            name_label_text="Max SNR drop:",
            name_label_tooltip=get_attribute_docstring(
                WallMountSessionAbstractionConfig, "max_snr_drop_db"
            ),
            limits=(0.0, 3.0),
            decimals=1,
            suffix=" dB",
        ),
        "sweeps_per_frame": pidgets.IntPidgetFactory(
            name_label_text="Num sweeps per frame:",
            name_label_tooltip=get_attribute_docstring(
                WallMountSessionAbstractionConfig, "sweeps_per_frame"
            ),
            limits=(min_sweeps_per_frame, 64),
        ),
        "sweep_rate": pidgets.OptionalFloatPidgetFactory(
            name_label_text="Sweep rate:",
            name_label_tooltip=get_attribute_docstring(
                WallMountSessionAbstractionConfig, "sweep_rate"
            ),
            placeholder_text="auto",
            limits=(1.0, 1e6),
            decimals=0,
            suffix=" Hz",
        ),
        "receiver_gain": pidgets.IntPidgetFactory(
            name_label_text="Receiver gain:",
            name_label_tooltip=get_attribute_docstring(
                WallMountSessionAbstractionConfig, "receiver_gain"
            ),
            limits=(0, 14),
        ),
    }

    return {
        pidgets.FlatPidgetGroup(): simple,
        pidgets.CollapsiblePidgetGroup(label="Advanced", collapsed=True): advanced,
    }
