# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

from acconeer.exptool.a121._core.entities import SensorInfo
from acconeer.exptool.a121._core.mediators import AgnosticClientFriends, Message

from .parse_error import ParseError


class SensorInfoHeader(te.TypedDict):
    connected: bool
    serial: t.Optional[str]


@attrs.frozen
class SensorInfoResponse(Message):
    sensor_infos: t.Dict[int, SensorInfo]

    def apply(self, client: AgnosticClientFriends) -> None:
        if client._sensor_infos == {}:
            client._sensor_infos = self.sensor_infos
        else:
            raise RuntimeError(f"{client} already has sensor infos")

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
