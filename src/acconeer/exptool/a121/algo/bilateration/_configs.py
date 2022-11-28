# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import DetectorConfig


def get_default_detector_config() -> DetectorConfig:
    return DetectorConfig(
        end_m=1.0,
        max_profile=a121.Profile.PROFILE_1,
        threshold_sensitivity=0.7,
        signal_quality=25.0,
        update_rate=20.0,
    )
