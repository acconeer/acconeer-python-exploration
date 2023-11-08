# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

import h5py

from acconeer.exptool._core.recording import h5_record
from acconeer.exptool._core.recording.h5_record.utils import PathOrH5File
from acconeer.exptool._core.recording.recorder import Recorder, RecorderAttachable
from acconeer.exptool.a121._core.entities import (
    Metadata,
    Result,
    SensorCalibration,
    ServerInfo,
    SessionConfig,
)

from .saver import H5Saver


T = t.TypeVar("T")


def get_h5py_str_dtype() -> t.Any:
    return h5py.special_dtype(vlen=str)


_H5PY_STR_DTYPE = get_h5py_str_dtype()


class H5Recorder(
    h5_record.H5Recorder[
        SessionConfig,  # Config type
        t.List[t.Dict[int, Metadata]],  # Metadata type
        t.List[t.Dict[int, Result]],  # Result type
        ServerInfo,  # Server info type
    ]
):
    """Recorder writing directly to an HDF5 file

    :param path_or_file:
        If a path-like object, by default (depending on ``mode`` below) an HDF5 file is created at
        that path. When stopping, the file is closed.

        If an ``h5py.File``, that file is used as-is. In this case, the file is not closed when
        stopping.
    :param attachable:
        A ``Client`` that the recorder will be attached to. When a recorder is attached to a
        ``Client``, all metadata and data frames will be recorded.
    :param mode:
        The file mode to use if a path-like object was given for ``path_or_file``. Default value is
        'x', meaning that we open for exclusive creation, failing if the file already exists.
    :param _chunk_size:
        If given, data will be written to file every ``_chunk_size`` samples.

        If not given, data will be written at least every 512:th sample, or at least once per
        second, whichever comes first.

        Setting a small chunk size (e.g. 1) may degrade performance for high sample rates.

        Internal parameter, subject to change.
    """

    def __init__(
        self,
        path_or_file: PathOrH5File,
        attachable: t.Optional[
            RecorderAttachable[
                Recorder[
                    SessionConfig,  # Config type
                    t.List[t.Dict[int, Metadata]],  # Metadata type
                    t.List[t.Dict[int, Result]],  # Result type
                    ServerInfo,  # Server info type
                ]
            ]
        ] = None,
        mode: str = "x",
        *,
        _chunk_size: t.Optional[int] = None,
        _lib_version: t.Optional[str] = None,
        _timestamp: t.Optional[str] = None,
        _uuid: t.Optional[str] = None,
    ) -> None:
        super().__init__(
            path_or_file,
            "a121",
            h5_record.ChunkedH5Saver(H5Saver(), _chunk_size=_chunk_size),
            attachable,
            mode,
            _lib_version=_lib_version,
            _timestamp=_timestamp,
            _uuid=_uuid,
        )

    def _start_session(
        self,
        *,
        config: SessionConfig,
        metadata: t.List[t.Dict[int, Metadata]],
        calibrations: t.Optional[t.Dict[int, SensorCalibration]] = None,
        calibrations_provided: t.Optional[t.Dict[int, bool]] = None,
        **kwargs: t.Any,
    ) -> None:
        super()._start_session(
            config=config,
            metadata=metadata,
            calibrations=calibrations,
            calibrations_provided=calibrations_provided,
            **kwargs,
        )
