# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any, Optional, TypeVar
from uuid import uuid4

import h5py
import importlib_metadata
import numpy as np

from acconeer.exptool.a121._core.entities import (
    INT_16_COMPLEX,
    ClientInfo,
    Metadata,
    Result,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.mediators import Recorder

from .utils import PathOrH5File, h5_file_factory


T = TypeVar("T")


def get_h5py_str_dtype():
    return h5py.special_dtype(vlen=str)


_H5PY_STR_DTYPE = get_h5py_str_dtype()


def get_timestamp() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def get_uuid() -> str:
    return str(uuid4())


class H5Recorder(Recorder):
    path: Optional[os.PathLike]
    file: h5py.File
    owns_file: bool
    _num_frames: int

    def __init__(
        self,
        path_or_file: PathOrH5File,
        mode: str = "x",
        *,
        _lib_version: Optional[str] = None,
        _timestamp: Optional[str] = None,
        _uuid: Optional[str] = None,
    ) -> None:
        self.file, self.owns_file = h5_file_factory(path_or_file, h5_file_mode=mode)
        self.path = Path(self.file.filename) if self.owns_file else None

        if _lib_version is None:
            _lib_version = importlib_metadata.version("acconeer-exptool")

        if _timestamp is None:
            _timestamp = get_timestamp()

        if _uuid is None:
            _uuid = get_uuid()

        self._num_frames = 0

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
        extended_metadata: list[dict[int, Metadata]],
        server_info: ServerInfo,
        session_config: SessionConfig,
    ) -> None:
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

        session_group = self.file.create_group("session")

        session_group.create_dataset(
            "session_config",
            data=session_config.to_json(),
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )

        for i, metadata_group_dict in enumerate(extended_metadata):
            group_group = session_group.create_group(f"group_{i}")

            for entry_id, (sensor_id, metadata) in enumerate(metadata_group_dict.items()):
                entry_group = group_group.create_group(f"entry_{entry_id}")
                entry_group.create_dataset("sensor_id", data=sensor_id, track_times=False)

                entry_group.create_dataset(
                    "metadata",
                    data=metadata.to_json(),
                    dtype=_H5PY_STR_DTYPE,
                    track_times=False,
                )

                result_group = entry_group.create_group("result")
                self._create_result_datasets(result_group, metadata)

    def _sample(self, extended_result: list[dict[int, Result]]) -> None:
        for group_index, result_group_dict in enumerate(extended_result):
            for entry_id, result in enumerate(result_group_dict.values()):
                result_group = self.file[f"session/group_{group_index}/entry_{entry_id}/result"]
                self._write_result(result_group, self._num_frames, result)

        self._num_frames += 1

    def _stop(self) -> Any:
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
        )
        g.create_dataset(
            "frame_delayed",
            shape=(0,),
            maxshape=(None,),
            dtype=bool,
            track_times=False,
        )
        g.create_dataset(
            "calibration_needed",
            shape=(0,),
            maxshape=(None,),
            dtype=bool,
            track_times=False,
        )
        g.create_dataset(
            "temperature",
            shape=(0,),
            maxshape=(None,),
            dtype=int,
            track_times=False,
        )

        g.create_dataset(
            "tick",
            shape=(0,),
            maxshape=(None,),
            dtype=np.dtype("int64"),
            track_times=False,
        )

        g.create_dataset(
            "frame",
            shape=(0, *metadata.frame_shape),
            maxshape=(None, *metadata.frame_shape),
            dtype=INT_16_COMPLEX,
            track_times=False,
        )

    @staticmethod
    def _write_result(g: h5py.Group, index: int, result: Result) -> None:
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
            g[dataset_name].resize(size=index + 1, axis=0)

        g["data_saturated"][index] = result.data_saturated
        g["frame_delayed"][index] = result.frame_delayed
        g["calibration_needed"][index] = result.calibration_needed
        g["temperature"][index] = result.temperature
        g["tick"][index] = result.tick
        g["frame"][index] = result._frame

    def require_algo_group(self, key: str) -> h5py.Group:
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
