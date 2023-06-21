# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import functools
import math
import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo import breathing
from acconeer.exptool.a121.algo.breathing._processor import BreathingProcessorResult
from acconeer.exptool.a121.algo.breathing._ref_app import RefAppResult, _load_algo_data
from acconeer.exptool.a121.algo.breathing._serializer import RefAppResultListH5Serializer


def breathing_rate_comp(
    a: t.Optional[BreathingProcessorResult], b: t.Optional[BreathingProcessorResult]
) -> bool:
    return (
        (a is None and b is None)
        or (a.breathing_rate is None and b.breathing_rate is None)
        or (
            a.breathing_rate is not None
            and b.breathing_rate is not None
            and (
                (np.isnan(a.breathing_rate) and np.isnan(b.breathing_rate))
                or math.isclose(a.breathing_rate, b.breathing_rate)
            )
        )
    )


_FIELD_COMPARATORS = {
    "app_state": lambda a, b: a == b,
    "distances_being_analyzed": lambda a, b: (a is None and b is None) or (a == b),
    "breathing_result": lambda a, b: breathing_rate_comp(a, b),
}

_SERIALIZED_TEST_FIELDS = tuple(_FIELD_COMPARATORS.keys())

BreathingResultH5Serializer = functools.partial(
    RefAppResultListH5Serializer,
    fields=_SERIALIZED_TEST_FIELDS,
    allow_missing_fields=False,
)


@attrs.frozen
class ProcessorResultSlice:
    breathing_rate: t.Optional[float]


@attrs.frozen
class RefAppResultSlice:
    app_state: breathing.AppState
    _distances_being_analyzed: npt.NDArray[np.int_]
    """
    Originally t.Optional[t.Tuple[int, int]]
    None             |-> np.array([])
    Tuple[int, int]  |-> np.array([x, y])
    """
    breathing_rate: t.Optional[float]
    """
    <float> |-> ProcessorResult(breathing_rate=<float>)
    NaN     |-> ProcessorResult(breathing_rate=None)
    None    |-> None
    """

    @property
    def breathing_result(self) -> t.Optional[ProcessorResultSlice]:
        if self.breathing_rate is None:
            return None
        elif np.isnan(self.breathing_rate):
            return ProcessorResultSlice(None)
        else:
            return ProcessorResultSlice(self.breathing_rate)

    @property
    def distances_being_analyzed(self) -> t.Optional[t.Tuple[int, int]]:
        if np.array_equal(self._distances_being_analyzed, np.array([])):
            return None
        else:
            assert self._distances_being_analyzed.shape == (2,)
            return (
                int(self._distances_being_analyzed[0]),
                int(self._distances_being_analyzed[1]),
            )

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


def breathing_result_comparator(this: RefAppResult, other: RefAppResult) -> bool:
    for field, comp in _FIELD_COMPARATORS.items():
        lhs = getattr(this, field)
        rhs = getattr(other, field)
        if not comp(lhs, rhs):
            print(lhs)
            print(rhs)
            return False
    return True


def breathing_controller(record: a121.Record) -> RefAppWrapper:
    algo_group = record.get_algo_group("breathing")
    sensor_id, config = _load_algo_data(algo_group)
    client = _ReplayingClient(record)
    app = RefAppWrapper(
        breathing.RefApp(
            client=client,
            sensor_id=sensor_id,
            ref_app_config=config,
        )
    )

    app.start()

    return app
