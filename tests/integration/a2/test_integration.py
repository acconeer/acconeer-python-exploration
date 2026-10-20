# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import contextlib
import operator
import pathlib
import re
import typing as t

import h5py
import numpy as np
import numpy.testing as np_test
import numpy.typing as npt
import pytest

from acconeer.exptool import a2
from acconeer.exptool._core.entities.client_info import ClientInfo, SocketInfo
from acconeer.exptool._core.int_16_complex import complex_array_to_int16_complex
from acconeer.exptool.a2._core.communication import ExplorationClient


@pytest.fixture
def client_constructor_kwargs(worker_tcp_port, a2_exploration_server):
    return dict(
        client_info=ClientInfo(
            socket=SocketInfo(
                ip_address="localhost",
                tcp_port=worker_tcp_port,
            )
        ),
        enable_diagnostics=False,
    )


def test_can_connect(client_constructor_kwargs: dict[str, t.Any]):
    with ExplorationClient(**client_constructor_kwargs) as client:
        assert client.connected


def test_server_info(client_constructor_kwargs: dict[str, t.Any]):
    with ExplorationClient(**client_constructor_kwargs) as client:
        assert client.connected

        assert re.match(r"a2(11)?-v.*", client.server_info.rss_version)
        assert client.server_info.ticks_per_second > 0
        assert client.server_info.hardware_name in ["A21x", "linux"]
        assert client.server_info.sensor_serial is not None
        assert client.server_info.max_baudrate is None or client.server_info.max_baudrate >= 115200


def _get_a_result(config: a2.SessionConfig, **client_constructor_kwargs: t.Any) -> a2.Result:
    if any(sc.num_subsweeps > 1 for sc in config.sensor_configs):
        pytest.skip("Right now, only one subsweep is supported.")

    with ExplorationClient(**client_constructor_kwargs) as client:
        client.setup_session(config)

        client.start_session()
        result = client.get_next(format=a2.Client.ResultFormat.AUTO)
        client.stop_session()

    return result


def get_measured_points(
    mock_test_pattern_array: npt.NDArray[np.complex128],
) -> npt.NDArray[np.int_]:
    return complex_array_to_int16_complex(mock_test_pattern_array)["real"] >> 6


def get_tx_major_channel_indexes(
    mock_test_pattern_array: npt.NDArray[np.complex128],
) -> npt.NDArray[np.int_]:
    return (complex_array_to_int16_complex(mock_test_pattern_array)["real"] >> 1) & 0b1111


def get_sweep_indexes(mock_test_pattern_array: npt.NDArray[np.complex128]) -> npt.NDArray[np.int_]:
    return complex_array_to_int16_complex(mock_test_pattern_array)["imag"] >> 4


def get_subsweep_indexes(
    mock_test_pattern_array: npt.NDArray[np.complex128],
) -> npt.NDArray[np.int_]:
    return (complex_array_to_int16_complex(mock_test_pattern_array)["imag"] >> 1) & 0b111


