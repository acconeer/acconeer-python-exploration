# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import json
from typing import Any

import attrs


@attrs.frozen(kw_only=True)
class SensorCalibration:
    """SensorCalibration

    Represents the RSS ``cal_result`` and ``cal_info``.
    """

    temperature: int = attrs.field()
    """The calibration temperature"""

    data: str = attrs.field()
    """The calibration data"""

    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SensorCalibration:
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> SensorCalibration:
        return cls.from_dict(json.loads(json_str))
