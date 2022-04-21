from __future__ import annotations

import attrs
import numpy.typing as npt

from ._metadata import Metadata, SensorDataType
from .common import attrs_ndarray_eq


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
        data_type = self._context.metadata._data_type

        if data_type == SensorDataType.INT_16_COMPLEX:
            real_part = self._frame["real"].astype("float")
            imag_part = self._frame["imag"].astype("float")
            return real_part + 1.0j * imag_part  # type: ignore[no-any-return]
        elif data_type in [SensorDataType.INT_16, SensorDataType.UINT_16]:
            return self._frame.astype("float")
        else:
            raise RuntimeError

    @property
    def subframes(self) -> list[npt.NDArray]:
        offsets = self._context.metadata.subsweep_data_offset
        lengths = self._context.metadata.subsweep_data_length
        return [self.frame[:, o : (o + l)] for o, l in zip(offsets, lengths)]

    @property
    def tick_time(self) -> float:
        return self.tick / self._context.ticks_per_second
