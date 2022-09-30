# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import TypeVar

import numpy as np
import numpy.typing as npt

from acconeer.exptool.a121._core.entities.dtypes import INT_16_COMPLEX

from .metadata import Metadata


T = TypeVar("T", bound=np.generic)


def get_subsweeps_from_frame(frame: npt.NDArray[T], metadata: Metadata) -> list[npt.NDArray[T]]:
    """Gets the subsweeps from a frame (2D, (<sweeps>, <data points>))
    or frames (3D, (<frames>, <sweeps>, <data points>)).
    This is done by slicing the innermost dimension (the <data points> dimension) for both cases.
    """
    offsets = metadata.subsweep_data_offset
    lengths = metadata.subsweep_data_length
    return [frame[..., o : o + l] for o, l in zip(offsets, lengths)]


def int16_complex_array_to_complex(array: npt.NDArray) -> npt.NDArray[np.complex_]:
    """Converts an array with dtype = INT_16_COMPLEX
    (structured with parts "real" and "imag") into
    an array with plain complex dtype (non-structured).
    """
    real = array["real"].astype("float")
    imaginary = array["imag"].astype("float")
    return real + 1.0j * imaginary  # type: ignore[no-any-return]


def complex_array_to_int16_complex(array: npt.NDArray[np.complex_]) -> npt.NDArray:
    """Converts an array with plain complex dtype (non-structured)
    into an array with dtype = INT_16_COMPLEX
    (structured with parts "real" and "imag") using `numpy.round`.
    """
    struct_array = np.empty(array.shape, dtype=INT_16_COMPLEX)
    struct_array["real"] = np.round(array.real)
    struct_array["imag"] = np.round(array.imag)
    return struct_array
