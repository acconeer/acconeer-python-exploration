# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.parking._ref_app import RefAppConfig


def get_ground_config() -> RefAppConfig:
    ret = RefAppConfig(
        range_start_m=0.1,
        range_end_m=0.4,
        hwaas=24,
        profile=a121.Profile.PROFILE_1,
        update_rate=0.1,
        queue_length_n=3,
        amplitude_threshold=8.0,
        weighted_distance_threshold_m=0.1,
        obstruction_detection=True,
        obstruction_start_m=0.03,
        obstruction_end_m=0.05,
        obstruction_distance_threshold=0.06,
    )
    return ret


def get_pole_config() -> RefAppConfig:
    ret = RefAppConfig(
        range_start_m=0.2,
        range_end_m=3.0,
        hwaas=24,
        profile=a121.Profile.PROFILE_2,
        amplitude_threshold=6.0,
        weighted_distance_threshold_m=0.9,
        update_rate=6.0,
        queue_length_n=20,
        obstruction_detection=False,
    )
    return ret
