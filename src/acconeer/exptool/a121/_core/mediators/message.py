# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import abc
import typing as t

import typing_extensions as te

from acconeer.exptool.a121._core.entities import (
    Metadata,
    Result,
    SensorCalibration,
    SensorInfo,
    SessionConfig,
)


class SystemInfoDict(te.TypedDict):
    rss_version: str
    sensor: str
    sensor_count: int
    ticks_per_second: int
    hw: te.NotRequired[t.Optional[str]]
    max_baudrate: te.NotRequired[int]


class AgnosticClientFriends(te.Protocol):
    _session_config: t.Optional[SessionConfig]
    _session_is_started: bool
    _metadata: t.Optional[list[dict[int, Metadata]]]
    _sensor_calibrations: t.Optional[dict[int, SensorCalibration]]
    _sensor_infos: t.Dict[int, SensorInfo]
    _system_info: t.Optional[SystemInfoDict]
    _result_queue: t.List[list[dict[int, Result]]]


class Message(abc.ABC):
    @abc.abstractmethod
    def apply(self, client: AgnosticClientFriends) -> None:
        """Applies any needed changes to any of the Client friend fields."""
        pass

    @classmethod
    @abc.abstractmethod
    def parse(cls, header: t.Dict[str, t.Any], payload: bytes) -> Message:
        """Assumes that header and payload contains needed information and tries to parse.

        :param header: Message header
        :param payload: payload
        :raises Exception: whenever an error occurs (assumption doesn't hold)

        :returns: A freshly parsed Message
        """
        ...
