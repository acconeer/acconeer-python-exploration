# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool._core.class_creation.attrs import attrs_optional_ndarray_isclose
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo import distance
from acconeer.exptool.a121.algo.distance._detector import _load_algo_data


@attrs.frozen
class ResultSlice:
    distances: t.Optional[npt.NDArray[np.float64]] = attrs.field(eq=attrs_optional_ndarray_isclose)
    strengths: t.Optional[npt.NDArray[np.float64]] = attrs.field(eq=attrs_optional_ndarray_isclose)
    near_edge_status: t.Optional[bool]

    @property
    def estimated_distances(self) -> t.Optional[npt.NDArray[np.float64]]:
        return self.distances

    @property
    def estimated_strengths(self) -> t.Optional[npt.NDArray[np.float64]]:
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
    client = _ReplayingClient(record, realtime_replay=False)
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
