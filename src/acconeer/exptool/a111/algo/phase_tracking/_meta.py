# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo

from ._processor import Processor, get_sensor_config
from .ui import PGUpdater


module_info = ModuleInfo(
    key="iq_phase_tracking",
    label="Phase tracking (IQ)",
    pg_updater=PGUpdater,
    processing_config_class=lambda: None,
    module_family=ModuleFamily.EXAMPLE,
    sensor_config_class=get_sensor_config,
    processor=Processor,
    multi_sensor=False,
    docs_url="https://docs.acconeer.com/en/latest/processing/phase_tracking.html",
)
