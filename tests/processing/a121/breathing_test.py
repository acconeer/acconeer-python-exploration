# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import functools
import math
from typing import Optional

import numpy as np

from acconeer.exptool import a121
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo import breathing
from acconeer.exptool.a121.algo.breathing._processor import BreathingProcessorResult
from acconeer.exptool.a121.algo.breathing._ref_app import RefAppResult, _load_algo_data
from acconeer.exptool.a121.algo.breathing._serializer import RefAppResultListH5Serializer


def breathing_rate_comp(
    a: Optional[BreathingProcessorResult], b: Optional[BreathingProcessorResult]
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


def breathing_result_comparator(this: RefAppResult, other: RefAppResult) -> bool:
    for field, comp in _FIELD_COMPARATORS.items():
        lhs = getattr(this, field)
        rhs = getattr(other, field)
        if not comp(lhs, rhs):
            print(lhs)
            print(rhs)
            return False
    return True


def breathing_controller(record: a121.Record) -> breathing.RefApp:
    algo_group = record.get_algo_group("breathing")
    sensor_id, config = _load_algo_data(algo_group)
    client = _ReplayingClient(record)
    app = breathing.RefApp(
        client=client,
        sensor_id=sensor_id,
        ref_app_config=config,
    )

    app.start()

    return app
