from __future__ import annotations

import attrs
import numpy as np
import numpy.typing as npt

from .common import attrs_ndarray_eq
from .metadata import Metadata
from .utils import get_subsweeps_from_frame, int16_complex_array_to_complex


@attrs.frozen(kw_only=True)
class ResultContext:
    metadata: Metadata = attrs.field()
    ticks_per_second: int = attrs.field()


@attrs.frozen(kw_only=True)
class Result:
    data_saturated: bool = attrs.field()
    frame_delayed: bool = attrs.field()
    calibration_needed: bool = attrs.field()
    temperature: int = attrs.field()
    _frame: npt.NDArray = attrs.field(eq=attrs_ndarray_eq)

    tick: int = attrs.field()

    _context: ResultContext = attrs.field()

    @property
    def frame(self) -> npt.NDArray[np.complex_]:
        return int16_complex_array_to_complex(self._frame)

    @property
    def subframes(self) -> list[npt.NDArray[np.complex_]]:
        return get_subsweeps_from_frame(self.frame, self._context.metadata)

    @property
    def tick_time(self) -> float:
        return self.tick / self._context.ticks_per_second
