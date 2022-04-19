from __future__ import annotations

import re
from typing import Callable, Iterable, TypeVar

import h5py

from acconeer.exptool.a121._entities import (
    ClientInfo,
    Metadata,
    PersistentRecord,
    Result,
    ServerInfo,
    SessionConfig,
)


T = TypeVar("T")


class H5Record(PersistentRecord):
    file: h5py.File

    def __init__(self, file: h5py.File) -> None:
        self.file = file

    @property
    def client_info(self) -> ClientInfo:
        return ClientInfo.from_json(self.file["client_info"][()])

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        return self._map_over_session_structure(self._get_metadata_for_entry_group)

    @property
    def extended_results(self) -> Iterable[list[dict[int, Result]]]:
        raise NotImplementedError

    @property
    def lib_version(self) -> str:
        return self._h5py_dataset_to_str(self.file["lib_version"])

    @property
    def num_frames(self) -> int:
        raise NotImplementedError

    @property
    def server_info(self) -> ServerInfo:
        return ServerInfo.from_json(self.file["server_info"][()])

    @property
    def session_config(self) -> SessionConfig:
        return SessionConfig.from_json(self.file["session_config"][()])

    @property
    def timestamp(self) -> str:
        return self._h5py_dataset_to_str(self.file["timestamp"])

    @property
    def uuid(self) -> str:
        return self._h5py_dataset_to_str(self.file["uuid"])

    def close(self) -> None:
        self.file.close()

    def _get_session_structure(self) -> list[dict[int, h5py.Group]]:
        structure: dict[int, dict[int, h5py.Group]] = {}

        for k, v in self.file["session"].items():
            m = re.fullmatch(r"group_(\d+)", k)

            if not m:
                continue

            group_index = int(m.group(1))
            structure[group_index] = {}

            for vv in v.values():
                sensor_id = vv["sensor_id"][()]
                structure[group_index][sensor_id] = vv

        return [structure[i] for i in range(len(structure))]

    def _map_over_session_structure(self, func: Callable[[h5py.Group], T]) -> list[dict[int, T]]:
        structure = self._get_session_structure()
        return [{k: func(v) for k, v in d.items()} for d in structure]

    @staticmethod
    def _get_metadata_for_entry_group(g: h5py.Group) -> Metadata:
        return Metadata.from_json(g["server_info"][()])

    @staticmethod
    def _h5py_dataset_to_str(dataset: h5py.Dataset) -> str:
        return bytes(dataset[()]).decode()
