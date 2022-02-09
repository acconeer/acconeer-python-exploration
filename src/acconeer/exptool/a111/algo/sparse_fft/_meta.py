from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo

from .plotting import PGUpdater
from .processing import Processor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    key="sparse_fft",
    label="Sparse short-time FFT (sparse)",
    pg_updater=PGUpdater,
    processing_config_class=get_processing_config,
    module_family=ModuleFamily.EXAMPLE,
    sensor_config_class=get_sensor_config,
    processor=Processor,
    multi_sensor=False,
    docs_url=None,
)
