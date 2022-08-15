# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo

from ._processor import ProcessingConfiguration, Processor, get_sensor_config
from .calibration import (
    EnvelopeCalibration,
    EnvelopeCalibrationConfiguration,
    EnvelopeCalibrationMapper,
)
from .ui import PGUpdater


module_info = ModuleInfo(
    key="envelope",
    label="Envelope",
    pg_updater=PGUpdater,
    processing_config_class=ProcessingConfiguration,
    module_family=ModuleFamily.SERVICE,
    sensor_config_class=get_sensor_config,
    processor=Processor,
    multi_sensor=True,
    docs_url="https://docs.acconeer.com/en/latest/services/envelope.html",
    calibration_class=EnvelopeCalibration,
    calibration_config_class=EnvelopeCalibrationConfiguration,
    calibration_mapper=EnvelopeCalibrationMapper,
)
