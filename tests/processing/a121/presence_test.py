# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import presence
from acconeer.exptool.a121.algo.presence._configs import (
    get_long_range_config,
    get_medium_range_config,
    get_short_range_config,
)
from acconeer.exptool.a121.algo.presence._serializers import ProcessorResultListH5Serializer


@attrs.frozen
class ProcessorResultSlice:
    intra_presence_score: float = attrs.field()
    intra: npt.NDArray[np.float_] = attrs.field(eq=utils.attrs_ndarray_isclose)
    inter_presence_score: float = attrs.field()
    inter: npt.NDArray[np.float_] = attrs.field(eq=utils.attrs_ndarray_isclose)
    presence_distance: float = attrs.field()
    presence_detected: bool = attrs.field()

    @classmethod
    def from_processor_result(cls, result: presence.ProcessorResult) -> te.Self:
        return cls(
            intra_presence_score=result.intra_presence_score,
            intra=result.intra,
            inter_presence_score=result.inter_presence_score,
            inter=result.inter,
            presence_distance=float(result.presence_distance),
            presence_detected=result.presence_detected,
        )


@attrs.mutable
class ProcessorWrapper:
    processor: presence.Processor

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.processor, name)

    def process(self, result: a121.Result) -> ProcessorResultSlice:
        return ProcessorResultSlice.from_processor_result(self.processor.process(result))


PresenceResultH5Serializer = ProcessorResultListH5Serializer


def result_comparator(this: presence.ProcessorResult, other: presence.ProcessorResult) -> bool:
    return bool(
        np.isclose(this.inter_presence_score, other.inter_presence_score)
        and np.isclose(this.intra_presence_score, other.intra_presence_score)
        and this.presence_detected == other.presence_detected
        and np.isclose(this.presence_distance, other.presence_distance)
    )


def presence_default(record: a121.H5Record) -> ProcessorWrapper:
    return ProcessorWrapper(
        presence.Processor(
            sensor_config=record.session_config.sensor_config,
            processor_config=presence.Detector._get_processor_config(get_medium_range_config()),
            metadata=utils.unextend(record.extended_metadata),
        )
    )


def presence_short_range(record: a121.H5Record) -> ProcessorWrapper:
    return ProcessorWrapper(
        presence.Processor(
            sensor_config=record.session_config.sensor_config,
            processor_config=presence.Detector._get_processor_config(get_short_range_config()),
            metadata=utils.unextend(record.extended_metadata),
        )
    )


def presence_long_range(record: a121.H5Record) -> ProcessorWrapper:
    return ProcessorWrapper(
        presence.Processor(
            sensor_config=record.session_config.sensor_config,
            processor_config=presence.Detector._get_processor_config(get_long_range_config()),
            metadata=utils.unextend(record.extended_metadata),
        )
    )


def presence_medium_range_phase_boost_no_timeout(record: a121.H5Record) -> ProcessorWrapper:
    processor_config = presence.Detector._get_processor_config(get_medium_range_config())
    processor_config.inter_frame_presence_timeout = 0
    processor_config.inter_phase_boost = True
    return ProcessorWrapper(
        presence.Processor(
            sensor_config=record.session_config.sensor_config,
            processor_config=processor_config,
            metadata=utils.unextend(record.extended_metadata),
        )
    )
