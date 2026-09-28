# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import itertools
import typing as t
import warnings

import attrs
import h5py
import numpy as np
import typing_extensions as te
from packaging.version import Version

import acconeer.exptool
from acconeer.exptool._core.entities import ClientInfo
from acconeer.exptool._core.int_16_complex import int16_complex_array_to_complex
from acconeer.exptool._core.recording import SessionSchema
from acconeer.exptool.a2._core.entities import (
    GroupResult,
    Metadata,
    Result,
    ServerInfo,
    SessionConfig,
    server_info_timeline,
)
from acconeer.exptool.a2._core.rx_major_frame_translation import translate_rx_major_frame
from acconeer.exptool.utils import get_module_version


_T = t.TypeVar("_T")

_TOO_MANY_SESSIONS_ERROR_FORMAT = (
    "This Record contains too many sessions to use accessor "
    '"{0}". Access a specific "{0}" with ".session(x).{0}"'
)


class H5RecordException:
    pass


@attrs.frozen
class H5SessionRecord:
    _group: h5py.Group
    _chunk_size: int
    _lib_version: str

    @property
    def group_results(self) -> t.Iterator[GroupResult]:
        for chunk_start_index in range(0, self.num_frames, self._chunk_size):
            chunk_slice = slice(chunk_start_index, chunk_start_index + self._chunk_size)
            frames = []
            data_saturateds = []
            sweep_rates = []
            ticks = []
            temperatures = []
            frame_delayeds = []
            calibration_temperatures = []
            calibration_neededs = []

            for group_index in itertools.count(0):
                group_name = f"group_{group_index}"
                if group_name not in self._group:
                    break

                frames.append(
                    int16_complex_array_to_complex(
                        self._group[f"{group_name}/result/frame"][chunk_slice]
                    )
                )
                ticks.append(
                    [int(x) for x in self._group[f"{group_name}/result/tick"][chunk_slice]]
                )

                try:
                    data_saturateds.append(
                        self._group[f"{group_name}/result/data_saturated"][chunk_slice]
                    )
                except KeyError:
                    data_saturateds.append(None)

                try:
                    sweep_rates.append(
                        self._group[f"{group_name}/result/measured_sweep_rate"][chunk_slice]
                    )
                except KeyError:
                    sweep_rates.append(None)

                temperatures.append(self._group[f"{group_name}/result/temperature"][chunk_slice])

                try:
                    frame_delayeds.append(
                        self._group[f"{group_name}/result/frame_delayed"][chunk_slice]
                    )
                except KeyError:
                    frame_delayeds.append(None)

                try:
                    calibration_temperatures.append(
                        self._group[f"{group_name}/result/calibration_temperature"][chunk_slice]
                    )
                except KeyError:
                    calibration_temperatures.append(None)

                try:
                    calibration_neededs.append(
                        self._group[f"{group_name}/result/calibration_needed"][chunk_slice]
                    )
                except KeyError:
                    calibration_neededs.append(None)

            for chunk_index in range(self._chunk_size):
                try:
                    results = [
                        Result(
                            temperature=temperature[chunk_index],
                            frame=(
                                translate_rx_major_frame(frame[chunk_index], sensor_config)
                                if self._is_older_than(Version("7.8.2.dev102"))
                                else frame[chunk_index]
                            ),
                            tick=tick[chunk_index],
                            data_saturated=(
                                [bool(x) for x in data_saturated[chunk_index]]
                                if data_saturated is not None
                                else [False] * len(sensor_config.subsweeps)
                            ),
                            measured_sweep_rate=(
                                sweep_rate[chunk_index]
                                if (
                                    sweep_rate is not None
                                    and not np.isnan(sweep_rate[chunk_index])
                                )
                                else None
                            ),
                            frame_delayed=(
                                False if frame_delayed is None else frame_delayed[chunk_index]
                            ),
                            calibration_temperature=(
                                25
                                if calibration_temperature is None
                                else calibration_temperature[chunk_index]
                            ),
                            calibration_needed=(
                                False
                                if calibration_needed is None
                                else calibration_needed[chunk_index]
                            ),
                        )
                        for (
                            sensor_config,
                            data_saturated,
                            sweep_rate,
                            temperature,
                            frame,
                            tick,
                            frame_delayed,
                            calibration_temperature,
                            calibration_needed,
                        ) in zip(
                            self.session_config.sensor_configs,
                            data_saturateds,
                            sweep_rates,
                            temperatures,
                            frames,
                            ticks,
                            frame_delayeds,
                            calibration_temperatures,
                            calibration_neededs,
                        )
                    ]
                    yield GroupResult(results=results)
                except IndexError:
                    return

    def _is_older_than(self, version: Version) -> bool:
        return Version(self._lib_version) < version

    @property
    def results(self) -> t.Iterator[Result]:
        for group_results in self.group_results:
            yield group_results.result

    @property
    def num_frames(self) -> int:
        # assumes all groups have the same number of frames.
        return int(self._group["group_0/result/frame"].shape[0])

    @property
    def session_config(self) -> SessionConfig:
        return SessionConfig.from_json(self._group["session_config"][()])

    @property
    def tick_period(self) -> int:
        # assumes all groups have the same tick_period.
        return int(self._group["group_0/tick_period"][()])

    @property
    def metadata(self) -> Metadata:
        tick_period = self.tick_period
        return Metadata(tick_period=tick_period, sensor_calibration=None, update_period=None)

    def __eq__(self, other: t.Any) -> bool:
        if not isinstance(other, H5SessionRecord):
            return False

        return (
            self.session_config,
            self.tick_period,
            list(self.group_results),
        ) == (
            other.session_config,
            other.tick_period,
            list(other.group_results),
        )


