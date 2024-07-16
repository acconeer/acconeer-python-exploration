# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import typing as t

import h5py
import numpy as np

from acconeer.exptool._core.int_16_complex import INT_16_COMPLEX
from acconeer.exptool._core.recording import h5_record
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core.entities import (
    Metadata,
    Result,
    SensorCalibration,
    ServerInfo,
    SessionConfig,
)


def get_h5py_str_dtype() -> t.Any:
    return h5py.special_dtype(vlen=str)


_H5PY_STR_DTYPE = get_h5py_str_dtype()


class H5Saver(
    h5_record.H5Saver[
        SessionConfig,  # Config type
        t.List[t.Dict[int, Metadata]],  # Metadata type
        t.List[t.Dict[int, Result]],  # Result type
        ServerInfo,  # Server info type
    ]
):
    """H5Saver for A121 data"""

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
        self,
        group: h5py.Group,
        config: SessionConfig,
        metadata: t.List[t.Dict[int, Metadata]],
        calibrations: t.Optional[t.Dict[int, SensorCalibration]] = None,
        calibrations_provided: t.Optional[t.Dict[int, bool]] = None,
        **kwargs: t.Any,
    ) -> None:
        group.create_dataset(
            "session_config",
            data=config.to_json(),
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )

        for i, metadata_group_dict in enumerate(metadata):
            group_group = group.create_group(f"group_{i}")

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
            msg = "'calibrations_provided' must be provided if 'calibrations' is provided"
            raise ValueError(msg)

        if calibrations is not None and calibrations_provided is not None:
            calibrations_group = group.create_group("calibrations")
            for sensor_id, calibration in calibrations.items():
                sensor_calibration_group = calibrations_group.create_group(f"sensor_{sensor_id}")

                calibration.to_h5(sensor_calibration_group)

                sensor_calibration_group.create_dataset(
                    "provided", data=calibrations_provided[sensor_id], track_times=False
                )

    def _sample(self, group: h5py.Group, results: t.Iterable[t.List[t.Dict[int, Result]]]) -> None:
        self._num_frames_current_session += self._write_results_to_file(
            group=group,
            start_idx=self._num_frames_current_session,
            results=list(results),
        )

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

    def _write_results_to_file(
        self, group: h5py.Group, start_idx: int, results: t.List[t.List[t.Dict[int, Result]]]
    ) -> int:
        """Saves the results to file.

        :returns: the number of extended results saved.
        """
        if len(results) == 0:
            return 0

        res: t.List[Result]
        for group_idx, entry_idx, res in utils.iterate_extended_structure_as_entry_list(
            utils.transpose_extended_structures(results)
        ):
            self._write_results(
                g=group[f"group_{group_idx}/entry_{entry_idx}/result"],
                start_index=start_idx,
                results=res,
            )

        return len(results)

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

    def _stop_session(self, group: h5py.Group) -> None:
        self._num_frames_current_session = 0
