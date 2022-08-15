# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo

from ._processor import ProcessingConfiguration, Processor, get_sensor_config
from .calibration import (
    ObstacleDetectionCalibration,
    ObstacleDetectionCalibrationConfiguration,
    ObstacleDetectionCalibrationMapper,
)
from .ui import PGUpdater


module_info = ModuleInfo(
    key="iq_obstacle",
    label="Obstacle detection (IQ)",
    pg_updater=PGUpdater,
    processing_config_class=ProcessingConfiguration,
    module_family=ModuleFamily.DETECTOR,
    sensor_config_class=get_sensor_config,
    processor=Processor,
    multi_sensor=[1, 2],
    docs_url="https://docs.acconeer.com/en/latest/processing/obstacle.html",
    calibration_class=ObstacleDetectionCalibration,
    calibration_config_class=ObstacleDetectionCalibrationConfiguration,
    calibration_mapper=ObstacleDetectionCalibrationMapper,
)
