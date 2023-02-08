# Copyright (c) Acconeer AB, 2023
# All rights reserved

from acconeer.exptool import a121

from ._ref_app import RefAppConfig


def get_short_range_config() -> RefAppConfig:
    return RefAppConfig(
        start_m=0.06,
        end_m=1.0,
        frame_rate=10,
        sweeps_per_frame=16,
        hwaas=16,
        inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
        intra_enable=True,
        intra_detection_threshold=1.4,
        intra_frame_time_const=0.15,
        intra_output_time_const=0.3,
        inter_enable=True,
        inter_detection_threshold=1,
        inter_frame_slow_cutoff=0.2,
        inter_frame_fast_cutoff=5,
        inter_frame_deviation_time_const=0.5,
        inter_output_time_const=2,
        inter_phase_boost=False,
        inter_frame_presence_timeout=3,
        num_zones=5,
    )


def get_medium_range_config() -> RefAppConfig:
    return RefAppConfig(
        start_m=0.3,
        end_m=2.5,
        frame_rate=12,
        sweeps_per_frame=16,
        hwaas=32,
        inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
        intra_enable=True,
        intra_detection_threshold=1.3,
        intra_frame_time_const=0.15,
        intra_output_time_const=0.3,
        inter_enable=True,
        inter_detection_threshold=1,
        inter_frame_slow_cutoff=0.2,
        inter_frame_fast_cutoff=6,
        inter_frame_deviation_time_const=0.5,
        inter_output_time_const=2,
        inter_phase_boost=False,
        inter_frame_presence_timeout=3,
        num_zones=7,
    )


def get_long_range_config() -> RefAppConfig:
    return RefAppConfig(
        start_m=5,
        end_m=7.5,
        frame_rate=12,
        sweeps_per_frame=32,
        hwaas=128,
        inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
        intra_enable=True,
        intra_detection_threshold=1.2,
        intra_frame_time_const=0.15,
        intra_output_time_const=0.3,
        inter_enable=True,
        inter_detection_threshold=0.8,
        inter_frame_slow_cutoff=0.2,
        inter_frame_fast_cutoff=6,
        inter_frame_deviation_time_const=0.5,
        inter_output_time_const=2,
        inter_phase_boost=False,
        inter_frame_presence_timeout=3,
        num_zones=5,
    )
