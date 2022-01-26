from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ModuleFamily(Enum):
    EXAMPLE = "Example processing"
    SERVICE = "Services"
    DETECTOR = "Detectors"
    OTHER = None


@dataclass(frozen=True)
class ModuleInfo:
    key: str
    label: str
    pg_updater: Any
    processing_config_class: Any
    module_family: ModuleFamily
    sensor_config_class: Any
    processor: Any
    multi_sensor: Any
    docs_url: Optional[str]
