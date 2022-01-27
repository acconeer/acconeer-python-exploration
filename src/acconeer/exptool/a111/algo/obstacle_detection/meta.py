from ..module_info import ModuleFamily, ModuleInfo
from .plotting import PGUpdater
from .processing import ObstacleDetectionProcessor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    key="iq_obstacle",
    label="Obstacle detection (IQ)",
    pg_updater=PGUpdater,
    processing_config_class=get_processing_config,
    module_family=ModuleFamily.DETECTOR,
    sensor_config_class=get_sensor_config,
    processor=ObstacleDetectionProcessor,
    multi_sensor=[1, 2],
    docs_url=(
        "https://acconeer-python-exploration.readthedocs.io/en/latest/processing/obstacle.html"
    ),
)
