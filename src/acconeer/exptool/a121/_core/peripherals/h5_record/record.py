# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import re
import warnings
from typing import Callable, Iterator, Tuple, TypeVar

import h5py
import importlib_metadata
import numpy as np
from packaging.version import Version

from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    PersistentRecord,
    RecordException,
    Result,
    ResultContext,
    SensorCalibration,
    ServerInfo,
    SessionConfig,
    StackedResults,
)


T = TypeVar("T")


class H5RecordException(RecordException):
    pass


class H5Record(PersistentRecord):
    file: h5py.File

    def __init__(self, file: h5py.File) -> None:
        self.file = file

        try:
            version_of_record = Version(self.lib_version)
        except KeyError:
            pass
        else:
            installed_version = Version(importlib_metadata.version("acconeer-exptool"))
            if installed_version < version_of_record:
                warnings.warn(
                    f"The loaded file {str(self.file.name)!r} was recorded "
                    + f"with a newer version of Exploration Tool ({version_of_record}) "
                    + f"than is installed ({installed_version})."
                )

    @property
    def client_info(self) -> ClientInfo:
        return ClientInfo.from_json(self.file["client_info"][()])

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        return self._map_over_entries(self._get_metadata_for_entry_group)

    @property
    def extended_stacked_results(self) -> list[dict[int, StackedResults]]:
        return self._map_over_entries(self._entry_group_to_stacked_results)

    def _entry_group_to_stacked_results(self, entry_group: h5py.Group) -> StackedResults:
        return StackedResults(
            data_saturated=entry_group["result/data_saturated"][()],
            calibration_needed=entry_group["result/calibration_needed"][()],
            temperature=entry_group["result/temperature"][()],
            tick=entry_group["result/tick"][()],
            frame_delayed=entry_group["result/frame_delayed"][()],
            frame=entry_group["result/frame"][()],
            context=self._get_result_context_for_entry_group(entry_group),
        )

    @property
    def extended_results(self) -> Iterator[list[dict[int, Result]]]:
        for frame_no in range(self.num_frames):
            yield self._get_result_for_all_entries(frame_no)

    def _get_result_for_all_entries(self, frame_no: int) -> list[dict[int, Result]]:
        def entry_group_to_result(entry_group: h5py.Group) -> Result:
            return Result(
                data_saturated=entry_group["result/data_saturated"][frame_no],
                frame_delayed=entry_group["result/frame_delayed"][frame_no],
                calibration_needed=entry_group["result/calibration_needed"][frame_no],
                temperature=entry_group["result/temperature"][frame_no],
                tick=entry_group["result/tick"][frame_no],
                frame=np.array(entry_group["result/frame"][frame_no]),
                context=self._get_result_context_for_entry_group(entry_group),
            )

        return self._map_over_entries(entry_group_to_result)

    def _get_result_context_for_entry_group(self, entry_group: h5py.Group) -> ResultContext:
        return ResultContext(
            metadata=self._get_metadata_for_entry_group(entry_group),
            ticks_per_second=self.server_info.ticks_per_second,
        )

    @property
    def lib_version(self) -> str:
        return self._h5py_dataset_to_str(self.file["lib_version"])

    @property
    def num_frames(self) -> int:
        (num_frames,) = {len(entry["result/frame"]) for _, _, entry in self._iterate_entries()}
        return num_frames

    @property
    def server_info(self) -> ServerInfo:
        return ServerInfo.from_json(self.file["server_info"][()])

    @property
    def session_config(self) -> SessionConfig:
        return SessionConfig.from_json(self.file["session/session_config"][()])

    @property
    def sensor_id(self) -> int:
        entry_group = utils.unextend(self._get_entries())
        return int(entry_group["sensor_id"][()])

    @property
    def timestamp(self) -> str:
        return self._h5py_dataset_to_str(self.file["timestamp"])

    @property
    def uuid(self) -> str:
        return self._h5py_dataset_to_str(self.file["uuid"])

    def close(self) -> None:
        self.file.close()

    def _get_entries(self) -> list[dict[int, h5py.Group]]:
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

    def _map_over_entries(self, func: Callable[[h5py.Group], T]) -> list[dict[int, T]]:
        return utils.map_over_extended_structure(func, self._get_entries())

    def _iterate_entries(self) -> Iterator[Tuple[int, int, h5py.Group]]:
        """Iterates over "Entry" items in this record.

        :returns: An iterable of <group_id>, <sensor_id>, <"EntryGroup">
        """
        for group_id, group_dict in enumerate(self._get_entries()):
            for sensor_id, entry_group in group_dict.items():
                yield (group_id, sensor_id, entry_group)

    @staticmethod
    def _get_metadata_for_entry_group(g: h5py.Group) -> Metadata:
        return Metadata.from_json(g["metadata"][()])

    @staticmethod
    def _h5py_dataset_to_str(dataset: h5py.Dataset) -> str:
        return bytes(dataset[()]).decode()

    def get_algo_group(self, key: str) -> h5py.Group:
        group = self.file["algo"]  # Raises KeyError if the "algo" group doesn't exist

        existing_key = self._h5py_dataset_to_str(group["key"])
        if existing_key != key:
            raise KeyError

        return group

    def _get_calibrations_group(self) -> h5py.Group:
        session_group = self.file["session"]

        if "calibrations" in session_group.keys():
            return session_group["calibrations"]
        raise H5RecordException("No calibration in h5 file")

    def _iterate_calibrations(self) -> Iterator[Tuple[int, h5py.Group]]:
        """Iterates over "Calibration" items in this record.

        :returns: An iterable of <sensor_id>, <"CalibrationGroup">
        """
        calibrations_group = self._get_calibrations_group()
        for sensor_group_name, group in calibrations_group.items():
            m = re.fullmatch(r"sensor_(\d+)", sensor_group_name)

            if not m:
                continue

            sensor_id = int(m.group(1))
            yield (sensor_id, group)

    @property
    def calibrations(self) -> dict[int, SensorCalibration]:
        sensor_calibrations_dict = {}
        for sensor_id, group in self._iterate_calibrations():
            sensor_calibrations_dict[sensor_id] = SensorCalibration.from_h5(group)

        return sensor_calibrations_dict

    @property
    def calibrations_provided(self) -> dict[int, bool]:
        calibrations_provided = {}
        for sensor_id, group in self._iterate_calibrations():
            calibrations_provided[sensor_id] = group["provided"][()] > 0

        return calibrations_provided
