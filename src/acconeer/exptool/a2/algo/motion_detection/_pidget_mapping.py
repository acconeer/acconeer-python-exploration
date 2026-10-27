# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.a2.algo._detection_geometry import (
    DEFAULT_AZ_ANGLE_RANGE,
    DEFAULT_EL_ANGLE_RANGE,
)
from acconeer.exptool.a2.algo._utils import CONVENTIONAL_AZ_FWHM_DEG
from acconeer.exptool.a2.algo.nodes._cfar_subnodes import CFARKernelType
from acconeer.exptool.a2.algo.nodes._peak_interpolation_nodes import InterpolationMethod2D
from acconeer.exptool.app.new.ui import pidgets
from acconeer.exptool.app.new.ui.components.pidgets.hooks import (
    disable_if,
    parameter_is,
)
from acconeer.exptool.app.new.ui.components.types import PidgetGroupFactoryMapping

from .config import BeamformingMethod, HeatmapDisplayMode, MotionDetectionConfig, PlotSettings


def get_motion_detection_config_pidget_mapping() -> PidgetGroupFactoryMapping:
    simple = {
        "high_pass_filter_time_constant_s": pidgets.FloatSliderPidgetFactory(
            name_label_text="High-pass filter time constant:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "high_pass_filter_time_constant_s"
            ),
            limits=(0.0, 10.0),
            decimals=2,
            suffix=" s",
        ),
        "covariance_matrix_time_constant_s": pidgets.FloatSliderPidgetFactory(
            name_label_text="Covar. matrix time constant:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "covariance_matrix_time_constant_s"
            ),
            limits=(0.0, 10.0),
            decimals=2,
            suffix=" s",
        ),
        "cfar_sensitivity": pidgets.FloatSliderPidgetFactory(
            name_label_text="CFAR sensitivity:",
            name_label_tooltip=get_attribute_docstring(MotionDetectionConfig, "cfar_sensitivity"),
            limits=(0.0, 1.0),
            decimals=2,
            show_limit_values=False,
            limit_texts=("Fewer detections", "More detections"),
        ),
    }

    advanced = {
        "beamforming_method": pidgets.EnumPidgetFactory(
            name_label_text="Beamforming method:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "beamforming_method"
            ),
            enum_type=BeamformingMethod,
            label_mapping={
                BeamformingMethod.CAPON: "Capon",
                BeamformingMethod.ROBUST_CAPON: "Robust Capon",
            },
        ),
        "robust_capon_epsilon": pidgets.FloatSliderPidgetFactory(
            name_label_text="Robust Capon epsilon:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "robust_capon_epsilon"
            ),
            limits=(1e-3, 1.0),
            decimals=3,
            log_scale=True,
        ),
        "vibration_std_um": pidgets.FloatSliderPidgetFactory(
            name_label_text="Vibration std dev:",
            name_label_tooltip=get_attribute_docstring(MotionDetectionConfig, "vibration_std_um"),
            limits=(0.0, 100.0),
            decimals=1,
            suffix=" µm",
        ),
        "cfar_kernel_type": pidgets.EnumPidgetFactory(
            name_label_text="CFAR kernel type:",
            name_label_tooltip=get_attribute_docstring(MotionDetectionConfig, "cfar_kernel_type"),
            enum_type=CFARKernelType,
            label_mapping={
                CFARKernelType.THIN_CROSS: "Thin cross",
                CFARKernelType.THICK_CROSS: "Thick cross",
            },
        ),
        "cfar_az_guard_fwhm_factor": pidgets.FloatSliderPidgetFactory(
            name_label_text="CFAR az guard FWHM factor:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "cfar_az_guard_fwhm_factor"
            ),
            limits=(0.0, 2.0),
            decimals=2,
        ),
        "cfar_dist_guard_envelope_len_factor": pidgets.FloatSliderPidgetFactory(
            name_label_text="CFAR dist guard factor:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "cfar_dist_guard_envelope_len_factor"
            ),
            limits=(0.0, 2.0),
            decimals=2,
        ),
        "cfar_az_reference_fwhm_factor": pidgets.FloatSliderPidgetFactory(
            name_label_text="CFAR az reference FWHM factor:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "cfar_az_reference_fwhm_factor"
            ),
            limits=(0.0, 2.0),
            decimals=2,
        ),
        "cfar_dist_reference_envelope_len_factor": pidgets.FloatSliderPidgetFactory(
            name_label_text="CFAR dist reference factor:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "cfar_dist_reference_envelope_len_factor"
            ),
            limits=(0.0, 2.0),
            decimals=2,
        ),
        "cfar_fixed_threshold": pidgets.FloatSliderPidgetFactory(
            name_label_text="CFAR fixed threshold:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "cfar_fixed_threshold"
            ),
            limits=(0.0, 100.0),
            decimals=2,
        ),
        "cfar_side_lobe_compensation_db": pidgets.OptionalFloatPidgetFactory(
            name_label_text="CFAR side lobe comp.:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "cfar_side_lobe_compensation_db"
            ),
            placeholder_text="disabled",
            limits=(-30.0, 0.0),
            decimals=1,
            suffix=" dB",
        ),
        "peak_min_dist_separation_m": pidgets.FloatSliderPidgetFactory(
            name_label_text="Peak min separation:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "peak_min_dist_separation_m"
            ),
            limits=(0.0, 2.0),
            decimals=2,
            suffix=" m",
        ),
        "peak_interpolation_az_dist_method": pidgets.EnumPidgetFactory(
            name_label_text="Peak interpolation method:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "peak_interpolation_az_dist_method"
            ),
            enum_type=InterpolationMethod2D,
            label_mapping={
                InterpolationMethod2D.NONE: "None",
                InterpolationMethod2D.GAUSSIAN_INDEPENDENT: "Gaussian (independent)",
                InterpolationMethod2D.GAUSSIAN_2D: "Gaussian (2D)",
            },
        ),
        "peak_finding_dist_radius_fwhm_factor": pidgets.FloatSliderPidgetFactory(
            name_label_text="Peak finding dist radius factor:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "peak_finding_dist_radius_fwhm_factor"
            ),
            limits=(0.0, 1.0),
            decimals=2,
        ),
        "peak_finding_az_radius_fwhm_factor": pidgets.FloatSliderPidgetFactory(
            name_label_text="Peak finding az radius factor:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "peak_finding_az_radius_fwhm_factor"
            ),
            limits=(0.0, 1.0),
            decimals=2,
        ),
        "spatial_high_pass_filter_time_constant_s": pidgets.FloatSliderPidgetFactory(
            name_label_text="Spatial HP filter time constant:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "spatial_high_pass_filter_time_constant_s"
            ),
            limits=(0.01, 30.0),
            decimals=2,
            suffix=" s",
            log_scale=True,
        ),
        "az_grid_resolution_deg": pidgets.FloatSliderPidgetFactory(
            name_label_text="Az grid resolution:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "az_grid_resolution_deg"
            ),
            limits=(0.5, CONVENTIONAL_AZ_FWHM_DEG),
            decimals=1,
            suffix="°",
        ),
        "el_grid_resolution_deg": pidgets.OptionalFloatPidgetFactory(
            name_label_text="El grid resolution:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "el_grid_resolution_deg"
            ),
            placeholder_text="single boresight",
            limits=(0.5, 30.0),
            decimals=1,
            suffix="°",
        ),
        "az_angle_range": pidgets.OptionalFloatRangeSliderPidgetFactory(
            name_label_text="Az angle range override:",
            name_label_tooltip=get_attribute_docstring(MotionDetectionConfig, "az_angle_range"),
            checkbox_label_text="Override",
            init_set_value=DEFAULT_AZ_ANGLE_RANGE,
            limits=(-80.0, 80.0),
            decimals=1,
            suffix="°",
        ),
        "el_angle_range": pidgets.OptionalFloatRangeSliderPidgetFactory(
            name_label_text="El angle range override:",
            name_label_tooltip=get_attribute_docstring(MotionDetectionConfig, "el_angle_range"),
            checkbox_label_text="Override",
            init_set_value=DEFAULT_EL_ANGLE_RANGE,
            limits=(-60.0, 60.0),
            decimals=1,
            suffix="°",
            hooks=disable_if(parameter_is("el_grid_resolution_deg", None)),
        ),
        "detection_volume_x_bound_offset_m": pidgets.OptionalFloatRangeSliderPidgetFactory(
            name_label_text="X bound offset:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "detection_volume_x_bound_offset_m"
            ),
            checkbox_label_text="Box bound",
            limits=(-10.0, 10.0),
            decimals=2,
            suffix=" m",
        ),
        "detection_volume_y_bound_offset_m": pidgets.OptionalFloatRangeSliderPidgetFactory(
            name_label_text="Y bound offset:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "detection_volume_y_bound_offset_m"
            ),
            checkbox_label_text="Box bound",
            limits=(-10.0, 10.0),
            decimals=2,
            suffix=" m",
        ),
        "detection_volume_z_bound_offset_m": pidgets.OptionalFloatRangeSliderPidgetFactory(
            name_label_text="Z bound offset:",
            name_label_tooltip=get_attribute_docstring(
                MotionDetectionConfig, "detection_volume_z_bound_offset_m"
            ),
            checkbox_label_text="Box bound",
            limits=(-5.0, 5.0),
            decimals=2,
            suffix=" m",
        ),
    }

    return {
        pidgets.FlatPidgetGroup(): simple,
        pidgets.CollapsiblePidgetGroup(label="Advanced", collapsed=True): advanced,
    }


