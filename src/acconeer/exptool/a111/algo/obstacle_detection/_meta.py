from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo

from .calibration import (
    ObstacleDetectionCalibration,
    ObstacleDetectionCalibrationConfiguration,
    ObstacleDetectionCalibrationMapper,
)
from .plotting import PGUpdater
from .processing import Processor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    key="iq_obstacle",
    label="Obstacle detection (IQ)",
    pg_updater=PGUpdater,
    processing_config_class=get_processing_config,
    module_family=ModuleFamily.DETECTOR,
    sensor_config_class=get_sensor_config,
    processor=Processor,
    multi_sensor=[1, 2],
    docs_url=(
        "https://acconeer-python-exploration.readthedocs.io/en/latest/processing/obstacle.html"
    ),
    calibration_class=ObstacleDetectionCalibration,
    calibration_config_class=ObstacleDetectionCalibrationConfiguration,
    calibration_mapper=ObstacleDetectionCalibrationMapper,
)
