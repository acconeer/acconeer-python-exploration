import sys

from ..module_info import ModuleFamily, ModuleInfo
from .plotting import PGUpdater
from .processing import BreathingProcessor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    "iq_breathing",
    "Breathing (IQ)",
    sys.modules[__name__],
    ModuleFamily.EXAMPLE,
    get_sensor_config,
    BreathingProcessor,
    False,
    None,
)
