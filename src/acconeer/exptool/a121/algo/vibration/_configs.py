# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from acconeer.exptool import a121

from ._example_app import ExampleAppConfig


def _get_base_config() -> ExampleAppConfig:
    return ExampleAppConfig(
        measured_point=80,
        profile=a121.Profile.PROFILE_3,
        hwaas=16,
        frame_rate=None,
        inter_frame_idle_state=a121.IdleState.READY,
        inter_sweep_idle_state=a121.IdleState.READY,
    )


def get_low_frequency_config() -> ExampleAppConfig:
    # Example app config for running low frequency(low sweep rate) in continuous sweep mode
    example_app_config = _get_base_config()
    example_app_config.continuous_sweep_mode = True
    example_app_config.double_buffering = True
    example_app_config.sweeps_per_frame = 20
    example_app_config.sweep_rate = 200
    example_app_config.low_frequency_enhancement = True
    example_app_config.lp_coeff = 0.8

    return example_app_config


def get_high_frequency_config() -> ExampleAppConfig:
    # Example app config for running frame mode
    example_app_config = _get_base_config()
    example_app_config.continuous_sweep_mode = False
    example_app_config.double_buffering = False
    example_app_config.sweeps_per_frame = 2048
    example_app_config.sweep_rate = 10000
    example_app_config.low_frequency_enhancement = False
    example_app_config.lp_coeff = 0.5

    return example_app_config
