# Copyright (c) Acconeer AB, 2023
# All rights reserved

from acconeer.exptool.a121.algo.breathing._ref_app import RefAppConfig
from acconeer.exptool.a121.algo.presence import ProcessorConfig


def get_sitting_config() -> RefAppConfig:
    presence_config = ProcessorConfig()
    presence_config.intra_detection_threshold = 6.0

    ref_app_config = RefAppConfig()
    ref_app_config.end_m = 1.5
    ref_app_config.presence_config = presence_config

    return ref_app_config


def get_infant_config() -> RefAppConfig:
    presence_config = ProcessorConfig()
    presence_config.intra_detection_threshold = 4.0

    ref_app_config = RefAppConfig()
    ref_app_config.end_m = 1.0
    ref_app_config.presence_config = presence_config

    return ref_app_config
