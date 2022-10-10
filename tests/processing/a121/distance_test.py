# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import functools
import typing as t

import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import distance
from acconeer.exptool.a121.algo.distance._serializers import ProcessorResultListH5Serializer


def optional_float_arraylike_comp(
    rhs: t.Optional[npt.ArrayLike], lhs: t.Optional[npt.ArrayLike]
) -> bool:
    # Seems like e.g. estimated_distances have 2 sentinels;
    # both None and []. It's assumed they mean the same thing.
    if (rhs == [] and lhs is None) or (rhs is None and lhs == []):
        return True

    if rhs is None or lhs is None:
        return rhs is lhs

    return bool(np.isclose(rhs, lhs).all())


_FIELD_COMPARATORS = {
    "estimated_distances": optional_float_arraylike_comp,
    "estimated_amplitudes": optional_float_arraylike_comp,
    # ignored: "recorded_threshold_mean_sweep"
    # ignored: "recorded_threshold_noise_std"
    # ignored: "direct_leakage"
    # ignored: "phase_jitter_comp_reference"
}

_SERIALIZED_TEST_FIELDS = tuple(_FIELD_COMPARATORS.keys())

DistanceResultH5Serializer = functools.partial(
    ProcessorResultListH5Serializer,
    fields=_SERIALIZED_TEST_FIELDS,
    allow_missing_fields=True,
)


def result_comparator(this: distance.ProcessorResult, other: distance.ProcessorResult) -> bool:
    for field, comp in _FIELD_COMPARATORS.items():
        lhs = getattr(this, field)
        rhs = getattr(other, field)
        if not comp(lhs, rhs):
            return False
    return True


def distance_default(record: a121.H5Record) -> distance.Processor:
    sensor_config = record.session_config.sensor_config
    sensor_config.phase_enhancement = True
    return distance.Processor(
        sensor_config=sensor_config,
        processor_config=distance.ProcessorConfig(),
        metadata=utils.unextend(record.extended_metadata),
    )
