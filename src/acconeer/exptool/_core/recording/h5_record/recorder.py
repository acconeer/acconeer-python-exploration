# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import datetime
import os
import typing as t
from pathlib import Path
from uuid import uuid4

import h5py

import acconeer.exptool
from acconeer.exptool._core.entities import ClientInfo
from acconeer.exptool._core.recording import recorder
from acconeer.exptool._core.recording.h5_session_schema import SessionSchema
from acconeer.exptool.utils import get_module_version

from .saver import H5Saver
from .utils import PathOrH5File, h5_file_factory


_ConfigT = t.TypeVar("_ConfigT", contravariant=True)
_MetadataT = t.TypeVar("_MetadataT", contravariant=True)
_ResultT = t.TypeVar("_ResultT", contravariant=True)
_ServerInfoT = t.TypeVar("_ServerInfoT", contravariant=True)


def get_h5py_str_dtype() -> t.Any:
    return h5py.special_dtype(vlen=str)


_H5PY_STR_DTYPE = get_h5py_str_dtype()


def get_timestamp() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def get_uuid() -> str:
    return str(uuid4())


class H5Recorder(recorder.Recorder[_ConfigT, _MetadataT, _ResultT, _ServerInfoT]):
    """Recorder writing directly to an HDF5 file

    :param path_or_file:
        If a path-like object, by default (depending on ``mode`` below) an HDF5 file is created at
        that path. When stopping, the file is closed.

        If an ``h5py.File``, that file is used as-is. In this case, the file is not closed when
        stopping.
    :param generation:
        Sensor generation being recorded
    :param saver:
        Saver used to write results to file
    :param attachable:
        A ``Client`` that the recorder will be attached to. When a recorder is attached to a
        ``Client``, all metadata and data frames will be recorded.
    :param mode:
        The file mode to use if a path-like object was given for ``path_or_file``. Default value is
        'x', meaning that we open for exclusive creation, failing if the file already exists.
    """

    _schema = SessionSchema

    path: t.Optional[os.PathLike[t.Any]]
    """The file path, if a path-like object was given for ``path_or_file``."""
    file: h5py.File
    """The ``h5py.File``."""
    owns_file: bool
    """Whether :class:`H5Recorder` opened and owns the file, i.e., if a path-like object was given
    for ``path_or_file``. If it does, the file is closed when stopping.
    """
    _saver: H5Saver[_ConfigT, _MetadataT, _ResultT, _ServerInfoT]
    """Defining how session data should be stored in H5 session groups"""

    def __init__(
        self,
        path_or_file: PathOrH5File,
        generation: str,
        saver: H5Saver[_ConfigT, _MetadataT, _ResultT, _ServerInfoT],
        attachable: t.Optional[
            recorder.RecorderAttachable[
                recorder.Recorder[_ConfigT, _MetadataT, _ResultT, _ServerInfoT]
            ]
        ] = None,
        mode: str = "x",
        *,
        _lib_version: t.Optional[str] = None,
        _timestamp: t.Optional[str] = None,
        _uuid: t.Optional[str] = None,
    ) -> None:
        self.file, self.owns_file = h5_file_factory(path_or_file, h5_file_mode=mode)
        self.path = Path(self.file.filename) if self.owns_file else None
        self._saver = saver
        self._current_session_group: t.Optional[h5py.Group] = None

        if attachable is None:
            self._attachable = None
        else:
            self._attachable = attachable
            attachable.attach_recorder(self)

        if _lib_version is None:
            _lib_version = get_module_version(acconeer.exptool)

        if _timestamp is None:
            _timestamp = get_timestamp()

        if _uuid is None:
            _uuid = get_uuid()

        self.file.create_dataset(
            "uuid",
            data=_uuid,
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )
        self.file.create_dataset(
            "timestamp",
            data=_timestamp,
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )
        self.file.create_dataset(
            "lib_version",
            data=_lib_version,
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )
        self.file.create_dataset(
            "generation",
            data=generation,
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )

    def _start(
        self,
        *,
        client_info: ClientInfo,
        server_info: _ServerInfoT,
    ) -> None:
        if "client_info" in self.file or "server_info" in self.file:
            msg = "It's not allowed to call '_start' once."
            raise RuntimeError(msg)

        self.file.create_dataset(
            "client_info",
            data=client_info.to_json(),
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )

        self._saver._write_server_info(self.file, server_info)

        self._saver._start()

    def _start_session(self, *, config: _ConfigT, metadata: _MetadataT, **kwargs: t.Any) -> None:
        self._current_session_group = self._schema.create_next_session_group(self.file)

        self._saver._start_session(
            self._current_session_group, config=config, metadata=metadata, **kwargs
        )

    def _sample(self, result: _ResultT) -> None:
        if self._current_session_group is None:
            msg = "No session group selected yet. This should not happen."
            raise RuntimeError(msg)

        self._saver._sample(self._current_session_group, results=[result])

    def _stop_session(self) -> None:
        self._saver._stop_session(self._current_session_group)

    def close(self) -> t.Any:
        try:
            self._stop_session()

            # If the client has self as an attached recorder, make sure to detatch it.
            if self._attachable is not None:
                _ = self._attachable.detach_recorder()
        finally:
            if self.owns_file:
                self.file.close()

    def require_algo_group(self, key: str) -> h5py.Group:
        """Creates/gets the ``algo`` group with a given ``key``.

        :raises: Exception if the key does not match the file content
        """

        group = self.file.require_group("algo")

        if "key" in group:
            existing_key = bytes(group["key"][()]).decode()
            if existing_key != key:
                msg = f"Algo group key mismatch: got '{key}' but had '{existing_key}'"
                raise Exception(msg)
        else:
            group.create_dataset(
                "key",
                data=key,
                dtype=_H5PY_STR_DTYPE,
                track_times=False,
            )

        return group
