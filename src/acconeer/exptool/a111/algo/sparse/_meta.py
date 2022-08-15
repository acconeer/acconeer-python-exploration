# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo

from ._processor import ProcessingConfiguration, Processor, get_sensor_config
from .ui import PGUpdater


module_info = ModuleInfo(
    key="sparse",
    label="Sparse",
    pg_updater=PGUpdater,
    processing_config_class=ProcessingConfiguration,
    module_family=ModuleFamily.SERVICE,
    sensor_config_class=get_sensor_config,
    processor=Processor,
    multi_sensor=True,
    docs_url="https://docs.acconeer.com/en/latest/services/sparse.html",
)
