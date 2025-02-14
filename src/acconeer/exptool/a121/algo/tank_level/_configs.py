# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import PeakSortingMethod, ReflectorShape, ThresholdMethod
from acconeer.exptool.a121.algo.tank_level._ref_app import RefAppConfig


def get_small_config() -> RefAppConfig:
    return RefAppConfig(
        median_filter_length=3,
        num_medians_to_average=2,
        start_m=0.030,
        end_m=0.5,
        max_step_length=12,
        max_profile=a121.Profile.PROFILE_3,
        num_frames_in_recorded_threshold=50,
        peaksorting_method=PeakSortingMethod.CLOSEST,
        reflector_shape=ReflectorShape.PLANAR,
        threshold_method=ThresholdMethod.CFAR,
        close_range_leakage_cancellation=False,
        fixed_threshold_value=100.0,
        fixed_strength_threshold_value=0.0,
        threshold_sensitivity=0.0,
        signal_quality=3.0,
        update_rate=None,
        level_tracking_active=False,
    )


def get_medium_config() -> RefAppConfig:
    return RefAppConfig(
        median_filter_length=3,
        num_medians_to_average=1,
        start_m=0.050,
        end_m=6.0,
        max_profile=a121.Profile.PROFILE_5,
        num_frames_in_recorded_threshold=50,
        peaksorting_method=PeakSortingMethod.STRONGEST,
        reflector_shape=ReflectorShape.PLANAR,
        threshold_method=ThresholdMethod.CFAR,
        close_range_leakage_cancellation=False,
        fixed_threshold_value=100.0,
        fixed_strength_threshold_value=3.0,
        threshold_sensitivity=0.0,
        signal_quality=19.0,
        update_rate=None,
        level_tracking_active=False,
    )


def get_large_config() -> RefAppConfig:
    return RefAppConfig(
        median_filter_length=1,
        num_medians_to_average=1,
        start_m=0.10,
        end_m=15,
        max_profile=a121.Profile.PROFILE_5,
        num_frames_in_recorded_threshold=50,
        peaksorting_method=PeakSortingMethod.STRONGEST,
        reflector_shape=ReflectorShape.PLANAR,
        threshold_method=ThresholdMethod.CFAR,
        close_range_leakage_cancellation=False,
        fixed_threshold_value=100.0,
        fixed_strength_threshold_value=5.0,
        threshold_sensitivity=0.0,
        signal_quality=20.0,
        update_rate=None,
        level_tracking_active=False,
    )
