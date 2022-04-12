from __future__ import annotations

from typing import Any

import attrs


@attrs.frozen(kw_only=True)
class ClientInfo:
    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d: dict) -> ClientInfo:
        raise NotImplementedError

    def to_json(self) -> str:
        raise NotImplementedError

    @classmethod
    def from_json(cls, json_str: str) -> ClientInfo:
        raise NotImplementedError
