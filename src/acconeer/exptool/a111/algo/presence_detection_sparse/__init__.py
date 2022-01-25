import sys

from ..module_info import ModuleFamily, ModuleInfo
from ..utils import multi_sensor_wrap
from .plotting import PGUpdater
from .processing import Processor, get_processing_config, get_sensor_config


_multi_sensor_wrap = multi_sensor_wrap(sys.modules[__name__])


module_info = ModuleInfo(
    "sparse_presence",
    "Presence detection (sparse)",
    _multi_sensor_wrap,
    ModuleFamily.DETECTOR,
    _multi_sensor_wrap.get_sensor_config,
    _multi_sensor_wrap.Processor,
    True,
    "https://acconeer-python-exploration.readthedocs.io"
    "/en/latest/processing/presence_detection_sparse.html",
)
