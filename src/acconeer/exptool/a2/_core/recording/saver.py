# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import typing as t

import h5py
import numpy as np

from acconeer.exptool._core.int_16_complex import INT_16_COMPLEX
from acconeer.exptool._core.recording import h5_record
from acconeer.exptool.a2._core.entities import (
    GroupResult,
    Metadata,
    Result,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)


def get_h5py_str_dtype() -> t.Any:
    return h5py.special_dtype(vlen=str)


_H5PY_STR_DTYPE = get_h5py_str_dtype()


class H5Saver(h5_record.H5Saver[SessionConfig, Metadata, GroupResult, ServerInfo]):
    """H5Saver for A2 data"""

    _num_frames_current_session: int

    def __init__(self) -> None:
        self._num_frames_current_session = 0

    def _start(self) -> None:
        pass

    def _write_server_info(self, group: h5py.Group, server_info: ServerInfo) -> None:
        group.create_dataset(
            "server_info",
            data=server_info.to_json(),
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )

    def _start_session(
        self, group: h5py.Group, config: SessionConfig, metadata: Metadata, **kwargs: t.Any
    ) -> None:
        group.create_dataset(
            "session_config",
            data=config.to_json(),
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )

        for i, sensor_config in enumerate(config.sensor_configs):
            group_group = group.create_group(f"group_{i}")

            group_group.create_dataset(
                "tick_period",
                data=metadata.tick_period,
                dtype=int,
                track_times=False,
            )

            result_group = group_group.create_group("result")
            self._create_result_datasets(result_group, sensor_config)

    def _sample(self, group: h5py.Group, results: t.Iterable[GroupResult]) -> None:
        self._num_frames_current_session += self._write_results_to_file(
            group=group,
            start_idx=self._num_frames_current_session,
            results=list(results),
        )

    @staticmethod
    def _create_result_datasets(g: h5py.Group, sensor_config: SensorConfig) -> None:
        g.create_dataset(
            "data_saturated",
            shape=(0, len(sensor_config.subsweeps)),
            maxshape=(None, sensor_config.MAX_NUM_SUBSWEEPS),
            dtype=bool,
            track_times=False,
            compression="gzip",
        )

        g.create_dataset(
            "measured_sweep_rate",
            shape=(0,),
            maxshape=(None,),
            dtype=np.dtype("float32"),
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
            shape=(0, *sensor_config.frame_shape),
            maxshape=(None, *sensor_config.frame_shape),
            dtype=INT_16_COMPLEX,
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
            "calibration_temperature",
            shape=(0,),
            maxshape=(None,),
            dtype=np.dtype("int64"),
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

    def _write_results_to_file(
        self, group: h5py.Group, start_idx: int, results: list[GroupResult]
    ) -> int:
        """Saves the contents of ``self.chunk_buffer`` to file.

        :returns: the number of extended results saved.
        """
        if len(results) == 0:
            return 0

        lol = [result.results for result in results]
        (length,) = {len(l) for l in lol}

        for group_idx in range(length):
            try:
                result_group = group[f"group_{group_idx}/result"]
            except Exception as e:
                print(f"group_{group_idx}")
                group.visititems(print)
                raise e

            if not isinstance(result_group, h5py.Group):
                raise RuntimeError

            self._write_results(
                g=result_group,
                start_index=start_idx,
                results=[group_result.results[group_idx] for group_result in results],
            )

        return len(results)

    @staticmethod
    def _write_results(g: h5py.Group, start_index: int, results: t.Sequence[Result]) -> None:
        """Extends the Dataset to the appropriate (new) size with .resize,
        and then copies the data over
        """
        g["data_saturated"].resize(size=start_index + len(results), axis=0)
        g["measured_sweep_rate"].resize(size=start_index + len(results), axis=0)
        g["temperature"].resize(size=start_index + len(results), axis=0)
        g["tick"].resize(size=start_index + len(results), axis=0)
        g["frame"].resize(size=start_index + len(results), axis=0)
        g["frame_delayed"].resize(size=start_index + len(results), axis=0)
        g["calibration_temperature"].resize(size=start_index + len(results), axis=0)
        g["calibration_needed"].resize(size=start_index + len(results), axis=0)

        dataset_slice = slice(start_index, start_index + len(results))

        g["data_saturated"][dataset_slice] = [result.data_saturated for result in results]
        g["measured_sweep_rate"][dataset_slice] = [
            result.measured_sweep_rate if result.measured_sweep_rate is not None else float("nan")
            for result in results
        ]
        g["temperature"][dataset_slice] = [result.temperature for result in results]
        g["tick"][dataset_slice] = [result.tick for result in results]
        g["frame"][dataset_slice] = [result.int16_complex_frame for result in results]
        g["frame_delayed"][dataset_slice] = [result.frame_delayed for result in results]
        g["calibration_temperature"][dataset_slice] = [
            result.calibration_temperature for result in results
        ]
        g["calibration_needed"][dataset_slice] = [result.calibration_needed for result in results]

    def _stop_session(self, group: h5py.Group) -> None:
        self._num_frames_current_session = 0
