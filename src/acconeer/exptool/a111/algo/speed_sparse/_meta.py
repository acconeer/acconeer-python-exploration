# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo
from acconeer.exptool.a111.algo.utils import (
    MultiSensorPGUpdaterCreator,
    MultiSensorProcessorCreator,
)

from ._processor import ProcessingConfiguration, Processor, get_sensor_config
from .ui import PGUpdater


processor_creator = MultiSensorProcessorCreator(Processor)
pg_updater_creator = MultiSensorPGUpdaterCreator(PGUpdater)

module_info = ModuleInfo(
    key="speed_sparse",
    label="Speed (sparse)",
    pg_updater=pg_updater_creator.create_pg_updater,
    processing_config_class=ProcessingConfiguration,
    module_family=ModuleFamily.EXAMPLE,
    sensor_config_class=get_sensor_config,
    processor=processor_creator.create_processor,
    multi_sensor=True,
    docs_url=None,
)
