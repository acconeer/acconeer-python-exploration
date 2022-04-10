from __future__ import annotations

from typing import Any

import attrs


@attrs.frozen(kw_only=True)
class ServerInfo:
    rss_version: str = attrs.field()
    sensor_count: int = attrs.field()
    ticks_per_second: int = attrs.field()

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d: dict) -> ServerInfo:
        raise NotImplementedError

    def to_json(self) -> str:
        raise NotImplementedError

    @classmethod
    def from_json(cls, json_str: str) -> ServerInfo:
        raise NotImplementedError
