# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

import numpy as np
import numpy.typing as npt

from .metadata import Metadata


T = t.TypeVar("T", bound=np.generic)


def get_subsweeps_from_frame(frame: npt.NDArray[T], metadata: Metadata) -> list[npt.NDArray[T]]:
    """Gets the subsweeps from a frame (2D, (<sweeps>, <data points>))
    or frames (3D, (<frames>, <sweeps>, <data points>)).
    This is done by slicing the innermost dimension (the <data points> dimension) for both cases.
    """
    offsets = metadata.subsweep_data_offset
    lengths = metadata.subsweep_data_length
    return [frame[..., o : o + l] for o, l in zip(offsets, lengths)]
