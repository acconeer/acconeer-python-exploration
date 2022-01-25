import sys

from ..module_info import ModuleFamily, ModuleInfo
from .plotting import PGUpdater
from .processing import PhaseTrackingProcessor, get_sensor_config


module_info = ModuleInfo(
    "iq_phase_tracking",
    "Phase tracking (IQ)",
    sys.modules[__name__],
    ModuleFamily.EXAMPLE,
    get_sensor_config,
    PhaseTrackingProcessor,
    False,
    "https://acconeer-python-exploration.readthedocs.io"
    "/en/latest/processing/phase_tracking.html",
)
