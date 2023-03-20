# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, cast
from uuid import uuid4

import h5py
import numpy as np
import numpy.typing as npt
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities import INT_16_COMPLEX, SensorInfo
from acconeer.exptool.a121._core.peripherals.h5_record import _H5PY_STR_DTYPE


@pytest.fixture
def tmp_file_path(tmp_path: Path) -> Path:
    return tmp_path / str(uuid4())


@pytest.fixture
def ref_lib_version() -> str:
    return "0.1.2"


@pytest.fixture
def ref_timestamp() -> str:
    return "2022-03-14T15:00:00"


@pytest.fixture
def ref_uuid() -> str:
    return "b0ca48f7-0bcf-4160-965a-9a865a8fc989"


@pytest.fixture
def ref_server_info() -> a121.ServerInfo:
    return a121.ServerInfo(
        rss_version="0.2.4",
        sensor_count=3,
        ticks_per_second=100,
        sensor_infos={
            1: SensorInfo(connected=True),
            2: SensorInfo(connected=True),
            3: SensorInfo(connected=True),
        },
        hardware_name="xy123",
    )


@pytest.fixture
def ref_client_info() -> a121.ClientInfo:
    return a121.ClientInfo(
        ip_address="address",
        serial_port="serial_port",
        override_baudrate=0,
    )


@pytest.fixture
def ref_session_config() -> a121.SessionConfig:
    return a121.SessionConfig(a121.SensorConfig())


@pytest.fixture(
    params=[
        [{1}],
        [{2, 3}, {2}],
        [{1, 2}, {3, 4}, {1, 2, 3, 4, 5}],
    ]
)
def ref_structure(request: pytest.FixtureRequest) -> Iterator[Iterator[int]]:
    return cast(Iterator[Iterator[int]], request.param)


@pytest.fixture(params=range(1, 4, 2))
def ref_num_frames(request: pytest.FixtureRequest) -> int:
    """This is a parametrized fixture.
    Dependent fixtures will also be parameterized as a result
    """
    return cast(int, request.param)


@pytest.fixture(params=range(1, 4, 2))
def ref_sweep_data_length(request: pytest.FixtureRequest) -> int:
    """This is a parametrized fixture.
    Dependent fixtures will also be parameterized as a result
    """
    return cast(int, request.param)


@pytest.fixture
def ref_frame_data_length(ref_num_frames: int, ref_sweep_data_length: int) -> int:
    return ref_num_frames * ref_sweep_data_length


@pytest.fixture
def ref_frame_raw(
    ref_sweep_data_length: int, ref_frame_data_length: int, ref_num_frames: int
) -> npt.NDArray[Any]:
    array = np.arange(ref_frame_data_length)
    array = array.astype(dtype=INT_16_COMPLEX)

    num_sweeps = ref_frame_data_length // ref_sweep_data_length
    array.resize(num_sweeps, ref_sweep_data_length)

    return cast(npt.NDArray[Any], array)


@pytest.fixture
def ref_frame(ref_frame_raw: npt.NDArray[Any]) -> npt.NDArray[np.complex_]:
    return cast(npt.NDArray[np.complex_], ref_frame_raw["real"] + 1j * ref_frame_raw["imag"])


@pytest.fixture
def ref_metadata(ref_sweep_data_length: int, ref_frame_data_length: int) -> a121.Metadata:
    # Note: This is metadata for a no-subsweep frame
    return a121.Metadata(
        frame_data_length=ref_frame_data_length,
        sweep_data_length=ref_sweep_data_length,
        subsweep_data_length=np.array([ref_sweep_data_length]),
        subsweep_data_offset=np.array([0]),
        calibration_temperature=10,
        tick_period=50,
        base_step_length_m=0.0025,
        max_sweep_rate=1000.0,
        high_speed_mode=True,
    )


@pytest.fixture
def ref_data(ref_frame_raw: npt.NDArray[np.int_], ref_num_frames: int) -> npt.NDArray[np.int_]:
    data_frames = np.stack((ref_frame_raw,) * ref_num_frames)

    # sanity check
    np.testing.assert_array_equal(data_frames[0], ref_frame_raw)

    return data_frames


@pytest.fixture
def ref_record_file(
    ref_lib_version: str,
    ref_timestamp: str,
    ref_uuid: str,
    ref_server_info: a121.ServerInfo,
    ref_client_info: a121.ClientInfo,
    ref_metadata: a121.Metadata,
    ref_session_config: a121.SessionConfig,
    ref_structure: Iterator[Iterator[int]],
    ref_num_frames: int,
    ref_data: npt.NDArray[np.int_],
    tmp_file_path: Path,
) -> Path:
    with h5py.File(tmp_file_path, mode="x") as f:
        f.create_dataset(
            "lib_version", data=ref_lib_version, dtype=_H5PY_STR_DTYPE, track_times=False
        )
        f.create_dataset("timestamp", data=ref_timestamp, dtype=_H5PY_STR_DTYPE, track_times=False)
        f.create_dataset("uuid", data=ref_uuid, dtype=_H5PY_STR_DTYPE, track_times=False)

        server_info_data = ref_server_info.to_json()
        f.create_dataset(
            "server_info", data=server_info_data, dtype=_H5PY_STR_DTYPE, track_times=False
        )

        client_info_data = ref_client_info.to_json()
        f.create_dataset(
            "client_info", data=client_info_data, dtype=_H5PY_STR_DTYPE, track_times=False
        )

        f.create_dataset("generation", data="a121", dtype=_H5PY_STR_DTYPE, track_times=False)

        session_config_data = ref_session_config.to_json()
        session_group = f.create_group("session")
        session_group.create_dataset(
            "session_config",
            data=session_config_data,
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )

        calibrations_group = session_group.create_group("calibrations")
        for group in ref_structure:
            for sensor_id in group:
                sensor_group_name = f"sensor_{sensor_id}"
                if sensor_group_name not in calibrations_group.keys():
                    sensor_calibration_group = calibrations_group.create_group(sensor_group_name)
                    sensor_calibration_group.create_dataset(
                        "temperature", data=15, track_times=False
                    )
                    sensor_calibration_group.create_dataset(
                        "data",
                        data="01234567890abcdef",
                        dtype=_H5PY_STR_DTYPE,
                        track_times=False,
                    )
                    sensor_calibration_group.create_dataset(
                        "provided", data=False, track_times=False
                    )

        zero_array = np.zeros(ref_num_frames, dtype=int)
        false_array = np.zeros(ref_num_frames, dtype=bool)
        tick_array = np.arange(ref_num_frames, dtype=int)

        for group_id, group in enumerate(ref_structure):
            for entry_id, sensor_id in enumerate(group):
                entry_group = session_group.create_group(f"group_{group_id}/entry_{entry_id}")
                entry_group.create_dataset("metadata", data=ref_metadata.to_json())
                entry_group.create_dataset("sensor_id", data=sensor_id)

                result_group = entry_group.create_group("result")
                result_group.create_dataset("frame", data=ref_data)
                result_group.create_dataset("data_saturated", data=false_array)
                result_group.create_dataset("calibration_needed", data=false_array)
                result_group.create_dataset("frame_delayed", data=false_array)
                result_group.create_dataset("temperature", data=zero_array)
                result_group.create_dataset("tick", data=tick_array)

    return tmp_file_path


@pytest.fixture
def ref_record(ref_record_file: Path) -> Iterator[a121.Record]:
    with a121.open_record(ref_record_file) as record:
        yield record
