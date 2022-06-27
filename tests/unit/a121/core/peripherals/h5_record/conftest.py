from uuid import uuid4

import h5py
import numpy as np
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities import INT_16_COMPLEX, SensorInfo
from acconeer.exptool.a121._core.peripherals.h5_record import _H5PY_STR_DTYPE


@pytest.fixture
def tmp_file_path(tmp_path):
    return tmp_path / str(uuid4())


@pytest.fixture
def ref_lib_version():
    return "0.1.2"


@pytest.fixture
def ref_timestamp():
    return "2022-03-14T15:00:00"


@pytest.fixture
def ref_uuid():
    return "b0ca48f7-0bcf-4160-965a-9a865a8fc989"


@pytest.fixture
def ref_server_info():
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
def ref_client_info():
    return a121.ClientInfo(
        ip_address="address",
        serial_port="serial_port",
        override_baudrate=0,
    )


@pytest.fixture
def ref_session_config():
    return a121.SessionConfig(a121.SensorConfig())


@pytest.fixture(
    params=[
        [{1}],
        [{2, 3}, {2}],
        [{1, 2}, {3, 4}, {1, 2, 3, 4, 5}],
    ]
)
def ref_structure(request):
    return request.param


@pytest.fixture(params=range(1, 4, 2))
def ref_num_frames(request):
    """This is a parametrized fixture.
    Dependent fixtures will also be parameterized as a result
    """
    return request.param


@pytest.fixture(params=range(1, 4, 2))
def ref_sweep_data_length(request):
    """This is a parametrized fixture.
    Dependent fixtures will also be parameterized as a result
    """
    return request.param


@pytest.fixture
def ref_frame_data_length(ref_num_frames, ref_sweep_data_length):
    return ref_num_frames * ref_sweep_data_length


@pytest.fixture
def ref_frame_raw(ref_sweep_data_length, ref_frame_data_length, ref_num_frames):
    array = np.arange(ref_frame_data_length)
    array = array.astype(dtype=INT_16_COMPLEX)

    num_sweeps = ref_frame_data_length // ref_sweep_data_length
    array.resize(num_sweeps, ref_sweep_data_length)

    return array


@pytest.fixture
def ref_frame(ref_frame_raw):
    return ref_frame_raw["real"] + 1j * ref_frame_raw["imag"]


@pytest.fixture
def ref_metadata(ref_sweep_data_length, ref_frame_data_length):
    # Note: This is metadata for a no-subsweep frame
    return a121.Metadata(
        frame_data_length=ref_frame_data_length,
        sweep_data_length=ref_sweep_data_length,
        subsweep_data_length=np.array([ref_sweep_data_length]),
        subsweep_data_offset=np.array([0]),
        calibration_temperature=None,
        tick_period=50,
        base_step_length_m=0.0025,
        max_sweep_rate=1000.0,
    )


@pytest.fixture
def ref_data(ref_frame_raw, ref_num_frames):
    data_frames = np.stack((ref_frame_raw,) * ref_num_frames)

    # sanity check
    np.testing.assert_array_equal(data_frames[0], ref_frame_raw)

    return data_frames


@pytest.fixture
def ref_record_file(
    ref_lib_version,
    ref_timestamp,
    ref_uuid,
    ref_server_info,
    ref_client_info,
    ref_metadata,
    ref_session_config,
    ref_structure,
    ref_num_frames,
    ref_data,
    tmp_file_path,
):
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
        f.create_dataset(
            "session/session_config",
            data=session_config_data,
            dtype=_H5PY_STR_DTYPE,
            track_times=False,
        )

        zero_array = np.zeros(ref_num_frames, dtype=int)
        false_array = np.zeros(ref_num_frames, dtype=bool)
        tick_array = np.arange(ref_num_frames, dtype=int)

        for group_id, group in enumerate(ref_structure):
            for entry_id, sensor_id in enumerate(group):
                entry_group = f.create_group(f"session/group_{group_id}/entry_{entry_id}")
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
def ref_record(ref_record_file):
    with a121.open_record(ref_record_file) as record:
        yield record
