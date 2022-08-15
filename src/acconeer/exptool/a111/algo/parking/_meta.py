# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo
from acconeer.exptool.a111.algo.utils import multi_sensor_pg_updater, multi_sensor_processor

from ._processor import ProcessingConfiguration, Processor, get_sensor_config
from .ui import PGUpdater


module_info = ModuleInfo(
    key="envelope_parking",
    label="Parking (envelope)",
    pg_updater=multi_sensor_pg_updater(PGUpdater),
    processing_config_class=ProcessingConfiguration,
    module_family=ModuleFamily.EXAMPLE,
    sensor_config_class=get_sensor_config,
    processor=multi_sensor_processor(Processor),
    multi_sensor=True,
    docs_url="https://docs.acconeer.com/en/latest/processing/parking.html",
)
