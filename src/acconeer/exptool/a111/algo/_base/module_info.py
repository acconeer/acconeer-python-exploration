# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

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
    docs_url: str | None
    calibration_class: type[Calibration] | None = None
    calibration_config_class: type[et.configbase.Config] | None = None
    calibration_mapper: type[CalibrationMapper] | None = None
