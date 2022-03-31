from __future__ import annotations

import attrs
import numpy.typing as npt

from ._metadata import Metadata


@attrs.frozen
class _ResultContext:
    metadata: Metadata = attrs.field()
    ticks_per_second: int = attrs.field()


@attrs.frozen
class Result:
    data_saturated: bool = attrs.field()
    frame_delayed: bool = attrs.field()
    calibration_needed: bool = attrs.field()
    temperature: int = attrs.field()
    _frame: npt.NDArray = attrs.field()

    tick: int = attrs.field()

    _context: _ResultContext = attrs.field()

    @property
    def frame(self) -> npt.NDArray:
        raise NotImplementedError

    @property
    def subframes(self) -> list[npt.NDArray]:
        raise NotImplementedError

    @property
    def tick_time(self) -> float:
        raise NotImplementedError
