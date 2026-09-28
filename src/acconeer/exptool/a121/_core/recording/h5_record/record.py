# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import re
import warnings
from typing import Callable, Iterator, TypeVar

import h5py
from packaging.version import Version

import acconeer.exptool
from acconeer.exptool._core import ClientInfo
from acconeer.exptool._core.recording.h5_session_schema import SessionSchema
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core.entities import (
    Metadata,
    PersistentRecord,
    RecordException,
    Result,
    ResultContext,
    SensorCalibration,
    ServerInfo,
    SessionConfig,
    SessionRecord,
    StackedResults,
)
from acconeer.exptool.utils import get_module_version


T = TypeVar("T")

# Frames per h5 read: fewer reads, at a bounded memory cost.
_RESULT_READ_CHUNK_FRAMES = 256


class H5RecordException(RecordException):
    pass


class H5SessionRecord(SessionRecord):
    def __init__(self, group: h5py.Group, ticks_per_second: int) -> None:
        self._group = group
        self._ticks_per_second = ticks_per_second

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        return self._map_over_entries(self._get_metadata_for_entry_group)

    @property
    def extended_results(self) -> Iterator[list[dict[int, Result]]]:
        # The entries and their result contexts are the same for every frame.
        entries = self._get_entries()
        contexts = utils.map_over_extended_structure(
            self._get_result_context_for_entry_group, entries
        )
        entries_and_contexts = utils.zip_extended_structures(entries, contexts)
        num_frames = self.num_frames

        for start in range(0, num_frames, _RESULT_READ_CHUNK_FRAMES):
            frames = slice(start, min(start + _RESULT_READ_CHUNK_FRAMES, num_frames))
            chunks = utils.map_over_extended_structure(
                lambda pair: self._entry_group_to_stacked_results(*pair, frames=frames),
                entries_and_contexts,
            )
            for i in range(frames.stop - frames.start):
                yield utils.map_over_extended_structure(lambda stacked: stacked[i], chunks)

    @property
    def extended_stacked_results(self) -> list[dict[int, StackedResults]]:
        return self._map_over_entries(self._entry_group_to_stacked_results)

    @property
    def num_frames(self) -> int:
        (num_frames,) = {len(entry["result/frame"]) for _, _, entry in self._iterate_entries()}
        return num_frames

    @property
    def session_config(self) -> SessionConfig:
        return SessionConfig.from_json(self._group["session_config"][()])

    @property
    def sensor_id(self) -> int:
        """Retrieves the sole sensor id used in this session.

        A session may span multiple groups (e.g. multi-group subsweep
        configurations) while still using a single physical sensor, so this
        looks across all groups rather than requiring exactly one.

        :raises: ValueError if the session is empty or more than one distinct sensor id is used.
        """
        sensor_ids = {sensor_id for _, sensor_id, _ in self._iterate_entries()}
        (sensor_id,) = sensor_ids
        return int(sensor_id)

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

    @staticmethod
    def _get_metadata_for_entry_group(g: h5py.Group) -> Metadata:
        return Metadata.from_json(g["metadata"][()])

    def _entry_group_to_stacked_results(
        self,
        entry_group: h5py.Group,
        context: ResultContext | None = None,
        frames: slice = slice(None),
    ) -> StackedResults:
        if context is None:
            context = self._get_result_context_for_entry_group(entry_group)

        return StackedResults(
            data_saturated=entry_group["result/data_saturated"][frames],
            calibration_needed=entry_group["result/calibration_needed"][frames],
            temperature=entry_group["result/temperature"][frames],
            tick=entry_group["result/tick"][frames],
            frame_delayed=entry_group["result/frame_delayed"][frames],
            frame=entry_group["result/frame"][frames],
            context=context,
        )

    def _get_result_context_for_entry_group(self, entry_group: h5py.Group) -> ResultContext:
        return ResultContext(
            metadata=self._get_metadata_for_entry_group(entry_group),
            ticks_per_second=self._ticks_per_second,
        )

    def _get_entries(self) -> list[dict[int, h5py.Group]]:
        structure: dict[int, dict[int, h5py.Group]] = {}

        for k, v in self._group.items():
            m = re.fullmatch(r"group_(\d+)", k)

            if not m:
                continue

            group_index = int(m.group(1))
            structure[group_index] = {}

            for vv in v.values():
                sensor_id = vv["sensor_id"][()]
                structure[group_index][sensor_id] = vv

        return [structure[i] for i in range(len(structure))]

    def _iterate_entries(self) -> Iterator[tuple[int, int, h5py.Group]]:
        """Iterates over "Entry" items in this record.

        :returns: An iterable of <group_id>, <sensor_id>, <"EntryGroup">
        """
        for group_id, group_dict in enumerate(self._get_entries()):
            for sensor_id, entry_group in group_dict.items():
                yield (group_id, sensor_id, entry_group)

    def _get_calibrations_group(self) -> h5py.Group:
        if "calibrations" in self._group.keys():  # noqa: SIM118
            return self._group["calibrations"]
        msg = "No calibration in h5 file"
        raise H5RecordException(msg)

    def _iterate_calibrations(self) -> Iterator[tuple[int, h5py.Group]]:
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

    def _map_over_entries(self, func: Callable[[h5py.Group], T]) -> list[dict[int, T]]:
        return utils.map_over_extended_structure(func, self._get_entries())


class H5Record(PersistentRecord):
    _schema = SessionSchema

    file: h5py.File

    def __init__(self, file: h5py.File) -> None:
        self.file = file

        try:
            version_of_record = Version(self.lib_version)
        except KeyError:
            pass
        else:
            installed_version = Version(get_module_version(acconeer.exptool))
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
    def lib_version(self) -> str:
        return self._h5py_dataset_to_str(self.file["lib_version"])

    @property
    def server_info(self) -> ServerInfo:
        return ServerInfo.from_json(self.file["server_info"][()])

    @property
    def timestamp(self) -> str:
        return self._h5py_dataset_to_str(self.file["timestamp"])

    @property
    def uuid(self) -> str:
        return self._h5py_dataset_to_str(self.file["uuid"])

    def close(self) -> None:
        self.file.close()

    @staticmethod
    def _h5py_dataset_to_str(dataset: h5py.Dataset) -> str:
        return bytes(dataset[()]).decode()

    def get_algo_group(self, key: str) -> h5py.Group:
        group = self.file["algo"]  # Raises KeyError if the "algo" group doesn't exist

        existing_key = self._h5py_dataset_to_str(group["key"])
        if existing_key != key:
            raise KeyError

        return group

    def session(self, session_index: int) -> H5SessionRecord:
        return H5SessionRecord(
            group=self._schema.session_groups_on_disk(self.file)[session_index],
            ticks_per_second=self.server_info.ticks_per_second,
        )

    @property
    def num_sessions(self) -> int:
        return len(self._schema.session_groups_on_disk(self.file))
