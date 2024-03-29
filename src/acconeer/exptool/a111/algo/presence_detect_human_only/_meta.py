# Copyright (c) Acconeer AB, 2023
# All rights reserved

from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo

from ._processor import ProcessingConfiguration, Processor, get_sensor_config
from .ui import PGUpdater


module_info = ModuleInfo(
    key="presence_detect_human_only",
    label="Presence detection human only (sparse) ",
    pg_updater=PGUpdater,
    processing_config_class=ProcessingConfiguration,
    module_family=ModuleFamily.EXAMPLE,
    sensor_config_class=get_sensor_config,
    processor=Processor,
    multi_sensor=False,
    docs_url=None,
)
