import sys

from ..module_info import ModuleFamily, ModuleInfo
from .plotting import PGUpdater
from .processing import Processor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    "iq_sleep_breathing",
    "Sleep breathing (IQ)",
    sys.modules[__name__],
    ModuleFamily.EXAMPLE,
    get_sensor_config,
    Processor,
    False,
    "https://acconeer-python-exploration.readthedocs.io"
    "/en/latest/processing/sleep_breathing.html",
)
