# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

import attrs
import attrs.validators as av
import typing_extensions as te
from attributes_doc import attributes_doc

from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin


@attributes_doc
@attrs.mutable
class HeatmapPlotConfig(AttrsMappingTransformsMixin):
    normalized_heat_cutoff: float = attrs.field(default=0.75)
    """Cutoff for 'heat points'. A value of 0.5 will discard points that have less than 50% of the max heat"""

    max_2d_heat: t.Optional[int] = attrs.field(default=None, validator=av.optional(av.gt(0)))
    """Max magnitude to display. Magnitudes above this value will be white in the heatmap"""

    log_scale_output: bool = attrs.field(default=False)
    """Whether the values in the heatmap should be plotted in log-scale"""

    @classmethod
    def default(cls) -> te.Self:
        return cls()
