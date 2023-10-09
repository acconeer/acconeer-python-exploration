# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import datetime
import os
from pathlib import Path
from time import time
from typing import Any, Optional, TypeVar
from uuid import uuid4

import h5py
import numpy as np

import acconeer.exptool
from acconeer.exptool._core import ClientInfo
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core.entities import (
    INT_16_COMPLEX,
    Metadata,
    Result,
    SensorCalibration,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.recording.recorder import Recorder, RecorderAttachable
from acconeer.exptool.utils import get_module_version

from .session_schema import SessionSchema
from .utils import PathOrH5File, h5_file_factory


T = TypeVar("T")


def get_h5py_str_dtype() -> Any:
    return h5py.special_dtype(vlen=str)


_H5PY_STR_DTYPE = get_h5py_str_dtype()


def get_timestamp() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def get_uuid() -> str:
    return str(uuid4())


class H5Recorder(Recorder):
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

    _AUTO_CHUNK_MAX_SIZE = 512
    _AUTO_CHUNK_MAX_TIME = 1.0
    _schema = SessionSchema

    path: Optional[os.PathLike[Any]]
    """The file path, if a path-like object was given for ``path_or_file``."""
    file: h5py.File
    """The ``h5py.File``."""
    owns_file: bool
    """Whether :class:`H5Recorder` opened and owns the file, i.e., if a path-like object was given
    for ``path_or_file``. If it does, the file is closed when stopping.
    """
    _num_frames_current_session: int
    _chunk_size: Optional[int]
    _chunk_buffer: list[list[dict[int, Result]]]
    _last_write_time: float

    def __init__(
        self,
        path_or_file: PathOrH5File,
        attachable: Optional[RecorderAttachable] = None,
        mode: str = "x",
        *,
        _chunk_size: Optional[int] = None,
        _lib_version: Optional[str] = None,
        _timestamp: Optional[str] = None,
        _uuid: Optional[str] = None,
    ) -> None:
        self.file, self.owns_file = h5_file_factory(path_or_file, h5_file_mode=mode)
        self.path = Path(self.file.filename) if self.owns_file else None
        self._chunk_size = _chunk_size
        self._chunk_buffer = []
        self._num_frames_current_session = 0
        self._last_write_time = 0.0
        self._current_session_group: Optional[h5py.Group] = None

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
            data="a121",
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )

    def _start(
        self,
        *,
        client_info: ClientInfo,
        server_info: ServerInfo,
    ) -> None:
        if "client_info" in self.file or "server_info" in self.file:
            raise RuntimeError("It's not allowed to call '_start' once.")

        self.file.create_dataset(
            "client_info",
            data=client_info.to_json(),
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )
        self.file.create_dataset(
            "server_info",
            data=server_info.to_json(),
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )
        self._last_write_time = time()

    def _start_session(
        self,
        *,
        config: SessionConfig,
        metadata: list[dict[int, Metadata]],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
        calibrations_provided: Optional[dict[int, bool]] = None,
    ) -> None:
        self._current_session_group = self._schema.create_next_session_group(self.file)

        self._current_session_group.create_dataset(
            "session_config",
            data=config.to_json(),
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )

        for i, metadata_group_dict in enumerate(metadata):
            group_group = self._current_session_group.create_group(f"group_{i}")

            for entry_id, (sensor_id, single_metadata) in enumerate(metadata_group_dict.items()):
                entry_group = group_group.create_group(f"entry_{entry_id}")
                entry_group.create_dataset("sensor_id", data=sensor_id, track_times=False)

                entry_group.create_dataset(
                    "metadata",
                    data=single_metadata.to_json(),
                    dtype=_H5PY_STR_DTYPE,
                    track_times=False,
                )

                result_group = entry_group.create_group("result")
                self._create_result_datasets(result_group, single_metadata)

        if (calibrations is None) != (calibrations_provided is None):
            raise ValueError(
                "'calibrations_provided' must be provided if 'calibrations' is provided"
            )

        if calibrations is not None and calibrations_provided is not None:
            calibrations_group = self._current_session_group.create_group("calibrations")
            for sensor_id, calibration in calibrations.items():
                sensor_calibration_group = calibrations_group.create_group(f"sensor_{sensor_id}")

                calibration.to_h5(sensor_calibration_group)

                sensor_calibration_group.create_dataset(
                    "provided", data=calibrations_provided[sensor_id], track_times=False
                )

        self._last_write_time = time()

    def _write_chunk_buffer_to_file(self, start_idx: int) -> int:
        """Saves the contents of ``self.chunk_buffer`` to file.

        :returns: the number of extended results saved.
        """
        if len(self._chunk_buffer) == 0:
            return 0

        if self._current_session_group is None:
            raise RuntimeError("No session group selected yet. This should not happen.")

        for group_idx, entry_idx, results in utils.iterate_extended_structure_as_entry_list(
            utils.transpose_extended_structures(self._chunk_buffer)
        ):
            self._write_results(
                g=self._current_session_group[f"group_{group_idx}/entry_{entry_idx}/result"],
                start_index=start_idx,
                results=results,
            )

        return len(self._chunk_buffer)

    def _sample(self, extended_result: list[dict[int, Result]]) -> None:
        self._chunk_buffer.append(extended_result)

        if self._chunk_size is None:
            reached_size_limit = len(self._chunk_buffer) >= self._AUTO_CHUNK_MAX_SIZE
            reached_time_limit = (time() - self._last_write_time) >= self._AUTO_CHUNK_MAX_TIME
            write = reached_size_limit or reached_time_limit
        else:
            write = len(self._chunk_buffer) == self._chunk_size

        if write:
            self._num_frames_current_session += self._write_chunk_buffer_to_file(
                start_idx=self._num_frames_current_session
            )
            self._chunk_buffer = []
            self._last_write_time = time()

    def _stop_session(self) -> None:
        if len(self._chunk_buffer) > 0:
            _ = self._write_chunk_buffer_to_file(start_idx=self._num_frames_current_session)
            self._chunk_buffer = []
        self._num_frames_current_session = 0

    def close(self) -> Any:
        try:
            self._stop_session()

            # If the client has self as an attached recorder, make sure to detatch it.
            if self._attachable is not None:
                _ = self._attachable.detach_recorder()
        finally:
            if self.owns_file:
                self.file.close()

    @staticmethod
    def _create_result_datasets(g: h5py.Group, metadata: Metadata) -> None:
        g.create_dataset(
            "data_saturated",
            shape=(0,),
            maxshape=(None,),
            dtype=bool,
            track_times=False,
            compression="gzip",
        )
        g.create_dataset(
            "frame_delayed",
            shape=(0,),
            maxshape=(None,),
            dtype=bool,
            track_times=False,
            compression="gzip",
        )
        g.create_dataset(
            "calibration_needed",
            shape=(0,),
            maxshape=(None,),
            dtype=bool,
            track_times=False,
            compression="gzip",
        )
        g.create_dataset(
            "temperature",
            shape=(0,),
            maxshape=(None,),
            dtype=int,
            track_times=False,
            compression="gzip",
        )

        g.create_dataset(
            "tick",
            shape=(0,),
            maxshape=(None,),
            dtype=np.dtype("int64"),
            track_times=False,
            compression="gzip",
        )

        g.create_dataset(
            "frame",
            shape=(0, *metadata.frame_shape),
            maxshape=(None, *metadata.frame_shape),
            dtype=INT_16_COMPLEX,
            track_times=False,
            compression="gzip",
        )

    @staticmethod
    def _write_results(g: h5py.Group, start_index: int, results: list[Result]) -> None:
        """Extends the Dataset to the appropriate (new) size with .resize,
        and then copies the data over
        """
        datasets_to_extend = [
            "data_saturated",
            "frame_delayed",
            "calibration_needed",
            "temperature",
            "tick",
            "frame",
        ]
        for dataset_name in datasets_to_extend:
            g[dataset_name].resize(size=start_index + len(results), axis=0)

        dataset_slice = slice(start_index, start_index + len(results))

        g["data_saturated"][dataset_slice] = [result.data_saturated for result in results]
        g["frame_delayed"][dataset_slice] = [result.frame_delayed for result in results]
        g["calibration_needed"][dataset_slice] = [result.calibration_needed for result in results]
        g["temperature"][dataset_slice] = [result.temperature for result in results]
        g["tick"][dataset_slice] = [result.tick for result in results]
        g["frame"][dataset_slice] = [result._frame for result in results]

    def require_algo_group(self, key: str) -> h5py.Group:
        """Creates/gets the ``algo`` group with a given ``key``.

        :raises: Exception if the key does not match the file content
        """

        group = self.file.require_group("algo")

        if "key" in group:
            existing_key = bytes(group["key"][()]).decode()
            if existing_key != key:
                raise Exception(f"Algo group key mismatch: got '{key}' but had '{existing_key}'")
        else:
            group.create_dataset(
                "key",
                data=key,
                dtype=_H5PY_STR_DTYPE,
                track_times=False,
            )

        return group
