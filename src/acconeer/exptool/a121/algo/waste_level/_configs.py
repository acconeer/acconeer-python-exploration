# Copyright (c) Acconeer AB, 2024
# All rights reserved

from acconeer.exptool import a121

from ._processor import ProcessorConfig


def get_sensor_config() -> a121.SensorConfig:
    return a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(
                start_point=40,
                step_length=8,
                num_points=14,
                profile=a121.Profile.PROFILE_1,
                hwaas=4,
            ),
            a121.SubsweepConfig(
                start_point=150,
                step_length=12,
                num_points=23,
                profile=a121.Profile.PROFILE_3,
                hwaas=8,
            ),
        ],
        sweeps_per_frame=32,
        frame_rate=5,
    )


def get_processor_config() -> ProcessorConfig:
    return ProcessorConfig()
