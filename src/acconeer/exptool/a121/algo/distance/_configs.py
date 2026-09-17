# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from acconeer.exptool import a121

from ._detector import DetectorConfig


def get_high_accuracy_detector_config() -> DetectorConfig:
    return DetectorConfig(
        max_step_length=2, signal_quality=31.6, max_profile=a121.Profile.PROFILE_3
    )
