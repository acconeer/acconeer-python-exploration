# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool.a121._core.utils import attrs_ndarray_eq

from .metadata import Metadata
from .utils import get_subsweeps_from_frame, int16_complex_array_to_complex


@attrs.frozen(kw_only=True)
class ResultContext:
    metadata: Metadata = attrs.field()
    ticks_per_second: int = attrs.field()


@attrs.frozen(kw_only=True)
class Result:
    """Result

    Represents the RSS ``processing_result``.
    """

    data_saturated: bool = attrs.field()
    """
    Indication of sensor data being saturated, can cause data corruption. Lower the receiver gain
    if this indication is set.
    """

    frame_delayed: bool = attrs.field()
    """
    Indication of a delayed frame. The frame rate might need to be lowered if this indication is
    set.
    """

    calibration_needed: bool = attrs.field()
    """
    Indication of calibration needed. The sensor calibration needs to be redone if this indication
    is set.
    """

    temperature: int = attrs.field()
    """
    Temperature in sensor during measurement (in degree Celsius). Notice that this has poor
    absolute accuracy.
    """

    _frame: npt.NDArray = attrs.field(eq=attrs_ndarray_eq)
    """Frame data in the original data format (complex int16)"""

    tick: int = attrs.field()
    """Server tick when the server got the interrupt from the sensor"""

    _context: ResultContext = attrs.field()

    @property
    def frame(self) -> npt.NDArray[np.complex_]:
        """Frame data in a complex float data format

        2-D with dimensions (sweep, distance).
        """

        return int16_complex_array_to_complex(self._frame)

    @property
    def subframes(self) -> list[npt.NDArray[np.complex_]]:
        """Frame split up into subframes, one for every subsweep config used"""

        return get_subsweeps_from_frame(self.frame, self._context.metadata)

    @property
    def tick_time(self) -> float:
        """Tick converted to a time in seconds"""

        return self.tick / self._context.ticks_per_second
