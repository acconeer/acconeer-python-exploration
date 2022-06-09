from __future__ import annotations

from typing import Optional, Union

import attrs

from acconeer.exptool import a121


@attrs.define
class CoreStore:
    server_info: Optional[a121.ServerInfo] = None
    metadata: Optional[Union[a121.Metadata, list[dict[int, a121.Metadata]]]] = None
    session_config: Optional[a121.SessionConfig] = None
