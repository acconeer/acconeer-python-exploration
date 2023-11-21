# Copyright (c) Acconeer AB, 2023
# All rights reserved


from ._detector import DetectorConfig


def get_default_config() -> DetectorConfig:
    return DetectorConfig()


def get_traffic_config() -> DetectorConfig:
    return DetectorConfig(
        start_point=2400,
        num_bins=200,
        max_speed=50.0,
        threshold=10.0,
    )
