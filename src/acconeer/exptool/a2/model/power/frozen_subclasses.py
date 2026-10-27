# Copyright (c) Acconeer AB, 2026
# All rights reserved
import typing as t

import attrs
import typing_extensions as te

from acconeer.exptool import a2
from acconeer.exptool.a2.algo.heatmap.capon.config import HeatmapConfig as HeatmapCaponConfig
from acconeer.exptool.a2.algo.heatmap.coherent.config import (
    HeatmapConfig as HeatmapCoherentConfig,
)
from acconeer.exptool.a2.algo.heatmap.conventional.config import (
    HeatmapConfig as HeatmapConventionalConfig,
)
from acconeer.exptool.a2.algo.heatmap.robust_capon.config import (
    HeatmapConfig as HeatmapRobustCaponConfig,
)


@attrs.frozen
class _FrozenSubsweepConfig(a2.SubsweepConfig): ...


# `eq=tuple` on the inherited list fields makes attrs use tuple(value)
# when computing __eq__ and __hash__, so the frozen subclasses are
# hashable for @functools.cache use without changing the parent's
# list-typed annotation (opser keeps working).


@attrs.frozen
class _FrozenSensorConfig(a2.SensorConfig):
    subsweeps: list[a2.SubsweepConfig] = attrs.field(eq=tuple, factory=list)

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
        return cls(
            **{
                **dict_repr,
                "subsweeps": [
                    _FrozenSubsweepConfig.from_dict(subsweep_dict)
                    for subsweep_dict in dict_repr["subsweeps"]
                ],
            }
        )


@attrs.frozen
class FrozenSessionConfig(a2.SessionConfig):
    sensor_configs: list[a2.SensorConfig] = attrs.field(eq=tuple, factory=list)

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
        return cls(
            sensor_configs=[
                _FrozenSensorConfig.from_dict(sensor_config_dict)
                for sensor_config_dict in dict_repr["sensor_configs"]
            ],
            update_rate=dict_repr["update_rate"],
        )


@attrs.frozen
class FrozenHeatmapCaponConfig(HeatmapCaponConfig): ...


@attrs.frozen
class FrozenHeatmapCoherentConfig(HeatmapCoherentConfig): ...


@attrs.frozen
class FrozenHeatmapConventionalConfig(HeatmapConventionalConfig): ...


@attrs.frozen
class FrozenHeatmapRobustCaponConfig(HeatmapRobustCaponConfig): ...
