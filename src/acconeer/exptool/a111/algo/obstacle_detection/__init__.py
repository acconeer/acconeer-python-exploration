import sys

from ..module_info import ModuleFamily, ModuleInfo
from .plotting import PGUpdater
from .processing import ObstacleDetectionProcessor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    "iq_obstacle",
    "Obstacle detection (IQ)",
    sys.modules[__name__],
    ModuleFamily.DETECTOR,
    get_sensor_config,
    ObstacleDetectionProcessor,
    [1, 2],
    "https://acconeer-python-exploration.readthedocs.io/en/latest/processing/obstacle.html",
)
