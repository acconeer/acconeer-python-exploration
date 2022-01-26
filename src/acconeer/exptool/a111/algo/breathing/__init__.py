from ..module_info import ModuleFamily, ModuleInfo
from .plotting import PGUpdater
from .processing import BreathingProcessor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    key="iq_breathing",
    label="Breathing (IQ)",
    pg_updater=PGUpdater,
    processing_config_class=get_processing_config,
    module_family=ModuleFamily.EXAMPLE,
    sensor_config_class=get_sensor_config,
    processor=BreathingProcessor,
    multi_sensor=False,
    docs_url=None,
)
