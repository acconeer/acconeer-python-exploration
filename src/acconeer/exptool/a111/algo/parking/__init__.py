import sys

from ..module_info import ModuleFamily, ModuleInfo
from ..utils import multi_sensor_wrap
from .plotting import PGUpdater
from .processing import Processor, get_processing_config, get_sensor_config


_multi_sensor_wrap = multi_sensor_wrap(sys.modules[__name__])

module_info = ModuleInfo(
    key="envelope_parking",
    label="Parking (envelope)",
    pg_updater=_multi_sensor_wrap.PGUpdater,
    processing_config_class=_multi_sensor_wrap.get_processing_config,
    module_family=ModuleFamily.DETECTOR,
    sensor_config_class=_multi_sensor_wrap.get_sensor_config,
    processor=_multi_sensor_wrap.Processor,
    multi_sensor=True,
    docs_url=(
        "https://acconeer-python-exploration.readthedocs.io/en/latest/processing/parking.html"
    ),
)
