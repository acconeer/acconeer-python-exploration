# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo

from ._processor import ProcessingConfiguration, Processor, get_sensor_config
from .calibration import (
    DistaceDetectorCalibrationConfiguration,
    DistaceDetectorCalibrationMapper,
    DistanceDetectorCalibration,
)
from .ui import PGUpdater


module_info = ModuleInfo(
    key="envelope_distance",
    label="Distance Detector (envelope)",
    pg_updater=PGUpdater,
    processing_config_class=ProcessingConfiguration,
    module_family=ModuleFamily.DETECTOR,
    sensor_config_class=get_sensor_config,
    processor=Processor,
    multi_sensor=False,
    docs_url="https://docs.acconeer.com/en/latest/processing/distance_detector.html",
    calibration_class=DistanceDetectorCalibration,
    calibration_config_class=DistaceDetectorCalibrationConfiguration,
    calibration_mapper=DistaceDetectorCalibrationMapper,
)
