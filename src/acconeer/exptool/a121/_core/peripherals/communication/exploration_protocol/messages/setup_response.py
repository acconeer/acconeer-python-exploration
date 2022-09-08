# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import numpy as np
import typing_extensions as te

from acconeer.exptool.a121._core.entities import Metadata
from acconeer.exptool.a121._core.mediators import AgnosticClientFriends, Message

from .parse_error import ParseError


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


@attrs.frozen
class SetupResponse(Message):
    grouped_metadatas: list[list[Metadata]]

    def apply(self, client: AgnosticClientFriends) -> None:
        if client._session_config is None:
            raise RuntimeError(f"{client} does not have a session config.")

        client._metadata = [
            {
                sensor_id: metadata
                for metadata, sensor_id in zip(metadata_group, config_group.keys())
            }
            for metadata_group, config_group in zip(
                self.grouped_metadatas, client._session_config.groups
            )
        ]

    @classmethod
    def parse(cls, header: dict[str, t.Any], payload: bytes) -> SetupResponse:
        t.cast(SetupResponseHeader, header)

        try:
            metadata_groups = header["metadata"]

            return cls(
                [
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
            )
        except KeyError as ke:
            raise ParseError from ke
