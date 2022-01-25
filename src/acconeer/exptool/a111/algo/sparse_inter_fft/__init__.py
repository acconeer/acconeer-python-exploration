import sys

from ..module_info import ModuleFamily, ModuleInfo
from .plotting import PGUpdater
from .processing import Processor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    "sparse_inter_fft",
    "Sparse long-time FFT (sparse)",
    sys.modules[__name__],
    ModuleFamily.EXAMPLE,
    get_sensor_config,
    Processor,
    False,
    None,
)
