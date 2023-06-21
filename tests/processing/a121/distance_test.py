# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import functools
import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

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


@attrs.frozen
class ResultSlice:
    distances: t.Optional[npt.NDArray[np.float_]]
    strengths: t.Optional[npt.NDArray[np.float_]]
    near_edge_status: t.Optional[bool]

    @property
    def estimated_distances(self) -> t.Optional[npt.NDArray[np.float_]]:
        return self.distances

    @property
    def estimated_strengths(self) -> t.Optional[npt.NDArray[np.float_]]:
        return self.strengths

    @classmethod
    def from_processor_result(cls, result: distance.ProcessorResult) -> te.Self:
        return cls(
            distances=np.array(result.estimated_distances),
            strengths=np.array(result.estimated_strengths),
            near_edge_status=result.near_edge_status,
        )

    @classmethod
    def from_semi_extended_detector_result(
        cls, results: t.Dict[int, distance.DetectorResult]
    ) -> te.Self:
        (result,) = results.values()
        return cls(
            distances=result.distances,
            strengths=result.strengths,
            near_edge_status=result.near_edge_status,
        )


@attrs.mutable
class ProcessorWrapper:
    processor: distance.Processor

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.processor, name)

    def process(self, result: a121.Result) -> ResultSlice:
        return ResultSlice.from_processor_result(self.processor.process(result))


@attrs.mutable
class DetectorWrapper:
    detector: distance.Detector

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.detector, name)

    def get_next(self) -> ResultSlice:
        return ResultSlice.from_semi_extended_detector_result(self.detector.get_next())


_PROCESSOR_FIELD_COMPARATORS = {
    "estimated_distances": optional_float_arraylike_comp,
    "estimated_strengths": optional_float_arraylike_comp,
    "near_edge_status": lambda a, b: a == b,
    # ignored: "recorded_threshold_mean_sweep"
    # ignored: "recorded_threshold_noise_std"
    # ignored: "direct_leakage"
    # ignored: "phase_jitter_comp_reference"
}

_DETECTOR_FIELD_COMPARATORS = {
    "strengths": optional_float_arraylike_comp,
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


def _dict_squeeze(
    __x: t.Union[t.Dict[int, distance.DetectorResult], distance.DetectorResult]
) -> t.Union[t.Dict[int, distance.DetectorResult], distance.DetectorResult]:
    try:
        (result,) = __x.values()
    except Exception:
        return __x
    else:
        return result


def detector_result_comparator(
    this: t.Dict[int, distance.DetectorResult], other: t.Dict[int, distance.DetectorResult]
) -> bool:
    for field, comp in _DETECTOR_FIELD_COMPARATORS.items():
        lhs = getattr(_dict_squeeze(this), field)
        rhs = getattr(_dict_squeeze(other), field)
        if not comp(lhs, rhs):
            return False
    return True


def distance_processor(record: a121.H5Record) -> ProcessorWrapper:
    sensor_config = record.session_config.sensor_config
    sensor_config.phase_enhancement = True
    return ProcessorWrapper(
        distance.Processor(
            sensor_config=sensor_config,
            processor_config=distance.ProcessorConfig(),
            metadata=utils.unextend(record.extended_metadata),
        )
    )


def distance_detector(record: a121.H5Record) -> DetectorWrapper:
    algo_group = record.get_algo_group("distance_detector")
    _, config, context = _load_algo_data(algo_group)
    sensor_ids = list(next(iter(record.session_config.groups)).keys())
    client = _ReplayingClient(record)
    detector = DetectorWrapper(
        distance.Detector(
            client=client,
            sensor_ids=sensor_ids,
            detector_config=config,
            context=context,
        )
    )

    detector.start()

    return detector
