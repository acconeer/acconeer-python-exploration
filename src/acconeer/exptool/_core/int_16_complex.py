# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import typing as t

import numpy as np
from numpy import typing as npt


INT_16_COMPLEX = np.dtype([("real", "int16"), ("imag", "int16")])


def int16_complex_array_to_complex(array: npt.NDArray[t.Any]) -> npt.NDArray[np.complex128]:
    """Converts an array with dtype = INT_16_COMPLEX
    (structured with parts "real" and "imag") into
    an array with plain complex dtype (non-structured).
    """
    real = array["real"].astype("float")
    imaginary = array["imag"].astype("float")
    return real + 1.0j * imaginary  # type: ignore[no-any-return]


def complex_array_to_int16_complex(array: npt.NDArray[np.complex128]) -> npt.NDArray[t.Any]:
    """Converts an array with plain complex dtype (non-structured)
    into an array with dtype = INT_16_COMPLEX
    (structured with parts "real" and "imag") using `numpy.round`.
    """
    struct_array = np.empty(array.shape, dtype=INT_16_COMPLEX)
    struct_array["real"] = np.round(array.real)
    struct_array["imag"] = np.round(array.imag)
    return struct_array
