# Copyright (c) Acconeer AB, 2023
# All rights reserved

from acconeer.exptool import a121

from ._processor import ProcessorConfig


def _get_base_config() -> a121.SensorConfig:
    return a121.SensorConfig(
        start_point=80,
        num_points=1,
        step_length=1,
        profile=a121.Profile.PROFILE_3,
        receiver_gain=10,
        hwaas=16,
        sweep_rate=2000,
        inter_frame_idle_state=a121.IdleState.READY,
        inter_sweep_idle_state=a121.IdleState.READY,
    )


def get_low_frequency_sensor_config() -> a121.SensorConfig:
    # Sensor config for running low frequency(low sweep rate) in continuous sweep mode
    sensor_config = _get_base_config()
    sensor_config.continuous_sweep_mode = True
    sensor_config.double_buffering = True
    sensor_config.sweeps_per_frame = 50

    return sensor_config


def get_low_frequency_processor_config() -> ProcessorConfig:
    # Processor config for running low frequency(low sweep rate) in continuous sweep mode

    return ProcessorConfig()


def get_high_frequency_sensor_config() -> a121.SensorConfig:
    # Sensor config for running frame mode
    sensor_config = _get_base_config()
    sensor_config.continuous_sweep_mode = False
    sensor_config.double_buffering = False
    sensor_config.sweeps_per_frame = 2048
    sensor_config.sweep_rate = 10000

    return sensor_config


def get_high_frequency_processor_config() -> ProcessorConfig:
    # Processor config for running frame mode

    return ProcessorConfig(lp_coeff=0.5)