class TestMockExplorationServerDataParsing:
    @pytest.fixture
    def all_channels_result_and_config(
        self, client_constructor_kwargs: dict[str, t.Any]
    ) -> tuple[a2.Result, a2.SessionConfig]:
        config = a2.SessionConfig(
            [
                a2.SensorConfig.single_subsweep(
                    start_point=100,
                    num_points=3,
                    step_length=1,
                    profile=a2.Profile.PROFILE_3,
                    tx_antenna_mask=0b111,
                    rx_antenna_mask=0b1111,
                    hwaas_max=50,
                    receiver_gain=10,
                    enable_tx=True,
                    sweeps_per_frame=1,
                    jitter_compensation=False,
                )
            ],
            update_rate=None,
        )
        return (_get_a_result(config, **client_constructor_kwargs), config)

    def test_all_channels_measured_points(
        self, all_channels_result_and_config: tuple[a2.Result, a2.SessionConfig]
    ) -> None:
        (result, _) = all_channels_result_and_config

        expected = [
            ([100] * 12) + ([101] * 12) + ([102] * 12),
        ]
        np_test.assert_array_equal(get_measured_points(result.frame), expected)

    def test_all_channels_channel_indexes(
        self, all_channels_result_and_config: tuple[a2.Result, a2.SessionConfig]
    ) -> None:
        (result, _) = all_channels_result_and_config

        expected = [[tx_ch_idx for tx_ch_idx in range(12)] * 3]
        np_test.assert_array_equal(get_tx_major_channel_indexes(result.frame), expected)

    def test_all_channels_channel_indexes_get_subframe(
        self, all_channels_result_and_config: tuple[a2.Result, a2.SessionConfig]
    ) -> None:
        (result, all_channels_config) = all_channels_result_and_config
        sensor_config = all_channels_config.sensor_config

        for subsweep_index, subsweep_config in enumerate(sensor_config.subsweeps):
            for tx_major_channel_index in range(4):
                subframe = result.get_subframe(
                    sensor_config, subsweep_index, channel_indexes=[tx_major_channel_index]
                )

                assert (get_tx_major_channel_indexes(subframe) == tx_major_channel_index).all()

    def test_all_channels_sweep_indexes(
        self, all_channels_result_and_config: tuple[a2.Result, a2.SessionConfig]
    ) -> None:
        (result, _) = all_channels_result_and_config

        expected = [[0] * 12 * 3]
        np_test.assert_array_equal(get_sweep_indexes(result.frame), expected)

    def test_all_channels_subsweep_indexes(
        self, all_channels_result_and_config: tuple[a2.Result, a2.SessionConfig]
    ) -> None:
        (result, _) = all_channels_result_and_config

        expected = [[0] * 12 * 3]
        np_test.assert_array_equal(get_subsweep_indexes(result.frame), expected)

    def test_all_channels_subsweep_indexes_get_subframe(
        self, all_channels_result_and_config: tuple[a2.Result, a2.SessionConfig]
    ) -> None:
        (result, all_channels_config) = all_channels_result_and_config
        sensor_config = all_channels_config.sensor_config

        for subsweep_index in range(sensor_config.num_subsweeps):
            subframe = result.get_subframe(sensor_config, subsweep_index)
            assert (get_subsweep_indexes(subframe) == subsweep_index).all()

    @pytest.fixture
    def two_sensor_configs_result_and_config(
        self, client_constructor_kwargs: dict[str, t.Any]
    ) -> tuple[a2.GroupResult, a2.SessionConfig]:
        config = a2.SessionConfig(
            [
                a2.SensorConfig.single_subsweep(
                    start_point=0,
                    num_points=5,
                    step_length=1,
                    profile=a2.Profile.PROFILE_3,
                    tx_antenna_mask=0b001,
                    rx_antenna_mask=0b0001,
                    hwaas_max=50,
                    receiver_gain=10,
                    enable_tx=True,
                    sweeps_per_frame=2,
                    jitter_compensation=False,
                ),
                a2.SensorConfig.single_subsweep(
                    start_point=100,
                    num_points=5,
                    step_length=1,
                    profile=a2.Profile.PROFILE_3,
                    tx_antenna_mask=0b001,
                    rx_antenna_mask=0b0001,
                    hwaas_max=50,
                    receiver_gain=10,
                    enable_tx=True,
                    sweeps_per_frame=2,
                    jitter_compensation=False,
                ),
            ],
            update_rate=None,
        )
        return (_get_a_result(config, **client_constructor_kwargs), config)

    def test_two_sensor_configs_measured_points(
        self, two_sensor_configs_result_and_config: tuple[a2.GroupResult, a2.SessionConfig]
    ) -> None:
        (result, _) = two_sensor_configs_result_and_config
        (first_result, second_result) = result.results

        expected = [
            [0, 1, 2, 3, 4],
            [0, 1, 2, 3, 4],
        ]
        np_test.assert_array_equal(get_measured_points(first_result.frame), expected)

        expected = [
            [100, 101, 102, 103, 104],
            [100, 101, 102, 103, 104],
        ]
        np_test.assert_array_equal(get_measured_points(second_result.frame), expected)

    def test_two_sensor_configs_channel_indexes(
        self, two_sensor_configs_result_and_config: tuple[a2.GroupResult, a2.SessionConfig]
    ) -> None:
        (result, _) = two_sensor_configs_result_and_config
        (first_result, second_result) = result.results

        expected = [
            [0] * 5,
            [0] * 5,
        ]
        np_test.assert_array_equal(get_tx_major_channel_indexes(first_result.frame), expected)

        expected = [
            [0] * 5,
            [0] * 5,
        ]
        np_test.assert_array_equal(get_tx_major_channel_indexes(second_result.frame), expected)

    def test_two_sensor_configs_sweep_indexes(
        self, two_sensor_configs_result_and_config: tuple[a2.GroupResult, a2.SessionConfig]
    ) -> None:
        (result, _) = two_sensor_configs_result_and_config
        (first_result, second_result) = result.results

        expected = [
            [0] * 5,
            [1] * 5,
        ]
        np_test.assert_array_equal(get_sweep_indexes(first_result.frame), expected)

        expected = [
            [0] * 5,
            [1] * 5,
        ]
        np_test.assert_array_equal(get_sweep_indexes(second_result.frame), expected)

    def test_two_sensor_configs_subsweep_indexes(
        self, two_sensor_configs_result_and_config: tuple[a2.GroupResult, a2.SessionConfig]
    ) -> None:
        (result, _) = two_sensor_configs_result_and_config
        (first_result, second_result) = result.results

        expected = [
            [0] * 5,
            [0] * 5,
        ]
        np_test.assert_array_equal(get_subsweep_indexes(first_result.frame), expected)

        expected = [
            [0] * 5,
            [0] * 5,
        ]
        np_test.assert_array_equal(get_subsweep_indexes(second_result.frame), expected)


