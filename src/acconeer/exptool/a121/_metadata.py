from __future__ import annotations

import enum
from typing import Any

import attrs
import numpy as np
import numpy.typing as npt


class SensorDataType(enum.Enum):
    UINT_16 = np.dtype("uint16")
    INT_16 = np.dtype("int16")
    INT_16_COMPLEX = np.dtype([("real", "int16"), ("imag", "int16")])


@attrs.frozen(kw_only=True)
class Metadata:
    frame_data_length: int = attrs.field()
    sweep_data_length: int = attrs.field()
    subsweep_data_offset: npt.NDArray = attrs.field()
    subsweep_data_length: npt.NDArray = attrs.field()
    _data_type: SensorDataType = attrs.field()

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d: dict) -> Metadata:
        raise NotImplementedError

    def to_json(self) -> str:
        raise NotImplementedError

    @classmethod
    def from_json(cls, json_str: str) -> Metadata:
        raise NotImplementedError
