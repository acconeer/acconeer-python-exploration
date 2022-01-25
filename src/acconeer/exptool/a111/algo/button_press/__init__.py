import sys

from ..module_info import ModuleFamily, ModuleInfo
from .plotting import PGUpdater
from .processing import ButtonPressProcessor, get_processing_config, get_sensor_config


module_info = ModuleInfo(
    "envelope_button_press",
    "Button Press (envelope)",
    sys.modules[__name__],
    ModuleFamily.EXAMPLE,
    get_sensor_config,
    ButtonPressProcessor,
    False,
    "https://acconeer-python-exploration.readthedocs.io/en/latest/processing/button_press.html",
)
