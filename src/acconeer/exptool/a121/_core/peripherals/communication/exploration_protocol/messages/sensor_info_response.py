# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

from acconeer.exptool.a121._core.entities import SensorInfo
from acconeer.exptool.a121._core.peripherals.communication.message import Message

from .parse_error import ParseError


class SensorInfoHeader(te.TypedDict):
    connected: bool
    serial: t.Optional[str]


@attrs.frozen
class SensorInfoResponse(Message):
    sensor_infos: t.Dict[int, SensorInfo]

    @classmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> SensorInfoResponse:
        try:
            sensor_infos: t.List[SensorInfoHeader] = header["sensor_info"]

            return cls(
                {
                    i: SensorInfo(
                        connected=sensor_info_dict["connected"],
                        serial=sensor_info_dict.get("serial", None),
                    )
                    for i, sensor_info_dict in enumerate(sensor_infos, start=1)
                }
            )
        except KeyError as ke:
            raise ParseError from ke
