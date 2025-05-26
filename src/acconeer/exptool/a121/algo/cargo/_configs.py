# Copyright (c) Acconeer AB, 2025
# All rights reserved


from ._ex_app import CargoPresenceConfig, ContainerSize, ExAppConfig, UtilizationLevelConfig


def get_10_ft_container_config() -> ExAppConfig:
    return ExAppConfig(
        container_size=ContainerSize.CONTAINER_10_FT,
        activate_utilization_level=True,
        activate_presence=False,
    )


def get_20_ft_container_config() -> ExAppConfig:
    return ExAppConfig(
        container_size=ContainerSize.CONTAINER_20_FT,
        activate_utilization_level=True,
        activate_presence=False,
    )


def get_40_ft_container_config() -> ExAppConfig:
    return ExAppConfig(
        container_size=ContainerSize.CONTAINER_40_FT,
        activate_utilization_level=True,
        utilization_level_config=UtilizationLevelConfig(update_rate=3),
        activate_presence=False,
    )


def get_no_lens_config() -> ExAppConfig:
    return ExAppConfig(
        container_size=ContainerSize.CONTAINER_20_FT,
        activate_utilization_level=True,
        utilization_level_config=get_no_lens_utilization_level_config(),
        activate_presence=False,
        cargo_presence_config=get_no_lens_cargo_presence_config(),
    )


def get_no_lens_utilization_level_config() -> UtilizationLevelConfig:
    return UtilizationLevelConfig(
        update_rate=5,
        signal_quality=25,
        threshold_sensitivity=0.5,
    )


def get_no_lens_cargo_presence_config() -> CargoPresenceConfig:
    return CargoPresenceConfig(
        burst_rate=0.1,
        signal_quality=30,
        inter_detection_threshold=2,
        intra_detection_threshold=2,
    )
