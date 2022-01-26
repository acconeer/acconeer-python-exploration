from ..module_info import ModuleFamily, ModuleInfo
from .plotting import PGUpdater
from .processing import PhaseTrackingProcessor, get_sensor_config


module_info = ModuleInfo(
    key="iq_phase_tracking",
    label="Phase tracking (IQ)",
    pg_updater=PGUpdater,
    processing_config_class=None,
    module_family=ModuleFamily.EXAMPLE,
    sensor_config_class=get_sensor_config,
    processor=PhaseTrackingProcessor,
    multi_sensor=False,
    docs_url=(
        "https://acconeer-python-exploration.readthedocs.io/"
        + "en/latest/processing/phase_tracking.html"
    ),
)
