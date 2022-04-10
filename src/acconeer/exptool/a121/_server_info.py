from __future__ import annotations

import json
from typing import Any

import attrs


@attrs.frozen(kw_only=True)
class ServerInfo:
    rss_version: str = attrs.field()
    sensor_count: int = attrs.field()
    ticks_per_second: int = attrs.field()

    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ServerInfo:
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> ServerInfo:
        return cls.from_dict(json.loads(json_str))
