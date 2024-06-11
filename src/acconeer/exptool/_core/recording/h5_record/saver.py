# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import typing as t
from time import time

import h5py
import typing_extensions as te


_ConfigT = t.TypeVar("_ConfigT", contravariant=True)
_MetadataT = t.TypeVar("_MetadataT", contravariant=True)
_ResultT = t.TypeVar("_ResultT", contravariant=True)
_ServerInfoT = t.TypeVar("_ServerInfoT", contravariant=True)


class H5Saver(te.Protocol[_ConfigT, _MetadataT, _ResultT, _ServerInfoT]):
    """Interface for savers handling writing results to file"""

    def _start(self) -> None: ...

    def _write_server_info(self, group: h5py.Group, server_info: _ServerInfoT) -> None: ...

    def _start_session(
        self, group: h5py.Group, *, config: _ConfigT, metadata: _MetadataT, **kwargs: t.Any
    ) -> None: ...

    def _sample(self, group: h5py.Group, results: t.Iterable[_ResultT]) -> None: ...

    def _stop_session(self, group: h5py.Group) -> None: ...


class ChunkedH5Saver(H5Saver[_ConfigT, _MetadataT, _ResultT, _ServerInfoT]):
    """Chunks result before writing to file to decrease file system access

    :param saver:
        Saver used to write results to file
    :param _chunk_size:
        If given, data will be written to file every ``_chunk_size`` samples.

        If not given, data will be written at least every 512:th sample, or at least once per
        second, whichever comes first.

        Setting a small chunk size (e.g. 1) may degrade performance for high sample rates.

        Internal parameter, subject to change.
    """

    _AUTO_CHUNK_MAX_SIZE = 512
    _AUTO_CHUNK_MAX_TIME = 1.0

    _saver: H5Saver[_ConfigT, _MetadataT, _ResultT, _ServerInfoT]
    _chunk_size: t.Optional[int]
    _chunk_buffer: list[_ResultT]
    _last_write_time: float

    def __init__(
        self,
        saver: H5Saver[_ConfigT, _MetadataT, _ResultT, _ServerInfoT],
        _chunk_size: t.Optional[int] = None,
    ) -> None:
        self._saver = saver
        self._chunk_size = _chunk_size
        self._chunk_buffer = []
        self._last_write_time = 0.0

    def _start(self) -> None:
        self._saver._start()
        self._last_write_time = time()

    def _write_server_info(self, group: h5py.Group, server_info: _ServerInfoT) -> None:
        self._saver._write_server_info(group, server_info)

    def _start_session(
        self, group: h5py.Group, *, config: _ConfigT, metadata: _MetadataT, **kwargs: t.Any
    ) -> None:
        self._saver._start_session(group, config=config, metadata=metadata, **kwargs)
        self._last_write_time = time()

    def _sample(self, group: h5py.Group, results: t.Iterable[_ResultT]) -> None:
        for result in results:
            self._chunk_buffer.append(result)

        if self._chunk_size is None:
            reached_size_limit = len(self._chunk_buffer) >= self._AUTO_CHUNK_MAX_SIZE
            reached_time_limit = (time() - self._last_write_time) >= self._AUTO_CHUNK_MAX_TIME
            write = reached_size_limit or reached_time_limit
        else:
            write = len(self._chunk_buffer) == self._chunk_size

        if write:
            self._saver._sample(group, self._chunk_buffer)
            self._chunk_buffer = []
            self._last_write_time = time()

    def _stop_session(self, group: h5py.Group) -> None:
        if len(self._chunk_buffer) > 0:
            self._saver._sample(group, self._chunk_buffer)
            self._chunk_buffer = []
        self._saver._stop_session(group)
