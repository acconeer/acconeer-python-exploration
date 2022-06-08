from __future__ import annotations

from typing import Optional

import attrs


@attrs.define
class Message:
    status: str
    command_name: str
    exception: Optional[Exception]
