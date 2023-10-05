# Copyright (c) Acconeer AB, 2023
# All rights reserved

from acconeer.exptool.a121.algo.obstacle import DetectorConfig


def get_default_detector_config() -> DetectorConfig:
    return DetectorConfig(
        enable_bilateration=True,
    )
