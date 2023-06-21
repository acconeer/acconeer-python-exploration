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
from acconeer.exptool.a121.algo import tank_level
from acconeer.exptool.a121.algo.tank_level._ref_app import _load_algo_data
from acconeer.exptool.a121.algo.tank_level._serializer import RefAppResultListH5Serializer


def optional_float_arraylike_comp(
    rhs: t.Optional[npt.ArrayLike], lhs: t.Optional[npt.ArrayLike]
) -> bool:
    # Seems like e.g. estimated_distances have 2 sentinels;
    # both None and []. It's assumed they mean the same thing.
    if (rhs is not None and len(rhs) == 0 and lhs is None) or (
        rhs is None and lhs is not None and len(lhs) == 0
    ):
        return True

    if rhs is None or lhs is None:
        return rhs is lhs

    return bool(np.isclose(rhs, lhs).all())


_FIELD_COMPARATORS = {
    "peak_detected": lambda a, b: a == b,
    "peak_status": lambda a, b: a == b,
    "level": lambda a, b: (a is None and b is None)
    or math.isclose(a, b)
    or (np.isnan(a) and np.isnan(b))
    or (a is None and np.isnan(b))
    or (np.isnan(a) and b is None),
    # ignored: "extra_result"
}

_SERIALIZED_TEST_FIELDS = tuple(_FIELD_COMPARATORS.keys())

TankLevelResultH5Serializer = functools.partial(
    RefAppResultListH5Serializer,
    fields=_SERIALIZED_TEST_FIELDS,
    allow_missing_fields=False,
)


@attrs.frozen
class RefAppResultSlice:
    peak_detected: t.Optional[bool]
    peak_status: t.Optional[tank_level.ProcessorLevelStatus]
    level: t.Optional[float]

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


def tank_level_result_comparator(
    this: tank_level.ProcessorResult, other: tank_level.ProcessorResult
) -> bool:
    for field, comp in _FIELD_COMPARATORS.items():
        lhs = getattr(this, field)
        rhs = getattr(other, field)
        if not comp(lhs, rhs):
            return False
    return True


def tank_level_controller(record: a121.H5Record) -> RefAppWrapper:
    algo_group = record.get_algo_group("tank_level")
    sensor_id, config, context = _load_algo_data(algo_group)
    client = _ReplayingClient(record)
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