def get_plot_settings_pidget_mapping() -> PidgetGroupFactoryMapping:
    return {
        pidgets.FlatPidgetGroup(): {
            "history_duration_s": pidgets.FloatSliderPidgetFactory(
                name_label_text="History duration:",
                name_label_tooltip=get_attribute_docstring(PlotSettings, "history_duration_s"),
                limits=(0.5, 10.0),
                decimals=1,
                suffix=" s",
            ),
            "heatmap_display_mode": pidgets.EnumPidgetFactory(
                name_label_text="Heatmap display mode:",
                name_label_tooltip=get_attribute_docstring(PlotSettings, "heatmap_display_mode"),
                enum_type=HeatmapDisplayMode,
                label_mapping={
                    HeatmapDisplayMode.HEATMAP_MASKED: "Masked",
                    HeatmapDisplayMode.HEATMAP_ON: "On",
                    HeatmapDisplayMode.HEATMAP_OFF: "Off",
                },
                tooltip_mapping={
                    HeatmapDisplayMode.HEATMAP_MASKED: (
                        "Heatmap with threshold masking: cells below the CFAR threshold "
                        "are shown in grey."
                    ),
                    HeatmapDisplayMode.HEATMAP_ON: (
                        "Full heatmap: all cells are shown without threshold masking, "
                        "in addition to the detection points."
                    ),
                    HeatmapDisplayMode.HEATMAP_OFF: (
                        "Detection points only: the heatmap is hidden."
                    ),
                },
            ),
        }
    }
