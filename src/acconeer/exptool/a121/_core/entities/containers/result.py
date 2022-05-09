from __future__ import annotations

import attrs
import numpy.typing as npt

from .common import attrs_ndarray_eq
from .metadata import Metadata


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
    def frame(self) -> npt.NDArray:
        real_part = self._frame["real"].astype("float")
        imag_part = self._frame["imag"].astype("float")
        return real_part + 1.0j * imag_part  # type: ignore[no-any-return]

    @property
    def subframes(self) -> list[npt.NDArray]:
        offsets = self._context.metadata.subsweep_data_offset
        lengths = self._context.metadata.subsweep_data_length
        return [self.frame[:, o : (o + l)] for o, l in zip(offsets, lengths)]

    @property
    def tick_time(self) -> float:
        return self.tick / self._context.ticks_per_second
