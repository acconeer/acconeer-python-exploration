# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool._core.class_creation.attrs import attrs_ndarray_validator


class Filter(te.Protocol):
    def apply(self, data: npt.NDArray[np.complex128], /) -> npt.NDArray[np.complex128]: ...


@attrs.mutable
class HighPassFilter(Filter):
    """Filter to remove low frequencies (i.e. static objects)."""

    average_data: npt.NDArray[np.complex128] = attrs.field(
        validator=attrs_ndarray_validator(ndim=1, element_type=np.complex128)
    )
    """Filter state. The average data that is seen in ``apply``"""
    alpha: float = attrs.field(converter=float)
    """Exponential smoothing coefficient"""
    num_increments: int = attrs.field(converter=int)
    """The number of increments the filter has gotten"""

    @classmethod
    def initial(cls, num_distances: int, num_channels: int, alpha: float) -> te.Self:
        return cls(
            average_data=np.zeros(num_distances * num_channels, dtype=np.complex128),
            alpha=alpha,
            num_increments=0,
        )

    @property
    def _used_alpha(self) -> float:
        return min(self.alpha, self.num_increments / (self.num_increments + 1))

    def apply(self, data: npt.NDArray[np.complex128]) -> npt.NDArray[np.complex128]:
        deviation = data - self.average_data
        self.average_data = (self._used_alpha) * self.average_data + (1 - self._used_alpha) * data
        if self.num_increments == 0:
            deviation = deviation * 0.0  # Deviation should not be large the first frame
        self.num_increments += 1
        return deviation


class NoopFilter(Filter):
    """A filter that does nothing"""

    def apply(self, data: npt.NDArray[np.complex128]) -> npt.NDArray[np.complex128]:
        return data
