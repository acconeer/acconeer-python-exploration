# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import numpy as np
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo import tank_level
from acconeer.exptool.a121.algo.tank_level._ref_app import _load_algo_data


def _nan_is_none(x: t.Optional[float]) -> t.Optional[float]:
    return None if x is None or np.isnan(x) else float(x)


@attrs.frozen
class RefAppResultSlice:
    peak_detected: t.Optional[bool]
    peak_status: t.Optional[tank_level.ProcessorLevelStatus]
    level: t.Optional[float] = attrs.field(
        converter=_nan_is_none, eq=utils.attrs_optional_ndarray_isclose
    )

    @classmethod
    def from_ref_app_result(cls, result: tank_level.RefAppResult) -> te.Self:
        return cls(
            peak_detected=result.peak_detected,
            peak_status=result.peak_status,
            level=result.level,
        )


@attrs.mutable
class RefAppWrapper:
    ref_app: tank_level.RefApp

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.ref_app, name)

    def get_next(self) -> RefAppResultSlice:
        return RefAppResultSlice.from_ref_app_result(self.ref_app.get_next())


def tank_level_controller(record: a121.H5Record) -> RefAppWrapper:
    algo_group = record.get_algo_group("tank_level")
    sensor_id, config, context = _load_algo_data(algo_group)
    client = _ReplayingClient(record, realtime_replay=False)
    app = RefAppWrapper(
        tank_level.RefApp(
            client=client,
            sensor_id=sensor_id,
            config=config,
            context=context,
        )
    )

    app.start()

    return app