@attrs.frozen
class H5Record:
    file: h5py.File

    _chunk_size: int = 100
    _schema: te.ClassVar[type[SessionSchema]] = SessionSchema

    def __attrs_post_init__(self) -> None:
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
        return server_info_timeline.migrate(self._h5py_dataset_to_str(self.file["server_info"]))

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

    def require_algo_group(self, key: str) -> h5py.Group:
        group = self.file["algo"]  # Raises KeyError if the "algo" group doesn't exist

        existing_key = self._h5py_dataset_to_str(group["key"])
        if existing_key != key:
            raise KeyError

        return group

    def session(self, session_index: int) -> H5SessionRecord:
        return H5SessionRecord(
            group=self._schema.session_groups_on_disk(self.file)[session_index],
            chunk_size=self._chunk_size,
            lib_version=self.lib_version,
        )

    @property
    def num_sessions(self) -> int:
        return len(self._schema.session_groups_on_disk(self.file))

    @property
    def _sole_session(self) -> H5SessionRecord:
        if self.num_sessions > 1:
            raise AttributeError(_TOO_MANY_SESSIONS_ERROR_FORMAT.format("_sole_session"))

        return self.session(0)

    @property
    def group_results(self) -> t.Iterator[GroupResult]:
        return self._sole_session.group_results

    @property
    def results(self) -> t.Iterator[Result]:
        return self._sole_session.results

    @property
    def num_frames(self) -> int:
        return self._sole_session.num_frames

    @property
    def session_config(self) -> SessionConfig:
        return self._sole_session.session_config

    def __eq__(self, other: t.Any) -> bool:
        if not isinstance(other, H5Record):
            return False

        # UUID is not part of equality comparison.
        return (
            self.client_info,
            self.lib_version,
            self.server_info,
            self.timestamp,
            [self.session(session_idx) for session_idx in range(self.num_sessions)],
        ) == (
            other.client_info,
            other.lib_version,
            other.server_info,
            other.timestamp,
            [other.session(session_idx) for session_idx in range(other.num_sessions)],
        )

    def __enter__(self) -> te.Self:
        return self

    def __exit__(self, *_: t.Any) -> None:
        self.close()
