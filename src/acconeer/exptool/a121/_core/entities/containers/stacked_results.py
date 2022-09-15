# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool.a121._core.utils import attrs_ndarray_eq

from .result import Result, ResultContext
from .utils import get_subsweeps_from_frame, int16_complex_array_to_complex


NDArrayBool = npt.NDArray[np.bool_]
NDArrayInt = npt.NDArray[np.int64]


@attrs.frozen(kw_only=True)
class StackedResults:
    """Stacked results

    For loading/processing data.

    Representation of multiple :class:`Result` stacked together. Scalar values, like
    :attr:`Result.data_saturated`, become 1-D arrays of the same type. The :attr:`Result.frame`,
    which is originally a 2-D array, becomes a 3-D array where the frames are stacked in the first
    dimension.

    See :class:`Result` for details on the attributes/properties.
    """

    data_saturated: NDArrayBool = attrs.field(eq=attrs_ndarray_eq)
    frame_delayed: NDArrayBool = attrs.field(eq=attrs_ndarray_eq)
    calibration_needed: NDArrayBool = attrs.field(eq=attrs_ndarray_eq)
    temperature: NDArrayBool = attrs.field(eq=attrs_ndarray_eq)
    _frame: npt.NDArray = attrs.field(eq=attrs_ndarray_eq)

    tick: NDArrayInt = attrs.field()

    _context: ResultContext = attrs.field()

    @property
    def frame(self) -> npt.NDArray[np.complex_]:
        return int16_complex_array_to_complex(self._frame)

    @property
    def subframes(self) -> list[npt.NDArray[np.complex_]]:
        return get_subsweeps_from_frame(self.frame, self._context.metadata)

    @property
    def tick_time(self) -> npt.NDArray[np.float_]:
        return self.tick / self._context.ticks_per_second

    def __len__(self) -> int:
        return len(self._frame)

    def __getitem__(self, key: int) -> Result:
        return Result(
            calibration_needed=self.calibration_needed[key],
            data_saturated=self.data_saturated[key],
            frame_delayed=self.frame_delayed[key],
            temperature=self.temperature[key],
            tick=self.tick[key],
            frame=self._frame[key],
            context=self._context,
        )