class TestRecording:
    NUM_SESSIONS = 2
    NUM_SAMPLES = 5

    @pytest.fixture
    def recorded_file(
        self, tmp_path: pathlib.Path, client_constructor_kwargs: dict[str, t.Any]
    ) -> h5py.File:
        with contextlib.suppress(FileExistsError):
            tmp_path.mkdir(parents=True)

        with (
            h5py.File(tmp_path / "record.h5", "w") as file_obj,
            ExplorationClient(**client_constructor_kwargs) as client,
            a2.H5Recorder(file_obj, client),
        ):
            client.setup_session(
                a2.SessionConfig(
                    sensor_configs=[
                        a2.SensorConfig.single_subsweep(
                            start_point=160,
                            num_points=5,
                            step_length=1,
                            profile=a2.Profile.PROFILE_3,
                            tx_antenna_mask=0b001,
                            rx_antenna_mask=0b0001,
                            hwaas_max=50,
                            receiver_gain=10,
                            enable_tx=True,
                            sweeps_per_frame=2,
                            jitter_compensation=False,
                        ),
                        a2.SensorConfig.single_subsweep(
                            start_point=160,
                            num_points=10,
                            step_length=1,
                            profile=a2.Profile.PROFILE_3,
                            tx_antenna_mask=0b001,
                            rx_antenna_mask=0b0001,
                            hwaas_max=50,
                            receiver_gain=10,
                            enable_tx=True,
                            sweeps_per_frame=1,
                            jitter_compensation=False,
                        ),
                    ],
                    update_rate=None,
                )
            )

            for _ in range(self.NUM_SESSIONS):
                client.start_session()

                for _ in range(self.NUM_SAMPLES):
                    client.get_next()

                client.stop_session()

            yield file_obj

    def test_record_file_structure(self, recorded_file: h5py.File) -> None:
        assert recorded_file["sessions/session_0"]
        assert recorded_file["sessions/session_1"]

        assert recorded_file["sessions/session_0/group_0"]
        assert recorded_file["sessions/session_0/group_1"]
        assert recorded_file["sessions/session_1/group_0"]
        assert recorded_file["sessions/session_1/group_1"]

        assert (
            recorded_file["sessions/session_0/group_0/result/frame"].shape
            == recorded_file["sessions/session_1/group_0/result/frame"].shape
            == (self.NUM_SAMPLES, 2, 5)
        )
        assert (
            recorded_file["sessions/session_0/group_1/result/frame"].shape
            == recorded_file["sessions/session_1/group_1/result/frame"].shape
            == (self.NUM_SAMPLES, 1, 10)
        )

    def test_record(self, recorded_file: h5py.File) -> None:
        record = a2.H5Record(recorded_file)

        assert record.num_sessions == self.NUM_SESSIONS
        assert record.session(0).num_frames == record.session(1).num_frames == self.NUM_SAMPLES

        assert (
            list(record.session(0).group_results)[0].results[0].frame.shape
            == list(record.session(1).group_results)[0].results[0].frame.shape
            == (2, 5)
        )

        assert (
            list(record.session(0).group_results)[0].results[1].frame.shape
            == list(record.session(1).group_results)[0].results[1].frame.shape
            == (1, 10)
        )

    def test_record_io(self, recorded_file: h5py.File, tmp_path: pathlib.Path) -> None:
        record = a2.open_record(recorded_file)

        a2.save_record(tmp_path / "tmp.h5", record)

        saved_record = a2.open_record(tmp_path / "tmp.h5")

        self.assert_record_data_equals(record, saved_record)

    def test_chunk_size_doesnt_affect_retrievable_results(self, recorded_file: h5py.File) -> None:
        record_1 = a2.H5Record(recorded_file, chunk_size=1)
        record_2 = a2.H5Record(recorded_file, chunk_size=2)
        record_overchunk = a2.H5Record(recorded_file, chunk_size=self.NUM_SAMPLES + 1)

        for session_idx in range(record_1.num_sessions):
            session_1 = record_1.session(session_idx)
            session_2 = record_2.session(session_idx)
            session_overchunk = record_overchunk.session(session_idx)

            assert (
                list(session_1.group_results)
                == list(session_2.group_results)
                == list(session_overchunk.group_results)
            )

    @staticmethod
    def assert_record_data_equals(record_a: a2.H5Record, record_b: a2.H5Record) -> None:
        """Asserts that contents of records are equal
        (omits "timestamp" and "uuid" as those are expected to change)
        between `open_record` & `save_record`
        """
        for attr in [
            "client_info",
            "lib_version",
            "server_info",
            "num_sessions",
        ]:
            attrgetter = operator.attrgetter(attr)
            assert attrgetter(record_a) == attrgetter(record_b), f".{attr} differs"

        for session_idx in range(record_a.num_sessions):
            session_a = record_a.session(session_idx)
            session_b = record_a.session(session_idx)
            assert session_a == session_b
