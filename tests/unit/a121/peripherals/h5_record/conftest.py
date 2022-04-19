from uuid import uuid4

import h5py
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._peripherals.h5_record import H5PY_STR_DTYPE


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
    )


@pytest.fixture
def ref_client_info():
    return a121.ClientInfo(
        address="address",
        serial_port="serial_port",
        override_baudrate=0,
        protocol="protocol",
        link="link",
    )


@pytest.fixture
def tmp_file_path(tmp_path):
    return tmp_path / str(uuid4())


@pytest.fixture
def ref_record_file(
    ref_lib_version,
    ref_timestamp,
    ref_uuid,
    ref_server_info,
    ref_client_info,
    tmp_file_path,
):
    with h5py.File(tmp_file_path, mode="x") as f:
        f.create_dataset(
            "lib_version", data=ref_lib_version, dtype=H5PY_STR_DTYPE, track_times=False
        )
        f.create_dataset("timestamp", data=ref_timestamp, dtype=H5PY_STR_DTYPE, track_times=False)
        f.create_dataset("uuid", data=ref_uuid, dtype=H5PY_STR_DTYPE, track_times=False)

        server_info_data = ref_server_info.to_json()
        f.create_dataset(
            "server_info", data=server_info_data, dtype=H5PY_STR_DTYPE, track_times=False
        )

        client_info_data = ref_client_info.to_json()
        f.create_dataset(
            "client_info", data=client_info_data, dtype=H5PY_STR_DTYPE, track_times=False
        )

        e0 = f.create_group("session/group_0/entry_0")
        e0.create_dataset("sensor_id", data=2)

        e1 = f.create_group("session/group_0/entry_1")
        e1.create_dataset("sensor_id", data=3)

        e2 = f.create_group("session/group_1/entry_2")
        e2.create_dataset("sensor_id", data=2)

    return tmp_file_path


@pytest.fixture
def ref_record(ref_record_file):
    with a121.open_record(ref_record_file) as record:
        yield record
