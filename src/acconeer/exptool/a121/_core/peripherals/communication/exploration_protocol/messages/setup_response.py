# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import numpy as np
import typing_extensions as te

from acconeer.exptool.a121._core.entities import Metadata, SensorCalibration
from acconeer.exptool.a121._core.peripherals.communication.message import Message

from .parse_error import ParseError


class SensorCalibrationDict(te.TypedDict):
    temperature: int
    data: str


class MetadataDict(te.TypedDict):
    frame_data_length: int
    sweep_data_length: int
    subsweep_data_offset: list[int]
    subsweep_data_length: list[int]
    calibration_temperature: int
    base_step_length_m: float
    max_sweep_rate: float


class SetupResponseHeader(te.TypedDict):
    tick_period: int
    metadata: list[list[MetadataDict]]
    sensor_calibrations: t.Optional[dict[int, SensorCalibrationDict]]


@attrs.frozen
class SetupResponse(Message):
    grouped_metadatas: list[list[Metadata]]
    sensor_calibrations: t.Optional[dict[int, SensorCalibration]]

    @classmethod
    def parse(cls, header: dict[str, t.Any], payload: bytes) -> SetupResponse:
        t.cast(SetupResponseHeader, header)

        try:
            metadata_groups = header["metadata"]
            calibration_info_list = header.get("calibration_info")

            metadata = [
                [
                    Metadata(
                        frame_data_length=metadata_dict["frame_data_length"],
                        sweep_data_length=metadata_dict["sweep_data_length"],
                        subsweep_data_offset=np.array(metadata_dict["subsweep_data_offset"]),
                        subsweep_data_length=np.array(metadata_dict["subsweep_data_length"]),
                        calibration_temperature=metadata_dict["calibration_temperature"],
                        base_step_length_m=metadata_dict["base_step_length_m"],
                        max_sweep_rate=metadata_dict["max_sweep_rate"],
                        tick_period=header["tick_period"],
                    )
                    for metadata_dict in metadata_group
                ]
                for metadata_group in metadata_groups
            ]

            sensor_calibrations = None
            if calibration_info_list:
                sensor_calibrations = {
                    calibration_info_dict["sensor_id"]: SensorCalibration(
                        temperature=calibration_info_dict["temperature"],
                        data=calibration_info_dict["data"],
                    )
                    for calibration_info_dict in calibration_info_list
                }
            return cls(metadata, sensor_calibrations)

        except KeyError as ke:
            raise ParseError from ke
