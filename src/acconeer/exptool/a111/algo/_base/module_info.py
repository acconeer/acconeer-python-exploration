# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Type

import acconeer.exptool as et

from .calibration import Calibration, CalibrationMapper


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
    calibration_class: Optional[Type[Calibration]] = None
    calibration_config_class: Optional[Type[et.configbase.Config]] = None
    calibration_mapper: Optional[Type[CalibrationMapper]] = None
