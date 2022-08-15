# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo
from acconeer.exptool.a111.algo.utils import PassthroughProcessor

from ._processor import get_sensor_config
from .ui import PGUpdater


module_info = ModuleInfo(
    key="power_bins",
    label="Power bins",
    pg_updater=PGUpdater,
    processing_config_class=lambda: None,
    module_family=ModuleFamily.SERVICE,
    sensor_config_class=get_sensor_config,
    processor=PassthroughProcessor,
    multi_sensor=False,
    docs_url="https://docs.acconeer.com/en/latest/services/pb.html",
)
