# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import typing as t

import typing_extensions as te

from acconeer.exptool._core.entities import ClientInfo


class RecorderAttachable[RecorderT](t.Protocol):
    """Dependecy Inversion interface for clients"""

    def attach_recorder(self, recorder: RecorderT) -> None: ...

    def detach_recorder(self) -> RecorderT | None: ...


class Recorder[ConfigT, MetadataT, ResultT, ServerInfoT](t.Protocol):
    """The interface a Recorder needs to follow"""

    def _start(
        self,
        *,
        client_info: ClientInfo,
        server_info: ServerInfoT,
    ) -> None: ...

    def _start_session(self, *, config: ConfigT, metadata: MetadataT) -> None: ...

    def _sample(self, result: ResultT) -> None: ...

    def _stop_session(self) -> None: ...

    def close(self) -> t.Any: ...

    def __enter__(self) -> te.Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
