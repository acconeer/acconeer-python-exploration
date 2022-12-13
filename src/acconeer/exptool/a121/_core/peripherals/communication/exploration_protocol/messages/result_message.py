# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import functools
import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool.a121._core.entities import (
    INT_16_COMPLEX,
    Metadata,
    Result,
    ResultContext,
    SensorConfig,
)
from acconeer.exptool.a121._core.peripherals.communication.message import Message
from acconeer.exptool.a121._core.utils import map_over_extended_structure, zip3_extended_structures

from .parse_error import ParseError


class ResultInfoDict(te.TypedDict):
    tick: int
    data_saturated: bool
    frame_delayed: bool
    calibration_needed: bool
    temperature: int


class ResultMessageHeader(te.TypedDict):
    result_info: list[list[ResultInfoDict]]
    payload_size: int


@attrs.frozen
class EmptyResultMessage(Message):
    """
    This message can come from the server if it somehow starts streaming
    after being stopped.
    """

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> EmptyResultMessage:
        head = t.cast(ResultMessageHeader, header)

        if head.get("payload_size") == 0 and head.get("result_info") == []:
            return EmptyResultMessage()
        else:
            raise ParseError


@attrs.frozen
class ResultMessage(Message):
    grouped_result_infos: list[list[ResultInfoDict]]
    frame_blob: bytes

    @staticmethod
    def _create_result_context(metadata: Metadata, ticks_per_second: int) -> ResultContext:
        return ResultContext(
            metadata=metadata,
            ticks_per_second=ticks_per_second,
        )

    @staticmethod
    def _create_result(args: tuple[ResultInfoDict, npt.NDArray, ResultContext]) -> Result:
        result_info, frame, context = args
        return Result(
            **result_info,
            frame=frame,
            context=context,
        )

    @classmethod
    def _get_array_from_blob(
        cls, frame_blob: bytes, start: int, end: int, frame_shape: t.Tuple[int, int]
    ) -> npt.NDArray:
        raw_frame_data = frame_blob[start:end]
        assert len(raw_frame_data) == end - start
        np_frame = np.frombuffer(raw_frame_data, dtype=INT_16_COMPLEX)
        resized_frame = np.resize(np_frame, frame_shape)
        return resized_frame

    @classmethod
    def _divide_frame_blob(
        cls, frame_blob: bytes, extended_metadata: list[dict[int, Metadata]]
    ) -> list[dict[int, npt.NDArray]]:
        start = 0
        result = []
        for metadata_group in extended_metadata:
            result_group: dict[int, npt.NDArray] = {}
            result.append(result_group)
            for sensor_id, metadata in metadata_group.items():
                end = start + metadata.frame_data_length * 4  # 4 = sizeof(int_16_complex)

                result_group[sensor_id] = cls._get_array_from_blob(
                    frame_blob, start, end, metadata.frame_shape
                )

                start = end

        return result

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> ResultMessage:
        t.cast(ResultMessageHeader, header)
        try:
            return cls(header["result_info"], payload)
        except KeyError as ke:
            raise ParseError from ke

    def get_extended_results(
        self,
        tps: int,
        metadata: list[dict[int, Metadata]],
        config_groups: list[dict[int, SensorConfig]],
    ) -> list[dict[int, Result]]:

        extended_frames = self._divide_frame_blob(self.frame_blob, metadata)
        extended_contexts = map_over_extended_structure(
            functools.partial(self._create_result_context, ticks_per_second=tps), metadata
        )
        extended_result_infos = [
            {
                sensor_id: result_info
                for result_info, sensor_id in zip(result_info_group, config_group.keys())
            }
            for result_info_group, config_group in zip(self.grouped_result_infos, config_groups)
        ]

        extended_results = map_over_extended_structure(
            self._create_result,
            zip3_extended_structures(extended_result_infos, extended_frames, extended_contexts),
        )

        return extended_results
