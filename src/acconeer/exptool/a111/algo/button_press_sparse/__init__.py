import sys

from ..module_info import ModuleFamily, ModuleInfo
from .plotting import PGUpdater
from .processing import ButtonPressProcessor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    "button_press_sparse",
    "Button Press (sparse)",
    sys.modules[__name__],
    ModuleFamily.EXAMPLE,
    get_sensor_config,
    ButtonPressProcessor,
    False,
    None,
)
