# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import typing as t

import typing_extensions as te

from acconeer.exptool._core.entities import ClientInfo


_ConfigT = t.TypeVar("_ConfigT", contravariant=True)
_MetadataT = t.TypeVar("_MetadataT", contravariant=True)
_ResultT = t.TypeVar("_ResultT", contravariant=True)
_ServerInfoT = t.TypeVar("_ServerInfoT", contravariant=True)

_RecorderT = t.TypeVar("_RecorderT")


class RecorderAttachable(te.Protocol[_RecorderT]):
    """Dependecy Inversion interface for clients"""

    def attach_recorder(self, recorder: _RecorderT) -> None: ...

    def detach_recorder(self) -> t.Optional[_RecorderT]: ...


class Recorder(te.Protocol[_ConfigT, _MetadataT, _ResultT, _ServerInfoT]):
    """The interface a Recorder needs to follow"""

    def _start(
        self,
        *,
        client_info: ClientInfo,
        server_info: _ServerInfoT,
    ) -> None: ...

    def _start_session(self, *, config: _ConfigT, metadata: _MetadataT) -> None: ...

    def _sample(self, result: _ResultT) -> None: ...

    def _stop_session(self) -> None: ...

    def close(self) -> t.Any: ...

    def __enter__(self) -> te.Self:
        return self

    def __exit__(self, *args: t.Any, **kwargs: t.Any) -> None:
        self.close()
