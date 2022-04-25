from __future__ import annotations

import enum
import json
from typing import Any, Tuple

import attrs
import numpy as np
import numpy.typing as npt

from .common import attrs_ndarray_eq


class SensorDataType(enum.Enum):
    UINT_16 = np.dtype("uint16")
    INT_16 = np.dtype("int16")
    INT_16_COMPLEX = np.dtype([("real", "int16"), ("imag", "int16")])


@attrs.frozen(kw_only=True)
class Metadata:
    frame_data_length: int = attrs.field()
    sweep_data_length: int = attrs.field()
    subsweep_data_offset: npt.NDArray = attrs.field(eq=attrs_ndarray_eq)
    subsweep_data_length: npt.NDArray = attrs.field(eq=attrs_ndarray_eq)
    _data_type: SensorDataType = attrs.field()

    @property
    def frame_shape(self) -> Tuple[int, int]:
        """The frame shape this Metadata defines"""
        num_sweeps = self.frame_data_length // self.sweep_data_length
        return (num_sweeps, self.sweep_data_length)

    def to_dict(self) -> dict[str, Any]:
        d = attrs.asdict(self)
        d["data_type"] = d.pop("_data_type")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Metadata:
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self, cls=MetadataEncoder)

    @classmethod
    def from_json(cls, json_str: str) -> Metadata:
        return cls.from_dict(json.loads(json_str, cls=MetadataDecoder))


class MetadataEncoder(json.JSONEncoder):
    """Encoder that transforms a Metadata instance to a serializable
    dict before any json transformation
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Metadata):
            metadata_dict = obj.to_dict()

            # numpy arrays are not serializable.
            # Since they are integer arrays, no precision will be lost
            metadata_dict["subsweep_data_length"] = metadata_dict["subsweep_data_length"].tolist()
            metadata_dict["subsweep_data_offset"] = metadata_dict["subsweep_data_offset"].tolist()
            metadata_dict["data_type"] = metadata_dict["data_type"].name
            return metadata_dict

        return super().default(obj)


class MetadataDecoder(json.JSONDecoder):
    """Decoder that post-processes the dict (parsed from json) to better fit Metadata.from_dict"""

    def decode(self, s: str) -> Any:  # type: ignore[override]
        metadata_dict = super().decode(s)

        # post process the parsed dict to have numpy-arrays instead of plain lists
        metadata_dict["subsweep_data_length"] = np.array(metadata_dict["subsweep_data_length"])
        metadata_dict["subsweep_data_offset"] = np.array(metadata_dict["subsweep_data_offset"])
        # - || - for the enum value.
        metadata_dict["data_type"] = SensorDataType[metadata_dict["data_type"]]

        return metadata_dict
