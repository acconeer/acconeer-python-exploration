# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import abc
import typing as t

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a2
from acconeer.exptool.a2.algo.heatmap.config_common import HeatmapConfigCommon


@attrs.frozen(kw_only=True)
class ProcessorResultCommon:
    heatmap: t.Optional[npt.NDArray[np.float64]]
    """3D array with dimensions (distance, az, el) containing amplitude information of returned energy."""
    heatmap_config: HeatmapConfigCommon
    """The configuration used to produce the heatmap"""

    def angle_envelope_iter(self) -> t.Iterator[tuple[int, int, npt.NDArray[np.float64]]]:
        """Return an iterator over tuples of (az, el, heat envelope for all distances)
        Note that the iterator will be empty if ``self.heatmap is None``.
        """
        if self.heatmap is None:
            return
        for i, az in enumerate(self.heatmap_config.az_angles):
            for j, el in enumerate(self.heatmap_config.el_angles):
                yield (az, el, self.heatmap[:, i, j])


_HeatmapConfigT = t.TypeVar("_HeatmapConfigT", bound=HeatmapConfigCommon)


class HeatmapProcessorCommon(abc.ABC, t.Generic[_HeatmapConfigT]):
    def __init__(
        self,
        subsweep_config: a2.SubsweepConfig,
        heatmap_config: _HeatmapConfigT,
        update_rate: float,
    ) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def process(self, result: a2.Result) -> ProcessorResultCommon:
        pass
