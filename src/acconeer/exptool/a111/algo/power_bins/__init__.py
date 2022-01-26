from ..module_info import ModuleFamily, ModuleInfo
from ..utils import PassthroughProcessor
from .plotting import PGUpdater
from .processing import get_sensor_config


module_info = ModuleInfo(
    key="power_bins",
    label="Power bins",
    pg_updater=PGUpdater,
    processing_config_class=None,
    module_family=ModuleFamily.SERVICE,
    sensor_config_class=get_sensor_config,
    processor=PassthroughProcessor,
    multi_sensor=False,
    docs_url="https://acconeer-python-exploration.readthedocs.io/en/latest/services/pb.html",
)
