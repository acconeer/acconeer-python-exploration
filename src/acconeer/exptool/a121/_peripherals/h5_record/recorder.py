from __future__ import annotations

import datetime
import os
from typing import Any, Optional, TypeVar, Union
from uuid import uuid4

import h5py

from acconeer.exptool.a121._entities import ClientInfo, Metadata, Result, ServerInfo, SessionConfig
from acconeer.exptool.a121._mediators import Recorder

import importlib_metadata


T = TypeVar("T")


def get_h5py_str_dtype():
    return h5py.special_dtype(vlen=str)


H5PY_STR_DTYPE = get_h5py_str_dtype()


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
        path_or_file: Union[os.PathLike, h5py.File],
        mode: str = "x",
        *,
        _lib_version: Optional[str] = None,
        _timestamp: Optional[str] = None,
        _uuid: Optional[str] = None,
    ) -> None:
        if isinstance(path_or_file, os.PathLike):
            self.path = path_or_file
            self.file = h5py.File(self.path, mode)
            self.owns_file = True
        elif isinstance(path_or_file, h5py.File):
            self.path = None
            self.file = path_or_file
            self.owns_file = False
        else:
            raise TypeError

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
            dtype=H5PY_STR_DTYPE,
            track_times=False,
        )
        self.file.create_dataset(
            "timestamp",
            data=_timestamp,
            dtype=H5PY_STR_DTYPE,
            track_times=False,
        )
        self.file.create_dataset(
            "lib_version",
            data=_lib_version,
            dtype=H5PY_STR_DTYPE,
            track_times=False,
        )

    def start(
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
            dtype=H5PY_STR_DTYPE,
            track_times=False,
        )
        self.file.create_dataset(
            "server_info",
            data=server_info.to_json(),
            dtype=H5PY_STR_DTYPE,
            track_times=False,
        )
        self.file.create_dataset(
            "session_config",
            data=session_config.to_json(),
            dtype=H5PY_STR_DTYPE,
            track_times=False,
        )

        session_group = self.file.create_group("session")

        for i, metadata_group_dict in enumerate(extended_metadata):
            group_group = session_group.create_group(f"group_{i}")

            for entry_id, (sensor_id, metadata) in enumerate(metadata_group_dict.items()):
                entry_group = group_group.create_group(f"entry_{entry_id}")
                entry_group.create_dataset("sensor_id", data=sensor_id, track_times=False)

                entry_group.create_dataset(
                    "metadata",
                    data=metadata.to_json(),
                    dtype=H5PY_STR_DTYPE,
                    track_times=False,
                )

                result_group = entry_group.create_group("result")
                self.create_result_datasets(result_group, metadata)

    def sample(self, extended_result: list[dict[int, Result]]) -> None:
        for group_index, result_group_dict in enumerate(extended_result):
            for entry_id, result in enumerate(result_group_dict.values()):
                result_group = self.file[f"session/group_{group_index}/entry_{entry_id}/result"]
                self.write_result(result_group, self._num_frames, result)

        self._num_frames += 1

    def stop(self) -> Any:
        if self.owns_file:
            self.file.close()

    @staticmethod
    def create_result_datasets(g: h5py.Group, metadata: Metadata) -> None:
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
            dtype=int,
            track_times=False,
        )

        num_sweeps = metadata.frame_data_length // metadata.sweep_data_length
        num_distances = metadata.sweep_data_length
        frame_shape = (num_sweeps, num_distances)

        frame_dtype = metadata._data_type.value

        g.create_dataset(
            "frame",
            shape=(0, *frame_shape),
            maxshape=(None, *frame_shape),
            dtype=frame_dtype,
            track_times=False,
        )

    @staticmethod
    def write_result(g: h5py.Group, index: int, result: Result) -> None:
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
