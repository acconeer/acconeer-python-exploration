from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo
from acconeer.exptool.a111.algo.utils import multi_sensor_pg_updater, multi_sensor_processor

from ._processor import Processor, get_processing_config, get_sensor_config
from .ui import PGUpdater


module_info = ModuleInfo(
    key="sparse_speed",
    label="Speed (sparse)",
    pg_updater=multi_sensor_pg_updater(PGUpdater),
    processing_config_class=get_processing_config,
    module_family=ModuleFamily.EXAMPLE,
    sensor_config_class=get_sensor_config,
    processor=multi_sensor_processor(Processor),
    multi_sensor=True,
    docs_url=None,
)
