# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import functools
import typing as t

import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo import distance
from acconeer.exptool.a121.algo.distance._detector import _load_algo_data
from acconeer.exptool.a121.algo.distance._serializers import (
    DetectorResultListH5Serializer,
    ProcessorResultListH5Serializer,
)


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


_PROCESSOR_FIELD_COMPARATORS = {
    "estimated_distances": optional_float_arraylike_comp,
    "estimated_rcs": optional_float_arraylike_comp,
    "near_edge_status": lambda a, b: a == b,
    # ignored: "recorded_threshold_mean_sweep"
    # ignored: "recorded_threshold_noise_std"
    # ignored: "direct_leakage"
    # ignored: "phase_jitter_comp_reference"
}

_DETECTOR_FIELD_COMPARATORS = {
    "rcs": optional_float_arraylike_comp,
    "distances": optional_float_arraylike_comp,
    "near_edge_status": lambda a, b: a == b,
    # ignored: "processor_results"
    # ignored: "service_extended_result"
}

PROCESSOR_SERIALIZED_TEST_FIELDS = tuple(_PROCESSOR_FIELD_COMPARATORS.keys())
_DETECTOR_SERIALIZED_TEST_FIELDS = tuple(_DETECTOR_FIELD_COMPARATORS.keys())

DistanceProcessorResultH5Serializer = functools.partial(
    ProcessorResultListH5Serializer,
    fields=PROCESSOR_SERIALIZED_TEST_FIELDS,
    allow_missing_fields=True,
)

DistanceDetectorResultH5Serializer = functools.partial(
    DetectorResultListH5Serializer,
    fields=_DETECTOR_SERIALIZED_TEST_FIELDS,
    allow_missing_fields=False,
)


def processor_result_comparator(
    this: distance.ProcessorResult, other: distance.ProcessorResult
) -> bool:
    for field, comp in _PROCESSOR_FIELD_COMPARATORS.items():
        lhs = getattr(this, field)
        rhs = getattr(other, field)
        if not comp(lhs, rhs):
            return False
    return True


def detector_result_comparator(
    this: t.Dict[distance.DetectorResult], other: t.Dict[distance.DetectorResult]
) -> bool:
    for (th, ot) in zip(this.values(), other.values()):
        for field, comp in _DETECTOR_FIELD_COMPARATORS.items():
            lhs = getattr(th, field)
            rhs = getattr(ot, field)
            if not comp(lhs, rhs):
                return False
    return True


def distance_processor(record: a121.H5Record) -> distance.Processor:
    sensor_config = record.session_config.sensor_config
    sensor_config.phase_enhancement = True
    return distance.Processor(
        sensor_config=sensor_config,
        processor_config=distance.ProcessorConfig(),
        metadata=utils.unextend(record.extended_metadata),
    )


def distance_detector(record: a121.H5Record) -> distance.Detector:
    algo_group = record.get_algo_group("distance_detector")
    _, config, context = _load_algo_data(algo_group)
    sensor_ids = list(next(iter(record.session_config.groups)).keys())
    client = _ReplayingClient(record)
    detector = distance.Detector(
        client=client,
        sensor_ids=sensor_ids,
        detector_config=config,
        context=context,
    )

    detector.start()

    return detector
