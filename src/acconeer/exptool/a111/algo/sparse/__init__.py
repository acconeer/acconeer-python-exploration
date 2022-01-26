import sys

from ..module_info import ModuleFamily, ModuleInfo
from ..utils import PassthroughProcessor
from .plotting import PGUpdater
from .processing import Processor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    key="sparse",
    label="Sparse",
    pg_updater=PGUpdater,
    processing_config_class=get_processing_config,
    module_family=ModuleFamily.SERVICE,
    sensor_config_class=get_sensor_config,
    processor=Processor,
    multi_sensor=True,
    docs_url="https://acconeer-python-exploration.readthedocs.io/en/latest/services/sparse.html",
)
