# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import json
from typing import Any, Optional

import attrs
import packaging.version

from acconeer.exptool.a121._core.utils import parse_rss_version


@attrs.frozen(kw_only=True)
class SensorInfo:
    """Holds information about a single sensor slot on a host."""

    connected: bool
    serial: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SensorInfo:
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> SensorInfo:
        return cls.from_dict(json.loads(json_str))


@attrs.frozen(kw_only=True)
class ServerInfo:
    rss_version: str = attrs.field()
    sensor_count: int = attrs.field()
    ticks_per_second: int = attrs.field()
    sensor_infos: dict[int, SensorInfo] = attrs.field()
    hardware_name: Optional[str] = attrs.field(default=None)

    @property
    def parsed_rss_version(self) -> packaging.version.Version:
        return parse_rss_version(self.rss_version)

    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ServerInfo:
        d = d.copy()
        d["sensor_infos"] = {
            int(sensor_id): SensorInfo.from_dict(sensor_info_dict)
            for sensor_id, sensor_info_dict in d["sensor_infos"].items()
        }
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> ServerInfo:
        return cls.from_dict(json.loads(json_str))
