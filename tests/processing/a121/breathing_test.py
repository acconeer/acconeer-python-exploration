# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool._core.class_creation.attrs import (
    attrs_ndarray_eq,
    attrs_optional_ndarray_isclose,
)
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo import breathing
from acconeer.exptool.a121.algo.breathing._ref_app import _load_algo_data


@attrs.frozen
class ProcessorResultSlice:
    breathing_rate: t.Optional[float]


@attrs.frozen
class RefAppResultSlice:
    app_state: breathing.AppState
    _distances_being_analyzed: npt.NDArray[np.int_] = attrs.field(eq=attrs_ndarray_eq)
    """
    Originally t.Optional[t.Tuple[int, int]]
    None             |-> np.array([])
    Tuple[int, int]  |-> np.array([x, y])
    """
    breathing_rate: t.Optional[float] = attrs.field(eq=attrs_optional_ndarray_isclose)
    """
    <float> |-> ProcessorResult(breathing_rate=<float>)
    NaN     |-> ProcessorResult(breathing_rate=None)
    None    |-> None
    """

    @classmethod
    def from_ref_app_result(cls, result: breathing.RefAppResult) -> te.Self:
        if result.breathing_result is None:
            breathing_rate = None
        elif result.breathing_result.breathing_rate is None:
            breathing_rate = np.nan
        else:
            breathing_rate = result.breathing_result.breathing_rate

        distances_being_analyzed = np.array(
            [] if result.distances_being_analyzed is None else result.distances_being_analyzed,
            dtype=np.dtype("i"),
        )

        return cls(
            app_state=result.app_state,
            breathing_rate=breathing_rate,
            distances_being_analyzed=distances_being_analyzed,
        )


@attrs.mutable
class RefAppWrapper:
    ref_app: breathing.RefApp

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.ref_app, name)

    def get_next(self) -> RefAppResultSlice:
        return RefAppResultSlice.from_ref_app_result(self.ref_app.get_next())


def breathing_controller(record: a121.Record) -> RefAppWrapper:
    algo_group = record.get_algo_group("breathing")
    sensor_id, config = _load_algo_data(algo_group)
    client = _ReplayingClient(record, realtime_replay=False)
    app = RefAppWrapper(
        breathing.RefApp(
            client=client,
            sensor_id=sensor_id,
            ref_app_config=config,
        )
    )

    app.start()

    return app
