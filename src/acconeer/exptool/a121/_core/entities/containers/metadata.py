# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import json
from typing import Any, Tuple

import attrs
import numpy as np
import numpy.typing as npt

from .common import attrs_ndarray_eq


@attrs.frozen(kw_only=True)
class Metadata:
    """Metadata

    Represents a superset of the RSS ``processing_metadata``.
    """

    frame_data_length: int = attrs.field()
    """Number of elements in the frame"""

    sweep_data_length: int = attrs.field()
    """Number of elements in the sweep"""

    subsweep_data_offset: npt.NDArray = attrs.field(eq=attrs_ndarray_eq)
    """Offset to the subsweeps data"""

    subsweep_data_length: npt.NDArray = attrs.field(eq=attrs_ndarray_eq)
    """Number of elements in the subsweeps"""

    calibration_temperature: int = attrs.field()
    """Temperature during calibration"""

    tick_period: int = attrs.field()
    """Target tick period if update rate is set, otherwise 0"""

    base_step_length_m: float = attrs.field()
    """Base step length in meter"""

    max_sweep_rate: float = attrs.field()
    """Maximum sweep rate that the sensor can provide for the given configuration"""

    @property
    def frame_shape(self) -> Tuple[int, int]:
        """The frame shape this Metadata defines"""

        num_sweeps = self.frame_data_length // self.sweep_data_length
        return (num_sweeps, self.sweep_data_length)

    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

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
            return metadata_dict

        return super().default(obj)


class MetadataDecoder(json.JSONDecoder):
    """Decoder that post-processes the dict (parsed from json) to better fit Metadata.from_dict"""

    def decode(self, s: str) -> Any:  # type: ignore[override]
        metadata_dict = super().decode(s)

        # post process the parsed dict to have numpy-arrays instead of plain lists
        metadata_dict["subsweep_data_length"] = np.array(metadata_dict["subsweep_data_length"])
        metadata_dict["subsweep_data_offset"] = np.array(metadata_dict["subsweep_data_offset"])

        return metadata_dict
