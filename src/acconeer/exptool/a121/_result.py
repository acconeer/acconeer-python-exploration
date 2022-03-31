from __future__ import annotations

import attrs
import numpy.typing as npt

from ._metadata import Metadata, SensorDataType


@attrs.frozen
class ResultContext:
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

    _context: ResultContext = attrs.field()

    @property
    def frame(self) -> npt.NDArray:
        data_type = self._context.metadata._data_type

        if data_type == SensorDataType.INT_16_COMPLEX:
            real_part = self._frame["real"].astype("float")
            imag_part = self._frame["imag"].astype("float")
            return real_part + 1.0j * imag_part
        elif data_type in [SensorDataType.INT_16, SensorDataType.UINT_16]:
            return self._frame.astype("float")
        else:
            raise RuntimeError

    @property
    def subframes(self) -> list[npt.NDArray]:
        raise NotImplementedError

    @property
    def tick_time(self) -> float:
        raise NotImplementedError
