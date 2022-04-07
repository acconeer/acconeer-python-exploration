from __future__ import annotations

import json
from typing import Any

from ._utils import convert_validate_int


class SubsweepConfig:
    _hwaas: int

    def __init__(self, hwaas: int = 8) -> None:
        self.hwaas = hwaas

    @property
    def hwaas(self) -> int:
        return self._hwaas

    @hwaas.setter
    def hwaas(self, value: int) -> None:
        int_value = convert_validate_int(value, min_value=1)
        self._hwaas = int_value

    def __eq__(self, other: Any) -> bool:
        return type(self) == type(other) and self.hwaas == other.hwaas

    def to_dict(self) -> dict[str, Any]:
        return {"hwaas": self.hwaas}

    @classmethod
    def from_dict(cls, d: dict) -> SubsweepConfig:
        return SubsweepConfig(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> SubsweepConfig:
        return cls.from_dict(json.loads(json_str))
