import sys

from acconeer.exptool.modes import Mode

from ..module_info import ModuleFamily, ModuleInfo
from ..utils import PassthroughProcessor
from .plotting import PGUpdater
from .processing import get_sensor_config


module_info = ModuleInfo(
    Mode.POWER_BINS.name.lower(),
    "Power bins",
    sys.modules[__name__],
    ModuleFamily.SERVICE,
    get_sensor_config,
    PassthroughProcessor,
    False,
    "https://acconeer-python-exploration.readthedocs.io/en/latest/services/pb.html",
)
