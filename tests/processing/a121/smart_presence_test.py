# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import functools

import numpy as np

from acconeer.exptool import a121
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo import smart_presence
from acconeer.exptool.a121.algo.smart_presence._ref_app import _load_algo_data
from acconeer.exptool.a121.algo.smart_presence._serializer import RefAppResultListH5Serializer


_FIELD_COMPARATORS = {
    "zone_limits": lambda a, b: bool(np.isclose(a, b).all()),
    "presence_detected": lambda a, b: a == b,
    "max_presence_zone": lambda a, b: a == b,
    "total_zone_detections": lambda a, b: bool(np.equal(a, b).all()),
    "inter_presence_score": lambda a, b: np.isclose(a, b),
    "inter_zone_detections": lambda a, b: bool(np.equal(a, b).all()),
    "max_inter_zone": lambda a, b: a == b,
    "intra_presence_score": lambda a, b: np.isclose(a, b),
    "intra_zone_detections": lambda a, b: bool(np.equal(a, b).all()),
    "max_intra_zone": lambda a, b: a == b,
}

_SERIALIZED_TEST_FIELDS = tuple(_FIELD_COMPARATORS.keys())
SmartPresenceResultH5Serializer = functools.partial(
    RefAppResultListH5Serializer,
    fields=_SERIALIZED_TEST_FIELDS,
    allow_missing_fields=False,
)


def smart_presence_result_comparator(
    this: smart_presence.ProcessorResult, other: smart_presence.ProcessorResult
) -> bool:
    for field, comp in _FIELD_COMPARATORS.items():
        lhs = getattr(this, field)
        rhs = getattr(other, field)
        if not comp(lhs, rhs):
            return False
    return True


def smart_presence_controller(record: a121.H5Record) -> smart_presence.RefApp:
    algo_group = record.get_algo_group("smart_presence")
    sensor_id, config = _load_algo_data(algo_group)
    client = _ReplayingClient(record)
    app = smart_presence.RefApp(
        client=client,
        sensor_id=sensor_id,
        ref_app_config=config,
    )

    app.start()

    return app
